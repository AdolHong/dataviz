function transform(context) {
  const rows = context.inputs.metrics || [];
  const cityCount = Math.max(1, Number(context.compute_params.city_count || 5));
  const latestQuarter = rows.reduce(
    (latest, row) => String(row.quarter) > latest ? String(row.quarter) : latest,
    "",
  );
  const latest = rows
    .filter(row => String(row.quarter) === latestQuarter)
    .sort((left, right) => Number(right.revenue || 0) - Number(left.revenue || 0))
    .slice(0, cityCount);
  return {main: latest};
}
