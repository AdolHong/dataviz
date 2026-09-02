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
      const rules = Object.entries(spec).map(([output, rule]) => {
        const definition = typeof rule === 'string' ? {field: output, op: rule} : rule;
        return {output, field: definition.field, operation: definition.op || 'sum'};
      });
      const groups = new Map();
      this._rows.forEach(row => {
        const keys = this._fields.map(field => row[field]);
        const signature = JSON.stringify(keys);
        if (!groups.has(signature)) {
          groups.set(signature, {
            keys,
            stats: rules.map(() => ({count:0, sum:0, minimum:Infinity, maximum:-Infinity})),
          });
        }
        const group = groups.get(signature);
        rules.forEach((rule, index) => {
          const value = Number(row[rule.field] ?? 0);
          const stats = group.stats[index];
          stats.count += 1;
          stats.sum += value;
          if (value < stats.minimum) stats.minimum = value;
          if (value > stats.maximum) stats.maximum = value;
        });
      });
      const rows = [...groups.values()].map(group => {
        const result = Object.fromEntries(
          this._fields.map((field, index) => [field, group.keys[index]])
        );
        rules.forEach((rule, index) => {
          const stats = group.stats[index];
          if (rule.operation === 'count') result[rule.output] = stats.count;
          else if (rule.operation === 'mean') result[rule.output] = stats.sum / Math.max(stats.count, 1);
          else if (rule.operation === 'min') result[rule.output] = stats.minimum;
          else if (rule.operation === 'max') result[rule.output] = stats.maximum;
          else result[rule.output] = stats.sum;
        });
        return result;
      });
      return new DatavizFrame(rows, this._numericAggregate);
    }
  }

  function selectedWorkerInputs(item, inputs, services, options = {}) {
    const transformInputs = global.dataviz.dependency_contract
      ?.interactive?.control_inputs?.[item.spec.id] || {};
    const filters = Object.values(transformInputs)
      .filter(binding => binding.mode === 'filter')
      .map(binding => ({
        binding,
        contract:global.dataviz.dependency_contract.controls[binding.control],
        state:options.controlState?.[binding.control]
          || global.dataviz.control.state(binding.control),
      }));
    const prepared = Object.fromEntries(
      Object.entries(inputs).map(([name, value]) => [name, services.workerValue(value)])
    );
    if (!filters.length) return prepared;

    const filterRows = rows => {
      if (!Array.isArray(rows) || !rows.some(row => row && typeof row === 'object' && !Array.isArray(row))) {
        return rows;
      }
      return rows.filter(row => filters.every(({binding, contract, state}) => (
        services.controlMatches(row, {...contract, consumer_binding:binding}, state)
      )));
    };
    const filterColumnar = table => {
      const columns = table?.columns || {};
      const length = Number(table?.length || 0);
      const applicable = filters.filter(({binding}) => {
        const fields = Array.isArray(binding.field) ? binding.field : [binding.field];
        return fields.every(field => Object.prototype.hasOwnProperty.call(columns, field));
      });
      if (!applicable.length || !length) return table;
      const indices = [];
      for (let index = 0; index < length; index += 1) {
        const row = Object.fromEntries(
          Object.entries(columns).map(([name, values]) => [name, values[index]])
        );
        if (applicable.every(({binding, contract, state}) => services.controlMatches(
          row, {...contract, consumer_binding:binding}, state
        ))) {
          indices.push(index);
        }
      }
      return {
        ...table,
        length:indices.length,
        columns:Object.fromEntries(
          Object.entries(columns).map(([name, values]) => [
            name,
            indices.map(index => values[index]),
          ])
        ),
      };
    };
    return Object.fromEntries(Object.entries(prepared).map(([name, value]) => {
      if (value?.__datavizColumnarTable) return [name, filterColumnar(value)];
      return [name, filterRows(value)];
    }));
  }

  function createInteractiveAdapters(runtime, services) {
    const workerValue = services.workerValue;
    const cancel = id => runtime.activeTransforms.get(id)?.cancel('Cancelled by Runtime Adapter');
    return {
      'browser-js': {
        validate:item => {
          if (typeof item.source?.code !== 'string') throw new Error('browser-js code is missing');
        },
        prepare:async (item, inputs, options) => selectedWorkerInputs(
          item, inputs, services, options,
        ),
        execute:(id, item, inputs, options) => runtime.executeBrowserRuntime(
          id, item, inputs, options,
        ),
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
    protocol:'dataviz/runtime/v14',
    createInteractiveAdapters,
    createDataApi,
    selectedWorkerInputs,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('data.pipeline', {
    protocol:'dataviz/runtime/v14',
    owns:['interactive-adapters', 'data-frame'],
  });
})(window);
