(function installDatavizWebComponentAdapter(global) {
  'use strict';

  const PROTOCOL = 'dataviz/runtime/v5';
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
  const fields = item => item.definition?.path_fields?.length
    ? item.definition.path_fields
    : [item.binding?.field || item.id];
  const canApply = (row, item) => row && typeof row === 'object'
    && fields(item).every(field => Object.prototype.hasOwnProperty.call(row, field));
  const projectedValue = (item, state) => {
    const values = Array.isArray(state?.values) ? state.values : [];
    if (item.definition?.type === 'multi_select') return values;
    if (item.definition?.type === 'date_range') return values.length ? values[0] : [];
    return values.length ? values[0] : null;
  };
  const matches = (row, item, state) => {
    if (!canApply(row, item)) return true;
    const value = projectedValue(item, state);
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return false;
    const pathFields = item.definition?.path_fields || [];
    if (pathFields.length) {
      const paths = Array.isArray(value?.[0]) ? value : [value];
      return paths.some(path => pathFields.every(
        (field, index) => String(row[field] ?? '') === String(path[index] ?? ''),
      ));
    }
    const actual = row[item.binding?.field || item.id];
    const operator = item.binding?.operator === 'auto'
      ? (item.definition?.type === 'multi_select' ? 'in'
        : item.definition?.type === 'date_range' ? 'between' : 'equals')
      : item.binding?.operator;
    if (operator === 'in') return (Array.isArray(value) ? value : [value]).map(String).includes(String(actual));
    if (operator === 'between') {
      const range = Array.isArray(value) ? value : [];
      return (!range[0] || String(actual) >= String(range[0]))
        && (!range[1] || String(actual) <= String(range[1]));
    }
    if (operator === 'contains') return String(actual ?? '').includes(String(value ?? ''));
    if (operator === 'gte') return Number(actual) >= Number(value);
    if (operator === 'lte') return Number(actual) <= Number(value);
    if (operator === 'gt') return Number(actual) > Number(value);
    if (operator === 'lt') return Number(actual) < Number(value);
    return String(actual ?? '') === String(value ?? '');
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
      const contract = this.manifest.dependency_contract?.views?.[id]?.selection_contract || [];
      return source.filter(row => contract.every(item => matches(
        row, item, this.manifest.selection_state?.[item.key],
      )));
    }
  }

  const escape = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  class DatavizOutputElement extends HTMLElement {
    connectedCallback() {
      this._listener = () => this.render();
      ['dataviz:ready', 'dataviz:selectionchange', 'dataviz:outputschange']
        .forEach(name => global.addEventListener(name, this._listener));
      this.render();
    }
    disconnectedCallback() {
      ['dataviz:ready', 'dataviz:selectionchange', 'dataviz:outputschange']
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
