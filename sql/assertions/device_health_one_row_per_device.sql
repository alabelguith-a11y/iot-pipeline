-- description: dim_device_health is unique per device
SELECT device_id FROM dim_device_health GROUP BY device_id HAVING COUNT(*) > 1
