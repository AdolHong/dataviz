select
  cast(:analysis_date as date) as analysis_date,
  cast(:range_start as date) as range_start,
  cast(:range_end as date) as range_end,
  date_diff('day', cast(:range_start as date), cast(:range_end as date)) + 1 as range_days

