# IoT Streaming Pipeline: ESP32 → MQTT/ZeroMQ → Kafka → SQL ELT → Governance

![CI](https://github.com/<you>/iot-pipeline/actions/workflows/ci.yml/badge.svg)

A small but complete data platform that shows **embedded**, **data engineering** and **DevOps** skills in one repo, with a **data-governance** layer (catalog, lineage, quality checks) on top.

```mermaid
flowchart LR
  subgraph Edge
    ESP[ESP32 firmware] -->|MQTT| MQ
    SIM[Simulator] -->|MQTT or ZeroMQ| MQ
  end
  MQ[(Mosquitto / ZeroMQ)] --> BR[Bridge<br/>validate + DLQ]
  BR -->|dev: Kafka| K[(Kafka)] --> CO[Consumer<br/>idempotent insert]
  BR -->|test: direct| RAW
  CO --> RAW[(raw_readings<br/>dead_letter)]
  RAW --> STG[stg_readings<br/>typed, deduped, flagged]
  STG --> AN[fct_hourly_metrics<br/>dim_device_health<br/>fct_anomalies<br/>fct_ingestion_quality]
  AN --> BI[Metabase / Looker Studio]
  STG -.-> GOV[Governance<br/>catalog · lineage · quality results]
  AN -.-> GOV
```

## Two profiles

| | `test` (default) | `dev` |
|---|---|---|
| Transport | **ZeroMQ** (no broker) | **MQTT** (Mosquitto) |
| Queue | direct to DB | **Kafka** (KRaft) |
| Database | **SQLite** | **PostgreSQL** |
| Needs Docker | no | yes |
| Use | unit tests, CI, 10-second demo | the real architecture |

Switch with `PROFILE=dev`, or mix any piece with `TRANSPORT=mqtt|zmq`, `QUEUE=kafka|direct`, `DB_URL=...`. The business code is identical in both profiles. Only the adapters differ.

## Quick start

```bash
# 1) zero dependencies beyond Python: ZeroMQ + SQLite
pip install -r requirements.txt -r requirements-dev.txt
make demo          # bridge + simulator + ELT + report, ~10 s
make dashboard     # FastAPI dashboard at http://127.0.0.1:8000
make test          # 23 tests, no services required

# 2) full stack: Mosquitto + Kafka + PostgreSQL + all services
make up            # then: docker compose exec etl python -m iotpipe.etl.report
make down


After `make demo`, `make dashboard` visualizes the local `data/demo.db` pipeline
with stage counts, ingestion quality, device health, hourly metrics, anomalies,
rejected messages and lineage. For the PostgreSQL profile, use
`PROFILE=dev DB_URL=postgresql://iot:change-me@localhost:5432/iot make dashboard`.
# 3) Kubernetes locally (free)
make kind
```

## What happens to the data

1. **Contract**: `schemas/reading.schema.json` is the single source of truth for simulator, firmware, bridge and consumer.
2. **Bridge**: validates every message; bad ones go to a dead-letter table/topic *with the reason* and never crash the pipeline.
3. **Raw**: payload stored as received; `reading_id` PK makes redelivery harmless (at-least-once + idempotent = effectively once).
4. **Staging**: typed, de-duplicated on `(device_id, event_ts)`, plausibility flag instead of deletion.
5. **Analytics**: hourly facts, device health, anomalies, row-count reconciliation.
6. **Assertions + governance** on every run: 7 SQL assertions, catalog-coverage check, lineage and quality results stored in `gov_*` tables. The runner exits non-zero on failure so CI/Kubernetes can alert.

The simulator injects ~6 % deliberate defects (duplicates, spikes, jumps, late data, missing fields, garbage bytes) so the cleaning layer has real work. Details and upgrade ideas: [`docs/ETL_IDEAS.md`](docs/ETL_IDEAS.md).

Example output (`make demo`):

```
 raw_rows  rejected_rows  staged_rows  duplicates_removed  implausible_rows
      478              9          471                   7                 1
```

## Repo layout

```
iotpipe/          config · db adapter · schema validator · transport (MQTT|ZeroMQ) · bridge · consumer · simulator
iotpipe/etl/      runner (mini-Dataform) · governance · report
sql/              staging/ analytics/ assertions/   (portable SQL, JSON_GET macro hides dialect differences)
governance/       catalog.yml (descriptions + sensitivity per column)
firmware/esp32/   Arduino sketch (real or fake sensor)
k8s/              base (apps + CronJob) · infra (demo Mosquitto/Kafka/Postgres)
.github/          CI: lint · tests · e2e demo · Postgres integration · manifest validation · image build/push
docs/             ETL_IDEAS.md · GOVERNANCE.md
```

## Design decisions worth discussing in an interview

- **ELT, not ETL**: raw is immutable, transformations are SQL that can be re-run after any bug fix.
- **Why ZeroMQ for tests**: brokerless, starts in milliseconds, same topic/payload contract → tests exercise the real bridge logic. MQTT stays the production transport because ESP32 devices need a broker with QoS and persistent sessions.
- **Commit offsets after the DB write** (consumer) and **idempotent inserts** make Kafka's at-least-once delivery safe.
- **Flag, don't delete**: implausible readings stay visible (`is_plausible = 0`) and show up in `fct_anomalies`.
- **Same SQL on SQLite and PostgreSQL** (CI runs both) shows the models are not tied to one engine; this also eases the move to BigQuery/Dataform.

## Roadmap

BigQuery + Dataform + Dataplex migration (see [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md)), incremental models, Prometheus/Grafana, Airflow/Dagster orchestration.

## CV line (matches what is actually in this repo)

> Built a real-time IoT data pipeline (ESP32, MQTT/ZeroMQ, Kafka, PostgreSQL) with SQL ELT layers, automated data-quality assertions and metadata/lineage tracking; containerised with Docker/Kubernetes and CI/CD on GitHub Actions.

`Technologies: C++, Python, MQTT, ZeroMQ, Kafka, PostgreSQL, SQL, Docker, Kubernetes, GitHub Actions`

Add BigQuery / Dataform / Dataplex to the line only after the roadmap migration exists in the repo.
