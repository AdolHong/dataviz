const DATAVIZ_BROWSER_WORKER_PROTOCOL = 'dataviz/browser-transform-worker/v1';

class DatavizFrame {
  constructor(rows = []) { this._rows = Array.isArray(rows) ? rows : []; }
  rows() { return this._rows.map(row => ({...row})); }
  column(name) { return this._rows.map(row => row[name]); }
  filter(predicate) { return new DatavizFrame(this._rows.filter(predicate)); }
  where(field, operator, value) {
    const values = Array.isArray(value) ? value : [value];
    return this.filter(row => {
      const actual = row[field];
      if (operator === 'in') return !values.length || values.includes(actual);
      if (operator === 'not_in') return !values.includes(actual);
      if (operator === '>=') return Number(actual) >= Number(value);
      if (operator === '<=') return Number(actual) <= Number(value);
      if (operator === '>') return Number(actual) > Number(value);
      if (operator === '<') return Number(actual) < Number(value);
      if (operator === 'contains') return String(actual ?? '').includes(String(value ?? ''));
      return actual === value;
    });
  }
  derive(columns) {
    return new DatavizFrame(this._rows.map(row => {
      const next = {...row};
      Object.entries(columns).forEach(([name, derive]) => { next[name] = derive(next); });
      return next;
    }));
  }
  sort(field, direction = 'asc') {
    const sign = direction === 'desc' ? -1 : 1;
    return new DatavizFrame([...this._rows].sort((left, right) => {
      const a = left[field], b = right[field];
      return (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b))) * sign;
    }));
  }
  limit(count) { return new DatavizFrame(this._rows.slice(0, count)); }
  groupBy(...fields) { return new DatavizGroupedFrame(this._rows, fields.flat()); }
}

class DatavizGroupedFrame {
  constructor(rows, fields) { this._rows = rows; this._fields = fields; }
  aggregate(spec) {
    const groups = new Map();
    this._rows.forEach(row => {
      const key = JSON.stringify(this._fields.map(field => row[field]));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    const rows = [...groups.entries()].map(([key, values]) => {
      const keys = JSON.parse(key);
      const result = Object.fromEntries(this._fields.map((field, index) => [field, keys[index]]));
      Object.entries(spec).forEach(([output, rule]) => {
        const definition = typeof rule === 'string' ? {field: output, op: rule} : rule;
        const numbers = values.map(row => Number(row[definition.field] ?? 0));
        if (definition.op === 'count') result[output] = values.length;
        else if (definition.op === 'mean') result[output] = numbers.reduce((a, b) => a + b, 0) / Math.max(numbers.length, 1);
        else if (definition.op === 'min') result[output] = Math.min(...numbers);
        else if (definition.op === 'max') result[output] = Math.max(...numbers);
        else result[output] = numbers.reduce((a, b) => a + b, 0);
      });
      return result;
    });
    return new DatavizFrame(rows);
  }
}

const serializeError = (error, transformId, code = 'browser_transform_failed') => ({
  code,
  name: String(error?.name || 'Error'),
  message: String(error?.message || error || 'Browser Transform failed'),
  stack: typeof error?.stack === 'string' ? error.stack : null,
  transform_id: transformId,
  worker: true,
});

const resolveEntrypoint = (code, entrypoint) => {
  const factory = new Function(
    'entrypointName',
    `"use strict";\n${code}\nconst candidate = eval(entrypointName);\nreturn candidate;`,
  );
  const transform = factory(entrypoint);
  if (typeof transform !== 'function') {
    throw new Error(`Browser Transform entrypoint is not a function: ${entrypoint}`);
  }
  return transform;
};

self.addEventListener('message', async event => {
  const request = event.data || {};
  if (request.protocol !== DATAVIZ_BROWSER_WORKER_PROTOCOL || request.type !== 'execute') return;
  try {
    const transform = resolveEntrypoint(request.code || '', request.entrypoint || 'transform');
    const inputs = request.context?.inputs || {};
    const output = await transform({
      inputs,
      input: name => inputs[name],
      parameters: request.context?.parameters || {},
      selections: request.context?.selections || {},
      frame: rows => new DatavizFrame(rows),
    });
    try {
      self.postMessage({
        protocol: DATAVIZ_BROWSER_WORKER_PROTOCOL,
        type: 'result',
        request_id: request.request_id,
        output,
      });
    } catch (error) {
      self.postMessage({
        protocol: DATAVIZ_BROWSER_WORKER_PROTOCOL,
        type: 'error',
        request_id: request.request_id,
        error: serializeError(error, request.transform_id, 'browser_transform_not_serializable'),
      });
    }
  } catch (error) {
    self.postMessage({
      protocol: DATAVIZ_BROWSER_WORKER_PROTOCOL,
      type: 'error',
      request_id: request.request_id,
      error: serializeError(error, request.transform_id),
    });
  }
});
