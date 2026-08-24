async function transform(context) {
  const delay = Number(context.compute_params.delay_ms || 0);
  await new Promise(resolve => setTimeout(resolve, delay));
  return {
    main: context.inputs.rows.map(row => ({
      name: row.name,
      value: Number(row.value) * 10,
    })),
  };
}
