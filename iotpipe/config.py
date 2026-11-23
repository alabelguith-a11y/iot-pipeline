"""Central configuration. A *profile* is a bundle of defaults; any env var overrides it.

  test : ZeroMQ transport + direct-to-DB (no Kafka) + SQLite     -> runs anywhere, zero services
  dev  : MQTT transport + Kafka + PostgreSQL                      -> the full architecture (docker compose)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

PROFILES = {
    "test": {"transport": "zmq", "queue": "direct", "db_url": "sqlite:///data/test.db"},
    "dev": {"transport": "mqtt", "queue": "kafka", "db_url": "postgresql://iot:iot@localhost:5432/iot"},
}


@dataclass(frozen=True)
class Settings:
    profile: str
    transport: str          # mqtt | zmq
    queue: str              # kafka | direct
    db_url: str
    topic_prefix: str = "sensors"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    zmq_endpoint: str = "tcp://127.0.0.1:5556"   # where publishers connect
    zmq_bind: str = ""                            # where the bridge binds (defaults to zmq_endpoint)
    kafka_bootstrap: str = "localhost:9092"
    kafka_topic: str = "sensors.readings"
    kafka_dlq_topic: str = "sensors.dlq"

    @property
    def subscribe_pattern(self) -> str:
        return f"{self.topic_prefix}/+/reading"


def load(**overrides) -> Settings:
    profile = overrides.pop("profile", None) or os.getenv("PROFILE", "test")
    if profile not in PROFILES:
        raise ValueError(f"unknown PROFILE '{profile}', expected one of {list(PROFILES)}")
    base = PROFILES[profile]
    env = os.getenv
    values = {
        "profile": profile,
        "transport": env("TRANSPORT", base["transport"]),
        "queue": env("QUEUE", base["queue"]),
        "db_url": env("DB_URL", base["db_url"]),
        "mqtt_host": env("MQTT_HOST", "localhost"),
        "mqtt_port": int(env("MQTT_PORT", "1883")),
        "zmq_endpoint": env("ZMQ_ENDPOINT", "tcp://127.0.0.1:5556"),
        "zmq_bind": env("ZMQ_BIND", ""),
        "kafka_bootstrap": env("KAFKA_BOOTSTRAP", "localhost:9092"),
    }
    values.update(overrides)
    return Settings(**values)
