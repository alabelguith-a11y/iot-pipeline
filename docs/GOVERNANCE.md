# Governance layer: local implementation and Dataplex mapping

| Capability | Local implementation (this repo) | GCP equivalent |
|---|---|---|
| Business metadata | `governance/catalog.yml` → table `gov_catalog` | Dataplex **aspects** / glossary |
| Sensitivity classification | `sensitivity: public/internal/confidential` per column | **Policy tags** (column-level security) |
| Completeness of metadata | `catalog_coverage` check fails the run if a column is undocumented | Aspect-completeness / data profile |
| Lineage | `-- depends:` headers → table `gov_lineage` per run | Dataplex **lineage** (OpenLineage / BigQuery native) |
| Data quality | SQL assertions → table `gov_quality_results` | Dataplex **data-quality scans** |
| Run history | `etl_run_log` (rows, seconds per model) | Dataform workflow invocations |

Query the governance tables directly:

```sql
SELECT table_name, column_name, sensitivity FROM gov_catalog WHERE sensitivity <> 'public';
SELECT DISTINCT source, target FROM gov_lineage WHERE run_id = (SELECT MAX(run_id) FROM gov_lineage);
SELECT * FROM gov_quality_results ORDER BY run_id DESC, status;
```

## Migration checklist (verify against the current Google docs, APIs change often)
1. Load `raw_readings` into a BigQuery dataset (Storage Write API or a Kafka→BigQuery sink).
2. Port each `sql/**/*.sql` to a Dataform `.sqlx` file; `-- depends:` becomes `${ref("...")}`.
3. Port each assertion to a Dataform assertion.
4. Create Dataplex aspect types from `catalog.yml`; attach policy tags for non-public columns.
5. Screenshot the lineage graph and one data-quality scan for the README.
