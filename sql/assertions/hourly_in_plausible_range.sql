-- description: hourly aggregates only contain plausible temperatures
SELECT * FROM fct_hourly_metrics WHERE min_temperature_c < -40 OR max_temperature_c > 85
