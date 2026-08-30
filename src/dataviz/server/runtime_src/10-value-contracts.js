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
