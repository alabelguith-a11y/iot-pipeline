"""Raw-layer writes shared by the direct bridge sink and the Kafka consumer. Idempotent by design."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from .db import DB


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_raw_tables(db: DB):
    payload_type = "JSONB" if db.dialect == "postgres" else "TEXT"
    db.execute(
        f"""CREATE TABLE IF NOT EXISTS raw_readings (
              reading_id  TEXT PRIMARY KEY,
              device_id   TEXT NOT NULL,
              payload     {payload_type} NOT NULL,
              ingested_at TEXT NOT NULL)"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS dead_letter (
              dl_id       TEXT PRIMARY KEY,
              received_at TEXT NOT NULL,
              reason      TEXT NOT NULL,
              payload     TEXT)"""
    )
    db.commit()


def insert_raw(db: DB, readings: list[dict]) -> int:
    """Insert readings; redelivered reading_ids are ignored. Returns number of NEW rows."""
    inserted = 0
    ts = now_iso()
    for r in readings:
        cur = db.execute(
            "INSERT INTO raw_readings (reading_id, device_id, payload, ingested_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (reading_id) DO NOTHING",
            (r["reading_id"], r["device_id"], json.dumps(r, separators=(",", ":")), ts),
        )
        inserted += max(cur.rowcount, 0)
    db.commit()
    return inserted


def insert_dead_letter(db: DB, reason: str, raw: bytes | str):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    db.execute(
        "INSERT INTO dead_letter (dl_id, received_at, reason, payload) VALUES (?, ?, ?, ?)",
        (uuid.uuid4().hex, now_iso(), reason[:500], raw[:4000]),
    )
    db.commit()
