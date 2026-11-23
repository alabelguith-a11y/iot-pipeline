-- description: staging can never hold more rows than raw
SELECT 1 AS failed FROM fct_ingestion_quality WHERE staged_rows > raw_rows
