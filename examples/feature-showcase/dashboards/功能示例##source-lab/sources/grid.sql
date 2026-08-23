select
  cast(i as varchar) as id,
  (i * 7) % 19 as val,
  (i * 11) % 23 as val2,
  (i * 13) % 29 as val3,
  (i * 17) % 31 as val4
from range(1, 16) as t(i)
