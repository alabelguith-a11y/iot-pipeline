# Data-treatment (ETL/ELT) ideas

What the repo already does is marked ✅. Everything else is an upgrade path ordered roughly by portfolio value per hour of effort.

## 1. Ingestion hygiene (raw layer)
- ✅ **Store the raw payload untouched** (`raw_readings.payload`) and parse later: you can always re-process after a bug fix (ELT, not ETL).
- ✅ **Idempotent loads**: `reading_id` primary key + `ON CONFLICT DO NOTHING`; safe under at-least-once delivery.
- ✅ **Dead-letter table/topic** with the rejection reason; monitor its size.
- **Schema versioning**: add `schema_version` to the payload; route unknown versions to the DLQ instead of crashing.
- **Partition raw by day** (Postgres declarative partitioning) and drop old partitions = cheap retention policy.

## 2. Cleaning (staging layer)
- ✅ **Typing + de-duplication** on the natural key `(device_id, event_ts)` (catches retries that got a new id).
- ✅ **Plausibility flag instead of deleting**: keep the row, mark `is_plausible = 0`, exclude downstream. Nothing is silently lost.
- **Hampel filter / rolling median** to detect spikes statistically instead of a fixed range (window function: median of last N readings, flag |x − median| > k·MAD).
- **Imputation of gaps**: build a time spine (`generate_series` in Postgres / recursive CTE in SQLite) and forward-fill short gaps (< 3 intervals), leave long gaps NULL and flag them.
- **Unit & calibration**: per-device offset table (`dim_device_calibration`) joined in staging: `temperature_c + offset`.
- **Timestamp trust**: compare `event_ts` with `ingested_at`; flag devices whose clock drifts (RTC without NTP) with `abs(ingested_at - event_ts)` stats.

## 3. Modelling (analytics layer)
- ✅ Hourly facts, device dimension, anomaly fact, reconciliation fact.
- **Incremental models**: only re-aggregate hours touched by new rows (watermark on `ingested_at`), and *re-open* the 2 previous hours for late-arriving data. This is the single most impressive upgrade: it is exactly how Dataform `incremental` / dbt incremental work.
- **SCD Type 2 for devices** (`valid_from`, `valid_to`) when firmware version or location changes.
- **Downsampling tiers**: 1-min raw → 1-hour → 1-day, with different retention each.
- **Derived metrics**: dew point from temperature + humidity, comfort index, battery discharge rate (V/day) → remaining-life forecast.
- **Feature table for ML**: lag/rolling features per device; train a small anomaly detector (Isolation Forest) and write scores back as `fct_ml_anomalies`.

## 4. Data quality & testing
- ✅ SQL assertions (return failing rows ⇒ non-zero exit), unit tests, end-to-end test with deliberately dirty data.
- **Freshness check**: `max(ingested_at)` older than N minutes ⇒ fail (alerts when a device or the bridge dies).
- **Volume anomaly check**: today's row count vs trailing 7-day average (±50 %).
- **Contract tests**: a test that generates a message from the firmware's field list and validates it against `schemas/reading.schema.json`, so firmware and pipeline can never drift.
- Try **Great Expectations** or **Soda** for the same checks, then compare with the home-made runner in the README (shows you understand the tools *and* what's under them).

## 5. Orchestration & ops
- ✅ Loop mode (`--every`), Kubernetes CronJob, failing job on failed assertion.
- Replace the CronJob with **Airflow/Dagster** (one DAG: ingest check → staging → analytics → tests → publish).
- Expose pipeline metrics (rows/s, DLQ rate, ETL duration) as **Prometheus** metrics and graph in Grafana.
- **Backfill command**: `python -m iotpipe.etl.runner --from 2026-01-01 --to 2026-01-07`.

## 6. Cloud mapping (when you get BigQuery access)
`raw_readings` → BigQuery raw dataset · `sql/*.sql` → Dataform SQLX (`config { type: "table"/"incremental" }`, assertions) · `governance/catalog.yml` → Dataplex aspects/policy tags · `gov_lineage` → Dataplex lineage · `gov_quality_results` → Dataplex data-quality scans · Metabase → Looker Studio. See `docs/GOVERNANCE.md`.
