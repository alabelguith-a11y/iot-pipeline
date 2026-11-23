"""Bridge: transport (MQTT or ZeroMQ) -> validate -> queue (Kafka, or straight to the DB in `direct` mode).

Invalid messages never crash the bridge: they go to a dead-letter topic / table with the reason.
Run:  python -m iotpipe.bridge
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import time

from . import loader, transport
from .config import Settings, load
from .db import connect
from .schema import validate

log = logging.getLogger("bridge")


# ------------------------------------------------------------------------- sinks
class DirectSink:
    """Test profile: skip Kafka, write batches straight to the raw table."""

    def __init__(self, s: Settings, batch_size: int = 100, max_age: float = 1.0):
        self.db = connect(s.db_url)
        loader.ensure_raw_tables(self.db)
        self.buf: list[dict] = []
        self.batch_size, self.max_age, self.last_flush = batch_size, max_age, time.monotonic()
        self.stats = {"accepted": 0, "rejected": 0}

    def accept(self, reading: dict):
        self.buf.append(reading)
        self.stats["accepted"] += 1
        if len(self.buf) >= self.batch_size:
            self.flush()

    def reject(self, reason: str, raw: bytes):
        self.stats["rejected"] += 1
        loader.insert_dead_letter(self.db, reason, raw)

    def flush(self):
        if self.buf:
            loader.insert_raw(self.db, self.buf)
            self.buf = []
        self.last_flush = time.monotonic()

    def tick(self):
        if self.buf and time.monotonic() - self.last_flush >= self.max_age:
            self.flush()

    def close(self):
        self.flush()
        self.db.close()


class KafkaSink:
    def __init__(self, s: Settings):
        from confluent_kafka import Producer

        self.s = s
        self.producer = Producer({"bootstrap.servers": s.kafka_bootstrap, "enable.idempotence": True, "linger.ms": 20})
        self.stats = {"accepted": 0, "rejected": 0}

    def accept(self, reading: dict):
        self.producer.produce(self.s.kafka_topic, key=reading["device_id"], value=json.dumps(reading))
        self.producer.poll(0)
        self.stats["accepted"] += 1

    def reject(self, reason: str, raw: bytes):
        self.producer.produce(self.s.kafka_dlq_topic, value=raw, headers={"reason": reason[:200]})
        self.producer.poll(0)
        self.stats["rejected"] += 1

    def tick(self):
        self.producer.poll(0)

    def close(self):
        self.producer.flush(10)


def make_sink(s: Settings):
    return KafkaSink(s) if s.queue == "kafka" else DirectSink(s)


# ------------------------------------------------------------------------- logic
def process(topic: str, payload: bytes, sink) -> bool:
    """Validate one message. Pure function over (topic, payload) -> easy to unit test."""
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        sink.reject("invalid_json", payload)
        return False
    errors = validate(obj)
    if not errors:
        parts = topic.split("/")
        if len(parts) != 3 or parts[1] != obj["device_id"]:
            errors = ["topic/device_id mismatch"]
    if errors:
        sink.reject("; ".join(errors), payload)
        return False
    sink.accept(obj)
    return True


def run(s: Settings, stop: threading.Event | None = None):
    stop = stop or threading.Event()
    sink = make_sink(s)
    log.info("bridge started profile=%s transport=%s queue=%s", s.profile, s.transport, s.queue)
    last_log = time.monotonic()
    try:
        for msg in transport.messages(s, stop):
            if msg is not None:
                process(msg[0], msg[1], sink)
            sink.tick()
            if time.monotonic() - last_log > 10:
                log.info("stats %s", sink.stats)
                last_log = time.monotonic()
    finally:
        sink.close()
        log.info("bridge stopped stats=%s", sink.stats)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run(load(), stop)


if __name__ == "__main__":
    main()
