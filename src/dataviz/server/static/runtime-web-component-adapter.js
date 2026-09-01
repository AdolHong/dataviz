(function installDatavizWebComponentAdapter(global) {
  'use strict';

  const PROTOCOL = 'dataviz/runtime/v12';
  const canonical = reference => {
    const raw = String(reference || '').trim();
    if (!raw) throw new Error('Output reference cannot be empty');
    if (!/^(source|dataset|interactive):[^/]+\/[^/]+$/.test(raw)) {
      throw new Error(`Output reference must be explicit: ${raw}`);
    }
    return raw;
  };
  const rows = value => {
    if (value?.__datavizArrowOutput && typeof value.rows === 'function') return value.rows();
    return Array.isArray(value) ? value : [];
  };
  const fields = item => Array.isArray(item.consumer_binding?.field)
    ? item.consumer_binding.field
    : [item.consumer_binding?.field].filter(Boolean);
  const canApply = (row, item) => row && typeof row === 'object'
    && fields(item).every(field => Object.prototype.hasOwnProperty.call(row, field));
  const contractError = (code, message, details = {}) => {
    const error = new Error(message);
    error.code = code;
    error.details = {code, ...details};
    return error;
  };
  const orderedOperators = new Set(['between', 'gte', 'lte', 'gt', 'lt']);
  const operatorsByType = {
    text:new Set(['equals', 'in', 'contains']),
    integer:new Set(['equals', 'in', ...orderedOperators]),
    number:new Set(['equals', 'in', ...orderedOperators]),
    date:new Set(['equals', 'in', ...orderedOperators]),
    boolean:new Set(['equals', 'in']),
  };
  const coerce = (value, valueType, role) => {
    if (value == null) return null;
    const invalid = () => contractError(
      'control_filter_value_invalid',
      `Control filter ${role} cannot be converted to ${valueType}`,
      {value_type:valueType, role, value},
    );
    if (valueType === 'text') return String(value);
    if (valueType === 'boolean') {
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string' && ['true', 'false'].includes(value.trim().toLowerCase())) {
        return value.trim().toLowerCase() === 'true';
      }
      throw invalid();
    }
    if (valueType === 'integer' || valueType === 'number') {
      if (typeof value === 'boolean' || value === '') throw invalid();
      const numeric = Number(value);
      if (!Number.isFinite(numeric) || (valueType === 'integer' && !Number.isInteger(numeric))) {
        throw invalid();
      }
      return numeric;
    }
    if (valueType === 'date') {
      if (value instanceof Date && !Number.isNaN(value.getTime())) {
        return value.toISOString().slice(0, 10);
      }
      if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) throw invalid();
      const normalized = value.trim();
      const parsed = new Date(`${normalized}T00:00:00Z`);
      if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== normalized) throw invalid();
      return normalized;
    }
    throw invalid();
  };
  const typedMatch = (actual, value, operator, valueType) => {
    if (!operatorsByType[valueType]?.has(operator)) {
      throw contractError(
        'control_filter_operator_incompatible',
        `Control filter operator ${operator} is not valid for ${valueType}`,
        {operator, value_type:valueType},
      );
    }
    if (actual == null) return false;
    const comparable = coerce(actual, valueType, 'field');
    const bound = item => coerce(item, valueType, 'bound');
    if (operator === 'in') {
      return (Array.isArray(value) ? value : [value]).map(bound).some(item => item === comparable);
    }
    if (operator === 'between') {
      const range = Array.isArray(value) ? value : [];
      const lower = range[0] == null || range[0] === '' ? null : bound(range[0]);
      const upper = range[1] == null || range[1] === '' ? null : bound(range[1]);
      return (lower == null || comparable >= lower) && (upper == null || comparable <= upper);
    }
    if (operator === 'contains') return comparable.includes(bound(value));
    const expected = bound(value);
    if (operator === 'gte') return comparable >= expected;
    if (operator === 'lte') return comparable <= expected;
    if (operator === 'gt') return comparable > expected;
    if (operator === 'lt') return comparable < expected;
    return comparable === expected;
  };
  const projectedValue = (item, state) => {
    return structuredClone(state?.value);
  };
  const matches = (row, item, state) => {
    if (!canApply(row, item)) return true;
    const value = projectedValue(item, state);
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
      return item.consumer_binding?.empty === 'passthrough';
    }
    const pathFields = fields(item);
    if (pathFields.length > 1) {
      const paths = Array.isArray(value?.[0]) ? value : [value];
      return paths.some(path => pathFields.every(
        (field, index) => String(row[field] ?? '') === String(path[index] ?? ''),
      ));
    }
    const actual = row[pathFields[0]];
    const operator = item.consumer_binding?.operator === 'auto'
      ? (['multiple_input', 'multiple_select'].includes(item.definition?.type) ? 'in'
        : item.definition?.type === 'range_input' ? 'between' : 'equals')
      : item.consumer_binding?.operator;
    return typedMatch(
      actual,
      value,
      operator,
      String(item.definition?.value_type || 'text'),
    );
  };

  class DatavizRuntimeV3Client {
    constructor(manifest) {
      if (manifest?.protocol?.schema !== PROTOCOL) {
        throw new Error(`Unsupported Dataviz Runtime protocol: ${manifest?.protocol?.schema || 'missing'}`);
      }
      this.manifest = manifest;
    }
    static fromWindow() { return new DatavizRuntimeV3Client(global.dataviz); }
    output(reference) {
      return this.manifest.portable?.outputs?.[canonical(reference)];
    }
    view(id) {
      return (this.manifest.view_specs || []).find(view => view.id === id) || null;
    }
    viewInputReferences(id) {
      return this.manifest.dependency_contract?.views?.[id]?.inputs || {};
    }
    viewRows(id, input = 'main') {
      const references = this.viewInputReferences(id);
      const reference = references[input] || Object.values(references)[0];
      const source = rows(this.output(reference));
      const contract = this.manifest.dependency_contract?.views?.[id]?.filter_contract || [];
      return source.filter(row => contract.every(item => matches(
        row, item, this.manifest.control_state?.[item.key],
      )));
    }
  }

  const escape = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  class DatavizOutputElement extends HTMLElement {
    connectedCallback() {
      this._listener = () => this.render();
      ['dataviz:ready', 'dataviz:controlchange', 'dataviz:outputschange']
        .forEach(name => global.addEventListener(name, this._listener));
      this.render();
    }
    disconnectedCallback() {
      ['dataviz:ready', 'dataviz:controlchange', 'dataviz:outputschange']
        .forEach(name => global.removeEventListener(name, this._listener));
    }
    render() {
      try {
        const client = DatavizRuntimeV3Client.fromWindow();
        const view = this.getAttribute('view');
        const value = view
          ? client.viewRows(view, this.getAttribute('input') || 'main')
          : client.output(this.getAttribute('output'));
        const mode = this.getAttribute('mode') || 'json';
        if (mode === 'count') {
          this.textContent = String(Array.isArray(value) ? value.length : (value == null ? 0 : 1));
          return;
        }
        if (mode === 'table' && Array.isArray(value)) {
          const limit = Math.max(1, Number(this.getAttribute('limit') || 20));
          const columns = [...new Set(value.slice(0, limit).flatMap(row => Object.keys(row || {})))];
          this.innerHTML = value.length
            ? `<table><thead><tr>${columns.map(column => `<th>${escape(column)}</th>`).join('')}</tr></thead>`
              + `<tbody>${value.slice(0, limit).map(row => `<tr>${columns.map(column => `<td>${escape(row?.[column])}</td>`).join('')}</tr>`).join('')}</tbody></table>`
            : '<p data-empty>No rows</p>';
          return;
        }
        this.innerHTML = `<pre>${escape(JSON.stringify(value, null, 2))}</pre>`;
      } catch (error) {
        this.innerHTML = `<p data-error>${escape(error.message)}</p>`;
      }
    }
  }

  global.DatavizRuntimeV3Client = DatavizRuntimeV3Client;
  if (!global.customElements.get('dataviz-output')) {
    global.customElements.define('dataviz-output', DatavizOutputElement);
  }
})(window);
