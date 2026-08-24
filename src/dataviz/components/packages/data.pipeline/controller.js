(function installDataPipelinePackage(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.dataPipeline) return;

  class DatavizFrame {
    constructor(rows = [], numericAggregate) {
      this._rows = Array.isArray(rows) ? rows : [];
      this._numericAggregate = numericAggregate;
    }
    rows() { return this._rows.map(row => ({...row})); }
    column(name) { return this._rows.map(row => row[name]); }
    filter(predicate) { return new DatavizFrame(this._rows.filter(predicate), this._numericAggregate); }
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
      }), this._numericAggregate);
    }
    sort(field, direction = 'asc') {
      const sign = direction === 'desc' ? -1 : 1;
      return new DatavizFrame([...this._rows].sort((left, right) => {
        const a = left[field], b = right[field];
        return (typeof a === 'number' && typeof b === 'number'
          ? a - b
          : String(a).localeCompare(String(b))) * sign;
      }), this._numericAggregate);
    }
    limit(count) { return new DatavizFrame(this._rows.slice(0, count), this._numericAggregate); }
    groupBy(...fields) {
      return new DatavizGroupedFrame(this._rows, fields.flat(), this._numericAggregate);
    }
  }

  class DatavizGroupedFrame {
    constructor(rows, fields, numericAggregate) {
      this._rows = rows;
      this._fields = fields;
      this._numericAggregate = numericAggregate;
    }
    aggregate(spec) {
      const groups = new Map();
      this._rows.forEach(row => {
        const key = JSON.stringify(this._fields.map(field => row[field]));
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(row);
      });
      const rows = [...groups.entries()].map(([key, values]) => {
        const keys = JSON.parse(key);
        const result = Object.fromEntries(
          this._fields.map((field, index) => [field, keys[index]])
        );
        Object.entries(spec).forEach(([output, rule]) => {
          const definition = typeof rule === 'string' ? {field: output, op: rule} : rule;
          result[output] = this._numericAggregate(
            values,
            definition.op,
            row => row[definition.field],
          );
        });
        return result;
      });
      return new DatavizFrame(rows, this._numericAggregate);
    }
  }

  function createInteractiveAdapters(runtime, services) {
    const workerValue = services.workerValue;
    const cancel = id => runtime.activeTransforms.get(id)?.cancel('Cancelled by Runtime Adapter');
    return {
      'browser-js': {
        validate:item => {
          if (typeof item.source?.code !== 'string') throw new Error('browser-js code is missing');
        },
        prepare:async (_item, inputs) => Object.fromEntries(
          Object.entries(inputs).map(([name, value]) => [name, workerValue(value)])
        ),
        execute:(id, item, inputs) => runtime.executeBrowserRuntime(id, item, inputs),
        cancel,
        dispose:() => {},
      },
      'browser-python': {
        validate:item => {
          if (typeof item.source?.code !== 'string') throw new Error('browser-python code is missing');
        },
        prepare:async (_item, inputs) => Object.fromEntries(
          Object.entries(inputs).map(([name, value]) => [name, workerValue(value)])
        ),
        execute:(id, item, inputs) => runtime.executeBrowserRuntime(id, item, inputs),
        cancel,
        dispose:() => {},
      },
      'server-python': {
        validate:item => {
          if (item.spec.export?.mode === 'interactive') {
            throw new Error('server-python cannot export as interactive');
          }
        },
        prepare:async (_item, inputs) => inputs,
        execute:(id, item, _inputs, options) => runtime.executeServerPython(id, item, options),
        cancel,
        dispose:() => {},
      },
    };
  }

  function createDataApi(services) {
    const {canonicalOutputReference, tableRows, numericAggregate} = services;
    return {
      output: reference => global.dataviz.portable?.outputs?.[canonicalOutputReference(reference)],
      table: reference => new DatavizFrame(
        tableRows(global.dataviz.portable?.outputs?.[canonicalOutputReference(reference)]),
        numericAggregate,
      ),
      frame: rows => new DatavizFrame(rows, numericAggregate),
    };
  }

  root.dataPipeline = {
    protocol:'dataviz/runtime/v2',
    createInteractiveAdapters,
    createDataApi,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('data.pipeline', {
    protocol:'dataviz/runtime/v2',
    owns:['interactive-adapters', 'data-frame'],
  });
})(window);
