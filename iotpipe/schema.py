"""Validation of messages against schemas/reading.schema.json (no external dependency)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "reading.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate(obj) -> list[str]:
    """Return a list of error strings (empty list = valid)."""
    if not isinstance(obj, dict):
        return ["payload is not a JSON object"]
    errors: list[str] = []
    props = SCHEMA["properties"]
    for name in SCHEMA["required"]:
        if name not in obj:
            errors.append(f"missing required field '{name}'")
    for name, value in obj.items():
        spec = props.get(name)
        if spec is None:
            if SCHEMA.get("additionalProperties") is False:
                errors.append(f"unexpected field '{name}'")
            continue
        if spec["type"] == "string":
            if not isinstance(value, str):
                errors.append(f"'{name}' must be a string")
                continue
            if len(value) < spec.get("minLength", 0) or len(value) > spec.get("maxLength", 10**9):
                errors.append(f"'{name}' has invalid length")
        elif spec["type"] == "number":
            if not _is_number(value):
                errors.append(f"'{name}' must be a number")
                continue
            if value < spec.get("minimum", float("-inf")) or value > spec.get("maximum", float("inf")):
                errors.append(f"'{name}' out of physical range ({value})")
    if isinstance(obj.get("ts"), str):
        try:
            parse_ts(obj["ts"])
        except ValueError:
            errors.append("'ts' is not ISO-8601")
    return errors
