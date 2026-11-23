-- depends: raw_readings, dead_letter, stg_readings
-- description: reconciliation of what entered the pipeline vs what survived each layer
SELECT
  (SELECT COUNT(*) FROM raw_readings)                       AS raw_rows,
  (SELECT COUNT(*) FROM dead_letter)                        AS rejected_rows,
  (SELECT COUNT(*) FROM stg_readings)                       AS staged_rows,
  (SELECT COUNT(*) FROM raw_readings) - (SELECT COUNT(*) FROM stg_readings) AS duplicates_removed,
  (SELECT COUNT(*) FROM stg_readings WHERE is_plausible = 0) AS implausible_rows
