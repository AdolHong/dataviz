async function transform(context) {
  const delay = Number(context.selections['dashboard:worker-runtime/delay_ms'] || 0);
  await new Promise(resolve => setTimeout(resolve, delay));
  return {
    main: context.inputs.rows.map(row => ({
      name: row.name,
      value: Number(row.value) * 10,
    })),
  };
}
