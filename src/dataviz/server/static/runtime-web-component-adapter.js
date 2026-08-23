(function installDatavizWebComponentAdapter(global) {
  'use strict';

  const PROTOCOL = 'dataviz/runtime/v1';
  const canonical = reference => {
    const raw = String(reference || '').trim();
    if (!raw) throw new Error('Output reference cannot be empty');
    const node = raw.includes(':') ? raw : `source:${raw}`;
    return node.includes('/') ? node : `${node}/main`;
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
  const matches = (row, item, value) => {
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return true;
    if (!canApply(row, item)) return true;
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
    if (operator === 'between') return !Array.isArray(value) || value.length < 2
      || (String(actual) >= String(value[0]) && String(actual) <= String(value[1]));
    if (operator === 'contains') return String(actual ?? '').includes(String(value ?? ''));
    if (operator === 'gte') return Number(actual) >= Number(value);
    if (operator === 'lte') return Number(actual) <= Number(value);
    if (operator === 'gt') return Number(actual) > Number(value);
    if (operator === 'lt') return Number(actual) < Number(value);
    return String(actual ?? '') === String(value ?? '');
  };

  class DatavizRuntimeV1Client {
    constructor(manifest) {
      if (manifest?.protocol?.schema !== PROTOCOL) {
        throw new Error(`Unsupported Dataviz Runtime protocol: ${manifest?.protocol?.schema || 'missing'}`);
      }
      this.manifest = manifest;
    }
    static fromWindow() { return new DatavizRuntimeV1Client(global.dataviz); }
    output(reference) {
      return this.manifest.portable?.outputs?.[canonical(reference)];
    }
    view(id) {
      return (this.manifest.view_specs || []).find(view => view.id === id) || null;
    }
    viewInputReferences(id) {
      return this.manifest.portable?.view_inputs?.[id] || this.view(id)?.inputs || {};
    }
    viewRows(id, input = 'main') {
      const references = this.viewInputReferences(id);
      const reference = references[input] || Object.values(references)[0];
      const source = rows(this.output(reference));
      const contract = this.manifest.portable?.selection_contract?.[id] || [];
      return source.filter(row => contract.every(item => matches(
        row, item, this.manifest.selections?.[item.key],
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
        const client = DatavizRuntimeV1Client.fromWindow();
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

  global.DatavizRuntimeV1Client = DatavizRuntimeV1Client;
  if (!global.customElements.get('dataviz-output')) {
    global.customElements.define('dataviz-output', DatavizOutputElement);
  }
})(window);
