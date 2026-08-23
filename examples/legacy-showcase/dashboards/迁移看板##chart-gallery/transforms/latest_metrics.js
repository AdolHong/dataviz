function transform(context) {
  const rows = context.inputs.metrics || [];
  const latestQuarter = rows.reduce(
    (latest, row) => String(row.quarter) > latest ? String(row.quarter) : latest,
    "",
  );
  return rows.filter(row => String(row.quarter) === latestQuarter);
}
