"""Pretty-print the analytics layer: python -m iotpipe.etl.report"""
from __future__ import annotations

from ..config import load
from ..db import connect


def table(rows: list[dict], cols: list[str]) -> str:
    def f(v):
        return f"{v:.2f}" if isinstance(v, float) else str(v)
    w = {c: max(len(c), *(len(f(r[c])) for r in rows)) if rows else len(c) for c in cols}
    line = "  ".join(c.ljust(w[c]) for c in cols)
    return "\n".join([line, "  ".join("-" * w[c] for c in cols)] +
                     ["  ".join(f(r[c]).ljust(w[c]) for c in cols) for r in rows])


def main():
    db = connect(load().db_url)
    print("\n== Ingestion reconciliation ==")
    q = db.query("SELECT * FROM fct_ingestion_quality")
    print(table(q, list(q[0])))
    print("\n== Device health ==")
    print(table(
        db.query(
            "SELECT device_id, total_readings, last_seen, last_battery_v, status "
            "FROM dim_device_health ORDER BY device_id"
        ),
        ["device_id", "total_readings", "last_seen", "last_battery_v", "status"],
    ))
    print("\n== Anomalies by type ==")
    print(table(db.query("SELECT anomaly_type, COUNT(*) AS n FROM fct_anomalies GROUP BY anomaly_type"), ["anomaly_type", "n"]))
    print("\n== Rejected messages by reason ==")
    print(table(db.query("SELECT substr(reason,1,45) AS reason, COUNT(*) AS n "
                        "FROM dead_letter GROUP BY 1 ORDER BY n DESC"),
                ["reason", "n"]))
    print("\n== Lineage (latest run) ==")
    print(table(db.query("SELECT DISTINCT source, target FROM gov_lineage WHERE run_id=(SELECT MAX(run_id) FROM gov_lineage)"),
                ["source", "target"]))
    db.close()


if __name__ == "__main__":
    main()
