select
  i % 128 as bucket,
  i as row_id,
  (i * 17) % 1000 as measure
from range(1, :row_count + 1) as generated(i)
