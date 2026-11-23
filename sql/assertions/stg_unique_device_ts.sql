-- description: one reading per device and event time
SELECT device_id, event_ts FROM stg_readings GROUP BY device_id, event_ts HAVING COUNT(*) > 1
