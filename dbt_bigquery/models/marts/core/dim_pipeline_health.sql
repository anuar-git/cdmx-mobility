{{
    config(
        materialized='table',
        partition_by={'field': 'run_date', 'data_type': 'date'},
        cluster_by=['canonical_source']
    )
}}

-- One row per (run_date, canonical_source).
-- Joins ingestion counts, dbt model runtime, dbt test pass rate,
-- GE expectation results, and freshness SLA checks into a single
-- observability table for the pipeline health dashboard.
--
-- Canonical source mapping (ingestion_log → freshness_sla_log namespace):
--   ecobici_* / spark_ecobici_* → ecobici
--   metrobus_* / spark_metrobus_* → metrobus   (must precede metro% check)
--   metro_* / spark_metro_*     → metro
--   weather_* / spark_weather_* → weather

with ingestion as (
    select
        date(ingested_at)                                       as run_date,
        case
            when source like 'ecobici%'  or source like 'spark_ecobici%'   then 'ecobici'
            when source like 'metrobus%' or source like 'spark_metrobus%'  then 'metrobus'
            when source like 'metro%'    or source like 'spark_metro%'     then 'metro'
            when source like 'weather%'  or source like 'spark_weather%'   then 'weather'
            else source
        end                                                     as canonical_source,
        max(ingested_at)                                        as last_ingested_at,
        sum(coalesce(file_count, 0))                            as total_files,
        sum(coalesce(byte_count, 0))                            as total_bytes,
        sum(coalesce(row_count, 0))                             as total_rows_ingested,
        countif(status = 'success')                             as ingest_success_runs,
        countif(status = 'error')                               as ingest_error_runs,
        countif(status = 'skipped')                             as ingest_skipped_runs
    from {{ source('meta_cdmx', 'ingestion_log') }}
    group by 1, 2
),

-- dbt model runtime is pipeline-wide (not per source). Aggregate total runtime
-- and per-layer row counts so each source row carries the same dbt summary.
dbt_models as (
    select
        run_date,
        round(sum(coalesce(execution_ms, 0)) / 1000.0, 2)      as dbt_total_runtime_seconds,
        countif(status = 'success')                             as dbt_models_succeeded,
        countif(status != 'success')                            as dbt_models_failed,
        sum(coalesce(rows_affected, 0))                         as dbt_total_rows_affected
    from {{ source('meta_cdmx', 'dbt_run_results') }}
    where node_name not like 'my_%'  -- exclude dbt example models
    group by 1
),

dbt_tests as (
    select
        run_date,
        countif(status = 'pass')                                as dbt_tests_passed,
        countif(status = 'fail')                                as dbt_tests_failed,
        count(*)                                                as dbt_tests_total,
        round(
            safe_divide(countif(status = 'pass'), count(*)) * 100,
            2
        )                                                       as dbt_test_pass_rate_pct
    from {{ source('meta_cdmx', 'dbt_test_results') }}
    group by 1
),

gx as (
    select
        run_date,
        case
            when suite_name like '%ecobici%'   then 'ecobici'
            when suite_name like '%metro%'      then 'metro'
            when suite_name like '%metrobus%'   then 'metrobus'
            when suite_name like '%weather%'    then 'weather'
            else suite_name
        end                                                     as canonical_source,
        logical_and(success)                                    as gx_all_suites_passed,
        sum(evaluated_count)                                    as gx_evaluated_count,
        sum(successful_count)                                   as gx_successful_count,
        sum(unsuccessful_count)                                 as gx_unsuccessful_count,
        round(
            safe_divide(sum(successful_count), sum(evaluated_count)) * 100,
            2
        )                                                       as gx_pass_rate_pct
    from {{ source('meta_cdmx', 'gx_validation_results') }}
    group by 1, 2
),

-- Keep the most recent freshness check per (run_date, source) in case of reruns.
freshness as (
    select
        date(checked_at)                                        as run_date,
        source                                                  as canonical_source,
        latest_ts,
        lag_minutes                                             as freshness_lag_minutes,
        sla_minutes                                             as freshness_sla_minutes,
        is_violated                                             as freshness_sla_violated,
        checked_at
    from {{ source('meta_cdmx', 'freshness_sla_log') }}
    qualify row_number() over (
        partition by date(checked_at), source
        order by checked_at desc
    ) = 1
)

select
    i.run_date,
    i.canonical_source,
    -- ingestion
    i.last_ingested_at,
    i.total_files,
    i.total_bytes,
    i.total_rows_ingested,
    i.ingest_success_runs,
    i.ingest_error_runs,
    i.ingest_skipped_runs,
    -- dbt (pipeline-wide, repeated per source row)
    m.dbt_total_runtime_seconds,
    m.dbt_models_succeeded,
    m.dbt_models_failed,
    m.dbt_total_rows_affected,
    t.dbt_tests_passed,
    t.dbt_tests_failed,
    t.dbt_tests_total,
    t.dbt_test_pass_rate_pct,
    -- great expectations
    g.gx_all_suites_passed,
    g.gx_evaluated_count,
    g.gx_successful_count,
    g.gx_unsuccessful_count,
    g.gx_pass_rate_pct,
    -- freshness sla
    f.freshness_lag_minutes,
    f.freshness_sla_minutes,
    f.freshness_sla_violated,
    f.latest_ts                                                 as silver_latest_ts
from ingestion          i
left join dbt_models    m on m.run_date             = i.run_date
left join dbt_tests     t on t.run_date             = i.run_date
left join gx            g on g.run_date             = i.run_date
                         and g.canonical_source      = i.canonical_source
left join freshness     f on f.run_date             = i.run_date
                         and f.canonical_source      = i.canonical_source
