with stores as (
  select
    store_no,
    printf('S%03d', store_no) as store_id,
    printf('门店 %03d', store_no) as store_name,
    case store_no % 4
      when 0 then '华北'
      when 1 then '华东'
      when 2 then '华南'
      else '西南'
    end as region,
    case store_no % 4
      when 0 then '北京'
      when 1 then '上海'
      when 2 then '深圳'
      else '成都'
    end as city
  from range(1, 101) as stores(store_no)
), periods as (
  select period_no from range(0, 12) as periods(period_no)
)
select
  store_id,
  store_name,
  region,
  city,
  strftime(date '2026-01-04' + period_no * interval '7 days', '%Y-%m-%d') as week,
  round(18000 + store_no * 137 + period_no * 820 + ((store_no * 17 + period_no * 29) % 11) * 430, 2) as revenue
from stores
cross join periods
order by store_id, week
