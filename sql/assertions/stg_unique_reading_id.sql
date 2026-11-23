-- description: reading_id must be unique in staging
SELECT reading_id FROM stg_readings GROUP BY reading_id HAVING COUNT(*) > 1
