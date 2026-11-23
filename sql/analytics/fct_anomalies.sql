-- depends: stg_readings
-- description: out-of-range readings and sudden temperature jumps (> 5C between consecutive readings)
WITH ordered AS (
  SELECT device_id, event_ts, temperature_c,
         LAG(temperature_c) OVER (PARTITION BY device_id ORDER BY event_ts) AS prev_temperature_c
  FROM stg_readings
  WHERE is_plausible = 1
)
SELECT device_id, event_ts, 'out_of_range' AS anomaly_type, temperature_c AS value
FROM stg_readings
WHERE is_plausible = 0
UNION ALL
SELECT device_id, event_ts, 'temperature_jump' AS anomaly_type, temperature_c - prev_temperature_c AS value
FROM ordered
WHERE prev_temperature_c IS NOT NULL AND ABS(temperature_c - prev_temperature_c) > 5
