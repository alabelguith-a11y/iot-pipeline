"""Local governance layer (what Dataplex gives you on GCP): catalog/aspects, lineage, quality results."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..db import DB

CATALOG = Path(__file__).resolve().parents[2] / "governance" / "catalog.yml"


def load_catalog(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CATALOG).read_text())


def ensure_tables(db: DB):
    db.execute("""CREATE TABLE IF NOT EXISTS etl_run_log (
        run_id TEXT, model TEXT, layer TEXT, row_count INTEGER, seconds REAL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS gov_lineage (run_id TEXT, source TEXT, target TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS gov_quality_results (
        run_id TEXT, check_name TEXT, status TEXT, failing_rows INTEGER, description TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS gov_catalog (
        table_name TEXT, column_name TEXT, description TEXT, sensitivity TEXT, owner TEXT)""")
    db.commit()


def coverage_check(db: DB, models, catalog_path: Path | None = None) -> dict:
    """Every column of every modelled table must be documented in the catalog (like aspect completeness)."""
    catalog = load_catalog(catalog_path)["tables"]
    missing = 0
    for m in models:
        documented = set((catalog.get(m.name) or {}).get("columns", {}))
        missing += len([c for c in db.columns(m.name) if c not in documented])
    return {"check": "catalog_coverage", "status": "pass" if missing == 0 else "FAIL",
            "failing_rows": missing, "description": "all columns documented in governance/catalog.yml"}


def record(db: DB, run_id, log, lineage, checks, catalog_path: Path | None = None):
    for row in log:
        db.execute("INSERT INTO etl_run_log VALUES (?, ?, ?, ?, ?)", row)
    for row in lineage:
        db.execute("INSERT INTO gov_lineage VALUES (?, ?, ?)", row)
    for c in checks:
        db.execute("INSERT INTO gov_quality_results VALUES (?, ?, ?, ?, ?)",
                   (run_id, c["check"], c["status"], c["failing_rows"], c["description"]))
    catalog = load_catalog(catalog_path)
    owner = catalog.get("defaults", {}).get("owner", "unknown")
    db.execute("DELETE FROM gov_catalog")  # catalog is declarative: the YAML is the source of truth
    for table, spec in catalog["tables"].items():
        for col, meta in spec["columns"].items():
            db.execute("INSERT INTO gov_catalog VALUES (?, ?, ?, ?, ?)",
                       (table, col, meta["description"], meta["sensitivity"], owner))
    db.commit()
