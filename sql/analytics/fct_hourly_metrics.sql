-- depends: stg_readings
-- description: hourly aggregates per device, plausible readings only
SELECT
  device_id,
  event_hour,
  COUNT(*)            AS n_readings,
  AVG(temperature_c)  AS avg_temperature_c,
  MIN(temperature_c)  AS min_temperature_c,
  MAX(temperature_c)  AS max_temperature_c,
  AVG(humidity_pct)   AS avg_humidity_pct,
  MIN(battery_v)      AS min_battery_v
FROM stg_readings
WHERE is_plausible = 1
GROUP BY device_id, event_hour
