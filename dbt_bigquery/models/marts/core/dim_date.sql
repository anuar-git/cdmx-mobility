{{ config(materialized='table') }}

-- Holy Week (Semana Santa) spring-break windows per SEP school calendar.
-- Each window is 14 days ending on Easter Sunday for the given year.
-- Easter dates: 2021=Apr-04, 2022=Apr-17, 2023=Apr-09, 2024=Mar-31,
--               2025=Apr-20, 2026=Apr-05, 2027=Mar-28.
-- Update when adding years beyond 2027.

with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2021-01-01' as date)",
        end_date="cast('2027-12-31' as date)"
    ) }}
),

holidays as (
    select * from {{ ref('mexican_holidays') }}
),

annotated as (
    select
        cast(date_day as date)                                          as date_day,
        extract(year from date_day)                                     as year,
        extract(month from date_day)                                    as month,
        extract(day from date_day)                                      as day,
        extract(dayofweek from date_day)                                as day_of_week,
        format_date('%A', date_day)                                     as day_name,
        format_date('%B', date_day)                                     as month_name,
        extract(isoweek from date_day)                                  as iso_week,
        extract(quarter from date_day)                                  as quarter,
        extract(dayofyear from date_day)                                as day_of_year,
        -- Quincena: days 1-15 = first, days 16+ = second.
        -- Payday is the 15th and the last calendar day of the month.
        extract(day from date_day) <= 15                                as is_first_quincena,
        extract(day from date_day) > 15                                 as is_second_quincena,
        extract(day from date_day) = 15
            or cast(date_day as date) = last_day(cast(date_day as date)) as is_quincena_payday,
        extract(dayofweek from date_day) in (1, 7)                      as is_weekend,
        extract(dayofweek from date_day) not in (1, 7)                  as is_weekday,
        -- Public holidays and bridge days (from seed).
        coalesce(h.holiday_type = 'public', false)                      as is_public_holiday,
        coalesce(h.holiday_type = 'bridge', false)                      as is_bridge_day,
        h.holiday_name                                                   as holiday_name,
        -- School vacations: computed via SEP calendar date ranges.
        -- Not stored in the holidays seed to avoid 600+ individual rows.
        case
            -- Summer break (July – August)
            when extract(month from date_day) between 7 and 8 then true
            -- Winter break (Dec 20 – Jan 6)
            when extract(month from date_day) = 12
                and extract(day from date_day) >= 20 then true
            when extract(month from date_day) = 1
                and extract(day from date_day) <= 6 then true
            -- Holy Week: 14-day window ending on Easter Sunday
            when cast(date_day as date)
                between date('2021-03-22') and date('2021-04-04') then true
            when cast(date_day as date)
                between date('2022-04-04') and date('2022-04-17') then true
            when cast(date_day as date)
                between date('2023-03-27') and date('2023-04-09') then true
            when cast(date_day as date)
                between date('2024-03-18') and date('2024-03-31') then true
            when cast(date_day as date)
                between date('2025-04-07') and date('2025-04-20') then true
            when cast(date_day as date)
                between date('2026-03-23') and date('2026-04-05') then true
            when cast(date_day as date)
                between date('2027-03-15') and date('2027-03-28') then true
            else false
        end                                                              as is_school_vacation
    from spine
    left join holidays h on h.holiday_date = cast(date_day as date)
)

select * from annotated
