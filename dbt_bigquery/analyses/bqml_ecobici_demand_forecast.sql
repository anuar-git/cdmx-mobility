-- BigQuery ML ARIMA_PLUS demand forecast for EcoBici station availability.
--
-- This is a dbt analysis file: compiled by `dbt compile` but never executed by
-- dbt itself. To use:
--   1. Run: cd dbt_bigquery && uv run dbt compile --select bqml_ecobici_demand_forecast
--   2. Copy compiled SQL from target/compiled/.../bqml_ecobici_demand_forecast.sql
--   3. Run Step 1 in the BigQuery console (creates the ML model object).
--   4. Run Step 2 to generate the 24-hour forecast.
--
-- Requirements:
--   - fct_ecobici_station_hourly must have at least 14 days of data (ARIMA_PLUS
--     minimum). 30+ days recommended for reliable seasonality detection.
--   - The ML model is stored in marts_cdmx and persists between runs.
--
-- To refresh daily: create a BigQuery Scheduled Query that re-runs Step 1
-- (re-trains on a rolling 90-day window) and Step 2, writing results to
-- marts_cdmx.ecobici_demand_forecast_24h via CREATE OR REPLACE TABLE.
--
-- holiday_region = 'MX': ARIMA_PLUS has built-in Mexican holiday awareness —
-- the model accounts for demand patterns around Semana Santa, Día de Muertos,
-- Navidad, etc. without manual feature engineering via dim_date flags.

-- ─────────���─────────────────────────────────���─────────────────────────────────
-- Step 1: Train the model (re-run to retrain on fresh data)
-- ────────────────────────────────────���────────────────────────────────────────
CREATE OR REPLACE MODEL `{{ target.project }}.marts_cdmx.m_ecobici_demand_forecast`
OPTIONS (
    model_type       = 'ARIMA_PLUS',
    time_series_timestamp_col = 'hour_ts',
    time_series_data_col      = 'bikes_available_avg',
    time_series_id_col        = 'station_id',
    data_frequency   = 'HOURLY',
    holiday_region   = 'MX',
    horizon          = 24,
    auto_arima       = true
)
AS
select
    station_id,
    hour_ts,
    bikes_available_avg
from {{ ref('fct_ecobici_station_hourly') }}
where service_date >= date_sub(current_date('America/Mexico_City'), interval 90 day)
  and bikes_available_avg is not null
  and station_id in (
      -- Limit to top 20 stations by total state-change observations as a proxy
      -- for data completeness; sparse stations degrade ARIMA fit quality.
      select station_id
      from {{ ref('fct_ecobici_station_hourly') }}
      where service_date >= date_sub(current_date('America/Mexico_City'), interval 90 day)
      group by station_id
      order by sum(state_changes_count) desc
      limit 20
  );

-- ────────────────────────────────────────────��────────────────────────────────
-- Step 2: Generate 24-hour forecast
-- ────────────────────────────────────────────────────────────���────────────────
-- Wrap in CREATE OR REPLACE TABLE to persist results for Tableau:
--   CREATE OR REPLACE TABLE `{{ target.project }}.marts_cdmx.ecobici_demand_forecast_24h` AS
select
    station_id,
    forecast_timestamp,
    round(forecast_value, 1)                            as bikes_forecast,
    round(prediction_interval_lower_bound, 1)           as forecast_lower,
    round(prediction_interval_upper_bound, 1)           as forecast_upper,
    -- derive CDMX local service date from the UTC forecast timestamp
    date(forecast_timestamp, 'America/Mexico_City')     as service_date
from ml.forecast(
    model `{{ target.project }}.marts_cdmx.m_ecobici_demand_forecast`,
    struct(24 as horizon, 0.9 as confidence_level)
)
order by station_id, forecast_timestamp;
