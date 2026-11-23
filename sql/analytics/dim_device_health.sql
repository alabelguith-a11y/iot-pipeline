-- depends: stg_readings
-- description: one row per device with last-known state and a simple health status
WITH latest AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY event_ts DESC) AS rn
  FROM stg_readings
  WHERE is_plausible = 1
),
agg AS (
  SELECT device_id, COUNT(*) AS total_readings, MIN(event_ts) AS first_seen, MAX(event_ts) AS last_seen
  FROM stg_readings
  GROUP BY device_id
)
SELECT
  a.device_id,
  a.first_seen,
  a.last_seen,
  a.total_readings,
  l.battery_v  AS last_battery_v,
  l.fw_version AS fw_version,
  CASE WHEN l.battery_v < 3.4 THEN 'low_battery' ELSE 'ok' END AS status
FROM agg a
LEFT JOIN latest l ON l.device_id = a.device_id AND l.rn = 1
