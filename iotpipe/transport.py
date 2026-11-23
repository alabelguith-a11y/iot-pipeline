"""Pluggable transport: MQTT (real) or ZeroMQ (fast local testing). Same topics, same payloads.

  topic: sensors/<device_id>/reading     payload: JSON (see schemas/reading.schema.json)

ZeroMQ layout: the subscriber (bridge) *binds*, publishers (simulator) *connect*, so many
publishers can feed one bridge. Messages are 2-frame multipart: [topic, payload].
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Iterator, Optional

from .config import Settings


def topic_for(settings: Settings, device_id: str) -> str:
    return f"{settings.topic_prefix}/{device_id}/reading"


# --------------------------------------------------------------------- publishers
class MqttPublisher:
    def __init__(self, s: Settings):
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect(s.mqtt_host, s.mqtt_port, keepalive=30)
        self.client.loop_start()

    def publish(self, topic: str, payload: bytes):
        self.client.publish(topic, payload, qos=1).wait_for_publish(timeout=5)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


class ZmqPublisher:
    def __init__(self, s: Settings):
        import zmq

        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.PUB)
        self.sock.connect(s.zmq_endpoint)
        time.sleep(0.3)  # "slow joiner": give the TCP connection time to establish

    def publish(self, topic: str, payload: bytes):
        self.sock.send_multipart([topic.encode(), payload])

    def close(self):
        self.sock.close(linger=1000)


def make_publisher(s: Settings):
    if s.transport == "mqtt":
        return MqttPublisher(s)
    if s.transport == "zmq":
        return ZmqPublisher(s)
    raise ValueError(f"unknown transport {s.transport}")


# -------------------------------------------------------------------- subscribers
def _mqtt_messages(s: Settings, stop: threading.Event, tick: float):
    import paho.mqtt.client as mqtt

    q: queue.Queue = queue.Queue()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iot-bridge", clean_session=False)
    client.on_connect = lambda c, *_: c.subscribe(s.subscribe_pattern, qos=1)  # re-subscribes after reconnect
    client.on_message = lambda _c, _u, m: q.put((m.topic, bytes(m.payload)))
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(s.mqtt_host, s.mqtt_port, keepalive=30)
    client.loop_start()
    try:
        while not stop.is_set():
            try:
                yield q.get(timeout=tick)
            except queue.Empty:
                yield None
    finally:
        client.loop_stop()
        client.disconnect()


def _zmq_messages(s: Settings, stop: threading.Event, tick: float):
    import zmq

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.bind(s.zmq_bind or s.zmq_endpoint)
    sock.setsockopt_string(zmq.SUBSCRIBE, s.topic_prefix + "/")
    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)
    try:
        while not stop.is_set():
            if poller.poll(int(tick * 1000)):
                topic, payload = sock.recv_multipart()
                yield topic.decode(errors="replace"), payload
            else:
                yield None
    finally:
        sock.close(linger=0)


def messages(s: Settings, stop: Optional[threading.Event] = None, tick: float = 0.2) -> Iterator[Optional[tuple[str, bytes]]]:
    """Yield (topic, payload) tuples, or None on every idle tick (lets callers flush buffers)."""
    stop = stop or threading.Event()
    if s.transport == "mqtt":
        return _mqtt_messages(s, stop, tick)
    if s.transport == "zmq":
        return _zmq_messages(s, stop, tick)
    raise ValueError(f"unknown transport {s.transport}")
