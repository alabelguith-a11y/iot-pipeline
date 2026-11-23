"""Small browser dashboard for the pipeline tables."""
# The page template contains deliberately compact CSS and markup.
# ruff: noqa: E501
from __future__ import annotations

import html
import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import load
from .db import connect

app = FastAPI(title="IoT Pipeline Dashboard")


def cell(value) -> str:
    return html.escape("-" if value is None else str(value))


def table(rows: list[dict], columns: list[str]) -> str:
    header = "".join(f"<th>{cell(column.replace('_', ' '))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell(row.get(column))}</td>" for column in columns) + "</tr>"
        for row in rows
    )
    if not body:
        body = f'<tr><td class="empty" colspan="{len(columns)}">No rows yet</td></tr>'
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def query_or_empty(db, sql: str) -> list[dict]:
    try:
        return db.query(sql)
    except Exception:
        if db.dialect == "postgres":
            db.conn.rollback()
        return []


def count_rows(db, table_name: str) -> int:
    rows = query_or_empty(db, f"SELECT COUNT(*) AS n FROM {table_name}")
    return rows[0]["n"] if rows else 0


def dashboard_html() -> str:
    db = connect(load().db_url)
    try:
        counts = [
            {"stage": label, "rows": count_rows(db, table)}
            for label, table in (
                ("raw readings", "raw_readings"),
                ("dead letters", "dead_letter"),
                ("staged readings", "stg_readings"),
                ("hourly metrics", "fct_hourly_metrics"),
                ("anomalies", "fct_anomalies"),
                ("devices", "dim_device_health"),
            )
        ]
        quality = query_or_empty(db, "SELECT * FROM fct_ingestion_quality")
        health = query_or_empty(db,
            "SELECT device_id, total_readings, last_seen, last_battery_v, status "
            "FROM dim_device_health ORDER BY device_id"
        )
        hourly = query_or_empty(db,
            "SELECT device_id, event_hour, n_readings, avg_temperature_c, avg_humidity_pct "
            "FROM fct_hourly_metrics ORDER BY event_hour DESC, device_id LIMIT 24"
        )
        anomalies = query_or_empty(db,
            "SELECT device_id, event_ts, anomaly_type, temperature_c "
            "FROM fct_anomalies ORDER BY event_ts DESC LIMIT 20"
        )
        rejected = query_or_empty(db,
            "SELECT substr(reason, 1, 60) AS reason, COUNT(*) AS n "
            "FROM dead_letter GROUP BY 1 ORDER BY n DESC"
        )
        lineage = query_or_empty(db,
            "SELECT DISTINCT source, target FROM gov_lineage "
            "WHERE run_id = (SELECT MAX(run_id) FROM gov_lineage) ORDER BY source, target"
        )
    finally:
        db.close()

    cards = "".join(
        f'<article class="card"><span>{cell(row["stage"])}</span><strong>{cell(row["rows"])}</strong></article>'
        for row in counts
    )
    quality_summary = table(
        quality,
        ["raw_rows", "rejected_rows", "staged_rows", "duplicates_removed", "implausible_rows"],
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15"><title>IoT Pipeline Dashboard</title>
<style>
:root {{ color-scheme: light; --ink: #17211b; --muted: #64736a; --line: #dce5df; --accent: #0d766e; --paper: #f5f7f2; --panel: #fff; }}
* {{ box-sizing: border-box; }} body {{ margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.45 ui-sans-serif, system-ui, sans-serif; }}
main {{ max-width: 1280px; margin: auto; padding: 38px 24px 64px; }}
header {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 28px; }}
h1 {{ margin: 0; font: 700 34px/1.05 Georgia, serif; letter-spacing: 0; }} h2 {{ margin: 0 0 12px; font-size: 18px; }}
.subtle {{ color: var(--muted); margin: 8px 0 0; }} .refresh {{ color: var(--accent); font-size: 13px; }}
.cards {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 28px; }}
.card, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; }} .card {{ padding: 16px; }}
.card span {{ display: block; color: var(--muted); text-transform: uppercase; font-size: 11px; letter-spacing: .06em; }} .card strong {{ display: block; margin-top: 6px; color: var(--accent); font-size: 28px; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }} section {{ padding: 18px; overflow: auto; }}
section.wide {{ grid-column: 1 / -1; }} table {{ border-collapse: collapse; width: 100%; white-space: nowrap; }} th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); }} th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
td {{ font-size: 13px; }} .empty {{ color: var(--muted); text-align: center; padding: 20px; }}
@media (max-width: 850px) {{ main {{ padding: 24px 14px; }} header {{ display: block; }} .cards {{ grid-template-columns: repeat(2, 1fr); }} .grid {{ grid-template-columns: 1fr; }} section.wide {{ grid-column: auto; }} }}
</style></head><body><main>
<header><div><h1>IoT pipeline</h1><p class="subtle">A live view of ingestion, cleaning, analytics, and governance.</p></div><div class="refresh">Refreshes every 15 seconds</div></header>
<div class="cards">{cards}</div>
<div class="grid">
<section class="wide"><h2>Ingestion reconciliation</h2>{quality_summary}</section>
<section><h2>Device health</h2>{table(health, ["device_id", "total_readings", "last_seen", "last_battery_v", "status"])}</section>
<section><h2>Rejected messages</h2>{table(rejected, ["reason", "n"])}</section>
<section class="wide"><h2>Hourly metrics</h2>{table(hourly, ["device_id", "event_hour", "n_readings", "avg_temperature_c", "avg_humidity_pct"])}</section>
<section><h2>Anomalies</h2>{table(anomalies, ["device_id", "event_ts", "anomaly_type", "temperature_c"])}</section>
<section><h2>Latest lineage</h2>{table(lineage, ["source", "target"])}</section>
</div></main></body></html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return dashboard_html()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("DASHBOARD_HOST", "127.0.0.1"), port=int(os.getenv("DASHBOARD_PORT", "8000")))