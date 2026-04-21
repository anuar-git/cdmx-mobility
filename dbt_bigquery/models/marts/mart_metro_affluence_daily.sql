with stg as (
    select * from {{ ref('stg_metro_affluence') }}
)

select
    date,
    line,
    station,
    sum(entries) as total_entries
from stg
group by 1, 2, 3
