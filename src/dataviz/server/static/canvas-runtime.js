// Owner: Runtime protocol, manifest normalization, and shared constants.
const DATAVIZ_RUNTIME_PROTOCOL = 'dataviz/runtime/v6';
const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';
const DATAVIZ_DEPENDENCY_CONTRACT = 'dataviz/dependency-contract/v7';
if (window.dataviz.protocol?.schema !== DATAVIZ_RUNTIME_PROTOCOL) {
  throw new Error(`Unsupported Dataviz Runtime protocol: ${window.dataviz.protocol?.schema || 'missing'}`);
}
if (window.dataviz.dependency_contract?.schema !== DATAVIZ_DEPENDENCY_CONTRACT) {
  throw new Error(
    `Unsupported Dashboard dependency contract: ${window.dataviz.dependency_contract?.schema || 'missing'}`
  );
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
const datavizViewPipelineVisibleStatuses = new Set([
  'queued', 'loading', 'stale', 'error', 'cancelled', 'unavailable',
]);
const datavizViewPipelineStatusLabel = status => ({
  not_run:'Not run',
  queued:'Queued',
  loading:'Running',
  ready:'Ready',
  empty:'Ready · empty',
  stale:'Stale',
  error:'Failed',
  cancelled:'Cancelled',
  unavailable:'Unavailable',
}[status] || status);
const datavizSetViewPipelineNodeStatus = (nodeId, status) => {
  const normalized = String(status || 'not_run');
  document.querySelectorAll(
    `[data-view-pipeline-node="${CSS.escape(String(nodeId))}"]`,
  ).forEach(signal => {
    signal.dataset.status = normalized;
    signal.hidden = !datavizViewPipelineVisibleStatuses.has(normalized);
    const title = signal.querySelector('.dv-view-pipeline-tooltip strong')?.textContent
      || String(nodeId);
    signal.setAttribute(
      'aria-label',
      `${title}: ${datavizViewPipelineStatusLabel(normalized)}`,
    );
    if (['queued', 'loading', 'stale'].includes(normalized)) {
      const root = signal.closest('.dv-view');
      const rendererSignal = root?.querySelector('[data-view-renderer-signal]');
      if (rendererSignal) {
        rendererSignal.dataset.status = 'not_run';
        rendererSignal.hidden = true;
        rendererSignal.setAttribute('aria-hidden', 'true');
      }
      if (root) delete root.dataset.rendererSignalActive;
    }
  });
};
const canonicalOutputReference = reference => {
  const raw = String(reference || '').trim();
  if (!raw) throw new Error('Output reference cannot be empty');
  if (!/^(source|dataset|interactive):[^/]+\/[^/]+$/.test(raw)) {
    throw new Error(`Output reference must be explicit: ${raw}`);
  }
  return raw;
};
const datavizInputContractSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([name, reference]) => [name, canonicalOutputReference(reference)])
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizCanonicalControlReference = reference => {
  const raw = String(reference || '').trim();
  if (raw.startsWith('dashboard.')) {
    return `dashboard:${window.dataviz.dashboard_id}/${raw.slice('dashboard.'.length)}`;
  }
  return raw;
};
const datavizControlInputSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([alias, raw]) => {
        const binding = typeof raw === 'string'
          ? {mode:'value', control:datavizCanonicalControlReference(raw), projection:'value'}
          : {
              mode:String(raw?.mode || 'value'),
              control:datavizCanonicalControlReference(raw?.control),
              ...((raw?.mode || 'value') === 'value'
                ? {projection:String(raw?.projection || 'value')}
                : raw?.projection ? {projection:String(raw.projection)} : {}),
              ...(raw?.field ? {field:raw.field} : {}),
              ...(raw?.inputs ? {inputs:[...raw.inputs]} : {}),
              ...(raw?.empty ? {empty:String(raw.empty)} : {}),
              ...(raw?.operator ? {operator:String(raw.operator)} : {}),
            };
        return [alias, binding];
      })
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizParameterBinding = binding => typeof binding === 'string'
  ? {parameter:String(binding)}
  : {
      parameter:String(binding?.parameter || ''),
      ...(binding?.part ? {part:String(binding.part)} : {}),
    };
const datavizParameterInputSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([alias, binding]) => [alias, datavizParameterBinding(binding)])
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizProjectParameterInputs = inputs => Object.fromEntries(
  Object.entries(inputs || {}).map(([alias, rawBinding]) => {
    const binding = datavizParameterBinding(rawBinding);
    let value = window.dataviz.query_parameters?.[binding.parameter];
    if (binding.part) {
      if (!Array.isArray(value) || value.length !== 2) {
        throw new Error(`Query input ${alias} cannot read ${binding.part} from ${binding.parameter}`);
      }
      value = value[binding.part === 'start' ? 0 : 1];
    }
    return [alias, value];
  })
);
const datavizOutputContractSignature = (transformId, outputs) => JSON.stringify(
  Object.keys(outputs || {}).map(name => `interactive:${transformId}/${name}`).sort()
);
const datavizValueSignature = value => {
  if (value?.__datavizArrowOutput) return `arrow:${value.descriptor?.content_hash || value.descriptor?.row_count || 'table'}`;
  try { return JSON.stringify(value); }
  catch { return String(value); }
};
// Owner: canonical value, output-reference, and transport value contracts.
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
const datavizStaticChoices = definition => (
  definition?.options?.mode === 'static'
    ? (definition.options.choices || [])
    : []
);
const datavizChoiceValue = (definition, value) => {
  const choices = datavizStaticChoices(definition);
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
const datavizNormalizeScalarValue = (definition, value, label = 'Value') => {
  const valueType = definition?.value_type || 'text';
  if (valueType === 'text') {
    if (typeof value !== 'string') throw datavizContractError('invalid_type', `${label} must be text`);
    if (definition.max_length != null && value.length > Number(definition.max_length)) {
      throw datavizContractError('too_long', `${label} cannot be longer than ${definition.max_length} characters`);
    }
    return value;
  }
  if (['number', 'integer'].includes(valueType)) {
    const raw = typeof value === 'string' ? value.trim() : null;
    if (raw != null && (
      (valueType === 'integer' && !/^[+-]?\d+$/.test(raw))
      || (valueType === 'number' && !datavizDecimalNumberPattern.test(raw))
    )) {
      throw datavizContractError('invalid_type', `${label} must be a${valueType === 'integer' ? 'n integer' : ' finite number'}`);
    }
    const numeric = typeof value === 'number' ? value : Number(raw);
    if (!Number.isFinite(numeric) || (valueType === 'integer' && !Number.isInteger(numeric))) {
      throw datavizContractError('invalid_type', `${label} must be a${valueType === 'integer' ? 'n integer' : ' finite number'}`);
    }
    if (Number.isInteger(numeric) && !Number.isSafeInteger(numeric)) {
      throw datavizContractError('unsafe_integer', `${label} exceeds the exact JavaScript integer range`);
    }
    if (definition.min != null && numeric < Number(definition.min)) {
      throw datavizContractError('below_minimum', `${label} must be at least ${definition.min}`);
    }
    if (definition.max != null && numeric > Number(definition.max)) {
      throw datavizContractError('above_maximum', `${label} must be at most ${definition.max}`);
    }
    if (definition.step != null) {
      const base = Number(definition.min || 0);
      const quotient = (numeric - base) / Number(definition.step);
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) {
        throw datavizContractError('invalid_step', `${label} must follow step ${definition.step} from ${base}`);
      }
    }
    return numeric;
  }
  if (valueType === 'boolean') {
    if (typeof value === 'boolean') return value;
    if (value === 0 || value === 1) return Boolean(value);
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
      if (['false', '0', 'no', 'off'].includes(normalized)) return false;
    }
    throw datavizContractError('invalid_type', `${label} must be a boolean`);
  }
  if (valueType === 'date') {
    const normalized = datavizIsoDate(value, label);
    if (definition.min_date && normalized < definition.min_date) {
      throw datavizContractError('before_minimum_date', `${label} cannot be before ${definition.min_date}`);
    }
    if (definition.max_date && normalized > definition.max_date) {
      throw datavizContractError('after_maximum_date', `${label} cannot be after ${definition.max_date}`);
    }
    return normalized;
  }
  throw datavizContractError('unknown_value_type', `Unsupported value_type: ${valueType}`);
};
const datavizNormalizeControlValue = (definition, value, {namespace = 'control', key = ''} = {}) => {
  const type = definition?.type || 'single_input';
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
      return ['multiple_input', 'multiple_select', 'range_input'].includes(type) ? [] : null;
    }
    if (type === 'single_input') return datavizNormalizeScalarValue(definition, value);
    if (type === 'multiple_input') {
      let items = value;
      if (typeof items === 'string') {
        try { items = JSON.parse(items); }
        catch (_error) { items = items.split(',').map(item => item.trim()).filter(Boolean); }
      }
      if (!Array.isArray(items)) throw datavizContractError('invalid_type', 'Multiple input requires a list');
      const normalized = items.map((item, index) => datavizNormalizeScalarValue(definition, item, `Item ${index + 1}`));
      if (definition.max_items != null && normalized.length > Number(definition.max_items)) {
        throw datavizContractError('too_many_values', `At most ${definition.max_items} values may be entered`);
      }
      const signatures = normalized.map(datavizValueSignature);
      if (new Set(signatures).size !== signatures.length) {
        throw datavizContractError('duplicate_value', 'Multiple input values must be unique');
      }
      return normalized;
    }
    if (type === 'range_input') {
      const range = typeof value === 'string' ? value.split(',', 2).map(item => item.trim()) : value;
      if (!Array.isArray(range) || range.length !== 2) {
        throw datavizContractError('invalid_shape', 'Range input must contain exactly [start, end]');
      }
      const start = range[0] !== '' && range[0] != null
        ? datavizNormalizeScalarValue(definition, range[0], 'Range start') : '';
      const end = range[1] !== '' && range[1] != null
        ? datavizNormalizeScalarValue(definition, range[1], 'Range end') : '';
      if (start === '' && end === '') return [];
      const allowEmpty = Array.isArray(definition.allow_empty) ? definition.allow_empty : [false, false];
      if (start === '' && !allowEmpty[0]) throw datavizContractError('missing_range_start', 'Range input requires a start value');
      if (end === '' && !allowEmpty[1]) throw datavizContractError('missing_range_end', 'Range input requires an end value');
      if (start !== '' && end !== '' && start > end) {
        throw datavizContractError('invalid_range', 'Range input start cannot be after end');
      }
      return [start, end];
    }
    if (type === 'single_select') {
      const pathFields = definition.path_fields || [];
      if (pathFields.length) {
        if (!Array.isArray(value) || value.length !== pathFields.length || value.some(item => item == null)) {
          throw datavizContractError('invalid_path', `Single select hierarchy requires one ${pathFields.length}-level path`);
        }
        return value.map((item, index) => datavizNormalizeScalarValue(definition, item, pathFields[index]));
      }
      if (Array.isArray(value) || (value && typeof value === 'object')) {
        throw datavizContractError('invalid_type', 'Single select requires one value');
      }
      return datavizChoiceValue(definition, datavizNormalizeScalarValue(definition, value));
    }
    if (type === 'multiple_select') {
      if (!Array.isArray(value)) throw datavizContractError('invalid_type', 'Multiple select requires a list');
      const pathFields = definition.path_fields || [];
      const normalized = pathFields.length
        ? value.map(item => {
            if (!Array.isArray(item) || item.length !== pathFields.length || item.some(child => child == null)) {
              throw datavizContractError('invalid_path', `Multiple select hierarchy values require ${pathFields.length}-level paths`);
            }
            return item.map((child, index) => datavizNormalizeScalarValue(definition, child, pathFields[index]));
          })
        : value.map(item => datavizChoiceValue(definition, datavizNormalizeScalarValue(definition, item)));
      const signatures = normalized.map(datavizValueSignature);
      if (new Set(signatures).size !== signatures.length) {
        throw datavizContractError('duplicate_value', 'Multiple select values must be unique');
      }
      if (definition?.required && !normalized.length) {
        throw datavizContractError('required', 'At least one value is required');
      }
      if (definition?.max_selected != null && normalized.length > Number(definition.max_selected)) {
        throw datavizContractError('too_many_values', `At most ${definition.max_selected} values may be selected`);
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
// Owner: shared Runtime host state and public registration surface.
const datavizRuntime = window.datavizRuntime = {
  protocol: 'dataviz/runtime/v6',
  transforms: new Map(),
  views: new Map(),
  renderers: new Map(),
  outputSignatures: new Map(),
  outputErrors: new Map(),
  transformErrors: new Map(),
  rendererErrors: new Map(),
  activeTransforms: new Map(),
  inflightTransforms: new Map(),
  transformRequests: new Map(),
  transportPromises: new Map(),
  transformGenerations: new Map(),
  workerUrls: new Map(),
  interactionCache: new Map(),
  controlImpactSignatures: new Map(),
  initializing: false,
  initializationPromise: null,
  interactiveAdapters: Object.create(null),
  metrics: {
    interactiveTransforms: {started:0, completed:0, cancelled:0, timedOut:0, failed:0, cacheHits:0},
    transports: {started:0, completed:0, failed:0, arrowRows:0, arrowBytes:0, totalMs:0},
    renderers: {
      mounts:0, updates:0, empty:0, restores:0, interactions:0,
      resizes:0, disposes:0, failed:0, totalMs:0,
    },
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
    if (!(spec.id in (window.dataviz.dependency_contract?.interactive?.dependencies || {}))) {
      throw new Error(`Interactive Transform ${spec.id} is absent from the compiled dependency contract`);
    }
    const expectedInputs = window.dataviz.dependency_contract.interactive.inputs?.[spec.id] || {};
    if (datavizInputContractSignature(spec.inputs) !== datavizInputContractSignature(expectedInputs)) {
      throw new Error(`Interactive Transform ${spec.id} inputs differ from the compiled dependency contract`);
    }
    const interactiveContract = window.dataviz.dependency_contract.interactive;
    if (datavizControlInputSignature(spec.control_inputs) !== datavizControlInputSignature(interactiveContract.control_inputs?.[spec.id])) {
      throw new Error(`Interactive Transform ${spec.id} Control inputs differ from the compiled dependency contract`);
    }
    if (datavizParameterInputSignature(spec.query_inputs) !== datavizParameterInputSignature(interactiveContract.parameter_inputs?.[spec.id])) {
      throw new Error(`Interactive Transform ${spec.id} Query Parameter inputs differ from the compiled dependency contract`);
    }
    if (datavizOutputContractSignature(spec.id, spec.outputs) !== JSON.stringify([...(interactiveContract.outputs?.[spec.id] || [])].sort())) {
      throw new Error(`Interactive Transform ${spec.id} outputs differ from the compiled dependency contract`);
    }
    this.transforms.set(spec.id, {spec, source});
  },
  registerView(id, definition) {
    if (!id || typeof definition?.render !== 'function') throw new Error('View registration requires id and render');
    if (this.views.has(id)) throw new Error(`Duplicate View registration: ${id}`);
    if (!(id in (window.dataviz.dependency_contract?.views || {}))) {
      throw new Error(`View ${id} is absent from the compiled dependency contract`);
    }
    const expectedInputs = window.dataviz.dependency_contract.views[id].inputs || {};
    if (datavizInputContractSignature(definition.inputs) !== datavizInputContractSignature(expectedInputs)) {
      throw new Error(`View ${id} inputs differ from the compiled dependency contract`);
    }
    // The declarative registration payload is only a drift assertion. Runtime
    // scheduling must consume the immutable compiled contract so a View never
    // has two competing dependency sources.
    this.views.set(id, {inputs: {...expectedInputs}, render: definition.render});
  },
  registerRenderer(type, renderer) {
    if (!type || typeof renderer?.mount !== 'function') throw new Error('Renderer requires type and mount');
    if (this.renderers.has(type)) throw new Error(`Duplicate Renderer: ${type}`);
    this.renderers.set(type, renderer);
  },
  configureSnapshotControls() {
    const snapshotIds = new Set(window.dataviz.snapshot_interactions || []);
    const controlKeys = new Set();
    snapshotIds.forEach(id => {
      Object.values(this.transformControlInputs(id)).forEach(binding => controlKeys.add(binding.control));
    });
    controlKeys.forEach(key => {
      document.querySelectorAll(`[data-control-key="${CSS.escape(key)}"]`).forEach(control => {
        control.dataset.controlFrozen = 'true';
        control.setAttribute('aria-label', `${control.getAttribute('aria-label') || key} · fixed snapshot`);
        control.querySelectorAll('input,select,button').forEach(input => { input.disabled = true; });
      });
    });
  },
  transformOrder() {
    const order = [...(window.dataviz.dependency_contract?.interactive?.order || [])];
    const registered = new Set(this.transforms.keys());
    const missing = order.filter(id => !registered.has(id));
    const unknown = [...registered].filter(id => !order.includes(id));
    if (missing.length || unknown.length) {
      throw new Error(
        `Interactive registry differs from dependency contract; missing=${missing.join(',')} unknown=${unknown.join(',')}`
      );
    }
    return order;
  },
  transformDependencies(id) {
    const dependencies = window.dataviz.dependency_contract?.interactive?.dependencies?.[id];
    if (!Array.isArray(dependencies)) throw new Error(`Interactive dependency contract is missing ${id}`);
    return dependencies;
  },
  transformInputs(id) {
    const inputs = window.dataviz.dependency_contract?.interactive?.inputs?.[id];
    if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) {
      throw new Error(`Interactive input contract is missing ${id}`);
    }
    return inputs;
  },
  transformControlInputs(id) {
    return window.dataviz.dependency_contract?.interactive?.control_inputs?.[id] || {};
  },
  transformParameterInputs(id) {
    return window.dataviz.dependency_contract?.interactive?.parameter_inputs?.[id] || {};
  },
  transformViews(id, mode = 'downstream') {
    return window.dataviz.dependency_contract?.interactive?.[
      mode === 'direct' ? 'direct_views' : 'downstream_views'
    ]?.[id] || [];
  },
  outputViews(reference) {
    return window.dataviz.dependency_contract?.outputs?.[
      canonicalOutputReference(reference)
    ]?.views || [];
  }
};
// Owner: Interactive Transform scheduling, workers, cancellation, and status.
Object.assign(datavizRuntime, {
  interactiveWorkerUrl() {
    const runtime = 'browser-js';
    if (this.workerUrls.has(runtime)) return this.workerUrls.get(runtime);
    const source = window.datavizInteractiveJsWorkerSource;
    if (!source) throw new Error('browser-js Worker source is missing');
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
    const worker = new Worker(this.interactiveWorkerUrl());
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
          if (cancelBuffer) Atomics.store(cancelBuffer, 0, 1);
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
      const prepared = datavizPrepareControlInputs(this.transformControlInputs(id), inputValues);
      worker.postMessage({
        protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
        type:'execute',
        request_id:requestId,
        transform_id:id,
        code:item.source.code,
        entrypoint:item.source.entrypoint,
        code_dependencies:item.source.dependencies || {},
        context:{
          inputs:prepared.inputs,
          query_inputs:datavizProjectParameterInputs(this.transformParameterInputs(id)),
          control_inputs:prepared.controlInputs,
        },
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
          control_state:datavizControlStateSnapshot(),
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
      query_inputs:datavizProjectParameterInputs(this.transformParameterInputs(id)),
      control_state:Object.fromEntries(
        Object.values(this.transformControlInputs(id)).map(binding => [
          binding.control,
          datavizControlEntry(binding.control),
        ])
      ),
    });
  },
  async executeTransform(id, item, inputValues, generation) {
    const key = this.transformCacheKey(id, item, inputValues);
    if (item.spec.cache?.mode !== 'none' && this.interactionCache.has(key)) {
      this.metrics.interactiveTransforms.cacheHits += 1;
      return datavizCacheClone(this.interactionCache.get(key));
    }
    const inflightKey = `${id}\u0000${key}`;
    const existing = this.inflightTransforms.get(inflightKey);
    if (existing) return datavizCacheClone(await existing);
    const execution = (async () => {
      const adapter = this.interactiveAdapters[item.spec.runtime];
      if (!adapter) throw new Error(`Unsupported Interactive Runtime: ${item.spec.runtime}`);
      adapter.validate(item);
      const prepared = await adapter.prepare(item, inputValues);
      const value = await adapter.execute(id, item, prepared, {generation});
      if (item.spec.cache?.mode !== 'none') {
        this.interactionCache.set(key, datavizCacheClone(value));
      }
      return value;
    })();
    this.inflightTransforms.set(inflightKey, execution);
    try {
      return datavizCacheClone(await execution);
    } finally {
      if (this.inflightTransforms.get(inflightKey) === execution) {
        this.inflightTransforms.delete(inflightKey);
      }
    }
  },
  markTransformStale(id) {
    this.transformViews(id).forEach(viewId => {
      const root = this.viewAdapter?.node(viewId);
      if (root) this.viewAdapter?.setStatus(root, 'stale', 'run analysis');
    });
    this.publishTransformStatus(id, 'stale', {message:'Inputs changed; run analysis'});
  },
  markTransformLoading(id, message = 'running analysis') {
    this.transformViews(id).forEach(viewId => {
      const root = this.viewAdapter?.node(viewId);
      if (root) this.viewAdapter?.setStatus(root, 'loading', message);
    });
    this.publishTransformStatus(id, 'loading', {message});
  },
  markTransformReady(id) {
    this.transformViews(id, 'direct').forEach(viewId => {
      const root = this.viewAdapter?.node(viewId);
      if (!root) return;
      const renderer = this.viewAdapter?.states.get(viewId)?.type || 'ready';
      this.viewAdapter?.setStatus(root, 'ready', renderer);
    });
    this.publishTransformStatus(id, 'ready');
  },
  publishTransformStatus(id, status, details = {}) {
    datavizSetViewPipelineNodeStatus(`interactive:${id}`, status);
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
  async runTransforms(changedControlKeys = [], seedChangedOutputs = [], options = {}) {
    const outputs = window.dataviz.portable?.outputs || {};
    const changedControls = changedControlKeys == null ? null : new Set(changedControlKeys);
    const changedOutputs = new Set(seedChangedOutputs);
    const staleOutputs = new Set();
    const manualClosure = new Set(options.manualTargets || []);
    const order = this.transformOrder();
    const targetClosure = options.targets == null ? null : new Set(options.targets);
    if (targetClosure) {
      const addDependencies = id => {
        this.transformDependencies(id).forEach(dependency => {
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
      this.transformDependencies(id).forEach(dependency => manualClosure.add(dependency));
    }
    const tasks = new Map();
    const renderOutputDelta = references => {
      if (!references.size) return;
      const affectedViewIds = this.affectedViews([], references);
      if (affectedViewIds?.length) {
        this.renderViews({initial:false, changedControlKeys:[], affectedViewIds});
      }
    };
    for (const id of order) {
      if (targetClosure && !targetClosure.has(id)) continue;
      const item = this.transforms.get(id);
      const {spec} = item;
      const references = Object.fromEntries(
        Object.entries(this.transformInputs(id)).map(([name, reference]) => [
          name,
          canonicalOutputReference(reference),
        ])
      );
      const dependencyIds = this.transformDependencies(id);
      const task = (async () => {
        await Promise.all(dependencyIds.map(dependency => tasks.get(dependency)).filter(Boolean));
        const declared = Object.keys(spec.outputs || {});
        const outputReferences = declared.map(name => `interactive:${id}/${name}`);
        const requiredOutputReferences = declared
          .filter(name => spec.outputs?.[name]?.required !== false)
          .map(name => `interactive:${id}/${name}`);
        const upstreamChanged = Object.values(references).some(reference => changedOutputs.has(reference));
        const upstreamStale = Object.values(references).some(reference => staleOutputs.has(reference));
        const controlChanged = changedControls == null
          || Object.values(this.transformControlInputs(id)).some(binding => changedControls.has(binding.control));
        const missingOutput = requiredOutputReferences.some(reference =>
          !Object.prototype.hasOwnProperty.call(outputs, reference)
        );
        const relevant = upstreamChanged || upstreamStale || controlChanged
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
          // parent-frame state sync carries an empty Control delta.
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
          window.dataviz.applied_revisions ||= {views:{}, transforms:{}};
          window.dataviz.applied_revisions.transforms[id] = Object.fromEntries(
            Object.values(this.transformControlInputs(id)).map(binding => [
              binding.control,
              Number(datavizControlEntry(binding.control)?.revision || 0),
            ])
          );
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
});
// Owner: affected-view resolution and Renderer mount/update lifecycle.
Object.assign(datavizRuntime, {
  affectedViews(changedControlKeys, changedOutputs = new Set()) {
    // A null Control delta is the first render, not an empty update. Render
    // every registered host so input-free Markdown/Image Views become ready and
    // data-backed Views can enter their branch-local waiting state.
    if (changedControlKeys == null) return null;
    const changedControls = new Set(changedControlKeys || []);
    const outputs = changedOutputs || new Set();
    const affected = new Set();
    changedControls.forEach(key => {
      const dependency = window.dataviz.dependency_contract?.controls?.[key];
      (dependency?.direct_views || []).forEach(viewId => {
        const item = datavizViewControlContract(viewId)
          .find(candidate => candidate.key === key);
        if (item && datavizControlViewApplicability(viewId, item) !== 'not_applicable') {
          affected.add(viewId);
        }
      });
      (dependency?.repeat_views || []).forEach(viewId => affected.add(viewId));
    });
    outputs.forEach(reference => this.outputViews(reference).forEach(viewId => affected.add(viewId)));
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
      window.dataviz.applied_revisions ||= {views:{}, transforms:{}};
      const bindings = window.dataviz.dependency_contract?.views?.[id]?.control_inputs || {};
      window.dataviz.applied_revisions.views[id] = Object.fromEntries(
        Object.values(bindings).map(binding => [
          binding.control,
          Number(datavizControlEntry(binding.control)?.revision || 0),
        ])
      );
    });
  },
  async publishOutputs(bundle) {
    const outputs = window.dataviz.portable?.outputs || {};
    window.dataviz.portable.output_schemas ||= {};
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
    Object.assign(window.dataviz.portable.output_schemas, bundle.output_schemas || {});
    if (!changed.size || this.initializing) return changed;
    refreshControlOptionDomains();
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({initial:false, changedControlKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[]},
    }));
    this.publishControlImpacts();
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
    this.renderViews({initial:false, changedControlKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
    this.publishControlImpacts();
    return changedOutputs;
  },
});
// Owner: Named Output transport registration, hydration, and publication.
Object.assign(datavizRuntime, {
  registerOutputTransport(reference, descriptor) {
    const canonical = canonicalOutputReference(reference);
    window.dataviz.portable.output_schemas ||= {};
    window.dataviz.portable.output_transports[canonical] = descriptor;
    if (Array.isArray(descriptor?.schema)) {
      window.dataviz.portable.output_schemas[canonical] = descriptor.schema;
    }
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
      // Control domains. Hydration may publish Arrow tables, but no View or
      // Interactive branch is allowed to observe a half-initialized Control state.
      this.initializing = true;
      try {
        await this.hydrateOutputTransports();
      } finally {
        this.initializing = false;
      }
      await window.dataviz.applyControls();
      // Canvas ready is a lifecycle contract, not a script-load notification.
      // The parent may restore tab-local Controls only after Base Outputs,
      // dynamic option domains and the first canonical Control snapshot agree.
      datavizPostToParent({
        type:'dataviz:canvas-ready',
        control_state:datavizControlStateSnapshot(),
      });
    })();
    return this.initializationPromise;
  },
  publishControlImpacts() {
    const controls = datavizControlImpactSnapshot();
    let changed = false;
    controls.forEach(impact => {
      const signature = JSON.stringify(impact);
      if (this.controlImpactSignatures.get(impact.key) !== signature) changed = true;
      this.controlImpactSignatures.set(impact.key, signature);
      document.querySelectorAll('[data-control-impact-key]').forEach(node => {
        if (node.dataset.controlImpactKey !== impact.key) return;
        node.textContent = datavizControlImpactLabel(impact);
      });
    });
    if (changed) datavizPostToParent({type:'dataviz:control-impact-changed', controls});
    return controls;
  },
});
// Owner: Runtime-wide Renderer, worker, observer, and resource disposal.
Object.assign(datavizRuntime, {
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.cancelTransforms('Runtime disposed');
    this.inflightTransforms.clear();
    this.sectionAdapter?.dispose();
    this.viewAdapter?.dispose();
    this.presentationAdapter?.dispose();
    this.workerUrls.forEach(url => URL.revokeObjectURL(url));
    this.workerUrls.clear();
    this.interactionCache.clear();
    this.controlImpactSignatures.clear();
    Object.values(this.interactiveAdapters).forEach(adapter => adapter.dispose());
  },
});
// Owner: Control binding, canonical commits, and parent-frame synchronization.
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
const datavizControlFields = item => {
  const field = item.consumer_binding?.field;
  return Array.isArray(field) ? field : [field].filter(Boolean);
};
const datavizControlCanApply = (row, item) => (
  row != null
  && typeof row === 'object'
  && datavizControlFields(item).every(field => Object.prototype.hasOwnProperty.call(row, field))
);
const datavizViewControlContract = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.filter_contract || []
);
const datavizControlContractItem = key => {
  const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
  const definition = dependency.definition || {};
  return {
    key,
    id:definition.id || key?.split('/').at(-1),
    origin:dependency.origin,
    owner_id:dependency.owner_id,
    definition,
    consumer_binding:{
      field:(definition.path_fields || []).length
        ? definition.path_fields
        : (definition.field || definition.id),
      empty:'passthrough',
      operator:'auto',
    },
  };
};
const datavizControlDomainReferences = item => (
  window.dataviz.dependency_contract?.controls?.[item?.key]?.option_domain_references || []
).map(canonicalOutputReference);
const datavizOutputFieldNames = rawReference => {
  const reference = canonicalOutputReference(rawReference);
  if (datavizRuntime.outputErrors.has(reference)) return null;
  const schema = window.dataviz.portable?.output_schemas?.[reference];
  if (Array.isArray(schema) && schema.length) {
    return new Set(schema.map(column => column?.name).filter(Boolean));
  }
  const outputs = window.dataviz.portable?.outputs || {};
  if (!Object.prototype.hasOwnProperty.call(outputs, reference)) return null;
  const value = outputs[reference];
  if (value?.__datavizArrowOutput) {
    return new Set(value.table.schema.fields.map(field => field.name));
  }
  const rows = datavizTableRows(value);
  if (!rows.length) return null;
  return new Set(rows.flatMap(row => Object.keys(row || {})));
};
const datavizControlViewApplicability = (viewId, item) => {
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key];
  if (!dependency) return 'not_applicable';
  if ((dependency.declared_direct_views || []).includes(viewId)) return 'applies';
  const binding = dependency.direct_view_bindings?.[viewId];
  if (!binding || binding.applicability === 'not_applicable') return 'not_applicable';
  const fields = binding.fields?.length ? binding.fields : datavizControlFields(item);
  let pending = false;
  for (const reference of binding.input_references || []) {
    if (window.dataviz.portable?.output_kinds?.[canonicalOutputReference(reference)] !== 'table') {
      continue;
    }
    const names = datavizOutputFieldNames(reference);
    if (names == null) {
      pending = true;
      continue;
    }
    if (fields.every(field => names.has(field))) return 'applies';
  }
  return pending ? 'pending' : 'not_applicable';
};
const datavizControlImpactSnapshot = () => Object.entries(
  window.dataviz.dependency_contract?.controls || {}
).map(([key, dependency]) => {
  const affected = new Set([
    ...(dependency.declared_direct_views || []),
    ...(dependency.derived_views || []),
    ...(dependency.content_views || []),
  ]);
  if (dependency.writer_view) affected.add(dependency.writer_view);
  let pending = false;
  (dependency.runtime_checked_views || []).forEach(viewId => {
    const item = datavizViewControlContract(viewId).find(candidate => candidate.key === key);
    if (!item) return;
    const applicability = datavizControlViewApplicability(viewId, item);
    if (applicability === 'applies') affected.add(viewId);
    if (applicability === 'pending') pending = true;
  });
  return {
    key,
    status:pending ? 'pending' : 'resolved',
    affected_views:[...affected].sort(),
    potential_views:[...(dependency.affected_views || [])].sort(),
  };
});
const datavizControlImpactLabel = impact => {
  const views = impact.status === 'pending' ? impact.potential_views : impact.affected_views;
  const count = views.length;
  return `${impact.status === 'pending' ? 'Up to ' : ''}${count} view${count === 1 ? '' : 's'}`;
};
const datavizControlState = () => {
  if (!window.dataviz.control_state || typeof window.dataviz.control_state !== 'object') {
    window.dataviz.control_state = {};
  }
  return window.dataviz.control_state;
};
const datavizControlDefinition = key => (
  window.dataviz.dependency_contract?.controls?.[key]?.definition
  || Object.values(window.dataviz.dependency_contract?.views || {})
    .flatMap(view => view.filter_contract || [])
    .find(item => item.key === key)?.definition
  || {}
);
const datavizNormalizeControlState = (key, candidate = null) => {
  const definition = datavizControlDefinition(key);
  const initial = window.dataviz.dependency_contract?.controls?.[key]?.initial_state || {
    value:null, revision:0,
  };
  const source = candidate && typeof candidate === 'object' ? candidate : initial;
  const value = datavizNormalizeControlValue(definition, source.value, {
    namespace:'control_state', key,
  });
  const revision = Math.max(0, Number(source.revision || 0));
  const intent = definition.type === 'multiple_select'
    ? (source.intent === 'all_available' ? 'all_available' : 'explicit')
    : null;
  return {value:structuredClone(value), revision, ...(intent ? {intent} : {})};
};
const datavizControlEntry = key => {
  const state = datavizControlState();
  if (!state[key]) state[key] = datavizNormalizeControlState(key);
  return state[key];
};
const datavizControlValueFromState = (_definition, entry) => structuredClone(entry?.value);
const datavizControlValue = key => datavizControlValueFromState(
  datavizControlDefinition(key),
  datavizControlEntry(key),
);
const datavizSetControlValue = (key, value, {intent = null} = {}) => {
  const definition = datavizControlDefinition(key);
  const normalized = datavizNormalizeControlValue(definition, value, {
    namespace:'control', key,
  });
  const previous = datavizControlEntry(key);
  const candidate = datavizNormalizeControlState(key, {
    intent:intent || previous.intent || 'explicit',
    value:normalized,
    revision:Number(previous.revision || 0),
  });
  if (
    datavizValueSignature(previous.value) === datavizValueSignature(candidate.value)
    && previous.intent === candidate.intent
  ) return previous;
  datavizControlState()[key] = {
    ...candidate,
    revision:Number(previous.revision || 0) + 1,
  };
  return datavizControlState()[key];
};
const datavizControlStateSnapshot = () => {
  const validKeys = new Set(Object.keys(window.dataviz.dependency_contract?.controls || {}));
  return Object.fromEntries([...validKeys].map(key => [
    key,
    structuredClone(datavizControlEntry(key)),
  ]));
};
const datavizControlValueSnapshot = () => Object.fromEntries(
  Object.keys(datavizControlStateSnapshot()).map(key => [key, datavizControlValue(key)]),
);
const datavizProjectControlBinding = binding => {
  const entry = datavizControlEntry(binding.control);
  if (binding.projection === 'present') return !datavizIsEmptyControlValue(entry.value);
  if (binding.projection === 'intent') return entry.intent || 'explicit';
  return structuredClone(entry.value);
};
const datavizPrepareControlInputs = (bindings, rawInputs) => {
  const inputs = {...rawInputs};
  Object.entries(bindings || {}).forEach(([alias, binding]) => {
    if (binding.mode !== 'filter') return;
    const item = {
      key:binding.control,
      id:binding.control.split('/').at(-1),
      definition:datavizControlDefinition(binding.control),
      consumer_binding:binding,
    };
    (binding.inputs || []).forEach(inputAlias => {
      inputs[inputAlias] = datavizTableRows(inputs[inputAlias]).filter(row => (
        datavizControlMatches(row, item, datavizControlEntry(binding.control))
      ));
    });
  });
  return {
    inputs,
    controlInputs:Object.fromEntries(
      Object.entries(bindings || {}).map(([alias, binding]) => [
        alias,
        datavizProjectControlBinding(binding),
      ])
    ),
  };
};
const datavizControlMatches = (row, item, state) => {
  // Dashboard and Section controls are inherited structurally. A View whose
  // dataset does not expose the selected field is outside that data contract;
  // it must remain visible instead of being reduced to an accidental empty set.
  if (!datavizControlCanApply(row, item)) return true;
  const binding = item.consumer_binding || {};
  const value = datavizControlValueFromState(item.definition || {}, state || {value:null});
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return binding.empty === 'passthrough';
  }
  const pathFields = datavizControlFields(item);
  if (pathFields.length > 1) {
    const paths = Array.isArray(value?.[0]) ? value : [value];
    const matched = paths.some(path => pathFields.every((field, index) => String(row[field] ?? '') === String(path[index] ?? '')));
    return matched;
  }
  const field = pathFields[0];
  const actual = row[field];
  const operator = binding.operator === 'auto'
    ? (['multiple_input', 'multiple_select'].includes(item.definition?.type) ? 'in' : item.definition?.type === 'range_input' ? 'between' : 'equals')
    : binding.operator;
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
const datavizControlIntentKey = input => (
  input?.closest('[data-control-key]')?.dataset.controlKey || null
);
const datavizCaptureControlIntent = input => {
  const key = datavizControlIntentKey(input);
  const consume = window.datavizComponents?.controls?.consumeSelectionIntent;
  if (!key || !consume) return null;
  const intent = consume(input);
  if (intent) datavizControlEntry(key).intent = intent;
  return intent;
};
const datavizReconcileControlOptionDomain = (
  input,
  nextOptions,
  {selectedValues = [], required = input?.required === true} = {},
) => {
  const reconcile = window.datavizComponents?.controls?.reconcileOptionDomain;
  if (!reconcile) {
    input.replaceChildren(...Array.from(nextOptions || []));
    return {intent:null, selectedValues:[]};
  }
  const key = datavizControlIntentKey(input);
  const state = key ? datavizControlEntry(key) : {intent:'explicit', value:[], revision:0};
  const definition = key ? datavizControlDefinition(key) : {};
  const policy = definition.initial || {
    mode:definition.type === 'multiple_select' ? 'all' : 'first',
  };
  const rawInitialValues = policy.mode === 'values'
    ? (policy.values || [])
    : policy.mode === 'value'
      ? [policy.value]
      : [];
  const initialValues = rawInitialValues.map(value => datavizEncodeControlValue(input, value, {
    path:input.closest('[data-control-key]')?.dataset.controlPath === 'true',
  }));
  const result = reconcile(input, nextOptions, {
    selectedValues,
    intent:state.intent,
    required,
    initial:{mode:policy.mode, values:initialValues},
  });
  if (key && result.intent) state.intent = result.intent;
  return result;
};
window.dataviz.control = {
  fields: datavizControlFields,
  canApply: datavizControlCanApply,
  matches: datavizControlMatches,
  captureIntent: datavizCaptureControlIntent,
  reconcileOptionDomain: datavizReconcileControlOptionDomain,
  state: datavizControlEntry,
  value: datavizControlValue,
  set: datavizSetControlValue,
  stateSnapshot: datavizControlStateSnapshot,
};
let datavizControlActionRevision = 0;
let datavizControlActionQueue = Promise.resolve();
const datavizControlBindingForView = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.control_binding || null
);
const datavizControlBindingValue = (binding, datum) => {
  if (datum && Object.prototype.hasOwnProperty.call(datum, '__datavizControlValue')) {
    return structuredClone(datum.__datavizControlValue);
  }
  if (!datum || typeof datum !== 'object') return structuredClone(datum);
  const values = (binding?.fields || []).map(field => datum[field]);
  return values.length === 1 ? values[0] : values;
};
const datavizDispatchControlAction = event => {
  const binding = datavizControlBindingForView(event?.view_id);
  if (!binding || binding.control !== event?.control) {
    return Promise.reject(datavizContractError(
      'control_action_binding_invalid',
      `View ${event?.view_id || 'unknown'} cannot write ${event?.control || 'unknown'}`,
    ));
  }
  const root = document.querySelector(
    `.dv-view[data-view-id="${CSS.escape(event.view_id)}"]`
  );
  if (!root || (
    event.generation != null
    && Number(event.generation) !== Number(root._datavizRenderGeneration || 0)
  )) {
    return Promise.resolve({status:'discarded', reason:'stale_view_generation'});
  }
  datavizControlActionQueue = datavizControlActionQueue.catch(() => undefined).then(async () => {
    const currentRoot = document.querySelector(
      `.dv-view[data-view-id="${CSS.escape(event.view_id)}"]`
    );
    if (!currentRoot || (
      event.generation != null
      && Number(event.generation) !== Number(currentRoot._datavizRenderGeneration || 0)
    )) {
      return {status:'discarded', reason:'stale_view_generation'};
    }
    const definition = datavizControlDefinition(binding.control);
    const current = datavizControlEntry(binding.control);
    let next;
    let value;
    if (event.action === 'reset') {
      next = datavizNormalizeControlState(binding.control);
    } else if (event.action === 'clear') value = definition.type === 'range_input' ? [] : (
      ['multiple_input', 'multiple_select'].includes(definition.type) ? [] : null
    );
    else if (event.action === 'select_many') {
      value = (event.data || []).map(datum => datavizControlBindingValue(binding, datum));
    } else if (event.action === 'select') {
      const selected = datavizControlBindingValue(binding, event.data);
      value = ['multiple_input', 'multiple_select'].includes(definition.type) ? [selected] : selected;
    } else {
      throw datavizContractError(
        'control_action_unknown',
        `Unknown Control action: ${event.action}`,
      );
    }
    if (!next) next = datavizNormalizeControlState(binding.control, {
      intent:'explicit',
      value:datavizNormalizeControlValue(definition, value, {
        namespace:'control', key:binding.control,
      }),
      revision:Number(current.revision || 0),
    });
    if (JSON.stringify(current) === JSON.stringify(next)) {
      return {status:'noop', revision:datavizControlActionRevision};
    }
    next = {...next, revision:Number(current.revision || 0) + 1};
    const revision = ++datavizControlActionRevision;
    datavizControlState()[binding.control] = next;
    setControlInputs({[binding.control]:next});
    await window.dataviz.applyControls({keys:[binding.control]});
    return {status:'committed', revision};
  });
  return datavizControlActionQueue;
};
window.dataviz.controlActions = {
  dispatch:datavizDispatchControlAction,
  binding:datavizControlBindingForView,
  value:datavizControlBindingValue,
  get revision() { return datavizControlActionRevision; },
};
if (window.datavizComponents?.controls) {
  window.datavizComponents.controlPathOptions = ({control, input, levels}) => {
    const viewId = control.dataset.cascaderView;
    const controlKey = control.closest('[data-control-key]')?.dataset.controlKey;
    if (!viewId || !levels?.length) {
      return Array.from(input.options).map(option => {
        try { return JSON.parse(option.value); } catch (_error) { return [option.value]; }
      });
    }
    const contract = datavizViewControlContract(viewId);
    const item = contract.find(candidate => candidate.key === controlKey)
      || datavizControlContractItem(controlKey);
    const dependencyKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[controlKey]?.dependency_ancestors || []
    );
    const upstreamControls = [...dependencyKeys].map(key => (
      contract.find(candidate => candidate.key === key) || datavizControlContractItem(key)
    ));
    const rows = datavizControlDomainReferences(item).flatMap(reference =>
      datavizTableRows(window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)])
    ).filter(row => (
      upstreamControls.length === dependencyKeys.size
      && upstreamControls.every(item => (
        datavizControlCanApply(row, item)
        && datavizControlMatches(row, item, datavizControlEntry(item.key))
      ))
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
const datavizControlOccurrences = () => {
  const occurrences = new Map();
  Object.entries(window.dataviz.dependency_contract?.controls || {}).forEach(([key, dependency]) => {
    const definition = dependency.definition || {};
    (dependency.scope_views || []).forEach(viewId => {
      const filter = datavizViewControlContract(viewId).find(item => item.key === key);
      const item = filter || {
        key,
        id:definition.id || key.split('/').at(-1),
        origin:dependency.origin,
        definition,
        consumer_binding:{
          field:definition.path_fields?.length
            ? definition.path_fields
            : (definition.field || definition.id),
          empty:'passthrough',
          operator:'auto',
        },
      };
      if (!occurrences.has(key)) occurrences.set(key, []);
      occurrences.get(key).push({viewId, item});
    });
  });
  return occurrences;
};
const datavizAvailableControlOptions = targets => {
  const item = targets[0]?.item;
  const definition = item?.definition || {};
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key] || {};
  const hasDependencies = (dependency.depends_on || []).length > 0;
  const values = new Map();
  let observedSource = false;
  let observedDependencyRelation = !hasDependencies;
  targets.forEach(({viewId, item: target}) => {
    const outputRefs = datavizControlDomainReferences(target);
    const upstreamKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[target.key]?.dependency_ancestors || []
    );
    const upstream = datavizViewControlContract(viewId)
      .filter(candidate => upstreamKeys.has(candidate.key));
    outputRefs.forEach(reference => {
      const canonical = canonicalOutputReference(reference);
      const rows = datavizTableRows(window.dataviz.portable?.outputs?.[canonical]);
      // Progressive query branches may publish in any order. An unrelated
      // table being present does not mean it can define this Control's
      // option domain; otherwise a fast sibling branch can clear valid choices
      // before the actual field-bearing branch arrives.
      if (rows.some(row => datavizControlCanApply(row, target))) {
        observedSource = true;
      }
      rows.forEach(row => {
        const relationAvailable = (
          upstream.length === upstreamKeys.size
          && upstream.every(candidate => datavizControlCanApply(row, candidate))
        );
        if (hasDependencies && !relationAvailable) return;
        if (relationAvailable) observedDependencyRelation = true;
        if (!upstream.every(candidate =>
          datavizControlMatches(row, candidate, datavizControlEntry(candidate.key))
        )) return;
        const value = (definition.path_fields || []).length
          ? definition.path_fields.map(field => row[field])
          : row[definition.field || target.id];
        if (value == null || (Array.isArray(value) && value.some(part => part == null))) return;
        values.set(datavizValueSignature(value), value);
      });
    });
  });
  const staticChoices = datavizStaticChoices(definition);
  const options = staticChoices.length
    ? staticChoices.map(choice => ({
      value:choice.value,
      label:choice.label,
      group:choice.group || null,
      description:choice.description || '',
      keywords:choice.keywords || [],
      available:!hasDependencies || values.has(datavizValueSignature(choice.value)),
    }))
    : [...values.values()]
      .sort((left, right) => String(left).localeCompare(String(right)))
      .map(value => ({
        value,
        label:Array.isArray(value) ? value.join(' / ') : String(value),
        available:true,
      }));
  return {
    observed:observedSource,
    dependencyRelationReady:observedDependencyRelation,
    options,
  };
};
const publishDashboardControlOptions = occurrences => {
  if (window.parent === window) return;
  const controls = [];
  occurrences.forEach((targets, key) => {
    if (targets[0]?.item?.origin !== 'dashboard') return;
    controls.push({key, ...datavizAvailableControlOptions(targets)});
  });
  datavizPostToParent({type:'dataviz:control-options-changed', controls});
};
const refreshControlOptionDomains = () => {
  const occurrences = datavizControlOccurrences();
  const controls = Array.from(document.querySelectorAll('[data-control-key]'));
  const order = window.dataviz.dependency_contract?.control_order || [];
  order.forEach(key => {
    const targets = occurrences.get(key) || [];
    if (!targets.length) return;
    controls.filter(control => control.dataset.controlKey === key).forEach(control => {
      const input = control.querySelector('select');
      if (!input) return;
      const definition = targets[0]?.item?.definition || {};
      const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
      if (definition.value_type === 'boolean') {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      const availability = datavizAvailableControlOptions(targets);
      if (availability.observed && !availability.dependencyRelationReady) {
        const message = 'Option-domain rows do not expose every declared dependency field.';
        control.dataset.optionDomainState = 'error';
        control.dataset.optionDomainError = message;
        input.disabled = true;
        input.setCustomValidity(message);
        syncPortableChoices(control);
        return;
      }
      delete control.dataset.optionDomainError;
      input.disabled = false;
      input.setCustomValidity('');
      if (control.querySelector('[data-control-component="cascader"], [data-control-component="tree-select"]')) {
        control.dataset.optionDomainState = availability.observed ? 'ready' : 'pending';
        syncPortableChoices(control);
        return;
      }
      if (!(dependency.depends_on || []).length && datavizStaticChoices(definition).length) {
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
      const currentValue = datavizControlValue(control.dataset.controlKey);
      const currentValues = input.multiple
        ? (Array.isArray(currentValue) ? currentValue : [])
        : [currentValue];
      const selectedValues = currentValues
        .filter(value => !datavizIsEmptyControlValue(value))
        .map(value => datavizEncodeControlValue(input, value, {
          path:control.dataset.controlPath === 'true',
        }));
      const options = [];
      if (!input.multiple && !definition.required) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.hidden = true;
        empty.dataset.emptyOption = 'true';
        options.push(empty);
      }
      availability.options.forEach(item => {
        const option = document.createElement('option');
        option.value = datavizEncodeControlValue(input, item.value, {
          path:control.dataset.controlPath === 'true',
        });
        option.textContent = item.label ?? String(item.value);
        option.disabled = item.available === false;
        if (item.group) option.dataset.group = item.group;
        if (item.description) option.dataset.description = item.description;
        if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
        options.push(option);
      });
      datavizReconcileControlOptionDomain(input, options, {
        selectedValues,
        required:Boolean(definition.required),
      });
      control.dataset.optionAvailable = String(
        availability.options.filter(option => option.available !== false).length
      );
      syncPortableChoices(control);
    });
    // Commit each compiled Control before deriving its declared dependents.
    // The browser does not rebuild Control dependency edges from DOM order.
    readControlInputs({keys:new Set([key])});
  });
  publishDashboardControlOptions(occurrences);
};
const readControlInputs = ({keys = null} = {}) => {
  document.querySelectorAll('[data-control-key]').forEach(control => {
    const key = control.dataset.controlKey;
    if (keys && !keys.has(key)) return;
    const input = control.querySelector('[data-control-state-input]');
    if (!input) return;
    const definition = datavizControlDefinition(key);
    if (
      input.tagName === 'SELECT'
      && control.dataset.optionDomainState === 'pending'
      && Object.prototype.hasOwnProperty.call(datavizControlState(), key)
    ) return;
    const decode = raw => datavizDecodeControlValue(input, raw, {
      path:control.dataset.controlPath === 'true',
    });
    const type = definition.type;
    const valueType = definition.value_type;
    let value;
    if (valueType === 'boolean' && input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (valueType === 'boolean') value = input.checked;
    else if (type === 'multiple_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option => decode(option.value))
      : (datavizControlValue(key) || []);
    else if (type === 'multiple_input') {
      try { value = input.value ? JSON.parse(input.value) : []; }
      catch (_error) { value = input.value.split(',').map(item => item.trim()).filter(Boolean); }
    }
    else if (type === 'range_input') value = input.value
      ? input.value.split(',', 2).map(item => item.trim())
      : [];
    else if (input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (valueType === 'number' || valueType === 'integer') value = input.value === '' ? null : Number(input.value);
    else value = input.value;
    try {
      const intent = input.multiple
        ? (window.datavizComponents?.controls?.inferSelectionIntent(input) || 'explicit')
        : 'explicit';
      datavizSetControlValue(key, value, {intent});
      input.setCustomValidity?.('');
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = '';
        output.hidden = true;
      }
    } catch (error) {
      input.setCustomValidity?.(error.message);
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = error.message;
        output.hidden = false;
      }
      throw error;
    }
  });
};
const datavizControlSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(datavizValueSignature).sort() : value
);
const datavizChangedControlKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizControlSignature(previous[key]) !== datavizControlSignature(current[key])
  );
};
const datavizContentBindings = window.dataviz.content_bindings || {};
const datavizContentAllLabel = () => (
  String(document.documentElement.lang || '').toLocaleLowerCase().startsWith('zh')
    ? '全部'
    : 'All'
);
const datavizContentControl = key => Array.from(
  document.querySelectorAll('[data-control-key]')
).find(control => control.dataset.controlKey === key) || null;
const datavizContentChoiceLabel = (reference, value, control = null) => {
  const input = control?.querySelector('[data-control-state-input]');
  const option = Array.from(input?.options || []).find(candidate => (
    candidate.dataset.emptyOption !== 'true'
    && datavizValueSignature(datavizDecodeControlValue(input, candidate.value, {
      path:control?.dataset?.controlPath === 'true',
    })) === datavizValueSignature(value)
  ));
  if (option) return option.textContent?.trim() || String(value);
  const choice = datavizStaticChoices(reference.definition).find(candidate => (
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
  const control = datavizContentControl(reference.key);
  const value = datavizControlValue(reference.key) ?? definition.default;
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return '';
  }
  if (definition.type === 'range_input') {
    const range = Array.isArray(value) ? value : String(value).split(',', 2);
    return range.filter(item => item != null && item !== '').join(' 至 ');
  }
  if ((definition.path_fields || []).length) {
    const parsed = datavizContentPathValue(value);
    const paths = Array.isArray(parsed?.[0]) ? parsed : [parsed];
    const separator = control?.querySelector('.dv-control')?.dataset.pathSeparator || ' / ';
    return paths
      .filter(path => Array.isArray(path))
      .map(path => path.map(String).join(separator))
      .join('、') || String(value);
  }
  const values = Array.isArray(value) ? value : [value];
  if (Array.isArray(value)) {
    const input = control?.querySelector('[data-control-state-input]');
    const availableOptions = Array.from(input?.options || []).filter(option => (
      option.dataset.emptyOption !== 'true' && !option.disabled
    ));
    const available = availableOptions.map(option => datavizDecodeControlValue(input, option.value, {
      path:control?.dataset?.controlPath === 'true',
    }));
    const choices = datavizStaticChoices(reference.definition);
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
const syncDatavizContentBindings = changedControlKeys => {
  const changed = changedControlKeys == null ? null : new Set(changedControlKeys);
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
// Owner: analysis state projection and live Query/Interactive scheduling.
/*
 * Analysis state is evidence, not another editable control surface. The same
 * canonical snapshot drives Server canvases and exported reports.
 */
const datavizStateSummaryConfig = window.dataviz.state_summary || {
  enabled:false, max_values:3, items:{},
};
const datavizStateItemConfig = item => (
  datavizStateSummaryConfig.items?.[item.key]
  || datavizStateSummaryConfig.items?.[item.id]
  || {}
);
const datavizConsumerRevisionEvidence = () => {
  const contract = window.dataviz.dependency_contract || {};
  const applied = window.dataviz.applied_revisions || {};
  const project = (consumerType, consumerId, bindings, trigger) => {
    const keys = [...new Set(
      Object.values(bindings || {}).map(binding => binding.control).filter(Boolean)
    )].sort();
    if (!keys.length) return null;
    const controls = Object.fromEntries(keys.map(key => {
      const effectiveRevision = Number(datavizControlEntry(key)?.revision || 0);
      const rawApplied = applied?.[consumerType]?.[consumerId]?.[key];
      const appliedRevision = Number.isInteger(rawApplied) && rawApplied >= 0
        ? rawApplied
        : null;
      return [key, {
        effective_revision:effectiveRevision,
        applied_revision:appliedRevision,
        stale:appliedRevision !== effectiveRevision,
      }];
    }));
    return {
      trigger,
      stale:Object.values(controls).some(item => item.stale),
      controls,
    };
  };
  const views = {};
  Object.entries(contract.views || {}).forEach(([id, definition]) => {
    const evidence = project('views', id, definition.control_inputs, 'auto');
    if (evidence) views[id] = evidence;
  });
  const transforms = {};
  Object.entries(contract.interactive?.control_inputs || {}).forEach(([id, bindings]) => {
    const trigger = datavizRuntime.transforms.get(id)?.spec?.trigger || 'auto';
    const evidence = project('transforms', id, bindings, trigger);
    if (evidence) transforms[id] = evidence;
  });
  return {views, transforms};
};
const datavizBuildStateSnapshot = () => {
  const initial = window.dataviz.state_snapshot || {items:[]};
  const queryStale = Boolean(
    window.dataviz.query_stale ?? initial.query_stale
  );
  const items = (initial.items || []).map(item => {
    if (item.entry_type === 'control') {
      const current = structuredClone(datavizControlEntry(item.key));
      const committed = structuredClone(
        window.dataviz.applied_control_state?.[item.key] ?? current
      );
      const draft = structuredClone(
        window.dataviz.draft_control_state?.[item.key] ?? current
      );
      return {
        ...item,
        committed,
        draft,
        stale:datavizControlSignature(committed) !== datavizControlSignature(draft),
      };
    }
    const committed = structuredClone(
      window.dataviz.query_parameters?.[item.id] ?? item.committed
    );
    const draft = structuredClone(
      window.dataviz.draft_query_parameters?.[item.id] ?? item.draft ?? committed
    );
    return {
      ...item,
      committed,
      draft,
      stale:Boolean(window.dataviz.query_definition_stale)
        || datavizValueSignature(committed) !== datavizValueSignature(draft),
    };
  });
  const snapshot = {
    schema:'dataviz/state-snapshot/v2',
    dashboard:window.dataviz.dashboard_id,
    query_stale:queryStale,
    items,
    applied_revisions:structuredClone(
      window.dataviz.applied_revisions || initial.applied_revisions || {}
    ),
    consumer_revisions:datavizConsumerRevisionEvidence(),
  };
  window.dataviz.state_snapshot = snapshot;
  return snapshot;
};
const datavizStateLogicalValue = item => {
  if (item.entry_type !== 'control') return item.committed;
  return datavizControlValueFromState(item.definition || {}, item.committed);
};
const datavizStateChoiceLabel = (definition, value) => {
  const match = datavizStaticChoices(definition || {}).find(
    choice => datavizValueSignature(choice.value) === datavizValueSignature(value)
  );
  return match?.label || (Array.isArray(value) ? value.join(' / ') : String(value ?? ''));
};
const datavizStateValueParts = (item, rawValue, formatter = 'auto') => {
  if (item.entry_type === 'control' && item.committed?.intent === 'all_available') {
    const values = Array.isArray(rawValue) ? rawValue : [];
    return [values.length ? `全部（${values.length}）` : '全部'];
  }
  if (rawValue == null || rawValue === '' || (Array.isArray(rawValue) && rawValue.length === 0)) {
    return ['未选择'];
  }
  if (formatter === 'count') {
    return [String(Array.isArray(rawValue) ? rawValue.length : 1)];
  }
  const isDateRange = formatter === 'date_range'
    || item.type === 'range_input'
    || item.definition?.type === 'range_input';
  if (isDateRange && Array.isArray(rawValue)) return [rawValue.join(' ～ ')];
  const values = Array.isArray(rawValue) ? rawValue : [rawValue];
  return values.map(value => datavizStateChoiceLabel(item.definition, value));
};
const datavizStateItemVisibleIn = (item, scope, ownerId) => {
  if (scope === 'dashboard') return item.entry_type === 'query_parameter' || item.origin === 'dashboard';
  return item.origin === scope && item.owner_id === ownerId;
};
const datavizStateSummaryItem = item => {
  const config = datavizStateItemConfig(item);
  const formatter = config.formatter || 'auto';
  const parts = datavizStateValueParts(item, datavizStateLogicalValue(item), formatter);
  const max = Number(datavizStateSummaryConfig.max_values || 3);
  const label = config.label || item.label || item.id;
  const root = document.createElement(parts.length > max ? 'details' : 'span');
  root.className = 'dv-state-chip';
  root.dataset.stateKey = item.key;
  root.dataset.stateKind = item.entry_type;
  if (item.stale) root.dataset.stateStale = 'true';
  const visible = parts.slice(0, max).join('、');
  const suffix = parts.length > max ? ` +${parts.length - max}` : '';
  const main = document.createElement(parts.length > max ? 'summary' : 'span');
  main.className = 'dv-state-chip__main';
  const name = document.createElement('strong');
  name.textContent = label;
  const value = document.createElement('span');
  value.textContent = `${visible}${suffix}`;
  main.append(name, value);
  root.append(main);
  if (parts.length > max) {
    const expanded = document.createElement('span');
    expanded.className = 'dv-state-chip__expanded';
    expanded.textContent = parts.join('、');
    root.append(expanded);
  }
  if (item.stale) {
    const draftParts = datavizStateValueParts(item, item.draft, formatter);
    const pending = document.createElement('em');
    pending.className = 'dv-state-chip__pending';
    pending.textContent = `待应用：${draftParts.join('、')}`;
    root.append(pending);
  }
  return root;
};
const renderDatavizStateSummaries = () => {
  const snapshot = datavizBuildStateSnapshot();
  document.querySelectorAll('[data-state-summary-scope]').forEach(host => {
    const scope = host.dataset.stateSummaryScope;
    const ownerId = host.dataset.stateSummaryOwner;
    const items = snapshot.items
      .filter(item => datavizStateItemVisibleIn(item, scope, ownerId))
      .filter(item => !datavizStateItemConfig(item).hidden)
      .sort((left, right) => (
        Number(datavizStateItemConfig(left).order || 0)
        - Number(datavizStateItemConfig(right).order || 0)
      ));
    host.replaceChildren(...items.map(datavizStateSummaryItem));
    host.hidden = !datavizStateSummaryConfig.enabled || items.length === 0;
  });
  window.dispatchEvent(new CustomEvent('dataviz:state-snapshot', {
    detail:structuredClone(snapshot),
  }));
  return snapshot;
};
window.dataviz.stateSnapshot = datavizBuildStateSnapshot;
window.dataviz.renderStateSummaries = renderDatavizStateSummaries;
const syncControlDirtyState = () => {
  const changed = datavizChangedControlKeys(
    window.dataviz.applied_control_state || null,
    datavizControlStateSnapshot(),
  ) || [];
  document.querySelectorAll('[data-control-dirty-label]').forEach(node => {
    const button = node.parentElement?.querySelector('[data-control-apply]');
    const scopeKeys = new Set(JSON.parse(button?.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size ? changed.filter(key => scopeKeys.has(key)) : changed;
    node.textContent = localChanged.length
      ? `${localChanged.length} draft change${localChanged.length === 1 ? '' : 's'}`
      : 'Results are current';
  });
  document.querySelectorAll('[data-control-apply]').forEach(button => {
    const scopeKeys = new Set(JSON.parse(button.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size ? changed.filter(key => scopeKeys.has(key)) : changed;
    button.disabled = localChanged.length === 0 && button.dataset.analysisAlways !== 'true';
  });
  renderDatavizStateSummaries();
  return changed;
};
window.dataviz.applyControls = async (options = {}) => {
  const previous = window.dataviz.current_control_state || null;
  // Dynamic selects are empty until their immutable option domain is hydrated;
  // preserve the compiled initial state during the first pass.
  if (previous != null) readControlInputs({keys:options.keys ? new Set(options.keys) : null});
  refreshControlOptionDomains();
  readControlInputs({keys:options.keys ? new Set(options.keys) : null});
  const current = datavizControlStateSnapshot();
  const changed = datavizChangedControlKeys(previous, current);
  window.dataviz.current_control_state = structuredClone(current);
  let affectedViewIds = datavizRuntime.affectedViews(changed, new Set());
  const contentAffected = syncDatavizContentBindings(changed);
  if (affectedViewIds != null) affectedViewIds = [...new Set([...affectedViewIds, ...contentAffected])];
  if (previous == null) {
    window.dataviz.applied_control_state = structuredClone(current);
  } else if (options.apply === true) {
    const keys = options.keys?.length ? options.keys : Object.keys(current);
    window.dataviz.applied_control_state ||= {};
    keys.forEach(key => {
      if (current[key]) {
        window.dataviz.applied_control_state[key] = structuredClone(current[key]);
      }
    });
  } else {
    // Controls consumed only by immediate Views/auto Transforms have no pending
    // Apply lifecycle. Advance their evidence snapshot without committing keys
    // that still feed an apply/manual consumer.
    window.dataviz.applied_control_state ||= {};
    Object.keys(current).forEach(key => {
      const deferred = [...datavizRuntime.transforms].some(([id, item]) => (
        item.spec.trigger !== 'auto'
        && Object.values(datavizRuntime.transformControlInputs(id))
          .some(binding => binding.control === key)
      ));
      if (!deferred) {
        window.dataviz.applied_control_state[key] = structuredClone(current[key]);
      }
    });
  }
  window.dataviz.draft_control_state = structuredClone(current);
  window.dataviz.renderContext = {
    initial:changed == null,
    changedControlKeys:changed || Object.keys(current),
    affectedViewIds,
  };
  syncControlDirtyState();
  if (changed == null || changed.length) datavizRuntime.renderViews(window.dataviz.renderContext);
  const changedOutputs = await datavizRuntime.runTransforms(changed, [], {
    apply:options.apply === true,
    manualTargets:options.manualTargets || [],
    targets:options.targets,
  });
  window.dispatchEvent(new CustomEvent('dataviz:controlchange', {
    detail:{control_state:structuredClone(current), changed:changed || Object.keys(current), outputs:[...changedOutputs]},
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:controls-changed',
      control_state:structuredClone(current),
    });
  }
  datavizRuntime.publishControlImpacts();
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
          output_schemas: {
            [payload.reference]: payload.transport?.schema || payload.artifact?.schema || [],
          },
        });
      })
      .catch(error => {
        fetched.delete(reference);
        datavizSetViewPipelineNodeStatus(
          canonicalOutputReference(reference).split('/')[0],
          'error',
        );
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
  const queryNodeStatuses = {
    node_queued:'queued',
    node_started:'loading',
    node_progress:'loading',
    node_retrying:'loading',
    node_ready:'ready',
    node_error:'error',
    node_cancelled:'cancelled',
    node_unavailable:'unavailable',
  };
  Object.entries(queryNodeStatuses).forEach(([name, status]) => {
    source.addEventListener(name, message => {
      const event = JSON.parse(message.data);
      if (event.run_id !== live.run_id || !event.node_id) return;
      datavizSetViewPipelineNodeStatus(event.node_id, status);
    });
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
const setControlInputs = states => {
  Object.entries(states || {}).forEach(([key, state]) => {
    if (!window.dataviz.dependency_contract?.controls?.[key]) return;
    datavizControlState()[key] = datavizNormalizeControlState(key, state);
  });
  window.dataviz.draft_control_state = structuredClone(datavizControlStateSnapshot());
  document.querySelectorAll('[data-control-key]').forEach(control => {
    const key = control.dataset.controlKey;
    if (!(key in (states || {}))) return;
    const input = control.querySelector('[data-control-state-input]');
    if (!input || input.disabled) return;
    const definition = datavizControlDefinition(key);
    const value = datavizControlValue(key);
    const encode = item => datavizEncodeControlValue(input, item, {
      path:control.dataset.controlPath === 'true',
    });
    if (definition.value_type === 'boolean' && input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (definition.value_type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(encode));
      Array.from(input.options).forEach(option => { option.selected = selected.has(option.value); });
      syncPortableChoices(control);
    } else if (definition.type === 'range_input' && Array.isArray(value)) input.value = value.length ? value.join(',') : '';
    else if (input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (definition.type === 'multiple_input' && Array.isArray(value)) input.value = JSON.stringify(value);
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  });
  syncControlDirtyState();
};
window.addEventListener('message', event => {
  if (
    event.origin !== window.location.origin
    || window.parent === window
    || event.source !== window.parent
    || !datavizSameFrameIdentity(event.data)
  ) return;
  if (event.data?.type === 'dataviz:set-controls') {
    const states = event.data.control_state || {};
    setControlInputs(states);
    if (event.data.commit !== false) {
      window.dataviz.applyControls({
        keys:event.data.control_keys || Object.keys(states),
        apply:event.data.apply !== false,
        manualTargets:event.data.manual_targets || [],
      }).catch(error => console.error('[dataviz:controls]', error));
    }
  }
  if (event.data?.type === 'dataviz:set-query-draft') {
    window.dataviz.draft_query_parameters = structuredClone(
      event.data.query_parameters || {}
    );
    window.dataviz.query_stale = Boolean(event.data.query_stale);
    window.dataviz.query_definition_stale = Boolean(
      event.data.query_definition_stale
    );
    renderDatavizStateSummaries();
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
      datavizRuntime.runTransforms([], [], {targets})
        .catch(error => console.error('[dataviz:interaction]', error));
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
        control_state:datavizControlStateSnapshot(),
        state_snapshot:datavizBuildStateSnapshot(),
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
// Owner: DOM/bootstrap event wiring after every Runtime owner is registered.
let datavizControlScheduled = false;
let datavizControlQueue = Promise.resolve();
const scheduleDatavizControl = event => {
  // Capture the user's native control value before asynchronous initialization
  // or option-domain reconciliation can rebuild the underlying <select>.
  try {
    datavizCaptureControlIntent(event?.currentTarget || event?.target);
    readControlInputs();
  } catch (error) {
    console.error('[dataviz:controls]', error);
    return;
  }
  if (datavizControlScheduled) return;
  datavizControlScheduled = true;
  queueMicrotask(() => {
    datavizControlScheduled = false;
    // A native select emits both input and change for one user action. Coalesce
    // that event pair in the current task, then serialize any later actions
    // behind the in-flight Interactive branch. Control state is an immediate data
    // contract; it must not depend on a browser timer being scheduled promptly.
    const initialization = datavizRuntime.initializationPromise || Promise.resolve();
    datavizControlQueue = Promise.all([
      datavizControlQueue.catch(() => undefined),
      initialization.catch(() => undefined),
    ])
      .then(() => window.dataviz.applyControls())
      .catch(error => console.error('[dataviz:controls]', error));
  });
};
const datavizEscape = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

// The Server shell and Canvas iframe form one vertical reading surface. While
// the shell still has scrollable Header content (for example an expanded Query
// tray), consume downward wheel movement there before scrolling the iframe.
// On the way back, reveal the Header only after the Canvas has reached its top.
// Portable reports run at the top level and therefore bypass this bridge.
const routeDatavizCanvasWheelToShell = event => {
  if (window.parent === window || event.ctrlKey || !event.deltaY) return;
  let parentWindow;
  let parentDocument;
  try {
    parentWindow = window.parent;
    parentDocument = parentWindow.document;
    const frame = parentDocument.querySelector('#canvas-frame');
    if (frame?.contentWindow !== window) return;
  } catch (_) {
    return;
  }
  const shellScroller = parentDocument.scrollingElement;
  const canvasScroller = document.scrollingElement;
  if (!shellScroller || !canvasScroller) return;
  const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
    ? 16
    : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
      ? parentWindow.innerHeight
      : 1;
  const delta = event.deltaY * unit;
  const shellMax = Math.max(0, shellScroller.scrollHeight - parentWindow.innerHeight);
  const shellTop = shellScroller.scrollTop;
  const canvasTop = canvasScroller.scrollTop;
  const routeDown = delta > 0 && shellTop < shellMax - 1;
  const routeUp = delta < 0 && canvasTop <= 1 && shellTop > 1;
  if (!routeDown && !routeUp) return;
  event.preventDefault();
  parentWindow.scrollBy({top: delta, left: 0, behavior: 'auto'});
};
window.addEventListener('wheel', routeDatavizCanvasWheelToShell, {
  capture: true,
  passive: false,
});

const syncPortableChoices = control => control.querySelector('.dv-control')?._syncControl?.();
const datavizRuntimeQueryToggle = document.querySelector('[data-runtime-query-toggle]');
const datavizRuntimeQueryPanel = document.querySelector('#dv-runtime-query-panel');
const datavizRuntimeShortcutHelp = document.querySelector('[data-runtime-shortcut-help]');
const datavizRuntimeShortcutToast = document.querySelector('[data-runtime-shortcut-toast]');
let datavizRuntimeShortcutToastTimer;
const showDatavizRuntimeShortcutToast = message => {
  if (!datavizRuntimeShortcutToast) return;
  clearTimeout(datavizRuntimeShortcutToastTimer);
  datavizRuntimeShortcutToast.textContent = message;
  datavizRuntimeShortcutToast.hidden = false;
  requestAnimationFrame(() => datavizRuntimeShortcutToast.classList.add('is-visible'));
  datavizRuntimeShortcutToastTimer = setTimeout(() => {
    datavizRuntimeShortcutToast.classList.remove('is-visible');
    datavizRuntimeShortcutToastTimer = setTimeout(() => {
      datavizRuntimeShortcutToast.hidden = true;
    }, 160);
  }, 1800);
};
const setDatavizRuntimeQueryOpen = open => {
  if (!datavizRuntimeQueryToggle || !datavizRuntimeQueryPanel) return false;
  const expanded = Boolean(open);
  const tray = datavizRuntimeQueryPanel.closest('.dv-runtime-query-tray');
  datavizRuntimeQueryToggle.setAttribute('aria-expanded', String(expanded));
  datavizRuntimeQueryToggle.setAttribute(
    'aria-label',
    expanded ? 'Collapse query parameters' : 'Expand query parameters',
  );
  datavizRuntimeQueryToggle.title = `${expanded ? 'Collapse query parameters' : 'Expand query parameters'} (Q)`;
  if (tray) tray.dataset.open = String(expanded);
  datavizRuntimeQueryPanel.hidden = !expanded;
  return expanded;
};
datavizRuntimeQueryToggle?.addEventListener('click', () => {
  setDatavizRuntimeQueryOpen(
    datavizRuntimeQueryToggle.getAttribute('aria-expanded') !== 'true',
  );
});
const datavizKeyboardTargetIsEditable = target => target instanceof Element && Boolean(
  target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')
);
const datavizKeyboardShortcutCommand = event => {
  if (event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229) return null;
  if (document.querySelector('dialog[open]')) return null;
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key === 'Enter') return 'run-query';
  if (event.ctrlKey || event.metaKey || event.altKey || datavizKeyboardTargetIsEditable(event.target)) return null;
  if (event.key.toLowerCase() === 'q') return 'toggle-query-parameters';
  if (event.key.toLowerCase() === 'b') return 'toggle-sidebar';
  if (event.key === '?') return 'show-shortcuts';
  return null;
};
document.addEventListener('keydown', event => {
  const command = datavizKeyboardShortcutCommand(event);
  if (!command) return;
  if (window.parent !== window) {
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    event.preventDefault();
    datavizPostToParent({type:'dataviz:keyboard-shortcut', command});
    return;
  }
  if (command === 'toggle-query-parameters' && datavizRuntimeQueryToggle) {
    event.preventDefault();
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    const tray = datavizRuntimeQueryPanel?.closest('.dv-runtime-query-tray');
    if (Number(tray?.dataset.controlCount || 0) <= 0) {
      showDatavizRuntimeShortcutToast('当前报告没有查询参数');
      return;
    }
    setDatavizRuntimeQueryOpen(
      datavizRuntimeQueryToggle.getAttribute('aria-expanded') !== 'true',
    );
  } else if (command === 'show-shortcuts' && datavizRuntimeShortcutHelp) {
    event.preventDefault();
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    datavizRuntimeShortcutHelp.showModal();
  }
});
window.datavizComponents?.hydrate(document);
document.querySelectorAll('[data-control-state-input]').forEach(input => {
  input.addEventListener('input', scheduleDatavizControl);
  input.addEventListener('change', scheduleDatavizControl);
});
document.querySelectorAll('[data-control-apply]').forEach(button => {
  button.addEventListener('click', () => window.dataviz.applyControls({
    apply:true,
    keys:JSON.parse(button.dataset.controlKeys || '[]'),
    manualTargets:JSON.parse(button.dataset.manualTargets || '[]'),
  }).catch(error => {
    console.error('[dataviz:control:apply]', error);
  }));
});
syncControlDirtyState();
if (window.dataviz.asset_mode === 'server') {
  document.querySelectorAll('.dv-context-controls[data-editor-owner] > summary').forEach(trigger => {
    trigger.addEventListener('contextmenu', event => {
      event.preventDefault();
      event.stopPropagation();
      datavizPostToParent({
        type:'dataviz:open-parameter-editor',
        owner:trigger.parentElement.dataset.editorOwner,
      });
    });
  });
}
document.addEventListener('pointerdown', () => {
  if (window.parent !== window) {
    datavizPostToParent({type: 'dataviz:canvas-interaction'});
  }
}, {capture: true});
document.addEventListener('click', event => {
  const signal = event.target.closest('[data-view-pipeline-signal]');
  if (!signal) return;
  signal.blur();
  const title = signal.getAttribute('title');
  signal.removeAttribute('title');
  signal.addEventListener('pointerleave', () => {
    if (title) signal.setAttribute('title', title);
  }, {once:true});
  datavizPostToParent({
    type:'dataviz:view-pipeline-inspect',
    node_id:signal.dataset.viewPipelineNode,
  });
});
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
window.dataviz.getViewControls = viewId => {
  const contract = datavizViewControlContract(viewId);
  return Object.fromEntries(
    contract.map(item => [item.id, datavizControlValue(item.key)])
  );
};
window.datavizRuntimeServices = Object.freeze({
  canonicalOutputReference,
  tableRows:datavizTableRows,
  numericAggregate:datavizNumericAggregate,
  workerValue:datavizWorkerValue,
  controlCanApply:datavizControlCanApply,
  controlMatches:datavizControlMatches,
  runtimeError:datavizRuntimeError,
  escape:datavizEscape,
  decodeSpec:node => JSON.parse(new TextDecoder().decode(Uint8Array.from(
    atob(node.dataset.spec),
    value => value.charCodeAt(0),
  ))),
});
window.dispatchEvent(new CustomEvent('dataviz:runtime-ready', {detail: datavizRuntime}));
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
