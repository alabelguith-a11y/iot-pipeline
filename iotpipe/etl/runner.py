"""Mini Dataform/dbt: discovers SQL models, orders them by `-- depends:`, materialises them as tables,
records lineage + row counts, runs SQL assertions and the catalog coverage check.

  python -m iotpipe.etl.runner            # one run
  python -m iotpipe.etl.runner --every 60 # loop (docker mode)
Exit code is 1 when any assertion fails, so CI/Kubernetes can alert on it.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import load
from ..db import DB, connect
from . import governance

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
LAYER_ORDER = ["staging", "analytics"]


@dataclass
class Model:
    name: str
    layer: str
    sql: str
    deps: list[str] = field(default_factory=list)
    description: str = ""


def _header(sql: str, key: str) -> str:
    m = re.search(rf"^--\s*{key}:\s*(.*)$", sql, re.M)
    return m.group(1).strip() if m else ""


def discover(sql_dir: Path = SQL_DIR, layer: str | None = None) -> list[Model]:
    models = []
    for layer_name in ([layer] if layer else LAYER_ORDER):
        for path in sorted((sql_dir / layer_name).glob("*.sql")):
            text = path.read_text()
            deps = [d.strip() for d in _header(text, "depends").split(",") if d.strip()]
            models.append(Model(path.stem, layer_name, text.strip().rstrip(";"), deps, _header(text, "description")))
    return models


def toposort(models: list[Model]) -> list[Model]:
    by_name, done, order = {m.name: m for m in models}, set(), []

    def visit(m: Model, stack: tuple = ()):
        if m.name in done:
            return
        if m.name in stack:
            raise ValueError(f"dependency cycle: {' -> '.join(stack + (m.name,))}")
        for d in m.deps:
            if d in by_name:  # anything else is a *source* table (raw layer)
                visit(by_name[d], stack + (m.name,))
        done.add(m.name)
        order.append(m)

    for m in models:
        visit(m)
    return order


def run_assertions(db: DB, run_id: str, sql_dir: Path = SQL_DIR) -> list[dict]:
    results = []
    for path in sorted((sql_dir / "assertions").glob("*.sql")):
        text = path.read_text()
        failing = len(db.query(db.render(text.strip().rstrip(";"))))
        results.append({"check": path.stem, "status": "pass" if failing == 0 else "FAIL",
                        "failing_rows": failing, "description": _header(text, "description")})
    return results


def run(db: DB, sql_dir: Path = SQL_DIR, catalog_path: Path | None = None) -> dict:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:6]
    governance.ensure_tables(db)
    models = toposort(discover(sql_dir))
    lineage, log = [], []

    for m in models:
        t0 = time.perf_counter()
        db.execute(f"DROP TABLE IF EXISTS {m.name}")
        db.execute(f"CREATE TABLE {m.name} AS {db.render(m.sql)}")
        db.commit()
        rows = db.query(f"SELECT COUNT(*) AS n FROM {m.name}")[0]["n"]  # noqa: S608
        log.append((run_id, m.name, m.layer, rows, round(time.perf_counter() - t0, 4)))
        lineage += [(run_id, d, m.name) for d in m.deps]

    checks = run_assertions(db, run_id, sql_dir)
    checks.append(governance.coverage_check(db, models, catalog_path))
    governance.record(db, run_id, log, lineage, checks, catalog_path)
    return {"run_id": run_id, "models": log, "checks": checks,
            "ok": all(c["status"] == "pass" for c in checks)}


def print_summary(result: dict):
    print(f"\nETL run {result['run_id']}")
    for _, name, layer, rows, secs in result["models"]:
        print(f"  [{layer:9}] {name:24} {rows:>7} rows  {secs:.3f}s")
    print("  checks:")
    for c in result["checks"]:
        print(f"    {'OK ' if c['status'] == 'pass' else 'XX '} {c['check']:34} failing_rows={c['failing_rows']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=0, help="repeat every N seconds (0 = once)")
    a = ap.parse_args()
    s = load()
    while True:
        db = connect(s.db_url)
        try:
            result = run(db)
        finally:
            db.close()
        print_summary(result)
        if not a.every:
            sys.exit(0 if result["ok"] else 1)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
