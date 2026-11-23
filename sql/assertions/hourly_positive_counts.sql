-- description: every hourly bucket has at least one reading
SELECT * FROM fct_hourly_metrics WHERE n_readings < 1
