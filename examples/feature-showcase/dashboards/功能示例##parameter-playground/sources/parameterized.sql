select
  i as id,
  case when i % 3 = 1 then 'Alpha' when i % 3 = 2 then 'Beta' else 'Gamma' end as segment,
  i * :multiplier as value,
  round(sqrt(i * :multiplier) * 10, 2) as score
from range(1, :row_count + 1) as t(i)
