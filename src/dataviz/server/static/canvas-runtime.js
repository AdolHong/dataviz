
const DATAVIZ_RUNTIME_PROTOCOL = 'dataviz/runtime/v2';
const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';
if (window.dataviz.protocol?.schema !== DATAVIZ_RUNTIME_PROTOCOL) {
  throw new Error(`Unsupported Dataviz Runtime protocol: ${window.dataviz.protocol?.schema || 'missing'}`);
}
const datavizFrameIdentity = () => ({
  dashboard_id:window.dataviz.dashboard_id || null,
  run_id:window.dataviz.run_id || null,
  frame_id:window.dataviz.frame_id || null,
});
const datavizSameFrameIdentity = value => ['dashboard_id', 'run_id', 'frame_id'].every(
  key => (value?.[key] || null) === datavizFrameIdentity()[key],
);
const datavizPostToParent = payload => {
  if (window.parent === window) return;
  window.parent.postMessage({...payload, ...datavizFrameIdentity()}, window.location.origin);
};
const canonicalOutputReference = reference => {
  const raw = String(reference || '').trim();
  if (!raw) throw new Error('Output reference cannot be empty');
  if (!/^(source|dataset|interactive):[^/]+\/[^/]+$/.test(raw)) {
    throw new Error(`Output reference must be explicit: ${raw}`);
  }
  return raw;
};
const datavizValueSignature = value => {
  if (value?.__datavizArrowOutput) return `arrow:${value.descriptor?.content_hash || value.descriptor?.row_count || 'table'}`;
  try { return JSON.stringify(value); }
  catch { return String(value); }
};
const datavizRuntimeError = payload => {
  const error = new Error(payload?.message || 'Dataviz Runtime failed');
  Object.assign(error, payload || {});
  if (payload?.name) error.name = payload.name;
  if (payload?.stack) error.stack = payload.stack;
  return error;
};
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
const datavizContractError = (code, message, details = {}) => datavizRuntimeError({
  code,
  name:'DatavizContractError',
  message,
  ...details,
});
const datavizIsEmptyControlValue = value => (
  value == null || value === '' || (Array.isArray(value) && value.length === 0)
);
const datavizDecodeControlValue = (input, value, {path = false} = {}) => {
  if (value === '') return '';
  if (path || input?.dataset?.valueEncoding === 'json') {
    try { return JSON.parse(value); }
    catch (error) {
      throw datavizContractError(
        'control_value_decode_failed',
        `Control value is not valid JSON: ${value}`,
        {value, cause:error.message},
      );
    }
  }
  return value;
};
const datavizEncodeControlValue = (input, value, {path = false} = {}) => (
  path || input?.dataset?.valueEncoding === 'json'
    ? JSON.stringify(value)
    : String(value)
);
const datavizIsoDate = (value, label) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
    throw datavizContractError('invalid_date', `${label} must use YYYY-MM-DD`);
  }
  const normalized = value.trim();
  const parsed = new Date(`${normalized}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== normalized) {
    throw datavizContractError('invalid_date', `${label} must be a real calendar date`);
  }
  return normalized;
};
const datavizDecimalNumberPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const datavizChoiceValue = (definition, value) => {
  const choices = definition?.choices || [];
  if (!choices.length) return value;
  const signature = datavizValueSignature(value);
  const exact = choices.filter(choice => datavizValueSignature(choice.value) === signature);
  if (exact.length === 1) return exact[0].value;
  if (typeof value === 'string') {
    const comparable = choices.filter(choice => String(choice.value) === value);
    if (comparable.length === 1) return comparable[0].value;
  }
  throw datavizContractError('unknown_choice', `Value ${JSON.stringify(value)} is not a declared choice`);
};
const datavizNormalizeControlValue = (definition, value, {namespace = 'control', key = ''} = {}) => {
  const type = definition?.type || 'string';
  const fail = error => {
    if (error?.name === 'DatavizContractError') {
      error.code = `${namespace}_${error.code}`;
      error.key = key;
    }
    throw error;
  };
  try {
    if (datavizIsEmptyControlValue(value)) {
      if (definition?.required) throw datavizContractError('required', 'A value is required');
      return ['multi_select', 'date_range'].includes(type) ? [] : null;
    }
    if (type === 'string') {
      if (typeof value !== 'string') throw datavizContractError('invalid_type', 'Value must be a string');
      return value;
    }
    if (['number', 'integer'].includes(type)) {
      const raw = typeof value === 'string' ? value.trim() : null;
      if (raw != null && (
        (type === 'integer' && !/^[+-]?\d+$/.test(raw))
        || (type === 'number' && !datavizDecimalNumberPattern.test(raw))
      )) {
        throw datavizContractError('invalid_type', `Value must be a${type === 'integer' ? 'n integer' : ' finite number'}`);
      }
      const numeric = typeof value === 'number' ? value : Number(raw);
      if (!Number.isFinite(numeric) || (type === 'integer' && !Number.isInteger(numeric))) {
        throw datavizContractError('invalid_type', `Value must be a${type === 'integer' ? 'n integer' : ' finite number'}`);
      }
      if (Number.isInteger(numeric) && !Number.isSafeInteger(numeric)) {
        throw datavizContractError('unsafe_integer', 'Integer exceeds the exact JavaScript range; model identifiers as strings');
      }
      if (definition.min != null && numeric < Number(definition.min)) {
        throw datavizContractError('below_minimum', `Value must be at least ${definition.min}`);
      }
      if (definition.max != null && numeric > Number(definition.max)) {
        throw datavizContractError('above_maximum', `Value must be at most ${definition.max}`);
      }
      if (definition.step != null) {
        const base = Number(definition.min || 0);
        const quotient = (numeric - base) / Number(definition.step);
        if (Math.abs(quotient - Math.round(quotient)) > 1e-9) {
          throw datavizContractError('invalid_step', `Value must follow step ${definition.step} from ${base}`);
        }
      }
      return numeric;
    }
    if (type === 'boolean') {
      if (typeof value === 'boolean') return value;
      if (value === 0 || value === 1) return Boolean(value);
      if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
        if (['false', '0', 'no', 'off'].includes(normalized)) return false;
      }
      throw datavizContractError('invalid_type', 'Value must be a boolean');
    }
    if (type === 'date') return datavizIsoDate(value, 'Value');
    if (type === 'date_range') {
      const range = typeof value === 'string' ? value.split(',', 2).map(item => item.trim()) : value;
      if (!Array.isArray(range) || range.length !== 2) {
        throw datavizContractError('invalid_shape', 'Date range must contain exactly [start, end]');
      }
      const start = range[0] ? datavizIsoDate(range[0], 'Date range start') : '';
      const end = range[1] ? datavizIsoDate(range[1], 'Date range end') : '';
      if (!start && !end) return [];
      if (start && end && start > end) {
        throw datavizContractError('invalid_range', 'Date range start cannot be after end');
      }
      return [start, end];
    }
    if (type === 'single_select') {
      if (Array.isArray(value) || (value && typeof value === 'object')) {
        throw datavizContractError('invalid_type', 'Single select requires one value');
      }
      return datavizChoiceValue(definition, value);
    }
    if (type === 'multi_select') {
      if (!Array.isArray(value)) throw datavizContractError('invalid_type', 'Multi select requires a list');
      const normalized = value.map(item => datavizChoiceValue(definition, item));
      const signatures = normalized.map(datavizValueSignature);
      if (new Set(signatures).size !== signatures.length) {
        throw datavizContractError('duplicate_value', 'Multi select values must be unique');
      }
      if (definition?.required && !normalized.length) {
        throw datavizContractError('required', 'At least one value is required');
      }
      return normalized;
    }
    throw datavizContractError('unknown_type', `Unsupported control type: ${type}`);
  } catch (error) {
    return fail(error);
  }
};
const datavizNormalizeArrowValue = value => {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'bigint') {
    const number = Number(value);
    return Number.isSafeInteger(number) ? number : String(value);
  }
  if (ArrayBuffer.isView(value)) return Array.from(value, datavizNormalizeArrowValue);
  return value;
};
class DatavizArrowOutput {
  constructor(table, descriptor, bytes) {
    this.__datavizArrowOutput = true;
    this.table = table;
    this.descriptor = descriptor;
    this.bytes = bytes;
    this._rows = null;
    this._columnar = null;
  }
  rows() {
    if (this._rows) return this._rows;
    const fields = this.table.schema.fields.map(field => field.name);
    const columns = fields.map(field => this.table.getChild(field));
    this._rows = Array.from({length:this.table.numRows}, (_, rowIndex) => Object.fromEntries(
      fields.map((field, columnIndex) => [field, datavizNormalizeArrowValue(columns[columnIndex]?.get(rowIndex))])
    ));
    return this._rows;
  }
  columnar() {
    if (this._columnar) return this._columnar;
    const fields = this.table.schema.fields.map(field => field.name);
    this._columnar = {
      __datavizColumnarTable:true,
      length:this.table.numRows,
      columns:Object.fromEntries(fields.map(field => [
        field,
        Array.from(this.table.getChild(field) || [], datavizNormalizeArrowValue),
      ])),
    };
    return this._columnar;
  }
}
const datavizTableRows = value => value?.__datavizArrowOutput ? value.rows() : (Array.isArray(value) ? value : []);
const datavizMaterializeOutput = value => value?.__datavizArrowOutput ? value.rows() : value;
const datavizSnapshotValue = value => {
  if (value?.__datavizArrowOutput) return value.rows().map(datavizSnapshotValue);
  if (Array.isArray(value)) return value.map(datavizSnapshotValue);
  if (value && typeof value === 'object') {
    if (value instanceof Blob || value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
      throw new Error('Binary browser Outputs cannot be embedded as JSON snapshots');
    }
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, datavizSnapshotValue(item)])
    );
  }
  return value;
};
const datavizWorkerValue = value => value?.__datavizArrowOutput ? value.columnar() : value;
const datavizCacheClone = value => {
  if (value?.__datavizArrowOutput) return value;
  if (Array.isArray(value)) return value.map(datavizCacheClone);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, datavizCacheClone(item)]));
  }
  return value;
};
const datavizDecodeBase64Chunks = chunks => {
  const decoded = (chunks || []).map(chunk => Uint8Array.from(atob(chunk), value => value.charCodeAt(0)));
  const bytes = new Uint8Array(decoded.reduce((total, value) => total + value.byteLength, 0));
  let offset = 0;
  decoded.forEach(value => { bytes.set(value, offset); offset += value.byteLength; });
  return bytes;
};
const datavizDecompress = async (bytes, compression) => {
  if (!compression || compression === 'none' || compression === 'http') return bytes;
  if (compression !== 'gzip') throw new Error(`Unsupported browser transport compression: ${compression}`);
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot decompress embedded Arrow data');
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
};
const datavizLoadTransport = async descriptor => {
  if (descriptor?.encoding !== 'arrow-ipc') throw new Error(`Unsupported browser transport: ${descriptor?.encoding || 'missing'}`);
  const compressed = descriptor.url
    ? new Uint8Array(await fetch(descriptor.url, {cache:'no-store'}).then(response => {
        if (!response.ok) throw new Error(`Arrow output is unavailable (${response.status})`);
        return response.arrayBuffer();
      }))
    : datavizDecodeBase64Chunks(descriptor.chunks);
  const bytes = await datavizDecompress(compressed, descriptor.url ? 'http' : descriptor.compression);
  const Arrow = await window.datavizArrowReady;
  const table = await Arrow.tableFromIPC(bytes);
  return new DatavizArrowOutput(table, descriptor, bytes);
};
const datavizJsonCompatible = value => {
  const seen = new WeakSet();
  const visit = item => {
    if (typeof item === 'number' && !Number.isFinite(item)) return false;
    if (typeof item === 'bigint' || typeof item === 'function' || typeof item === 'symbol' || typeof item === 'undefined') return false;
    if (!item || typeof item !== 'object') return true;
    if (seen.has(item)) return false;
    seen.add(item);
    return (Array.isArray(item) ? item : Object.values(item)).every(visit);
  };
  return visit(value);
};
const datavizDtypeMatches = (value, dtype = '') => {
  const normalized = String(dtype).toLowerCase();
  if (!normalized || value == null) return true;
  if (normalized.includes('bool')) return typeof value === 'boolean';
  if (normalized.includes('int') || normalized.includes('uint')) return typeof value === 'number' && Number.isInteger(value);
  if (normalized.includes('float') || normalized === 'number' || normalized.includes('double')) return typeof value === 'number' && Number.isFinite(value);
  if (normalized.includes('date') || normalized.includes('time')) return value instanceof Date || (typeof value === 'string' && !Number.isNaN(Date.parse(value)));
  if (normalized.includes('str') || normalized.includes('string')) return typeof value === 'string';
  // pandas object is intentionally broad; concrete browser contracts should use
  // string/number/boolean/date when they require cross-Runtime type checking.
  if (normalized === 'object') return true;
  return true;
};
const datavizArrowDtypeMatches = (actual, expected = '') => {
  const source = String(actual || '').toLowerCase();
  const target = String(expected || '').toLowerCase();
  if (!target || target === 'object') return true;
  if (target.includes('bool')) return source.includes('bool');
  if (target.includes('uint')) return source.includes('uint');
  if (target.includes('int')) return /(^|[^a-z])u?int/.test(source);
  if (target.includes('float') || target === 'number' || target.includes('double')) {
    return /float|double|decimal/.test(source);
  }
  if (target.includes('date') || target.includes('time')) return /date|time|timestamp/.test(source);
  if (target.includes('str') || target.includes('string')) return /utf8|string/.test(source);
  return source === target;
};
const validateInteractiveTable = (
  transformId,
  label,
  value,
  schema = [],
  code = 'interactive_output_schema_mismatch',
  kindCode = 'interactive_output_kind_mismatch',
) => {
  if (!Array.isArray(value) && !value?.__datavizArrowOutput) {
    throw datavizContractError(kindCode, `${label} must be rows[] or an Arrow table`, {transform_id:transformId});
  }
  const rows = value?.__datavizArrowOutput ? null : value;
  if (rows && rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
    throw datavizContractError(kindCode, `${label} rows must be objects`, {transform_id:transformId});
  }
  const arrowFields = value?.__datavizArrowOutput
    ? new Map(value.table.schema.fields.map(field => [field.name, String(field.type)]))
    : null;
  const missing = schema.filter(column => column.required !== false && (
    arrowFields ? !arrowFields.has(column.name) : rows.some(row => !(column.name in row))
  )).map(column => column.name);
  const nulls = schema.filter(column => column.nullable === false && (
    arrowFields ? Number(value.table.getChild(column.name)?.nullCount || 0) > 0 : rows.some(row => row[column.name] == null)
  )).map(column => column.name);
  const dtypes = schema.filter(column => column.dtype && (
    arrowFields
      ? !datavizArrowDtypeMatches(arrowFields.get(column.name), column.dtype)
      : rows.some(row => column.name in row && !datavizDtypeMatches(row[column.name], column.dtype))
  )).map(column => column.name);
  if (missing.length || nulls.length || dtypes.length) {
    throw datavizContractError(
      code,
      `${label} schema mismatch; missing=${missing.join(',')} nulls=${nulls.join(',')} dtypes=${dtypes.join(',')}`,
      {transform_id:transformId, missing, nulls, dtypes},
    );
  }
};
const validateInteractiveOutput = (transformId, name, value, definition = {}) => {
  const label = `Interactive Transform ${transformId}/${name}`;
  if (definition.kind === 'table') {
    validateInteractiveTable(transformId, label, value, definition.schema || []);
    return;
  }
  if (definition.kind === 'scalar' && value !== null && (
    !['string', 'number', 'boolean'].includes(typeof value) || (typeof value === 'number' && !Number.isFinite(value))
  )) throw datavizContractError('interactive_output_kind_mismatch', `${label} must return a finite JSON scalar`, {transform_id:transformId, output:name});
  if (['text', 'html', 'image', 'file'].includes(definition.kind) && typeof value !== 'string') {
    throw datavizContractError('interactive_output_kind_mismatch', `${label} must return a string`, {transform_id:transformId, output:name});
  }
  if (['object', 'chart'].includes(definition.kind) && (!value || typeof value !== 'object' || Array.isArray(value))) {
    throw datavizContractError('interactive_output_kind_mismatch', `${label} must return an object`, {transform_id:transformId, output:name});
  }
  if (['object', 'chart'].includes(definition.kind) && !datavizJsonCompatible(value)) {
    throw datavizContractError('interactive_output_not_json_serializable', `${label} must return strict JSON data`, {transform_id:transformId, output:name});
  }
};
const datavizRuntime = window.datavizRuntime = {
  protocol: 'dataviz/runtime/v2',
  transforms: new Map(),
  views: new Map(),
  renderers: new Map(),
  outputSignatures: new Map(),
  outputErrors: new Map(),
  transformErrors: new Map(),
  rendererErrors: new Map(),
  activeTransforms: new Map(),
  transformRequests: new Map(),
  transportPromises: new Map(),
  transformGenerations: new Map(),
  workerUrls: new Map(),
  interactionCache: new Map(),
  initializing: false,
  initializationPromise: null,
  interactiveAdapters: Object.create(null),
  metrics: {
    interactiveTransforms: {started:0, completed:0, cancelled:0, timedOut:0, failed:0, cacheHits:0},
    transports: {started:0, completed:0, failed:0, arrowRows:0, arrowBytes:0, totalMs:0},
    renderers: {mounts:0, updates:0, empty:0, failed:0, totalMs:0},
    perspective: {created:0, updated:0, flushed:0, disposed:0, failed:0},
    repeat: {cards:0, mounted:0, maxMounted:0, disposed:0, searches:0},
  },
  registerInteractiveTransform(spec, source) {
    if (!spec?.id || !spec.runtime || !source?.entrypoint) throw new Error('Interactive Transform requires id, runtime and entrypoint');
    const inertExport = window.dataviz.asset_mode === 'inline' && (
      (window.dataviz.snapshot_interactions || []).includes(spec.id)
      || spec.export?.mode === 'unavailable'
    );
    if (spec.runtime !== 'server-python' && typeof source?.code !== 'string' && !inertExport) {
      throw new Error(`${spec.runtime} requires embedded code`);
    }
    if (this.transforms.has(spec.id)) throw new Error(`Duplicate Interactive Transform: ${spec.id}`);
    this.transforms.set(spec.id, {spec, source});
  },
  registerView(id, definition) {
    if (!id || typeof definition?.render !== 'function') throw new Error('View registration requires id and render');
    if (this.views.has(id)) throw new Error(`Duplicate View registration: ${id}`);
    this.views.set(id, {inputs: definition.inputs || {}, render: definition.render});
  },
  registerRenderer(type, renderer) {
    if (!type || typeof renderer?.mount !== 'function') throw new Error('Renderer requires type and mount');
    if (this.renderers.has(type)) throw new Error(`Duplicate Renderer: ${type}`);
    this.renderers.set(type, renderer);
  },
  configureSnapshotControls() {
    const snapshotIds = new Set(window.dataviz.snapshot_interactions || []);
    const selectionKeys = new Set();
    const computeKeys = new Set();
    snapshotIds.forEach(id => {
      const spec = this.transforms.get(id)?.spec;
      Object.values(spec?.selection_inputs || {}).forEach(key => selectionKeys.add(key));
      Object.values(spec?.compute_inputs || {}).forEach(key => computeKeys.add(key));
    });
    selectionKeys.forEach(key => {
      document.querySelectorAll(`[data-selection-key="${CSS.escape(key)}"]`).forEach(control => {
        control.dataset.selectionFrozen = 'true';
        control.setAttribute('aria-label', `${control.getAttribute('aria-label') || key} · fixed snapshot`);
        control.querySelectorAll('input,select,button').forEach(input => { input.disabled = true; });
      });
    });
    computeKeys.forEach(key => {
      document.querySelectorAll(`[data-compute-key="${CSS.escape(key)}"]`).forEach(control => {
        control.dataset.computeFrozen = 'true';
        control.querySelectorAll('input,select,button').forEach(input => { input.disabled = true; });
      });
    });
  },
  transformOrder() {
    const pending = new Map([...this.transforms].map(([id, item]) => [id, new Set(
      Object.values(item.spec.inputs || {})
        .map(canonicalOutputReference)
        .filter(reference => reference.startsWith('interactive:'))
        .map(reference => reference.slice('interactive:'.length).split('/')[0])
    )]));
    const order = [];
    while (pending.size) {
      const ready = [...pending].filter(([, dependencies]) => [...dependencies].every(value => !pending.has(value)));
      if (!ready.length) throw new Error(`Interactive Transform cycle: ${[...pending.keys()].join(', ')}`);
      ready.forEach(([id]) => { order.push(id); pending.delete(id); });
    }
    return order;
  },
  interactiveWorkerUrl(runtime) {
    if (this.workerUrls.has(runtime)) return this.workerUrls.get(runtime);
    const source = runtime === 'browser-python'
      ? window.datavizInteractivePythonWorkerSource
      : window.datavizInteractiveJsWorkerSource;
    if (!source) throw new Error(`${runtime} Worker source is missing`);
    const url = URL.createObjectURL(new Blob([source], {type:'application/javascript'}));
    this.workerUrls.set(runtime, url);
    return url;
  },
  cancelTransforms(reason = 'Runtime disposed') {
    this.activeTransforms.forEach(controller => controller.cancel(reason));
    this.activeTransforms.clear();
  },
  executeBrowserRuntime(id, item, inputValues) {
    const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const timeoutMs = Math.max(1, Number(item.spec.timeout_seconds || 30) * 1000);
    this.activeTransforms.get(id)?.cancel('Superseded by a newer generation');
    const generation = (this.transformGenerations.get(id) || 0) + 1;
    this.transformGenerations.set(id, generation);
    const worker = new Worker(
      this.interactiveWorkerUrl(item.spec.runtime),
      item.spec.runtime === 'browser-python' ? {type:'module'} : undefined,
    );
    const cancelBuffer = typeof SharedArrayBuffer === 'function'
      ? new Uint8Array(new SharedArrayBuffer(1))
      : null;
    this.metrics.interactiveTransforms.started += 1;
    return new Promise((resolve, reject) => {
      let settled = false;
      let cancelTimer = null;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        clearTimeout(cancelTimer);
        worker.terminate();
        if (this.activeTransforms.get(id) === controller) this.activeTransforms.delete(id);
        callback(value);
      };
      const controller = {
        cancel: reason => {
          if (settled) return;
          this.metrics.interactiveTransforms.cancelled += 1;
          if (cancelBuffer) Atomics.store(cancelBuffer, 0, item.spec.runtime === 'browser-python' ? 2 : 1);
          worker.postMessage({
            protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
            type:'cancel',
            request_id:requestId,
          });
          cancelTimer = setTimeout(() => finish(reject, datavizRuntimeError({
              code:'interactive_transform_cancelled',
              name:'AbortError',
              message:`Interactive Transform ${id} cancelled: ${reason}`,
              transform_id:id,
              worker:true,
            })), 40);
        },
      };
      const timer = setTimeout(() => {
        this.metrics.interactiveTransforms.timedOut += 1;
        finish(reject, datavizRuntimeError({
          code:'interactive_transform_timeout',
          name:'TimeoutError',
          message:`Interactive Transform ${id} exceeded ${item.spec.timeout_seconds || 30} seconds`,
          transform_id:id,
          timeout_seconds:Number(item.spec.timeout_seconds || 30),
          worker:true,
        }));
      }, timeoutMs);
      worker.addEventListener('message', event => {
        const response = event.data || {};
        if (response.protocol !== DATAVIZ_INTERACTIVE_WORKER_PROTOCOL || response.request_id !== requestId) return;
        if (response.type === 'progress') {
          window.dispatchEvent(new CustomEvent('dataviz:interactionprogress', {detail:{transformId:id, generation, value:response.value, message:response.message}}));
          return;
        }
        if (response.type === 'error') finish(reject, datavizRuntimeError(response.error));
        else {
          this.metrics.interactiveTransforms.completed += 1;
          finish(resolve, response.output);
        }
      });
      worker.addEventListener('error', event => finish(reject, datavizRuntimeError({
        code:'interactive_transform_worker_error',
        message:event.message || `Interactive Transform ${id} Worker crashed`,
        stack:event.error?.stack || null,
        transform_id:id,
        worker:true,
      })));
      this.activeTransforms.set(id, controller);
      worker.postMessage({
        protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
        type:'execute',
        request_id:requestId,
        transform_id:id,
        code:item.source.code,
        entrypoint:item.source.entrypoint,
        code_dependencies:item.source.dependencies || {},
        context:{
          inputs:inputValues,
          query_params:Object.fromEntries((item.spec.query_params || []).map(key => [key, window.dataviz.query_parameters?.[key]])),
          compute_params:Object.fromEntries(Object.entries(item.spec.compute_inputs || {}).map(([alias, key]) => [alias, window.dataviz.compute_parameters?.[key]])),
          selections:Object.fromEntries(Object.entries(item.spec.selection_inputs || {}).map(([alias, key]) => [alias, window.dataviz.selections?.[key]])),
        },
        python_dependencies:item.spec.python_dependencies || [],
        // Module Workers created from a Blob cannot resolve root-relative or
        // report-relative dynamic imports. Resolve against the Canvas document
        // before crossing the Worker boundary so Server and exported reports
        // follow the same URL contract.
        index_url:new URL(
          window.dataviz.runtime_versions?.pyodide_index_url,
          window.location.href,
        ).href,
        cancel_buffer:cancelBuffer,
      });
    });
  },
  async executeServerPython(id, item, options = {}) {
    const endpoint = window.dataviz.interaction;
    if (!endpoint) {
      throw datavizRuntimeError({
        code:'server_runtime_unavailable',
        message:item.spec.export?.reason || `Interactive Transform ${id} requires a running Dataviz server`,
        transform_id:id,
        runtime:'server-python',
      });
    }
    this.activeTransforms.get(id)?.cancel('Superseded by a newer generation');
    const abort = new AbortController();
    let interactionId = null;
    const controller = {
      cancel:reason => {
        abort.abort(reason);
        if (interactionId) fetch(
          `${endpoint.status_url.replace('{interaction_id}', encodeURIComponent(interactionId))}?session_id=${encodeURIComponent(endpoint.session_id)}`,
          {method:'DELETE', cache:'no-store'},
        ).catch(() => {});
      },
    };
    this.activeTransforms.set(id, controller);
    try {
      const started = await fetch(endpoint.start_url, {
        method:'POST',
        cache:'no-store',
        signal:abort.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          session_id:endpoint.session_id,
          transform_id:id,
          generation:options.generation,
          compute_parameters:window.dataviz.compute_parameters || {},
          selections:window.dataviz.selections || {},
        }),
      });
      if (!started.ok) throw new Error(`Server Compute request failed (${started.status}): ${await started.text()}`);
      const startPayload = await started.json();
      interactionId = startPayload.interaction_id;
      const statusUrl = endpoint.status_url.replace('{interaction_id}', encodeURIComponent(interactionId));
      let payload;
      let eventCursor = 0;
      while (!payload?.result) {
        await new Promise(resolve => setTimeout(resolve, 60));
        const response = await fetch(
          `${statusUrl}?session_id=${encodeURIComponent(endpoint.session_id)}`,
          {cache:'no-store', signal:abort.signal},
        );
        if (!response.ok) throw new Error(`Server Compute status failed (${response.status})`);
        payload = await response.json();
        const eventOffset = Number(payload.event_offset || 0);
        const retainedEvents = payload.events || [];
        const eventStart = Math.max(0, eventCursor - eventOffset);
        retainedEvents.slice(eventStart).forEach(item => {
          if (item.event !== 'node_progress') return;
          window.dispatchEvent(new CustomEvent('dataviz:interactionprogress', {
            detail:{
              transformId:id,
              generation:payload.generation,
              value:item.value,
              message:item.message,
            },
          }));
        });
        eventCursor = eventOffset + retainedEvents.length;
        if (['error', 'cancelled', 'unavailable'].includes(payload.status)) {
          throw datavizRuntimeError(payload.error || payload.result?.nodes?.[`interactive:${id}`]?.error || {
            code:`server_interaction_${payload.status}`,
            message:`Server Compute ${id} ${payload.status}`,
          });
        }
      }
      const bundle = {};
      for (const name of Object.keys(item.spec.outputs || {})) {
        const reference = `interactive:${id}/${name}`;
        const encoded = reference.split('/').map(encodeURIComponent).join('/');
        const outputUrl = endpoint.outputs_url
          .replace('{interaction_id}', encodeURIComponent(interactionId));
        const response = await fetch(
          `${outputUrl}/${encoded}?session_id=${encodeURIComponent(endpoint.session_id)}`,
          {cache:'no-store', signal:abort.signal},
        );
        if (!response.ok) throw new Error(`Interactive Output ${reference} is unavailable (${response.status})`);
        const output = await response.json();
        bundle[name] = output.transport
          ? await datavizLoadTransport(output.transport)
          : output.value;
      }
      return bundle;
    } finally {
      if (this.activeTransforms.get(id) === controller) this.activeTransforms.delete(id);
    }
  },
  transformCacheKey(id, item, inputValues) {
    return JSON.stringify({
      id,
      runtime:item.spec.runtime,
      code:item.source.code,
      entrypoint:item.source.entrypoint,
      code_dependencies:item.source.dependencies || {},
      python_dependencies:item.spec.python_dependencies || [],
      runtime_versions:window.dataviz.runtime_versions || {},
      inputs:Object.fromEntries(
        Object.entries(inputValues).map(([name, value]) => [name, datavizValueSignature(value)])
      ),
      query_params:Object.fromEntries((item.spec.query_params || []).map(key => [key, window.dataviz.query_parameters?.[key]])),
      compute_params:Object.fromEntries(Object.entries(item.spec.compute_inputs || {}).map(([alias, key]) => [alias, window.dataviz.compute_parameters?.[key]])),
      selections:Object.fromEntries(Object.entries(item.spec.selection_inputs || {}).map(([alias, key]) => [alias, window.dataviz.selections?.[key]])),
    });
  },
  async executeTransform(id, item, inputValues, generation) {
    const key = this.transformCacheKey(id, item, inputValues);
    if (item.spec.cache?.mode !== 'none' && this.interactionCache.has(key)) {
      this.metrics.interactiveTransforms.cacheHits += 1;
      return datavizCacheClone(this.interactionCache.get(key));
    }
    const adapter = this.interactiveAdapters[item.spec.runtime];
    if (!adapter) throw new Error(`Unsupported Interactive Runtime: ${item.spec.runtime}`);
    adapter.validate(item);
    const prepared = await adapter.prepare(item, inputValues);
    const value = await adapter.execute(id, item, prepared, {generation});
    if (item.spec.cache?.mode !== 'none') this.interactionCache.set(key, datavizCacheClone(value));
    return value;
  },
  markTransformStale(id) {
    document.querySelectorAll('.dv-view').forEach(root => {
      const view = this.views.get(root.dataset.viewId);
      if (!view) return;
      if (Object.values(view.inputs || {}).some(reference => canonicalOutputReference(reference).startsWith(`interactive:${id}/`))) {
        this.viewAdapter?.setStatus(root, 'stale', 'run analysis');
      }
    });
    this.publishTransformStatus(id, 'stale', {message:'Inputs changed; run analysis'});
  },
  markTransformLoading(id, message = 'running analysis') {
    document.querySelectorAll('.dv-view').forEach(root => {
      const view = this.views.get(root.dataset.viewId);
      if (!view) return;
      if (Object.values(view.inputs || {}).some(reference => canonicalOutputReference(reference).startsWith(`interactive:${id}/`))) {
        this.viewAdapter?.setStatus(root, 'loading', message);
      }
    });
    this.publishTransformStatus(id, 'loading', {message});
  },
  markTransformReady(id) {
    document.querySelectorAll('.dv-view').forEach(root => {
      const viewId = root.dataset.viewId;
      const view = this.views.get(viewId);
      if (!view) return;
      if (Object.values(view.inputs || {}).some(reference => canonicalOutputReference(reference).startsWith(`interactive:${id}/`))) {
        const renderer = this.viewAdapter?.states.get(viewId)?.type || 'ready';
        this.viewAdapter?.setStatus(root, 'ready', renderer);
      }
    });
    this.publishTransformStatus(id, 'ready');
  },
  publishTransformStatus(id, status, details = {}) {
    datavizPostToParent({
      type:'dataviz:interactive-status',
      node_id:`interactive:${id}`,
      transform_id:id,
      status,
      message:details.message || null,
      error:details.error ? {
        code:details.error.code || details.error.details?.code || 'interactive_transform_error',
        message:details.error.message || String(details.error),
      } : null,
    });
  },
  async runTransforms(changedSelectionKeys = [], seedChangedOutputs = [], options = {}) {
    const outputs = window.dataviz.portable?.outputs || {};
    const changedSelections = changedSelectionKeys == null ? null : new Set(changedSelectionKeys);
    const changedCompute = options.changedComputeKeys === null
      ? null
      : new Set(options.changedComputeKeys || []);
    const changedOutputs = new Set(seedChangedOutputs);
    const staleOutputs = new Set();
    const manualClosure = new Set(options.manualTargets || []);
    const order = this.transformOrder();
    const targetClosure = options.targets == null ? null : new Set(options.targets);
    if (targetClosure) {
      const addDependencies = id => {
        Object.values(this.transforms.get(id)?.spec.inputs || {}).forEach(reference => {
          const canonical = canonicalOutputReference(reference);
          if (!canonical.startsWith('interactive:')) return;
          const dependency = canonical.slice('interactive:'.length).split('/')[0];
          if (targetClosure.has(dependency)) return;
          targetClosure.add(dependency);
          addDependencies(dependency);
        });
      };
      [...targetClosure].forEach(addDependencies);
    }
    // A manual target means "run this dependency closure", not only the leaf.
    for (let index = order.length - 1; index >= 0; index -= 1) {
      const id = order[index];
      if (!manualClosure.has(id)) continue;
      Object.values(this.transforms.get(id)?.spec.inputs || {}).forEach(reference => {
        const canonical = canonicalOutputReference(reference);
        if (canonical.startsWith('interactive:')) {
          manualClosure.add(canonical.slice('interactive:'.length).split('/')[0]);
        }
      });
    }
    const tasks = new Map();
    const renderOutputDelta = references => {
      if (!references.size) return;
      const affectedViewIds = this.affectedViews([], references);
      if (affectedViewIds?.length) {
        this.renderViews({initial:false, changedSelectionKeys:[], affectedViewIds});
      }
    };
    for (const id of order) {
      if (targetClosure && !targetClosure.has(id)) continue;
      const item = this.transforms.get(id);
      const {spec} = item;
      const references = Object.fromEntries(
        Object.entries(spec.inputs || {}).map(([name, reference]) => [name, canonicalOutputReference(reference)])
      );
      const dependencyIds = Object.values(references)
        .filter(reference => reference.startsWith('interactive:'))
        .map(reference => reference.slice('interactive:'.length).split('/')[0]);
      const task = (async () => {
        await Promise.all(dependencyIds.map(dependency => tasks.get(dependency)).filter(Boolean));
        const declared = Object.keys(spec.outputs || {});
        const outputReferences = declared.map(name => `interactive:${id}/${name}`);
        const requiredOutputReferences = declared
          .filter(name => spec.outputs?.[name]?.required !== false)
          .map(name => `interactive:${id}/${name}`);
        const upstreamChanged = Object.values(references).some(reference => changedOutputs.has(reference));
        const upstreamStale = Object.values(references).some(reference => staleOutputs.has(reference));
        const selectionChanged = changedSelections == null
          || Object.values(spec.selection_inputs || {}).some(key => changedSelections.has(key));
        const computeChanged = changedCompute == null
          || Object.values(spec.compute_inputs || {}).some(key => changedCompute.has(key));
        const missingOutput = requiredOutputReferences.some(reference =>
          !Object.prototype.hasOwnProperty.call(outputs, reference)
        );
        const relevant = upstreamChanged || upstreamStale || selectionChanged || computeChanged
          || manualClosure.has(id);
        if (!relevant && !missingOutput) return;
        // Missing Derived Output starts a branch once. An unrelated Source may
        // publish while that branch is still running; it must not supersede the
        // active generation merely because its result has not arrived yet.
        if (!relevant && missingOutput && this.activeTransforms.has(id)) return;
        const snapshotted = window.dataviz.asset_mode === 'inline'
          && (window.dataviz.snapshot_interactions || []).includes(id)
          && !missingOutput;
        if (snapshotted) return;
        const request = (this.transformRequests.get(id) || 0) + 1;
        this.transformRequests.set(id, request);
        if (window.dataviz.asset_mode === 'inline' && spec.export?.mode === 'unavailable') {
          this.interactiveAdapters[spec.runtime]?.cancel(id);
          const error = datavizRuntimeError({
            code:'export_runtime_unavailable',
            message:spec.export.reason || `${spec.runtime} is unavailable in this exported report`,
            transform_id:id,
            runtime:spec.runtime,
          });
          const localChanged = new Set();
          this.transformErrors.set(id, error);
          outputReferences.forEach(reference => {
            delete outputs[reference];
            this.outputSignatures.delete(reference);
            this.outputErrors.set(reference, error);
            changedOutputs.add(reference);
            localChanged.add(reference);
          });
          renderOutputDelta(localChanged);
          this.publishTransformStatus(id, 'unavailable', {message:error.message, error});
          return;
        }
        const shouldExecute = manualClosure.has(id)
          // A newly loaded Query Run has no Derived Output yet. That initial
          // absence is itself a reason to execute an auto branch, even when a
          // parent-frame state sync carries an empty Selection/Compute delta.
          || (spec.trigger === 'auto' && (relevant || missingOutput))
          || (spec.trigger === 'apply' && (options.apply === true || missingOutput));
        if (upstreamStale || !shouldExecute) {
          if (relevant) {
            this.interactiveAdapters[spec.runtime]?.cancel(id);
            this.markTransformStale(id);
            outputReferences.forEach(reference => staleOutputs.add(reference));
          }
          return;
        }
        try {
          if (spec.trigger === 'auto' && relevant && Number(spec.debounce_ms || 0) > 0) {
            await new Promise(resolve => setTimeout(resolve, Number(spec.debounce_ms)));
            if (this.transformRequests.get(id) !== request) return;
          }
          const failedInput = Object.values(references).find(reference => {
            if (this.outputErrors.has(reference)) return true;
            if (!reference.startsWith('interactive:')) return false;
            return this.transformErrors.has(reference.slice('interactive:'.length).split('/')[0]);
          });
          if (failedInput) {
            throw this.outputErrors.get(failedInput)
              || new Error(`Upstream Output failed: ${failedInput}`);
          }
          const missingInput = Object.values(references).find(reference =>
            !Object.prototype.hasOwnProperty.call(outputs, reference)
          );
          if (missingInput) {
            this.publishTransformStatus(id, 'queued', {message:`Waiting for ${missingInput}`});
            return;
          }
          // The interaction endpoint belongs to the Query Run, not to its final
          // status. Wait only until an immutable Query snapshot exists; then a
          // ready branch can compute while unrelated Query branches continue.
          if (
            spec.runtime === 'server-python'
            && window.dataviz.interaction?.query_snapshot_available === false
          ) return;
          this.markTransformLoading(id);
          const inputValues = Object.fromEntries(
            Object.entries(references).map(([name, reference]) => [name, outputs[reference]])
          );
          Object.entries(spec.input_schemas || {}).forEach(([name, schema]) => {
            if (!(name in inputValues)) {
              throw datavizContractError(
                'interactive_input_schema_unknown',
                `Interactive Transform ${id} declares a schema for missing input ${name}`,
                {transform_id:id, input:name},
              );
            }
            validateInteractiveTable(
              id,
              `Interactive Transform ${id} input ${name}`,
              inputValues[name],
              schema,
              'interactive_input_schema_mismatch',
              'interactive_input_kind_mismatch',
            );
          });
          const bundle = await this.executeTransform(id, item, inputValues, request);
          if (this.transformRequests.get(id) !== request) return;
          if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
            throw new Error(`Interactive Transform ${id} must return a Named Output object`);
          }
          const missing = declared.filter(name => spec.outputs?.[name]?.required !== false && !(name in bundle));
          const unknown = Object.keys(bundle).filter(name => !declared.includes(name));
          if (missing.length || unknown.length) {
            throw datavizContractError(
              'interactive_output_contract_mismatch',
              `Interactive Transform ${id} output mismatch; missing=${missing.join(',')} unknown=${unknown.join(',')}`,
              {transform_id:id, missing, unknown},
            );
          }
          const localChanged = new Set();
          declared.filter(name => spec.outputs?.[name]?.required === false && !(name in bundle)).forEach(name => {
            const reference = `interactive:${id}/${name}`;
            if (!Object.prototype.hasOwnProperty.call(outputs, reference)) return;
            delete outputs[reference];
            this.outputSignatures.delete(reference);
            this.outputErrors.delete(reference);
            changedOutputs.add(reference);
            localChanged.add(reference);
          });
          Object.entries(bundle).forEach(([name, output]) => {
            validateInteractiveOutput(id, name, output, spec.outputs?.[name]);
            const reference = `interactive:${id}/${name}`;
            const signature = datavizValueSignature(output);
            if (this.outputSignatures.get(reference) !== signature) {
              outputs[reference] = output;
              this.outputErrors.delete(reference);
              this.outputSignatures.set(reference, signature);
              changedOutputs.add(reference);
              localChanged.add(reference);
            }
          });
          this.transformErrors.delete(id);
          if (localChanged.size) {
            renderOutputDelta(localChanged);
            this.publishTransformStatus(id, 'ready');
          } else {
            this.markTransformReady(id);
          }
        } catch (error) {
          if (this.transformRequests.get(id) !== request) return;
          if (error?.name === 'AbortError' || error?.code === 'interactive_transform_cancelled') {
            this.publishTransformStatus(id, 'cancelled', {message:error.message, error});
            return;
          }
          this.metrics.interactiveTransforms.failed += 1;
          this.transformErrors.set(id, error);
          const localChanged = new Set();
          outputReferences.forEach(reference => {
            delete outputs[reference];
            this.outputSignatures.delete(reference);
            this.outputErrors.set(reference, error);
            changedOutputs.add(reference);
            localChanged.add(reference);
          });
          renderOutputDelta(localChanged);
          this.publishTransformStatus(id, 'error', {message:error.message, error});
          console.error(`[dataviz:interactive-transform:${id}]`, error);
        }
      })();
      tasks.set(id, task);
    }
    await Promise.all(tasks.values());
    return changedOutputs;
  },
  affectedViews(changedSelectionKeys, changedOutputs = new Set()) {
    // A null Selection delta is the first render, not an empty update. Render
    // every registered host so input-free Markdown/Image Views become ready and
    // data-backed Views can enter their branch-local waiting state.
    if (changedSelectionKeys == null) return null;
    const changedSelections = new Set(changedSelectionKeys || []);
    const outputs = changedOutputs || new Set();
    const affected = new Set(
      Object.entries(window.dataviz.portable?.selection_contract || {})
        .filter(([viewId, contract]) => contract.some(item => (
          changedSelections.has(item.key) && datavizSelectionAffectsView(viewId, item)
        )))
        .map(([viewId]) => viewId)
    );
    this.views.forEach((definition, id) => {
      if (Object.values(definition.inputs).some(reference => outputs.has(canonicalOutputReference(reference)))) affected.add(id);
    });
    return [...affected];
  },
  renderViews(context) {
    const affected = context.affectedViewIds == null ? null : new Set(context.affectedViewIds);
    this.views.forEach((definition, id) => {
      if (affected && !affected.has(id)) return;
      const references = Object.values(definition.inputs).map(canonicalOutputReference);
      const failedReference = references.find(reference => {
        if (this.outputErrors.has(reference)) return true;
        const canonical = canonicalOutputReference(reference);
        return canonical.startsWith('interactive:') && this.transformErrors.has(canonical.slice('interactive:'.length).split('/')[0]);
      });
      if (failedReference) {
        const canonical = canonicalOutputReference(failedReference);
        const transformId = canonical.startsWith('interactive:') ? canonical.slice('interactive:'.length).split('/')[0] : null;
        const failure = this.outputErrors.get(canonical) || this.transformErrors.get(transformId);
        const failureCode = String(failure?.code || failure?.details?.code || '').toLocaleLowerCase();
        if (failureCode.includes('cancel')) {
          this.viewAdapter?.cancelled(
            this.viewAdapter.node(id),
            id,
            failure?.message || `Computation cancelled: ${canonical}`,
          );
          return;
        }
        if (failureCode.includes('unavailable')) {
          this.viewAdapter?.unavailable(
            this.viewAdapter.node(id),
            id,
            failure?.message || `Runtime unavailable: ${canonical}`,
          );
          return;
        }
        this.viewAdapter?.renderInto(this.viewAdapter.node(id), id, () => {
          throw failure || new Error(`Output failed: ${canonical}`);
        });
        return;
      }
      const missingReference = references.find(reference =>
        !Object.prototype.hasOwnProperty.call(window.dataviz.portable?.outputs || {}, reference)
      );
      if (missingReference) {
        this.viewAdapter?.waiting(
          this.viewAdapter.node(id),
          id,
          `Waiting for ${missingReference}`,
        );
        return;
      }
      definition.render(window.dataviz, context);
    });
  },
  async publishOutputs(bundle) {
    const outputs = window.dataviz.portable?.outputs || {};
    const changed = new Set();
    Object.entries(bundle.outputs || {}).forEach(([rawReference, value]) => {
      const reference = canonicalOutputReference(rawReference);
      const signature = datavizValueSignature(value);
      if (this.outputSignatures.get(reference) === signature) return;
      outputs[reference] = value;
      this.outputSignatures.set(reference, signature);
      this.outputErrors.delete(reference);
      changed.add(reference);
    });
    Object.assign(window.dataviz.portable.output_kinds, bundle.output_kinds || {});
    if (!changed.size || this.initializing) return changed;
    refreshCascadingSelections();
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({initial:false, changedSelectionKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed, {changedComputeKeys: []});
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[]},
    }));
    return changedOutputs;
  },
  collectSnapshotOutputs() {
    const outputs = window.dataviz.portable?.outputs || {};
    const values = {};
    const missing = [];
    this.transforms.forEach((item, id) => {
      if (item.spec.export?.mode !== 'snapshot' || item.spec.runtime === 'server-python') return;
      Object.entries(item.spec.outputs || {}).forEach(([name, definition]) => {
        const reference = `interactive:${id}/${name}`;
        if (!Object.prototype.hasOwnProperty.call(outputs, reference)) {
          if (definition.required !== false) missing.push(reference);
          return;
        }
        values[reference] = datavizSnapshotValue(outputs[reference]);
      });
    });
    return {outputs:values, missing};
  },
  async failOutputs(references, error) {
    const outputs = window.dataviz.portable?.outputs || {};
    const changed = new Set();
    (references || []).forEach(rawReference => {
      const reference = canonicalOutputReference(rawReference);
      delete outputs[reference];
      this.outputSignatures.delete(reference);
      this.outputErrors.set(reference, error || new Error(`Output failed: ${reference}`));
      changed.add(reference);
    });
    if (this.initializing) return changed;
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({initial:false, changedSelectionKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed, {changedComputeKeys: []});
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
    return changedOutputs;
  },
  registerOutputTransport(reference, descriptor) {
    const canonical = canonicalOutputReference(reference);
    window.dataviz.portable.output_transports[canonical] = descriptor;
    return canonical;
  },
  hydrateOutput(reference) {
    const canonical = canonicalOutputReference(reference);
    if (Object.prototype.hasOwnProperty.call(window.dataviz.portable.outputs, canonical)) {
      return Promise.resolve(window.dataviz.portable.outputs[canonical]);
    }
    if (this.transportPromises.has(canonical)) return this.transportPromises.get(canonical);
    const descriptor = window.dataviz.portable.output_transports?.[canonical];
    if (!descriptor) return Promise.resolve(undefined);
    this.metrics.transports.started += 1;
    const startedAt = performance.now();
    const pending = datavizLoadTransport(descriptor)
      .then(async value => {
        this.metrics.transports.completed += 1;
        this.metrics.transports.arrowRows += Number(descriptor.row_count || 0);
        this.metrics.transports.arrowBytes += Number(value?.bytes?.byteLength || descriptor.byte_count || 0);
        this.metrics.transports.totalMs += performance.now() - startedAt;
        await this.publishOutputs({
          outputs:{[canonical]:value},
          output_kinds:{[canonical]:'table'},
        });
        return value;
      })
      .catch(async error => {
        this.transportPromises.delete(canonical);
        this.metrics.transports.failed += 1;
        this.metrics.transports.totalMs += performance.now() - startedAt;
        await this.failOutputs([canonical], datavizRuntimeError({
          code:'output_transport_failed',
          message:error?.message || String(error),
          stack:error?.stack || null,
          reference:canonical,
        }));
        throw error;
      });
    this.transportPromises.set(canonical, pending);
    return pending;
  },
  hydrateOutputTransports() {
    const references = Object.keys(window.dataviz.portable?.output_transports || {});
    return Promise.allSettled(references.map(reference => this.hydrateOutput(reference)));
  },
  initializePortable() {
    if (this.initializationPromise) return this.initializationPromise;
    this.initializationPromise = (async () => {
      // Establish the immutable Base Output snapshot before reconciling dynamic
      // Selection domains. Hydration may publish Arrow tables, but no View or
      // Interactive branch is allowed to observe a half-initialized Control state.
      this.initializing = true;
      try {
        await this.hydrateOutputTransports();
      } finally {
        this.initializing = false;
      }
      await window.dataviz.applySelections();
      // Canvas ready is a lifecycle contract, not a script-load notification.
      // The parent may restore tab-local Controls only after Base Outputs,
      // dynamic option domains and the first canonical Selection snapshot agree.
      datavizPostToParent({
        type:'dataviz:canvas-ready',
        selections:structuredClone(window.dataviz.selections || {}),
      });
    })();
    return this.initializationPromise;
  },
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.cancelTransforms('Runtime disposed');
    this.sectionAdapter?.dispose();
    this.viewAdapter?.dispose();
    this.presentationAdapter?.dispose();
    this.workerUrls.forEach(url => URL.revokeObjectURL(url));
    this.workerUrls.clear();
    this.interactionCache.clear();
    Object.values(this.interactiveAdapters).forEach(adapter => adapter.dispose());
  },
};

window.addEventListener('dataviz:interactionprogress', event => {
  const detail = event.detail || {};
  const percent = Number.isFinite(Number(detail.value))
    ? ` · ${Math.round(Number(detail.value) * 100)}%`
    : '';
  datavizRuntime.markTransformLoading(
    detail.transformId,
    `${detail.message || 'running analysis'}${percent}`,
  );
});

const DATAVIZ_OWNER_PACKAGE_RUNTIME = true;
const datavizSelectionRank = {dashboard: 0, section: 1, view: 2};
const datavizSelectionFields = item => {
  const pathFields = item.definition?.path_fields || [];
  return pathFields.length ? pathFields : [item.binding?.field || item.id];
};
const datavizSelectionCanApply = (row, item) => (
  row != null
  && typeof row === 'object'
  && datavizSelectionFields(item).every(field => Object.prototype.hasOwnProperty.call(row, field))
);
const datavizRowsForView = viewId => Object.values(
  window.dataviz.portable?.view_inputs?.[viewId] || {}
).flatMap(reference => {
  return datavizTableRows(window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)]);
});
const datavizSelectionDomainReferences = item => (
  window.dataviz.portable?.selection_option_domains?.[item?.key] || []
).map(canonicalOutputReference);
const datavizSelectionAffectsView = (viewId, item) => {
  const rows = datavizRowsForView(viewId);
  // Empty or not-yet-loaded outputs are handled conservatively. Once a table
  // exists, an implicit Selection binding only affects it when the field is
  // actually part of that table's row contract.
  return rows.length === 0 || rows.some(row => datavizSelectionCanApply(row, item));
};
const datavizSelectionMatches = (row, item, value) => {
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return true;
  // Dashboard and Section selections are inherited structurally. A View whose
  // dataset does not expose the selected field is outside that data contract;
  // it must remain visible instead of being reduced to an accidental empty set.
  if (!datavizSelectionCanApply(row, item)) return true;
  const pathFields = item.definition?.path_fields || [];
  if (pathFields.length) {
    const paths = Array.isArray(value?.[0]) ? value : [value];
    const matched = paths.some(path => pathFields.every((field, index) => String(row[field] ?? '') === String(path[index] ?? '')));
    return matched;
  }
  const field = item.binding?.field || item.id;
  const actual = row[field];
  const operator = item.binding?.operator === 'auto'
    ? (item.definition?.type === 'multi_select' ? 'in' : item.definition?.type === 'date_range' ? 'between' : 'equals')
    : item.binding?.operator;
  let matched;
  if (operator === 'in') matched = (Array.isArray(value) ? value : [value]).map(String).includes(String(actual));
  else if (operator === 'between') {
    const range = Array.isArray(value) ? value : [];
    const start = range[0];
    const end = range[1];
    matched = (!start || String(actual) >= String(start))
      && (!end || String(actual) <= String(end));
  }
  else if (operator === 'contains') matched = String(actual ?? '').includes(String(value ?? ''));
  else if (operator === 'gte') matched = Number(actual) >= Number(value);
  else if (operator === 'lte') matched = Number(actual) <= Number(value);
  else if (operator === 'gt') matched = Number(actual) > Number(value);
  else if (operator === 'lt') matched = Number(actual) < Number(value);
  else matched = String(actual ?? '') === String(value ?? '');
  return matched;
};
window.dataviz.selection = {
  fields: datavizSelectionFields,
  canApply: datavizSelectionCanApply,
  matches: datavizSelectionMatches,
};
if (window.datavizComponents?.selectors) {
  window.datavizComponents.selectorPathOptions = ({selector, input, levels}) => {
    const viewId = selector.dataset.cascaderView;
    const selectionKey = selector.closest('[data-selection-key]')?.dataset.selectionKey;
    if (!viewId || !levels?.length) {
      return Array.from(input.options).map(option => {
        try { return JSON.parse(option.value); } catch (_error) { return [option.value]; }
      });
    }
    const contract = window.dataviz.portable?.selection_contract?.[viewId] || [];
    const otherSelections = contract.filter(item => item.key !== selectionKey);
    const item = contract.find(candidate => candidate.key === selectionKey);
    const rows = datavizSelectionDomainReferences(item).flatMap(reference =>
      datavizTableRows(window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)])
    ).filter(row => otherSelections.every(item =>
      datavizSelectionMatches(row, item, window.dataviz.selections[item.key])
    ));
    const unique = new Map();
    rows.forEach(row => {
      const path = levels.map(level => row[level.field]);
      if (path.some(value => value == null)) return;
      unique.set(JSON.stringify(path), path);
    });
    return [...unique.values()];
  };
}
const datavizCascadeOccurrences = () => {
  const occurrences = new Map();
  Object.entries(window.dataviz.portable?.selection_contract || {}).forEach(([viewId, contract]) => {
    contract.forEach(item => {
      if (!occurrences.has(item.key)) occurrences.set(item.key, []);
      occurrences.get(item.key).push({viewId, item});
    });
  });
  return occurrences;
};
const datavizAvailableSelectionOptions = targets => {
  const item = targets[0]?.item;
  const definition = item?.definition || {};
  const targetRank = datavizSelectionRank[item?.origin] ?? 99;
  const values = new Map();
  let observedSource = false;
  targets.forEach(({viewId, item: target}) => {
    const outputRefs = datavizSelectionDomainReferences(target);
    const upstream = (window.dataviz.portable?.selection_contract?.[viewId] || []).filter(candidate =>
      (datavizSelectionRank[candidate.origin] ?? 99) < targetRank
    );
    outputRefs.forEach(reference => {
      const canonical = canonicalOutputReference(reference);
      const rows = datavizTableRows(window.dataviz.portable?.outputs?.[canonical]);
      // Progressive query branches may publish in any order. An unrelated
      // table being present does not mean it can define this Selection's
      // option domain; otherwise a fast sibling branch can clear valid choices
      // before the actual field-bearing branch arrives.
      if (rows.some(row => datavizSelectionCanApply(row, target))) {
        observedSource = true;
      }
      rows.forEach(row => {
        if (!upstream.every(candidate =>
          datavizSelectionMatches(row, candidate, window.dataviz.selections[candidate.key])
        )) return;
        const value = (definition.path_fields || []).length
          ? definition.path_fields.map(field => row[field])
          : row[target.binding?.field || target.id];
        if (value == null || (Array.isArray(value) && value.some(part => part == null))) return;
        values.set(datavizValueSignature(value), value);
      });
    });
  });
  const staticChoices = definition.choices || [];
  const options = staticChoices.length
    ? staticChoices.map(choice => ({
      value:choice.value,
      label:choice.label,
      group:choice.group || null,
      description:choice.description || '',
      keywords:choice.keywords || [],
      available:definition.cascade === false || values.has(datavizValueSignature(choice.value)),
    }))
    : [...values.values()]
      .sort((left, right) => String(left).localeCompare(String(right)))
      .map(value => ({
        value,
        label:Array.isArray(value) ? value.join(' / ') : String(value),
        available:true,
      }));
  return {observed:observedSource, options};
};
const publishDashboardSelectionOptions = occurrences => {
  if (window.parent === window) return;
  const controls = [];
  occurrences.forEach((targets, key) => {
    if (targets[0]?.item?.origin !== 'dashboard') return;
    controls.push({key, ...datavizAvailableSelectionOptions(targets)});
  });
  datavizPostToParent({type:'dataviz:selection-options-changed', controls});
};
const refreshCascadingSelections = () => {
  const occurrences = datavizCascadeOccurrences();
  const controls = Array.from(document.querySelectorAll('[data-selection-key]'));
  [0, 1, 2].forEach(rank => {
    controls.forEach(control => {
      const targets = occurrences.get(control.dataset.selectionKey) || [];
      const targetRank = datavizSelectionRank[targets[0]?.item?.origin];
      if (!targets.length || targetRank !== rank) return;
      const input = control.querySelector('select');
      if (!input) return;
      const definition = targets[0]?.item?.definition || {};
      if (definition.type === 'boolean') {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      const availability = datavizAvailableSelectionOptions(targets);
      if (control.querySelector('[data-selector-template="cascader"], [data-selector-template="tree-select"]')) {
        control.dataset.optionDomainState = availability.observed ? 'ready' : 'pending';
        syncPortableChoices(control);
        return;
      }
      if (definition.cascade === false && definition.choices?.length) {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      if (!availability.observed) {
        control.dataset.optionDomainState = 'pending';
        syncPortableChoices(control);
        return;
      }
      control.dataset.optionDomainState = 'ready';
      const typed = availability.options.some(option => typeof option.value !== 'string');
      input.dataset.valueEncoding = typed ? 'json' : 'string';
      const currentValue = window.dataviz.selections[control.dataset.selectionKey];
      const currentValues = input.multiple
        ? (Array.isArray(currentValue) ? currentValue : [])
        : [currentValue];
      const selected = new Set(
        currentValues
          .filter(value => !datavizIsEmptyControlValue(value))
          .map(datavizValueSignature)
      );
      const options = [];
      if (!input.multiple && control.querySelector('[data-empty-means-all="true"]')) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.hidden = true;
        empty.dataset.emptyOption = 'true';
        empty.selected = datavizIsEmptyControlValue(currentValue);
        options.push(empty);
      }
      availability.options.forEach(item => {
        const option = document.createElement('option');
        option.value = datavizEncodeControlValue(input, item.value, {
          path:control.dataset.selectionPath === 'true',
        });
        option.textContent = item.label ?? String(item.value);
        option.disabled = item.available === false;
        option.selected = !option.disabled && selected.has(datavizValueSignature(item.value));
        if (item.group) option.dataset.group = item.group;
        if (item.description) option.dataset.description = item.description;
        if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
        options.push(option);
      });
      if (definition.required && !options.some(option => option.selected && !option.disabled)) {
        const fallback = options.find(option => option.dataset.emptyOption !== 'true' && !option.disabled);
        if (fallback) fallback.selected = true;
      }
      input.replaceChildren(...options);
      control.dataset.cascadeAvailable = String(
        availability.options.filter(option => option.available !== false).length
      );
      syncPortableChoices(control);
    });
    // Commit each scope before deriving the next one. A Dashboard change can
    // invalidate Section values, which must be visible to View selectors in
    // this same interaction rather than one event later.
    readSelectionInputs({maxRank:rank});
  });
  publishDashboardSelectionOptions(occurrences);
};
const readSelectionInputs = ({maxRank = null} = {}) => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    const type = control.dataset.selectionType;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const item = Object.values(window.dataviz.portable?.selection_contract || {})
      .flat()
      .find(candidate => candidate.key === key);
    if (maxRank != null && (datavizSelectionRank[item?.origin] ?? 99) > maxRank) return;
    const definition = item?.definition || {type};
    if (
      input.tagName === 'SELECT'
      && control.dataset.optionDomainState === 'pending'
      && Object.prototype.hasOwnProperty.call(window.dataviz.selections, key)
    ) return;
    const decode = raw => datavizDecodeControlValue(input, raw, {
      path:control.dataset.selectionPath === 'true',
    });
    let value;
    if (type === 'boolean' && input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (type === 'boolean') value = input.checked;
    else if (type === 'multi_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option => decode(option.value))
      : (window.dataviz.selections[key] || []);
    else if (type === 'number') value = input.value === '' ? null : Number(input.value);
    else if (type === 'integer') value = input.value === '' ? null : Number(input.value);
    else if (type === 'date_range') value = input.value
      ? input.value.split(',', 2).map(item => item.trim())
      : [];
    else if (input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else value = input.value;
    try {
      window.dataviz.selections[key] = datavizNormalizeControlValue(
        definition,
        value,
        {namespace:'selection', key},
      );
      input.setCustomValidity?.('');
    } catch (error) {
      input.setCustomValidity?.(error.message);
      throw error;
    }
  });
};
const datavizSelectionSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(datavizValueSignature).sort() : value
);
const datavizChangedSelectionKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizSelectionSignature(previous[key]) !== datavizSelectionSignature(current[key])
  );
};
const datavizContentBindings = window.dataviz.content_bindings || {};
const datavizContentAllLabel = () => (
  String(document.documentElement.lang || '').toLocaleLowerCase().startsWith('zh')
    ? '全部'
    : 'All'
);
const datavizContentControl = key => Array.from(
  document.querySelectorAll('[data-selection-key]')
).find(control => control.dataset.selectionKey === key) || null;
const datavizContentChoiceLabel = (reference, value, control = null) => {
  const input = control?.querySelector('[data-selection-input], [data-compute-input]');
  const option = Array.from(input?.options || []).find(candidate => (
    candidate.dataset.emptyOption !== 'true'
    && datavizValueSignature(datavizDecodeControlValue(input, candidate.value, {
      path:control?.dataset?.selectionPath === 'true',
    })) === datavizValueSignature(value)
  ));
  if (option) return option.textContent?.trim() || String(value);
  const choice = (reference.definition?.choices || []).find(candidate => (
    datavizValueSignature(candidate.value) === datavizValueSignature(value)
  ));
  return choice?.label ?? String(value);
};
const datavizContentPathValue = value => {
  if (typeof value !== 'string') return value;
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : value;
  } catch (_error) {
    return value;
  }
};
const datavizFormatContentReference = reference => {
  const definition = reference.definition || {};
  const isCompute = reference.kind === 'compute';
  const control = isCompute
    ? document.querySelector(`[data-compute-key="${CSS.escape(reference.key)}"]`)
    : datavizContentControl(reference.key);
  const value = isCompute
    ? (window.dataviz.compute_parameters?.[reference.key] ?? definition.default)
    : (window.dataviz.selections?.[reference.key] ?? definition.default);
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return isCompute ? '' : datavizContentAllLabel();
  }
  if (definition.type === 'date_range') {
    const range = Array.isArray(value) ? value : String(value).split(',', 2);
    return range.filter(item => item != null && item !== '').join(' 至 ');
  }
  if ((definition.path_fields || []).length) {
    const parsed = datavizContentPathValue(value);
    const paths = Array.isArray(parsed?.[0]) ? parsed : [parsed];
    const separator = control?.querySelector('.dv-selector')?.dataset.pathSeparator || ' / ';
    return paths
      .filter(path => Array.isArray(path))
      .map(path => path.map(String).join(separator))
      .join('、') || String(value);
  }
  const values = Array.isArray(value) ? value : [value];
  if (Array.isArray(value)) {
    const input = control?.querySelector('[data-selection-input], [data-compute-input]');
    const availableOptions = Array.from(input?.options || []).filter(option => (
      option.dataset.emptyOption !== 'true' && !option.disabled
    ));
    const available = availableOptions.map(option => datavizDecodeControlValue(input, option.value, {
      path:control?.dataset?.selectionPath === 'true',
    }));
    const choices = reference.definition?.choices || [];
    const universe = available.length
      ? available
      : choices.map(choice => choice.value);
    if (
      universe.length
      && values.length === universe.length
      && universe.every(item => values.some(
        valueItem => datavizValueSignature(valueItem) === datavizValueSignature(item)
      ))
    ) return datavizContentAllLabel();
  }
  return values.map(item => datavizContentChoiceLabel(reference, item, control)).join('、');
};
const datavizRenderContentBinding = binding => {
  let value = String(binding.template ?? '');
  (binding.references || []).forEach(reference => {
    const escaped = String(reference.expression).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    value = value.replace(
      new RegExp(`{{\\s*${escaped}\\s*}}`, 'g'),
      () => datavizFormatContentReference(reference),
    );
  });
  return value;
};
const syncDatavizContentBindings = changedSelectionKeys => {
  const changed = changedSelectionKeys == null ? null : new Set(changedSelectionKeys);
  const affectedViews = new Set();
  Object.entries(datavizContentBindings).forEach(([field, binding]) => {
    if (changed && !(binding.references || []).some(reference => changed.has(reference.key))) return;
    const value = datavizRenderContentBinding(binding);
    document.querySelectorAll('[data-dv-content-field]').forEach(node => {
      if (node.dataset.dvContentField === field && node.textContent !== value) node.textContent = value;
    });
    const target = binding.target || {};
    if (target.scope === 'dashboard' && target.property === 'title') document.title = value;
    if (target.scope !== 'view' || !target.owner_id) return;
    const view = (window.dataviz.view_specs || []).find(item => item.id === target.owner_id);
    if (view && ['title', 'description', 'text'].includes(target.property)) {
      view[target.property] = value;
    }
    if (['title', 'text'].includes(target.property)) affectedViews.add(target.owner_id);
  });
  return affectedViews;
};
window.dataviz.syncContentBindings = syncDatavizContentBindings;
const readComputeInputs = () => {
  const values = {...(window.dataviz.draft_compute_parameters || {})};
  document.querySelectorAll('[data-compute-key]').forEach(control => {
    const key = control.dataset.computeKey;
    const input = control.querySelector('[data-compute-input]');
    if (!input || input.disabled || control.dataset.computeFrozen === 'true') return;
    const type = input.dataset.computeType;
    const definition = window.dataviz.compute_definitions?.[key] || {type};
    const decode = raw => datavizDecodeControlValue(input, raw);
    if (type === 'date_range') {
      const range = [
        input.querySelector('[data-compute-range="start"]')?.value || '',
        input.querySelector('[data-compute-range="end"]')?.value || '',
      ];
      values[key] = range.some(Boolean) ? range : [];
    } else if (type === 'boolean') values[key] = Boolean(input.checked);
    else if (type === 'multi_select') values[key] = Array.from(input.selectedOptions).map(option => decode(option.value));
    else if (type === 'number') values[key] = input.value === '' ? null : Number(input.value);
    else if (type === 'integer') values[key] = input.value === '' ? null : Number(input.value);
    else if (input.tagName === 'SELECT') values[key] = input.value === '' ? null : decode(input.value);
    else values[key] = input.value;
    try {
      values[key] = datavizNormalizeControlValue(
        definition,
        values[key],
        {namespace:'compute_parameter', key},
      );
      input.setCustomValidity?.('');
    } catch (error) {
      input.setCustomValidity?.(error.message);
      throw error;
    }
  });
  window.dataviz.draft_compute_parameters = values;
  return values;
};
const datavizChangedComputeKeys = (previous, current) => {
  const keys = new Set([...Object.keys(previous || {}), ...Object.keys(current || {})]);
  return [...keys].filter(key => datavizValueSignature(previous?.[key]) !== datavizValueSignature(current?.[key]));
};
const syncComputeDirtyState = () => {
  const changed = datavizChangedComputeKeys(
    window.dataviz.compute_parameters || {},
    window.dataviz.draft_compute_parameters || {},
  );
  document.querySelectorAll('[data-compute-dirty-label]').forEach(node => {
    const button = node.parentElement?.querySelector('[data-compute-apply]');
    const scopeKeys = new Set(JSON.parse(button?.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size
      ? changed.filter(key => scopeKeys.has(key))
      : changed;
    node.textContent = localChanged.length
      ? `${localChanged.length} draft change${localChanged.length === 1 ? '' : 's'}`
      : 'Results are current';
  });
  document.querySelectorAll('[data-compute-apply]').forEach(button => {
    const scopeKeys = new Set(JSON.parse(button.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size
      ? changed.filter(key => scopeKeys.has(key))
      : changed;
    button.disabled = localChanged.length === 0 && button.dataset.analysisAlways !== 'true';
  });
  return changed;
};
const renderComputeResult = async (changedKeys, options = {}) => {
  const contentAffected = syncDatavizContentBindings(changedKeys);
  if (contentAffected.size) {
    datavizRuntime.renderViews({
      initial:false,
      changedSelectionKeys:[],
      changedComputeKeys:changedKeys,
      affectedViewIds:[...contentAffected],
    });
  }
  const changedOutputs = await datavizRuntime.runTransforms([], [], {
    changedComputeKeys:changedKeys,
    apply:options.apply === true,
    manualTargets:options.manualTargets || [],
  });
  window.dispatchEvent(new CustomEvent('dataviz:computechange', {
    detail:{
      compute_parameters:window.dataviz.compute_parameters,
      changed:changedKeys,
      outputs:[...changedOutputs],
    },
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:compute-changed',
      compute_parameters:window.dataviz.compute_parameters,
      draft_compute_parameters:window.dataviz.draft_compute_parameters,
    });
  }
};
window.dataviz.applyCompute = async (options = {}) => {
  const draft = readComputeInputs();
  const requested = options.keys || datavizChangedComputeKeys(window.dataviz.compute_parameters || {}, draft);
  const changed = requested.filter(key => datavizValueSignature(window.dataviz.compute_parameters?.[key]) !== datavizValueSignature(draft[key]));
  const committed = {...(window.dataviz.compute_parameters || {})};
  changed.forEach(key => { committed[key] = structuredClone(draft[key]); });
  window.dataviz.compute_parameters = committed;
  syncComputeDirtyState();
  await renderComputeResult(changed, options);
};
window.dataviz.applyControls = async (options = {}) => {
  const requestedKeys = options.keys || [];
  const draft = readComputeInputs();
  const computeKeys = requestedKeys.filter(key => Object.prototype.hasOwnProperty.call(draft, key));
  const selectionKeys = requestedKeys.filter(key => Object.prototype.hasOwnProperty.call(window.dataviz.selections || {}, key));
  const changedComputeKeys = computeKeys.filter(key => (
    datavizValueSignature(window.dataviz.compute_parameters?.[key])
    !== datavizValueSignature(draft[key])
  ));
  const committed = {...(window.dataviz.compute_parameters || {})};
  changedComputeKeys.forEach(key => { committed[key] = structuredClone(draft[key]); });
  window.dataviz.compute_parameters = committed;
  syncComputeDirtyState();
  const contentAffected = syncDatavizContentBindings(changedComputeKeys);
  if (contentAffected.size) {
    datavizRuntime.renderViews({
      initial:false,
      changedSelectionKeys:[],
      changedComputeKeys,
      affectedViewIds:[...contentAffected],
    });
  }
  const changedOutputs = await datavizRuntime.runTransforms(selectionKeys, [], {
    changedComputeKeys,
    apply:true,
    manualTargets:options.manualTargets || [],
  });
  window.dispatchEvent(new CustomEvent('dataviz:computechange', {
    detail:{
      compute_parameters:window.dataviz.compute_parameters,
      changed:changedComputeKeys,
      outputs:[...changedOutputs],
    },
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:compute-changed',
      compute_parameters:window.dataviz.compute_parameters,
      draft_compute_parameters:window.dataviz.draft_compute_parameters,
    });
  }
};
window.dataviz.applySelections = async () => {
  const previous = window.dataviz.appliedSelections || null;
  // On first paint the canonical values come from the validated Query/report
  // snapshot. Dynamic <select> elements are intentionally empty until their
  // immutable option domains are available, so reading the DOM first would erase
  // a valid required default and abort every unrelated View.
  if (previous != null) readSelectionInputs();
  refreshCascadingSelections();
  readSelectionInputs();
  const changedSelectionKeys = datavizChangedSelectionKeys(previous, window.dataviz.selections);
  let affectedViewIds = datavizRuntime.affectedViews(changedSelectionKeys, new Set());
  const contentAffectedViewIds = syncDatavizContentBindings(changedSelectionKeys);
  if (affectedViewIds != null) {
    affectedViewIds = [...new Set([...affectedViewIds, ...contentAffectedViewIds])];
  }
  window.dataviz.appliedSelections = JSON.parse(JSON.stringify(window.dataviz.selections));
  window.dataviz.renderContext = {
    initial: changedSelectionKeys == null,
    changedSelectionKeys: changedSelectionKeys || Object.keys(window.dataviz.selections),
    affectedViewIds,
  };
  if (changedSelectionKeys == null || changedSelectionKeys.length) {
    datavizRuntime.renderViews(window.dataviz.renderContext);
  }
  window.dispatchEvent(new CustomEvent('dataviz:selectionchange', {detail: window.dataviz.selections}));
  if (window.parent !== window) {
    datavizPostToParent({type: 'dataviz:selections-changed', selections: window.dataviz.selections});
  }
  await datavizRuntime.runTransforms(changedSelectionKeys, [], {
    changedComputeKeys: previous == null ? null : [],
  });
};
window.dataviz.connectLive = () => {
  const live = window.dataviz.live;
  if (!live || window.dataviz.liveSource) return;
  const source = new EventSource(live.events_url);
  const fetched = new Map();
  const fetchOutput = async reference => {
    const previous = fetched.get(reference);
    if (previous) return previous;
    const encoded = reference.split('/').map(encodeURIComponent).join('/');
    const promise = fetch(`${live.outputs_url}/${encoded}?session_id=${encodeURIComponent(live.session_id)}`)
      .then(async response => {
        if (!response.ok) throw new Error(`Output ${reference} is unavailable (${response.status})`);
        return response.json();
      })
      .then(payload => {
        if (payload.transport) {
          datavizRuntime.registerOutputTransport(payload.reference, payload.transport);
          return datavizRuntime.hydrateOutput(payload.reference);
        }
        return datavizRuntime.publishOutputs({
          outputs: {[payload.reference]: payload.value ?? (payload.artifact_url ? {url: payload.artifact_url} : null)},
          output_kinds: {[payload.reference]: payload.kind},
        });
      })
      .catch(error => {
        fetched.delete(reference);
        console.error(`[dataviz:live:${reference}]`, error);
      });
    fetched.set(reference, promise);
    return promise;
  };
  source.addEventListener('output_ready', message => {
    const event = JSON.parse(message.data);
    if (event.run_id !== live.run_id || !event.data?.reference) return;
    if (window.dataviz.interaction) {
      window.dataviz.interaction.query_snapshot_available = true;
    }
    fetchOutput(event.data.reference);
  });
  ['node_error', 'node_cancelled', 'node_unavailable'].forEach(name => source.addEventListener(name, message => {
    const event = JSON.parse(message.data);
    if (event.run_id !== live.run_id) return;
    if (window.dataviz.interaction) {
      window.dataviz.interaction.query_snapshot_available = true;
    }
    const error = datavizRuntimeError({
      ...(event.error || {}),
      code:event.error?.code || (name === 'node_cancelled' ? 'cancelled' : name === 'node_unavailable' ? 'unavailable' : 'node_failed'),
      message:event.error?.message || `${event.node_id} ${name.replace('node_', '')}`,
    });
    datavizRuntime.failOutputs(event.data?.outputs || [], error);
  }));
  source.addEventListener('run_ready', () => {
    source.close();
    window.dataviz.status = 'ready';
    window.dispatchEvent(new CustomEvent('dataviz:runready', {detail:{run_id:live.run_id}}));
  });
  source.addEventListener('run_error', () => {
    window.dataviz.status = 'error';
    source.close();
  });
  source.addEventListener('run_cancelled', () => {
    window.dataviz.status = 'cancelled';
    source.close();
  });
  source.addEventListener('stream_end', () => source.close());
  window.dataviz.liveSource = source;
};
const setSelectionInputs = values => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    if (!(key in values)) return;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const value = values[key];
    const encode = item => datavizEncodeControlValue(input, item, {
      path:control.dataset.selectionPath === 'true',
    });
    if (control.dataset.selectionType === 'boolean' && input.tagName === 'SELECT') {
      input.value = value == null ? '' : encode(value);
    }
    else if (control.dataset.selectionType === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(encode));
      Array.from(input.options).forEach(option => {
        option.selected = selected.has(option.value);
      });
      syncPortableChoices(control);
    }
    else if (control.dataset.selectionType === 'date_range' && Array.isArray(value)) {
      input.value = value.length ? value.join(',') : '';
    }
    else if (input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  });
};
const setComputeInputs = values => {
  window.dataviz.draft_compute_parameters = {
    ...(window.dataviz.draft_compute_parameters || {}),
    ...(values || {}),
  };
  document.querySelectorAll('[data-compute-key]').forEach(control => {
    const key = control.dataset.computeKey;
    if (!(key in (values || {}))) return;
    const input = control.querySelector('[data-compute-input]');
    if (!input || input.disabled) return;
    const value = values[key];
    const type = input.dataset.computeType;
    if (type === 'date_range') {
      const range = Array.isArray(value) ? value : String(value || '').split(',', 2);
      const start = input.querySelector('[data-compute-range="start"]');
      const end = input.querySelector('[data-compute-range="end"]');
      if (start) start.value = range[0] || '';
      if (end) end.value = range[1] || '';
    } else if (type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(item => datavizEncodeControlValue(input, item)));
      Array.from(input.options).forEach(option => { option.selected = selected.has(option.value); });
    } else if (input.tagName === 'SELECT') {
      input.value = value == null ? '' : datavizEncodeControlValue(input, value);
    } else input.value = value ?? '';
  });
  syncComputeDirtyState();
};
window.addEventListener('message', event => {
  if (
    event.origin !== window.location.origin
    || window.parent === window
    || event.source !== window.parent
    || !datavizSameFrameIdentity(event.data)
  ) return;
  if (event.data?.type === 'dataviz:set-selections') {
    const values = event.data.selections || {};
    Object.assign(window.dataviz.selections, values);
    setSelectionInputs(values);
    window.dataviz.applySelections().catch(error => console.error('[dataviz:selections]', error));
  }
  if (event.data?.type === 'dataviz:set-interaction') {
    const previous = window.dataviz.interaction;
    const next = event.data.interaction || null;
    window.dataviz.interaction = next;
    const endpointChanged = [
      'run_id', 'session_id', 'start_url', 'status_url', 'outputs_url',
      'query_snapshot_available', 'query_complete',
    ].some(
      key => (previous?.[key] || null) !== (next?.[key] || null),
    );
    if (next && endpointChanged) {
      const targets = [...datavizRuntime.transforms.entries()]
        .filter(([, item]) => item.spec.runtime === 'server-python')
        .map(([id]) => id);
      datavizRuntime.runTransforms([], [], {
        changedComputeKeys: [],
        targets,
      }).catch(error => console.error('[dataviz:interaction]', error));
    }
  }
  if (event.data?.type === 'dataviz:set-compute') {
    const values = event.data.compute_parameters || {};
    setComputeInputs(values);
    if (event.data.commit) {
      const apply = event.data.control_keys == null
        ? window.dataviz.applyCompute
        : window.dataviz.applyControls;
      apply({
        keys:event.data.control_keys || Object.keys(values),
        apply:event.data.apply !== false,
        manualTargets:event.data.manual_targets || [],
      }).catch(error => console.error('[dataviz:compute]', error));
    }
  }
  if (event.data?.type === 'dataviz:collect-snapshot') {
    const requestId = event.data.request_id;
    try {
      const snapshot = datavizRuntime.collectSnapshotOutputs();
      event.source?.postMessage({
        type:'dataviz:snapshot-collected',
        request_id:requestId,
        ...datavizFrameIdentity(),
        ...snapshot,
      }, event.origin);
    } catch (error) {
      event.source?.postMessage({
        type:'dataviz:snapshot-collected',
        request_id:requestId,
        ...datavizFrameIdentity(),
        error:{message:error?.message || String(error)},
      }, event.origin);
    }
  }
});
let datavizSelectionScheduled = false;
let datavizSelectionQueue = Promise.resolve();
const scheduleDatavizSelection = () => {
  // Capture the user's native control value before asynchronous initialization
  // or option-domain reconciliation can rebuild the underlying <select>.
  try {
    readSelectionInputs();
  } catch (error) {
    console.error('[dataviz:selections]', error);
    return;
  }
  if (datavizSelectionScheduled) return;
  datavizSelectionScheduled = true;
  queueMicrotask(() => {
    datavizSelectionScheduled = false;
    // A native select emits both input and change for one user action. Coalesce
    // that event pair in the current task, then serialize any later actions
    // behind the in-flight Interactive branch. Selection is an immediate data
    // contract; it must not depend on a browser timer being scheduled promptly.
    const initialization = datavizRuntime.initializationPromise || Promise.resolve();
    datavizSelectionQueue = Promise.all([
      datavizSelectionQueue.catch(() => undefined),
      initialization.catch(() => undefined),
    ])
      .then(() => window.dataviz.applySelections())
      .catch(error => console.error('[dataviz:selections]', error));
  });
};
const datavizEscape = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const syncPortableChoices = control => control.querySelector('.dv-selector')?._syncSelector?.();
window.datavizComponents?.hydrate(document);
document.querySelectorAll('[data-selection-input]').forEach(input => {
  input.addEventListener('input', scheduleDatavizSelection);
  input.addEventListener('change', scheduleDatavizSelection);
});
let datavizComputeTimer;
document.querySelectorAll('[data-compute-input]').forEach(input => {
  const onDraft = () => {
    readComputeInputs();
    const changed = syncComputeDirtyState();
    const key = input.closest('[data-compute-key]')?.dataset.computeKey || input.dataset.computeInput;
    const trigger = input.dataset.computeTrigger || input.closest('[data-compute-trigger]')?.dataset.computeTrigger;
    if (trigger !== 'auto' || !key || !changed.includes(key)) return;
    clearTimeout(datavizComputeTimer);
    const consumers = [...datavizRuntime.transforms.values()]
      .filter(item => item.spec.trigger === 'auto' && Object.values(item.spec.compute_inputs || {}).includes(key));
    const delay = Math.max(0, ...consumers.map(item => Number(item.spec.debounce_ms || 0)));
    datavizComputeTimer = setTimeout(() => window.dataviz.applyCompute({keys:[key]}).catch(error => {
      console.error('[dataviz:compute:auto]', error);
    }), delay);
  };
  input.addEventListener('input', onDraft);
  input.addEventListener('change', onDraft);
});
document.querySelectorAll('[data-compute-apply]').forEach(button => {
  button.addEventListener('click', () => window.dataviz.applyControls({
    apply:true,
    keys:JSON.parse(button.dataset.controlKeys || '[]'),
    manualTargets:JSON.parse(button.dataset.manualTargets || '[]'),
  }).catch(error => {
    console.error('[dataviz:compute:apply]', error);
  }));
});
syncComputeDirtyState();
document.addEventListener('pointerdown', () => {
  if (window.parent !== window) {
    datavizPostToParent({type: 'dataviz:canvas-interaction'});
  }
}, {capture: true});
window.addEventListener('pagehide', () => datavizRuntime.dispose(), {once:true});
Object.entries(window.dataviz.portable?.outputs || {}).forEach(([reference, value]) => {
  datavizRuntime.outputSignatures.set(
    canonicalOutputReference(reference),
    datavizValueSignature(value),
  );
});
Object.entries(window.dataviz.portable?.output_errors || {}).forEach(([reference, failure]) => {
  datavizRuntime.outputErrors.set(
    canonicalOutputReference(reference),
    datavizRuntimeError(failure),
  );
});
window.dataviz.getViewSelections = viewId => {
  const contract = window.dataviz.portable?.selection_contract?.[viewId] || [];
  return Object.fromEntries(
    contract.map(item => [item.id, window.dataviz.selections[item.key]])
  );
};
window.datavizRuntimeServices = Object.freeze({
  canonicalOutputReference,
  tableRows:datavizTableRows,
  numericAggregate:datavizNumericAggregate,
  workerValue:datavizWorkerValue,
  selectionCanApply:datavizSelectionCanApply,
  selectionMatches:datavizSelectionMatches,
  runtimeError:datavizRuntimeError,
  escape:datavizEscape,
  decodeSpec:node => JSON.parse(new TextDecoder().decode(Uint8Array.from(
    atob(node.dataset.spec),
    value => value.charCodeAt(0),
  ))),
});
window.dispatchEvent(new CustomEvent('dataviz:runtime-ready', {detail: datavizRuntime}));
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
