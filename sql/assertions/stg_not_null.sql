-- description: key columns must not be null
SELECT reading_id FROM stg_readings WHERE device_id IS NULL OR event_ts IS NULL OR temperature_c IS NULL OR humidity_pct IS NULL
