SELECT 'North' AS region, 68000 * :target_factor AS target
UNION ALL SELECT 'South', 57000 * :target_factor
UNION ALL SELECT 'East', 76000 * :target_factor
UNION ALL SELECT 'West', 48000 * :target_factor

