-- depends: raw_readings
-- description: typed, de-duplicated readings (one row per device_id + event_ts)
WITH parsed AS (
  SELECT
    reading_id,
    device_id,
    JSON_GET(payload, 'ts')                           AS event_ts,
    CAST(JSON_GET(payload, 'temperature_c') AS REAL)  AS temperature_c,
    CAST(JSON_GET(payload, 'humidity_pct')  AS REAL)  AS humidity_pct,
    CAST(JSON_GET(payload, 'pressure_hpa')  AS REAL)  AS pressure_hpa,
    CAST(JSON_GET(payload, 'battery_v')     AS REAL)  AS battery_v,
    JSON_GET(payload, 'fw_version')                   AS fw_version,
    ingested_at
  FROM raw_readings
),
ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY device_id, event_ts
                            ORDER BY ingested_at, reading_id) AS rn
  FROM parsed
)
SELECT
  reading_id,
  device_id,
  event_ts,
  substr(event_ts, 1, 13) || ':00:00Z' AS event_hour,
  temperature_c,
  humidity_pct,
  pressure_hpa,
  battery_v,
  fw_version,
  CASE WHEN temperature_c BETWEEN -40 AND 85
        AND humidity_pct  BETWEEN 0 AND 100 THEN 1 ELSE 0 END AS is_plausible,
  ingested_at
FROM ranked
WHERE rn = 1
