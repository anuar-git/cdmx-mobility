-- Headway must be NULL (first vehicle of day / data gap) or a positive duration.
-- A negative value means dwell_start_ts ordering is broken in the Silver job.
select fct_sk, headway_seconds
from {{ ref('fct_metrobus_stop_events') }}
where headway_seconds < 0
