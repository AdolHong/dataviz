const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';

const datavizNumericAggregate = (items, operation = 'sum', select = value => value) => {
  let count = 0;
  let sum = 0;
  let minimum = Infinity;
  let maximum = -Infinity;
  for (const item of items) {
    const value = Number(select(item) ?? 0);
    count += 1;
    sum += value;
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
  }
  if (operation === 'count') return count;
  if (operation === 'mean') return sum / Math.max(count, 1);
  if (operation === 'min') return minimum;
  if (operation === 'max') return maximum;
  return sum;
};

class DatavizFrame {
  constructor(rows = []) {
    this._rows = Array.isArray(rows) ? rows : null;
    this._columnar = rows?.__datavizColumnarTable ? rows : null;
  }
  get length() { return this._columnar?.length ?? this._rows?.length ?? 0; }
  _row(index) {
    if (!this._columnar) return this._rows[index];
    return Object.fromEntries(
      Object.entries(this._columnar.columns || {}).map(([name, values]) => [name, values[index]])
    );
  }
  map(callback) { return Array.from({length:this.length}, (_, index) => callback(this._row(index), index, this)); }
  [Symbol.iterator]() {
    let index = 0;
    return {next:() => index < this.length ? {value:this._row(index++), done:false} : {done:true}};
  }
  rows() { return this.map(row => ({...row})); }
  column(name) {
    if (this._columnar) return Array.from(this._columnar.columns?.[name] || []);
    return (this._rows || []).map(row => row[name]);
  }
  filter(predicate) { return new DatavizFrame(this.rows().filter(predicate)); }
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
    return new DatavizFrame(this.rows().map(row => {
      const next = {...row};
      Object.entries(columns).forEach(([name, derive]) => { next[name] = derive(next); });
      return next;
    }));
  }
  sort(field, direction = 'asc') {
    const sign = direction === 'desc' ? -1 : 1;
    return new DatavizFrame(this.rows().sort((left, right) => {
      const a = left[field], b = right[field];
      return (typeof a === 'number' && typeof b === 'number'
        ? a - b
        : String(a).localeCompare(String(b))) * sign;
    }));
  }
  limit(count) { return new DatavizFrame(this.rows().slice(0, count)); }
  groupBy(...fields) { return new DatavizGroupedFrame(this.rows(), fields.flat()); }
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
    return new DatavizFrame([...groups.entries()].map(([key, values]) => {
      const keys = JSON.parse(key);
      const result = Object.fromEntries(this._fields.map((field, index) => [field, keys[index]]));
      Object.entries(spec).forEach(([output, rule]) => {
        const definition = typeof rule === 'string' ? {field:output, op:rule} : rule;
        result[output] = datavizNumericAggregate(
          values,
          definition.op,
          row => row[definition.field],
        );
      });
      return result;
    }));
  }
}

const serializeError = (error, transformId, code = 'interactive_transform_failed') => ({
  code:String(error?.code || code),
  name:String(error?.name || 'Error'),
  message:String(error?.message || error || 'Interactive Transform failed'),
  stack:typeof error?.stack === 'string' ? error.stack : null,
  transform_id:transformId,
  runtime:'browser-js',
  worker:true,
});

const resolveEntrypoint = (code, entrypoint, dependencies = {}) => {
  const dependencyCode = Object.keys(dependencies).sort().map(name => dependencies[name]).join('\n');
  const factory = new Function(
    'entrypointName',
    `"use strict";\n${dependencyCode}\n${code}\nconst candidate = eval(entrypointName);\nreturn candidate;`,
  );
  const transform = factory(entrypoint);
  if (typeof transform !== 'function') {
    throw new Error(`browser-js entrypoint is not a function: ${entrypoint}`);
  }
  return transform;
};

const cancellationError = transformId => {
  const error = new Error(`Interactive Transform ${transformId} was cancelled`);
  error.name = 'AbortError';
  error.code = 'interactive_transform_cancelled';
  return error;
};

const cancelledRequests = new Set();

self.addEventListener('message', async event => {
  const request = event.data || {};
  if (request.protocol === DATAVIZ_INTERACTIVE_WORKER_PROTOCOL && request.type === 'cancel') {
    cancelledRequests.add(request.request_id);
    return;
  }
  if (request.protocol !== DATAVIZ_INTERACTIVE_WORKER_PROTOCOL || request.type !== 'execute') return;
  try {
    const isCancelled = () => cancelledRequests.has(request.request_id)
      || Boolean(request.cancel_buffer && Atomics.load(request.cancel_buffer, 0));
    const throwIfCancelled = () => {
      if (isCancelled()) throw cancellationError(request.transform_id);
    };
    throwIfCancelled();
    const transform = resolveEntrypoint(
      request.code || '', request.entrypoint || 'transform', request.code_dependencies || {}
    );
    const inputs = Object.fromEntries(Object.entries(request.context?.inputs || {}).map(
      ([name, value]) => [name, value?.__datavizColumnarTable ? new DatavizFrame(value) : value]
    ));
    const output = await transform({
      inputs,
      input:name => inputs[name],
      query_params:request.context?.query_params || {},
      compute_params:request.context?.compute_params || {},
      selections:request.context?.selections || {},
      table:name => inputs[name] instanceof DatavizFrame ? inputs[name] : new DatavizFrame(inputs[name]),
      frame:rows => rows instanceof DatavizFrame ? rows : new DatavizFrame(rows),
      cancelled:isCancelled,
      throwIfCancelled,
      progress:(value = null, message = '') => {
        throwIfCancelled();
        self.postMessage({
          protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
          type:'progress',
          request_id:request.request_id,
          value,
          message,
        });
      },
    });
    throwIfCancelled();
    self.postMessage({
      protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
      type:'result',
      request_id:request.request_id,
      output,
    });
  } catch (error) {
    self.postMessage({
      protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
      type:'error',
      request_id:request.request_id,
      error:serializeError(error, request.transform_id),
    });
  } finally {
    cancelledRequests.delete(request.request_id);
  }
});
