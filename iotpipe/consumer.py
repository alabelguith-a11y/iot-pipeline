"""Kafka consumer -> raw layer. At-least-once delivery + idempotent insert = effectively-once.
Offsets are committed only AFTER the batch is stored. Run: python -m iotpipe.consumer (dev profile).
"""
from __future__ import annotations

import json
import logging
import signal
import threading

from . import loader
from .config import load
from .db import connect
from .schema import validate

log = logging.getLogger("consumer")


def split_batch(payloads: list[bytes]) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """Return (valid readings, [(reason, raw)] rejects). Defence in depth: re-validate after Kafka."""
    good, bad = [], []
    for raw in payloads:
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            bad.append(("invalid_json", raw))
            continue
        errs = validate(obj)
        (bad.append(("; ".join(errs), raw)) if errs else good.append(obj))
    return good, bad


def main():
    from confluent_kafka import Consumer

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    s = load()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    db = connect(s.db_url)
    loader.ensure_raw_tables(db)
    consumer = Consumer({
        "bootstrap.servers": s.kafka_bootstrap,
        "group.id": "iot-raw-loader",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([s.kafka_topic])
    log.info("consumer started topic=%s", s.kafka_topic)
    try:
        while not stop.is_set():
            msgs = [m for m in consumer.consume(num_messages=200, timeout=1.0) if m.error() is None]
            if not msgs:
                continue
            good, bad = split_batch([m.value() for m in msgs])
            new = loader.insert_raw(db, good)
            for reason, raw in bad:
                loader.insert_dead_letter(db, reason, raw)
            consumer.commit(asynchronous=False)
            log.info("batch=%d new=%d duplicates=%d rejected=%d", len(msgs), new, len(good) - new, len(bad))
    finally:
        consumer.close()
        db.close()


if __name__ == "__main__":
    main()
