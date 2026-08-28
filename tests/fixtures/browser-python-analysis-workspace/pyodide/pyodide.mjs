export async function loadPyodide() {
  const values = new Map();
  const globals = {
    set(name, value) { values.set(name, value); },
    get(name) { return values.get(name); },
    delete(name) { values.delete(name); },
  };
  return {
    globals,
    FS: {
      mkdirTree() {}, writeFile() {}, unlink() {}, rmdir() {},
      readdir() { return ['.', '..']; }, stat() { return {mode: 0}; }, isDir() { return false; },
    },
    toPy(value) { return value; },
    setInterruptBuffer() {},
    async loadPackage() {},
    async runPythonAsync(source) {
      if (!source.includes('await _dataviz_execute')) return undefined;
      const payload = JSON.parse(values.get('__dv_payload'));
      if (Number(payload.query_inputs.batch) !== 3) {
        throw new Error('missing browser-python query input');
      }
      const input = payload.inputs.rows;
      const rows = input?.__datavizColumnarTable
        ? Array.from({length: input.length}, (_, index) => Object.fromEntries(
            Object.entries(input.columns).map(([name, column]) => [name, column[index]])
          ))
        : input;
      const factor = Number(payload.compute_params.factor);
      return JSON.stringify({
        main: rows.map(row => ({name: row.name, value: Number(row.value) * factor})),
      });
    },
  };
}
