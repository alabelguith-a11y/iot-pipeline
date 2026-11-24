"""Sensor simulator with *deliberately dirty* data so the ETL layer has real work to do.

Event timestamps are simulated (`--step` seconds apart, ending now) so hourly aggregates are meaningful;
`--rate` only controls how fast messages are emitted on the wire.

Injected defects (rates are tunable, default ~6% total):
  duplicate_id   same reading_id re-sent                         -> raw PK dedupe
  duplicate_key  same device+ts, NEW reading_id (retry)           -> staging dedupe
  spike          temperature 110C (inside sensor range, absurd)   -> plausibility flag
  jump           +12C step                                        -> anomaly model
  late           event time shifted 2h into the past              -> late-arriving data
  missing_field  humidity_pct dropped                             -> dead letter
  garbage        non-JSON bytes                                   -> dead letter

Run: python -m iotpipe.simulator --devices 4 --per-device 120 --rate 0
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

from . import transport
from .config import load

DEFECTS = {"duplicate_id": 0.02, "duplicate_key": 0.01, "spike": 0.01, "jump": 0.01,
           "late": 0.01, "missing_field": 0.01, "garbage": 0.005}


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(devices: int = 4, per_device: int = 120, step_s: int = 60, seed: int = 42,
             end: datetime | None = None, defects: dict | None = None):
    """Return a list of (device_id, payload_bytes, label). Deterministic for a given seed."""
    rng = random.Random(seed)
    rates = DEFECTS if defects is None else defects
    end = end or datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(seconds=step_s * per_device)
    out: list[tuple[str, bytes, str]] = []
    for d in range(devices):
        dev = f"esp32-{d + 1:02d}"
        offset = rng.uniform(-2, 2)
        drain = 0.9 if d == devices - 1 else 0.25  # last device runs out of battery
        for i in range(per_device):
            ts = start + timedelta(seconds=step_s * i)
            hour = ts.hour + ts.minute / 60
            temp = 22 + offset + 5 * math.sin(2 * math.pi * (hour - 9) / 24) + rng.gauss(0, 0.3)
            reading = {
                "reading_id": f"{dev}-{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
                "device_id": dev,
                "ts": fmt(ts),
                "temperature_c": round(temp, 2),
                "humidity_pct": round(max(5, min(95, 55 - (temp - 22) * 2 + rng.gauss(0, 1))), 1),
                "pressure_hpa": round(1013 + rng.gauss(0, 1.5), 1),
                "battery_v": round(4.15 - drain * i / per_device, 3),
                "fw_version": "1.2.0",
            }
            roll, acc, label = rng.random(), 0.0, "ok"
            for name, p in rates.items():
                acc += p
                if roll < acc:
                    label = name
                    break
            if label == "spike":
                reading["temperature_c"] = 110.0
            elif label == "jump":
                reading["temperature_c"] = round(temp + 12, 2)
            elif label == "late":
                reading["ts"] = fmt(ts - timedelta(hours=2))
            elif label == "missing_field":
                del reading["humidity_pct"]
            elif label == "garbage":
                out.append((dev, b"\xff\xfenot-json{{", label))
                continue
            payload = json.dumps(reading).encode()
            out.append((dev, payload, label))
            if label == "duplicate_id":
                out.append((dev, payload, label))
            elif label == "duplicate_key":
                retry = dict(reading, reading_id=reading["reading_id"] + "-retry")
                out.append((dev, json.dumps(retry).encode(), label))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--devices", type=int, default=4)
    ap.add_argument("--per-device", type=int, default=120)
    ap.add_argument("--step", type=int, default=60, help="simulated seconds between readings")
    ap.add_argument("--rate", type=float, default=200, help="messages/second on the wire (0 = unthrottled)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--loop", action="store_true", help="keep generating forever (docker mode)")
    ap.add_argument("--clean", action="store_true", help="no injected defects")
    a = ap.parse_args()

    s = load()
    pub = transport.make_publisher(s)
    seed = a.seed
    try:
        while True:
            msgs = generate(a.devices, a.per_device, a.step, seed, defects={} if a.clean else None)
            print(f"[simulator] sending {len(msgs)} messages via {s.transport}")
            for dev, payload, _ in msgs:
                pub.publish(transport.topic_for(s, dev), payload)
                if a.rate:
                    time.sleep(1 / a.rate)
            if not a.loop:
                break
            seed += 1
    finally:
        pub.close()


if __name__ == "__main__":
    main()
