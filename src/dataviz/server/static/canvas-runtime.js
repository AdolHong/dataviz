
const DATAVIZ_RUNTIME_PROTOCOL = 'dataviz/runtime/v1';
const DATAVIZ_BROWSER_WORKER_PROTOCOL = 'dataviz/browser-transform-worker/v1';
if (window.dataviz.protocol?.schema !== DATAVIZ_RUNTIME_PROTOCOL) {
  throw new Error(`Unsupported Dataviz Runtime protocol: ${window.dataviz.protocol?.schema || 'missing'}`);
}
const canonicalOutputReference = reference => {
  const raw = String(reference || '').trim();
  if (!raw) throw new Error('Output reference cannot be empty');
  const node = raw.includes(':') ? raw : `source:${raw}`;
  return node.includes('/') ? node : `${node}/main`;
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
}
const datavizTableRows = value => value?.__datavizArrowOutput ? value.rows() : (Array.isArray(value) ? value : []);
const datavizMaterializeOutput = value => value?.__datavizArrowOutput ? value.rows() : value;
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
const validateBrowserOutput = (transformId, name, value, definition = {}) => {
  const label = `Browser Transform ${transformId}/${name}`;
  if (definition.kind === 'table' && !Array.isArray(value)) throw new Error(`${label} must return rows[]`);
  if (definition.kind === 'scalar' && value !== null && !['string', 'number', 'boolean'].includes(typeof value)) throw new Error(`${label} must return a scalar`);
  if (definition.kind === 'text' && typeof value !== 'string') throw new Error(`${label} must return text`);
  if (definition.kind === 'object' && (!value || typeof value !== 'object' || Array.isArray(value))) throw new Error(`${label} must return an object`);
  if (definition.kind === 'table') {
    const schema = definition.schema || [];
    const missing = schema.filter(column => column.required !== false && value.some(row => !(column.name in row))).map(column => column.name);
    const nulls = schema.filter(column => column.nullable === false && value.some(row => row[column.name] == null)).map(column => column.name);
    if (missing.length || nulls.length) throw new Error(`${label} schema mismatch; missing=${missing.join(',')} nulls=${nulls.join(',')}`);
  }
};
const datavizRuntime = window.datavizRuntime = {
  transforms: new Map(),
  views: new Map(),
  renderers: new Map(),
  outputSignatures: new Map(),
  outputErrors: new Map(),
  transformErrors: new Map(),
  rendererErrors: new Map(),
  activeTransforms: new Map(),
  transportPromises: new Map(),
  transformGeneration: 0,
  workerUrl: null,
  metrics: {
    browserTransforms: {started:0, completed:0, cancelled:0, timedOut:0, failed:0},
    transports: {started:0, completed:0, failed:0, arrowRows:0},
    perspective: {created:0, updated:0, flushed:0, disposed:0, failed:0},
    repeat: {cards:0, mounted:0, maxMounted:0, disposed:0, searches:0},
  },
  registerTransform(spec, source) {
    if (!spec?.id || typeof source?.code !== 'string' || !source?.entrypoint) throw new Error('Browser Transform requires id, code and entrypoint');
    if (this.transforms.has(spec.id)) throw new Error(`Duplicate Browser Transform: ${spec.id}`);
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
  transformOrder() {
    const pending = new Map([...this.transforms].map(([id, item]) => [id, new Set(
      Object.values(item.spec.inputs || {})
        .map(canonicalOutputReference)
        .filter(reference => reference.startsWith('browser:'))
        .map(reference => reference.slice('browser:'.length).split('/')[0])
    )]));
    const order = [];
    while (pending.size) {
      const ready = [...pending].filter(([, dependencies]) => [...dependencies].every(value => !pending.has(value)));
      if (!ready.length) throw new Error(`Browser Transform cycle: ${[...pending.keys()].join(', ')}`);
      ready.forEach(([id]) => { order.push(id); pending.delete(id); });
    }
    return order;
  },
  browserWorkerUrl() {
    if (this.workerUrl) return this.workerUrl;
    if (!window.datavizBrowserTransformWorkerSource) throw new Error('Browser Transform Worker source is missing');
    this.workerUrl = URL.createObjectURL(new Blob(
      [window.datavizBrowserTransformWorkerSource],
      {type:'application/javascript'},
    ));
    return this.workerUrl;
  },
  cancelTransforms(reason = 'Superseded by a newer browser state') {
    this.activeTransforms.forEach(controller => controller.cancel(reason));
    this.activeTransforms.clear();
  },
  executeTransform(id, item, inputValues) {
    const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const timeoutMs = Math.max(1, Number(item.spec.timeout_seconds || 30) * 1000);
    const worker = new Worker(this.browserWorkerUrl());
    this.metrics.browserTransforms.started += 1;
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        worker.terminate();
        if (this.activeTransforms.get(id) === controller) this.activeTransforms.delete(id);
        callback(value);
      };
      const controller = {
        cancel: reason => {
          this.metrics.browserTransforms.cancelled += 1;
          finish(reject, datavizRuntimeError({
            code:'browser_transform_cancelled',
            name:'AbortError',
            message:`Browser Transform ${id} cancelled: ${reason}`,
            transform_id:id,
            worker:true,
          }));
        },
      };
      const timer = setTimeout(() => {
        this.metrics.browserTransforms.timedOut += 1;
        finish(reject, datavizRuntimeError({
          code:'browser_transform_timeout',
          name:'TimeoutError',
          message:`Browser Transform ${id} exceeded ${item.spec.timeout_seconds || 30} seconds`,
          transform_id:id,
          timeout_seconds:Number(item.spec.timeout_seconds || 30),
          worker:true,
        }));
      }, timeoutMs);
      worker.addEventListener('message', event => {
        const response = event.data || {};
        if (response.protocol !== DATAVIZ_BROWSER_WORKER_PROTOCOL || response.request_id !== requestId) return;
        if (response.type === 'error') finish(reject, datavizRuntimeError(response.error));
        else {
          this.metrics.browserTransforms.completed += 1;
          finish(resolve, response.output);
        }
      });
      worker.addEventListener('error', event => finish(reject, datavizRuntimeError({
        code:'browser_transform_worker_error',
        message:event.message || `Browser Transform ${id} Worker crashed`,
        stack:event.error?.stack || null,
        transform_id:id,
        worker:true,
      })));
      this.activeTransforms.set(id, controller);
      worker.postMessage({
        protocol:DATAVIZ_BROWSER_WORKER_PROTOCOL,
        type:'execute',
        request_id:requestId,
        transform_id:id,
        code:item.source.code,
        entrypoint:item.source.entrypoint,
        context:{
          inputs:inputValues,
          parameters:window.dataviz.parameters || {},
          selections:window.dataviz.selections || {},
        },
      });
    });
  },
  async runTransforms(changedSelectionKeys = null, seedChangedOutputs = []) {
    // If a newer Output/Selection arrives while a Worker is running, the old
    // dependency delta is no longer sufficient on its own. Cancel and rebuild
    // the complete browser DAG from the latest Output Store snapshot so a
    // concurrently hydrated branch cannot be skipped.
    const supersedingActiveRun = this.activeTransforms.size > 0;
    const generation = ++this.transformGeneration;
    this.cancelTransforms();
    const outputs = window.dataviz.portable?.outputs || {};
    const changedSelections = supersedingActiveRun || changedSelectionKeys == null
      ? null
      : new Set(changedSelectionKeys);
    const changedOutputs = new Set(seedChangedOutputs);
    for (const id of this.transformOrder()) {
      if (generation !== this.transformGeneration) break;
      const item = this.transforms.get(id);
      const {spec} = item;
      const declared = Object.keys(spec.outputs || {});
      const references = Object.fromEntries(
        Object.entries(spec.inputs || {}).map(([name, reference]) => [name, canonicalOutputReference(reference)])
      );
      const upstreamChanged = Object.values(references).some(reference => changedOutputs.has(reference));
      const selectionChanged = changedSelections == null || (spec.selections || []).some(key => changedSelections.has(key));
      if (changedSelections != null && !upstreamChanged && !selectionChanged) continue;
      try {
        const failedInput = Object.values(references).find(reference => {
          if (this.outputErrors.has(reference)) return true;
          if (!reference.startsWith('browser:')) return false;
          return this.transformErrors.has(reference.slice('browser:'.length).split('/')[0]);
        });
        if (failedInput) {
          const cause = this.outputErrors.get(failedInput);
          throw new Error(cause?.message || `Upstream Output failed: ${failedInput}`);
        }
        const missingInput = Object.values(references).find(reference =>
          !Object.prototype.hasOwnProperty.call(outputs, reference)
        );
        if (missingInput) continue;
        const inputValues = Object.fromEntries(
          Object.entries(references).map(([name, reference]) => [name, datavizMaterializeOutput(outputs[reference])])
        );
        const value = await this.executeTransform(id, item, inputValues);
        if (generation !== this.transformGeneration) break;
        const named = declared.length > 0;
        const bundle = named ? value : {main: value};
        if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
          throw new Error(`Browser Transform ${id} must return ${named ? 'a named output object' : 'a serializable value'}`);
        }
        if (named) {
          const missing = declared.filter(name => !(name in bundle));
          const unknown = Object.keys(bundle).filter(name => !declared.includes(name));
          if (missing.length || unknown.length) throw new Error(`Browser Transform ${id} output mismatch; missing=${missing.join(',')} unknown=${unknown.join(',')}`);
        }
        Object.entries(bundle).forEach(([name, output]) => {
          validateBrowserOutput(id, name, output, spec.outputs?.[name]);
          const reference = `browser:${id}/${name}`;
          const signature = datavizValueSignature(output);
          if (this.outputSignatures.get(reference) !== signature) {
            outputs[reference] = output;
            this.outputErrors.delete(reference);
            this.outputSignatures.set(reference, signature);
            changedOutputs.add(reference);
          }
        });
        this.transformErrors.delete(id);
      } catch (error) {
        if (error?.code === 'browser_transform_cancelled' && generation !== this.transformGeneration) break;
        this.metrics.browserTransforms.failed += 1;
        this.transformErrors.set(id, error);
        (declared.length ? declared : ['main']).forEach(name => {
          const reference = `browser:${id}/${name}`;
          delete outputs[reference];
          this.outputSignatures.delete(reference);
          changedOutputs.add(reference);
        });
        console.error(`[dataviz:browser-transform:${id}]`, error);
      }
    }
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
        return canonical.startsWith('browser:') && this.transformErrors.has(canonical.slice('browser:'.length).split('/')[0]);
      });
      if (failedReference) {
        const canonical = canonicalOutputReference(failedReference);
        const transformId = canonical.startsWith('browser:') ? canonical.slice('browser:'.length).split('/')[0] : null;
        renderViewInto(viewNode(id), id, () => {
          throw this.outputErrors.get(canonical) || this.transformErrors.get(transformId) || new Error(`Output failed: ${canonical}`);
        });
        return;
      }
      const missingReference = references.find(reference =>
        !Object.prototype.hasOwnProperty.call(window.dataviz.portable?.outputs || {}, reference)
      );
      if (missingReference) {
        renderViewWaiting(viewNode(id), id, `Waiting for ${missingReference}`);
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
    const changedOutputs = await this.runTransforms([], changed);
    refreshCascadingSelections();
    const affectedViewIds = this.affectedViews([], changedOutputs);
    this.renderViews({initial:false, changedSelectionKeys:[], affectedViewIds});
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[]},
    }));
    return changedOutputs;
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
    const changedOutputs = await this.runTransforms([], changed);
    const affectedViewIds = this.affectedViews([], changedOutputs);
    this.renderViews({initial:false, changedSelectionKeys:[], affectedViewIds});
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
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
    const pending = datavizLoadTransport(descriptor)
      .then(async value => {
        this.metrics.transports.completed += 1;
        this.metrics.transports.arrowRows += Number(descriptor.row_count || 0);
        await this.publishOutputs({
          outputs:{[canonical]:value},
          output_kinds:{[canonical]:'table'},
        });
        return value;
      })
      .catch(async error => {
        this.transportPromises.delete(canonical);
        this.metrics.transports.failed += 1;
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
  dispose() {
    this.transformGeneration += 1;
    this.cancelTransforms('Runtime disposed');
    viewRendererStates.forEach((mounted, key) => disposeViewRenderer(mounted.root, key));
    repeatSectionStates.forEach(state => {
      state.host?.querySelectorAll(':scope > .dv-repeat-card').forEach(disposeRepeatCard);
    });
    repeatSectionStates.clear();
    window.datavizPerspectiveReady?.then(runtime => runtime.worker?.terminate?.()).catch(() => {});
    if (this.workerUrl) URL.revokeObjectURL(this.workerUrl);
    this.workerUrl = null;
  },
};

const decodeSpec = (node) => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(node.dataset.spec), c => c.charCodeAt(0))));
document.querySelectorAll('.dv-plotly').forEach(node => {
  const spec = decodeSpec(node);
  if (typeof Plotly === 'undefined') {
    node.innerHTML = '<div class="dv-runtime-error">Plotly.js could not be loaded.</div>';
    return;
  }
  Plotly.newPlot(node, spec.data || [], spec.layout || {}, {responsive: true, displaylogo: false});
});
document.querySelectorAll('.dv-echarts').forEach(node => {
  if (typeof echarts === 'undefined') {
    node.innerHTML = '<div class="dv-runtime-error">ECharts could not be loaded. Check the runtime.echarts_js setting or network access.</div>';
    return;
  }
  const chart = echarts.init(node);
  chart.setOption(decodeSpec(node));
  new ResizeObserver(() => chart.resize()).observe(node);
});
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
const viewNode = id => document.querySelector(`.dv-view[data-view-id="${CSS.escape(id)}"]`);
const viewRendererStates = new Map();
let perspectiveTableSerial = 0;
const releaseWheelAtBoundary = host => {
  if (!host || host.__datavizWheelBoundary) return;
  host.__datavizWheelBoundary = true;
  host.addEventListener('wheel', event => {
    if (event.ctrlKey || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    const path = event.composedPath();
    const hostIndex = path.indexOf(host);
    const candidates = path.slice(0, hostIndex + 1).filter(node => {
      if (!(node instanceof Element)) return false;
      const style = getComputedStyle(node);
      return /(auto|scroll|overlay)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1;
    });
    const direction = Math.sign(event.deltaY);
    const canConsume = candidates.some(node => direction > 0
      ? node.scrollTop + node.clientHeight < node.scrollHeight - 1
      : node.scrollTop > 1);
    if (canConsume) return;
    const page = document.scrollingElement || document.documentElement;
    const pageCanConsume = page && page.scrollHeight > page.clientHeight + 1 && (direction > 0
      ? page.scrollTop + page.clientHeight < page.scrollHeight - 1
      : page.scrollTop > 1);
    if (!pageCanConsume) return;
    const multiplier = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 16
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1;
    event.preventDefault();
    event.stopImmediatePropagation();
    page.scrollTop += event.deltaY * multiplier;
  }, {capture:true, passive:false});
};
const formatTableValue = (value, rule) => {
  if (value == null) return '';
  if (!rule) return String(value);
  if (rule === 'number') return new Intl.NumberFormat().format(Number(value));
  if (rule === 'percent') return new Intl.NumberFormat(undefined, {style:'percent', maximumFractionDigits:2}).format(Number(value));
  if (rule === 'date') return new Intl.DateTimeFormat(undefined, {dateStyle:'medium'}).format(new Date(value));
  if (rule === 'datetime') return new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'}).format(new Date(value));
  if (rule === 'currency') return new Intl.NumberFormat(undefined, {style:'currency', currency:'CNY'}).format(Number(value));
  if (typeof rule === 'object') {
    if (rule.type === 'date' || rule.type === 'datetime') return new Intl.DateTimeFormat(rule.locale, rule.options || {}).format(new Date(value));
    return new Intl.NumberFormat(rule.locale, rule.options || rule).format(Number(value));
  }
  return String(value);
};
const renderPlainTable = (body, rows, columns, limit = 100, descriptor = {}) => {
  const options = descriptor.options || {};
  const visibleRows = rows.slice(0, limit || rows.length);
  const fragment = document.createDocumentFragment();
  if (options.show_count !== false) {
    const meta = document.createElement('div');
    meta.className = 'dv-table-meta';
    meta.innerHTML = `<strong>${rows.length}</strong><span>rows${visibleRows.length < rows.length ? ` · showing ${visibleRows.length}` : ''}</span>`;
    fragment.append(meta);
  }
  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'dv-table-empty';
    empty.textContent = options.empty_text || 'No rows match the current selections.';
    fragment.append(empty);
    body.replaceChildren(fragment);
    return;
  }
  const wrap = document.createElement('div');
  wrap.className = 'dv-table-wrap';
  const table = document.createElement('table');
  table.className = `dv-table${options.striped === false ? '' : ' dv-table--striped'}${options.compact ? ' dv-table--compact' : ''}`;
  if (options.layout === 'fixed') table.style.tableLayout = 'fixed';
  const head = table.createTHead().insertRow();
  columns.forEach(column => {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.dataset.column = column;
    cell.textContent = options.labels?.[column] || column;
    if (options.align?.[column]) cell.dataset.align = options.align[column];
    head.append(cell);
  });
  const tbody = table.createTBody();
  visibleRows.forEach((row, rowIndex) => {
    const tr = tbody.insertRow();
    tr.dataset.rowIndex = rowIndex;
    columns.forEach(column => {
      const cell = tr.insertCell();
      cell.dataset.column = column;
      if (options.align?.[column]) cell.dataset.align = options.align[column];
      cell.textContent = formatTableValue(row[column], options.formats?.[column]);
    });
  });
  wrap.append(table);
  releaseWheelAtBoundary(wrap);
  fragment.append(wrap);
  body.replaceChildren(fragment);
};
const flushPerspective = async state => {
  if (typeof state.viewer?.flush === 'function') await state.viewer.flush();
  else if (typeof state.viewer?.resize === 'function') await state.viewer.resize();
  datavizRuntime.metrics.perspective.flushed += 1;
};
const disposePerspectiveState = state => {
  if (!state || state.disposed) return;
  state.disposed = true;
  state.observer?.disconnect();
  state.pending = Promise.resolve(state.pending).catch(() => {}).then(async () => {
    try { if (typeof state.viewer?.delete === 'function') await state.viewer.delete(); }
    finally {
      if (typeof state.table?.delete === 'function') await state.table.delete();
      state.viewer = null;
      state.table = null;
      datavizRuntime.metrics.perspective.disposed += 1;
    }
  });
};
const createPerspectiveState = (context, descriptor) => {
  const {key, root, body} = context;
  const rows = descriptor.rows || [];
  const columns = descriptor.columns || Object.keys(rows[0] || {});
  root?.classList.add('dv-view--perspective');
  const loading = document.createElement('div');
  loading.className = 'dv-perspective-loading';
  loading.innerHTML = '<span></span><strong>Preparing analysis table</strong><small>sort · filter · pivot · chart</small>';
  body.replaceChildren(loading);
  const state = {
    table:null,
    viewer:null,
    observer:null,
    latestRows:rows,
    latestDescriptor:descriptor,
    mode:'loading',
    disposed:false,
    pending:Promise.resolve(),
  };
  state.pending = (async () => {
    if (!window.datavizPerspectiveReady) throw new Error('Perspective is not loaded; add perspective to canvas.client_libraries');
    if (!state.latestRows.length) {
      renderPlainTable(body, [], columns, descriptor.limit || 100, descriptor);
      state.mode = 'empty';
      setViewStatus(root, 'ready', 'empty');
      return;
    }
    const runtime = await window.datavizPerspectiveReady;
    const expectedMajor = String(window.dataviz.runtime_versions?.perspective || '').split('.')[0];
    const actualMajor = String(runtime.version || '').split('.')[0];
    if (expectedMajor && actualMajor && expectedMajor !== actualMajor) {
      throw new Error(`Perspective Runtime version mismatch: expected ${expectedMajor}.x, loaded ${runtime.version}`);
    }
    if (!state.latestRows.length) {
      renderPlainTable(body, [], columns, descriptor.limit || 100, descriptor);
      state.mode = 'empty';
      setViewStatus(root, 'ready', 'empty');
      return;
    }
    if (typeof runtime.worker?.table !== 'function') throw new Error('Perspective Client does not expose worker.table()');
    const tableName = `dataviz_${String(key).replace(/[^A-Za-z0-9_]/g, '_')}_${++perspectiveTableSerial}`;
    const table = await runtime.worker.table(state.latestRows, {name:tableName});
    if (state.disposed) { await table.delete?.(); return; }
    const viewer = document.createElement('perspective-viewer');
    if (
      typeof viewer.load !== 'function'
      || typeof viewer.restore !== 'function'
      || typeof viewer.flush !== 'function'
      || typeof viewer.delete !== 'function'
    ) {
      await table.delete?.();
      throw new Error('Perspective Viewer API is incompatible; load(), restore(), flush() and delete() are required');
    }
    viewer.className = 'dv-perspective';
    viewer.setAttribute('theme', descriptor.theme || 'Pro Light');
    releaseWheelAtBoundary(viewer);
    body.replaceChildren(viewer);
    state.table = table;
    state.viewer = viewer;
    await viewer.load(runtime.worker);
    await viewer.restore({
      plugin:'Datagrid',
      columns,
      settings:false,
      ...(descriptor.config || descriptor.perspective || {}),
      table:tableName,
    });
    await flushPerspective(state);
    if (state.latestRows !== rows) {
      await table.replace(state.latestRows);
      await flushPerspective(state);
    }
    state.observer = new ResizeObserver(() => { if (typeof viewer.resize === 'function') viewer.resize(); });
    state.observer.observe(body);
    state.mode = 'perspective';
    datavizRuntime.metrics.perspective.created += 1;
    setViewStatus(root, 'ready', 'perspective');
  })().catch(error => {
    if (state.disposed) return;
    state.mode = 'fallback';
    datavizRuntime.metrics.perspective.failed += 1;
    root?.classList.remove('dv-view--perspective');
    renderPlainTable(body, state.latestRows, columns, descriptor.limit || 100, descriptor);
    setViewStatus(root, 'ready', 'table fallback');
    console.warn(`[dataviz:${key}] Perspective unavailable; using basic table`, error);
  });
  return state;
};
const updatePerspectiveState = (context, descriptor, state) => {
  state.latestRows = descriptor.rows || [];
  state.latestDescriptor = descriptor;
  if (state.mode === 'empty' && state.latestRows.length) {
    disposePerspectiveState(state);
    return createPerspectiveState(context, descriptor);
  }
  if (state.mode === 'empty' || state.mode === 'fallback') {
    const columns = descriptor.columns || Object.keys(state.latestRows[0] || {});
    renderPlainTable(context.body, state.latestRows, columns, descriptor.limit || 100, descriptor);
    setViewStatus(context.root, 'ready', state.mode === 'empty' ? 'empty' : 'table fallback');
    return state;
  }
  state.pending = Promise.resolve(state.pending).then(async () => {
    if (state.disposed || !state.table) return;
    await state.table.replace(state.latestRows);
    await flushPerspective(state);
    datavizRuntime.metrics.perspective.updated += 1;
    setViewStatus(context.root, 'ready', 'perspective');
  }).catch(error => {
    if (state.disposed) return;
    datavizRuntime.metrics.perspective.failed += 1;
    setViewStatus(context.root, 'failed', 'perspective failed');
    console.error(`[dataviz:${context.key}] Perspective update failed`, error);
  });
  return state;
};
const clearViewRoot = (root, key) => {
  const body = root?.querySelector('.dv-view-body');
  if (!root || !body) return {root, body};
  root.classList.remove('dv-view--table');
  root.classList.remove('dv-view--perspective');
  body.querySelectorAll('.dv-echarts').forEach(node => {
    const instance = typeof echarts !== 'undefined' && echarts.getInstanceByDom(node);
    if (instance) instance.dispose();
  });
  body.querySelectorAll('.dv-plotly').forEach(node => { if (typeof Plotly !== 'undefined') Plotly.purge(node); });
  body.replaceChildren();
  return {root, body};
};
const clearView = id => {
  const root = viewNode(id);
  disposeViewRenderer(root, id);
  return clearViewRoot(root, id);
};
const setViewStatus = (root, status, label = status) => {
  if (!root) return;
  root.dataset.viewStatus = status;
  const node = root.querySelector('[data-view-status-label]');
  if (node) node.textContent = label;
};
const renderViewWaiting = (root, key, label = 'Waiting for data') => {
  if (!root) return;
  disposeViewRenderer(root, key);
  const {body} = clearViewRoot(root, key);
  if (body) {
    const placeholder = document.createElement('div');
    placeholder.className = 'dv-view-placeholder dv-view-placeholder--live';
    placeholder.innerHTML = '<span></span><strong>Waiting for this data branch</strong>';
    placeholder.title = label;
    body.append(placeholder);
  }
  setViewStatus(root, 'waiting', 'loading');
};
const bindEchartsLegendInteraction = (chart, descriptor) => {
  if (descriptor.legendInteraction !== 'filter') return;
  const options = descriptor.options || {};
  const xAxes = Array.isArray(options.xAxis) ? options.xAxis : [options.xAxis];
  const categoryAxis = xAxes[0];
  const sourceCategories = [...(categoryAxis?.data || [])];
  const sourceSeries = (options.series || []).map(series => ({
    ...series,
    data: [...(series.data || [])],
  }));
  if (categoryAxis?.type !== 'category' || !sourceCategories.length || !sourceSeries.length) return;
  chart.on('legendselectchanged', event => {
    const categories = sourceCategories.filter((category, index) => sourceSeries.some(series =>
      event.selected?.[series.name] !== false && series.data[index] != null
    ));
    const series = sourceSeries.map(item => ({
      ...item,
      data: categories.map(category => item.data[sourceCategories.indexOf(category)]),
    }));
    const nextAxes = [{...categoryAxis, data:categories}, ...xAxes.slice(1)];
    chart.setOption(
      {xAxis:Array.isArray(options.xAxis) ? nextAxes : nextAxes[0], series},
      {replaceMerge:['xAxis', 'series']},
    );
  });
};
const rendererContext = (root, body, key) => ({root, body, key});
datavizRuntime.registerRenderer('table', {
  validate: descriptor => {
    if (!Array.isArray(descriptor.rows || [])) throw new Error('Table renderer expects rows[]');
  },
  mount(context, descriptor) {
    context.root?.classList.add('dv-view--table');
    renderPlainTable(context.body, descriptor.rows || [], descriptor.columns || Object.keys(descriptor.rows?.[0] || {}), descriptor.limit || 100, descriptor);
    return {};
  },
  update(context, descriptor, state) {
    renderPlainTable(context.body, descriptor.rows || [], descriptor.columns || Object.keys(descriptor.rows?.[0] || {}), descriptor.limit || 100, descriptor);
    return state;
  },
  dispose(context) { context.root?.classList.remove('dv-view--table'); },
});
datavizRuntime.registerRenderer('plotly', {
  mount(context, descriptor) {
    if (typeof Plotly === 'undefined') throw new Error('Plotly.js is not loaded');
    const node = document.createElement('div');
    node.className = 'dv-chart dv-plotly';
    context.body.append(node);
    Plotly.newPlot(node, descriptor.data || [], descriptor.layout || {}, {responsive:true, displaylogo:false, ...(descriptor.config || {})});
    return {node};
  },
  update(_context, descriptor, state) {
    Plotly.react(state.node, descriptor.data || [], descriptor.layout || {}, {responsive:true, displaylogo:false, ...(descriptor.config || {})});
    return state;
  },
  dispose(_context, state) { if (state?.node && typeof Plotly !== 'undefined') Plotly.purge(state.node); },
});
datavizRuntime.registerRenderer('echarts', {
  mount(context, descriptor) {
    if (typeof echarts === 'undefined') throw new Error('ECharts.js is not loaded');
    const node = document.createElement('div');
    node.className = 'dv-chart dv-echarts';
    context.body.append(node);
    const chart = echarts.init(node);
    chart.setOption(descriptor.options || {});
    bindEchartsLegendInteraction(chart, descriptor);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(node);
    return {node, chart, observer};
  },
  update(_context, descriptor, state) {
    state.chart.off('legendselectchanged');
    state.chart.setOption(descriptor.options || {}, {notMerge:true});
    bindEchartsLegendInteraction(state.chart, descriptor);
    return state;
  },
  dispose(_context, state) {
    state?.observer?.disconnect();
    state?.chart?.dispose();
  },
});
datavizRuntime.registerRenderer('perspective', {
  mount(context, descriptor) {
    return createPerspectiveState(context, descriptor);
  },
  update(context, descriptor, state) {
    return updatePerspectiveState(context, descriptor, state);
  },
  dispose(context, state) {
    disposePerspectiveState(state);
    context.root?.classList.remove('dv-view--perspective');
  },
});
datavizRuntime.registerRenderer('html', {
  mount(context, descriptor) { context.body.innerHTML = descriptor.html || ''; return {}; },
  update(context, descriptor, state) { context.body.innerHTML = descriptor.html || ''; return state; },
  dispose() {},
});
datavizRuntime.registerRenderer('text', {
  mount(context, descriptor) {
    const node = document.createElement('div');
    node.className = 'dv-prose';
    node.textContent = descriptor?.text ?? '';
    context.body.append(node);
    return {node};
  },
  update(_context, descriptor, state) { state.node.textContent = descriptor?.text ?? ''; return state; },
  dispose() {},
});
const disposeViewRenderer = (root, key) => {
  const mounted = viewRendererStates.get(key);
  if (!mounted) return;
  viewRendererStates.delete(key);
  try {
    Promise.resolve(mounted.renderer.dispose?.(rendererContext(root, mounted.body, key), mounted.state)).catch(error => {
      console.error(`[dataviz:${key}] Renderer dispose failed`, error);
    });
  } catch (error) {
    console.error(`[dataviz:${key}] Renderer dispose failed`, error);
  }
};
const rendererLifecycleError = (key, type, phase, error) => ({
  code:'renderer_lifecycle_error',
  view_id:key,
  renderer:type,
  phase,
  message:error?.message || String(error),
  stack:error?.stack || null,
});
const showRendererError = (root, key, type, phase, error) => {
  const detail = rendererLifecycleError(key, type, phase, error);
  datavizRuntime.rendererErrors.set(key, detail);
  const mounted = viewRendererStates.get(key);
  if (mounted) disposeViewRenderer(mounted.root, key);
  const {body} = clearViewRoot(root, key);
  if (body) {
    const node = document.createElement('div');
    node.className = 'dv-view-error';
    node.setAttribute('role', 'alert');
    node.innerHTML = `<strong>${datavizEscape(detail.renderer)} · ${datavizEscape(detail.phase)}</strong><pre>${datavizEscape(detail.stack || detail.message)}</pre>`;
    body.append(node);
  }
  if (root) root.dataset.rendererError = `${type}:${phase}`;
  setViewStatus(root, 'failed', 'renderer error');
  console.error(`[dataviz:${key}:${type}:${phase}]`, detail);
};
const renderViewInto = (root, key, producer) => {
  setViewStatus(root, 'rendering');
  if (root) {
    delete root.dataset.rendererError;
    root._datavizRenderGeneration = (root._datavizRenderGeneration || 0) + 1;
  }
  const generation = root?._datavizRenderGeneration || 0;
  let descriptor;
  try {
    descriptor = producer();
    if (descriptor == null) return null;
  } catch (error) {
    showRendererError(root, key, 'descriptor', 'produce', error);
    return null;
  }
  const type = descriptor.type || 'text';
  const renderer = datavizRuntime.renderers.get(type);
  if (!renderer) {
    showRendererError(root, key, type, 'lookup', new Error(`Unknown Renderer: ${type}`));
    return null;
  }
  const previous = root?._datavizRendererPending || Promise.resolve();
  const pending = Promise.resolve(previous).catch(() => {}).then(async () => {
    if (root?._datavizRenderGeneration !== generation) return;
    let phase = 'validate';
    try {
      await renderer.validate?.(descriptor);
      if (root?._datavizRenderGeneration !== generation) return;
      const mounted = viewRendererStates.get(key);
      if (mounted && mounted.type === type && mounted.root === root && renderer.update) {
        phase = 'update';
        mounted.state = await renderer.update(rendererContext(root, mounted.body, key), descriptor, mounted.state) ?? mounted.state;
      } else {
        if (mounted) disposeViewRenderer(mounted.root, key);
        const {body} = clearViewRoot(root, key);
        if (!body) throw new Error(`Unknown view: ${key}`);
        phase = 'mount';
        const state = await renderer.mount(rendererContext(root, body, key), descriptor);
        if (root?._datavizRenderGeneration !== generation) {
          await renderer.dispose?.(rendererContext(root, body, key), state);
          return;
        }
        viewRendererStates.set(key, {type, renderer, state, root, body});
      }
      datavizRuntime.rendererErrors.delete(key);
      if (type !== 'perspective') setViewStatus(root, 'ready', type);
    } catch (error) {
      if (root?._datavizRenderGeneration === generation) showRendererError(root, key, type, phase, error);
    }
  });
  if (root) root._datavizRendererPending = pending;
  return descriptor;
};

const renderView = (id, producer) => renderViewInto(viewNode(id), id, producer);
const repeatSectionStates = new Map();
const repeatMountedCount = () => document.querySelectorAll('.dv-repeat-card[data-repeat-mounted="true"]').length;
const repeatObserver = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
  entries.forEach(entry => {
    const card = entry.target;
    if (entry.isIntersecting) card.__datavizRepeatMount?.();
    else card.__datavizRepeatUnmount?.();
  });
}, {rootMargin:'520px 0px'});
const mountRepeatCard = card => {
  if (card.dataset.repeatMounted === 'true' || !card.__datavizRepeatRender) return;
  card.dataset.repeatMounted = 'true';
  card.__datavizRepeatRender();
  datavizRuntime.metrics.repeat.mounted = repeatMountedCount();
  datavizRuntime.metrics.repeat.maxMounted = Math.max(
    datavizRuntime.metrics.repeat.maxMounted,
    datavizRuntime.metrics.repeat.mounted,
  );
};
const unmountRepeatCard = card => {
  if (card.dataset.repeatMounted !== 'true' || card.__datavizRepeatSpec?.recycle_offscreen === false) return;
  disposeViewRenderer(card, card.dataset.viewId);
  clearViewRoot(card, card.dataset.viewId);
  card.dataset.repeatMounted = 'false';
  card.dataset.viewStatus = 'waiting';
  const placeholder = document.createElement('div');
  placeholder.className = 'dv-view-placeholder dv-repeat-placeholder';
  placeholder.innerHTML = '<span></span><small>Recycled · scroll nearby to render</small>';
  card.querySelector('.dv-view-body')?.append(placeholder);
  datavizRuntime.metrics.repeat.disposed += 1;
  datavizRuntime.metrics.repeat.mounted = repeatMountedCount();
};
const disposeRepeatCard = card => {
  repeatObserver?.unobserve(card);
  if (card.dataset.repeatMounted === 'true') {
    disposeViewRenderer(card, card.dataset.viewId);
    clearViewRoot(card, card.dataset.viewId);
    datavizRuntime.metrics.repeat.disposed += 1;
  }
  card.remove();
  datavizRuntime.metrics.repeat.mounted = repeatMountedCount();
};
const ensureRepeatToolbar = state => {
  if (state.toolbar?.isConnected) return;
  const toolbar = document.createElement('div');
  toolbar.className = 'dv-repeat-toolbar';
  toolbar.innerHTML = `<label class="dv-repeat-search"><span>Search groups</span><input type="search" placeholder="${datavizEscape(state.spec.search_placeholder || 'Search groups…')}"></label><small data-repeat-summary></small><button type="button" data-repeat-more>Load more</button>`;
  const input = toolbar.querySelector('input');
  input.hidden = state.spec.searchable === false;
  input.closest('label').hidden = state.spec.searchable === false;
  let scheduled = 0;
  input.addEventListener('input', () => {
    cancelAnimationFrame(scheduled);
    scheduled = requestAnimationFrame(() => {
      state.query = input.value.trim().toLocaleLowerCase();
      state.visibleLimit = Number(state.spec.page_size || 40);
      datavizRuntime.metrics.repeat.searches += 1;
      reconcileRepeatedSection(state);
    });
  });
  toolbar.querySelector('[data-repeat-more]').addEventListener('click', () => {
    state.visibleLimit += Number(state.spec.page_size || 40);
    reconcileRepeatedSection(state);
  });
  state.toolbar = toolbar;
  state.host.prepend(toolbar);
};
const reconcileRepeatedSection = state => {
  const started = performance.now();
  const {host, spec} = state;
  ensureRepeatToolbar(state);
  const filtered = state.query
    ? state.instances.filter(instance => instance.searchText.toLocaleLowerCase().includes(state.query))
    : state.instances;
  const visible = filtered.slice(0, state.visibleLimit);
  const current = new Map(Array.from(host.querySelectorAll(':scope > .dv-repeat-card')).map(card => [card.dataset.repeatKey, card]));
  const keep = new Set(visible.map(instance => instance.key));
  current.forEach((card, key) => { if (!keep.has(key)) disposeRepeatCard(card); });
  let empty = host.querySelector(':scope > .dv-repeat-empty');
  if (!visible.length) {
    if (!empty) {
      empty = document.createElement('div');
      empty.className = 'dv-repeat-empty';
      host.append(empty);
    }
    empty.innerHTML = `<strong>${state.query ? 'No matching groups' : spec.template === 'selection-gallery' ? 'Nothing selected' : 'No groups available'}</strong><span>${String(spec.empty_text || 'No data matches the current selections.').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}</span>`;
  } else empty?.remove();
  visible.forEach((instance, index) => {
    let card = current.get(instance.key);
    if (!card) {
      card = document.createElement('article');
      card.className = 'dv-view dv-view--client dv-repeat-card';
      card.dataset.viewId = instance.id;
      card.dataset.repeatKey = instance.key;
      card.dataset.viewStatus = 'waiting';
      card.dataset.repeatMounted = 'false';
      card.innerHTML = `<header class="dv-view-header"><span></span><div class="dv-view-actions"><small data-view-status-label>queued</small></div></header><div class="dv-view-body"><div class="dv-view-placeholder">Waiting to enter the viewport</div></div>`;
    }
    card.__datavizRepeatSpec = spec;
    card.style.setProperty('--dv-repeat-index', index);
    card.querySelector('.dv-view-header > span').textContent = instance.title;
    const changed = card.dataset.repeatSignature !== instance.signature;
    card.__datavizRepeatRender = () => renderViewInto(card, instance.id, instance.render);
    card.__datavizRepeatMount = () => mountRepeatCard(card);
    card.__datavizRepeatUnmount = () => unmountRepeatCard(card);
    // Eager renderers need a measurable host. Attach the card before mounting
    // Plotly/ECharts/Perspective so their first layout is not computed at 0px.
    host.append(card);
    if (changed) {
      card.dataset.repeatSignature = instance.signature;
      if (card.dataset.repeatMounted === 'true') card.__datavizRepeatRender();
      else if (spec.render === 'eager' || !repeatObserver) mountRepeatCard(card);
      else {
        clearViewRoot(card, instance.id);
        const placeholder = document.createElement('div');
        placeholder.className = 'dv-view-placeholder dv-repeat-placeholder';
        placeholder.innerHTML = '<span></span><small>Queued for lazy rendering</small>';
        card.querySelector('.dv-view-body').append(placeholder);
      }
    }
    if (spec.render === 'lazy' && repeatObserver) repeatObserver.observe(card);
  });
  const remaining = Math.max(0, filtered.length - visible.length);
  const more = state.toolbar.querySelector('[data-repeat-more]');
  more.hidden = remaining === 0;
  more.textContent = `Load ${Math.min(remaining, Number(spec.page_size || 40))} more`;
  state.toolbar.querySelector('[data-repeat-summary]').textContent = state.query
    ? `${visible.length} shown · ${filtered.length} matched · ${state.instances.length} total`
    : `${visible.length} shown · ${state.instances.length} groups`;
  host.dataset.repeatCount = String(state.instances.length);
  host.dataset.repeatFilteredCount = String(filtered.length);
  host.dataset.repeatRenderedCards = String(visible.length);
  host.dataset.repeatReconcileMs = (performance.now() - started).toFixed(2);
  datavizRuntime.metrics.repeat.cards = document.querySelectorAll('.dv-repeat-card').length;
};
const renderRepeatedSection = (spec, instances) => {
  const host = document.querySelector(`.dv-repeat[data-repeat-section="${CSS.escape(spec.section)}"]`);
  if (!host) return;
  let state = repeatSectionStates.get(spec.section);
  if (!state) {
    state = {host, spec, instances:[], query:'', visibleLimit:Number(spec.page_size || 40), toolbar:null};
    repeatSectionStates.set(spec.section, state);
  }
  state.spec = spec;
  state.instances = instances;
  reconcileRepeatedSection(state);
};
document.querySelectorAll('.dv-perspective-bootstrap').forEach((node, index) => {
  try {
    const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(node.dataset.perspectivePayload), value => value.charCodeAt(0))));
    const body = node.closest('.dv-view-body');
    const root = node.closest('.dv-view');
    if (body) {
      const key = `artifact:${index}`;
      const context = rendererContext(root, body, key);
      const state = createPerspectiveState(context, {type:'perspective', ...payload});
      viewRendererStates.set(key, {type:'perspective', renderer:datavizRuntime.renderers.get('perspective'), state, root, body});
    }
  } catch (error) {
    node.textContent = `Interactive table failed: ${error.message}`;
  }
});
window.dataviz.data = {
  output: reference => {
    const canonical = canonicalOutputReference(reference);
    return window.dataviz.portable?.outputs?.[canonical];
  },
  table: reference => new DatavizFrame(datavizTableRows(
    window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)]
  )),
  frame: rows => new DatavizFrame(rows),
};
Object.entries(window.dataviz.portable?.outputs || {}).forEach(([reference, value]) => {
  datavizRuntime.outputSignatures.set(canonicalOutputReference(reference), datavizValueSignature(value));
});
window.dataviz.renderView = renderView;
window.dataviz.renderRepeatedSection = renderRepeatedSection;
window.dataviz.getViewSelections = (viewId) => {
  const contract = window.dataviz.portable?.selection_contract?.[viewId] || [];
  return Object.fromEntries(contract.map(item => [item.id, window.dataviz.selections[item.key]]));
};
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
  else if (operator === 'between') matched = !Array.isArray(value) || value.length < 2 || (String(actual) >= String(value[0]) && String(actual) <= String(value[1]));
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
    const rows = Object.values(window.dataviz.portable?.view_inputs?.[viewId] || {}).flatMap(reference =>
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
      if (control.querySelector('[data-selector-template="cascader"], [data-selector-template="tree-select"]')) {
        syncPortableChoices(control);
        return;
      }
      if (targets[0]?.item?.definition?.cascade === false && targets[0]?.item?.definition?.choices?.length) return;
      const available = new Set();
      let observedSource = false;
      targets.forEach(({viewId, item}) => {
        const outputRefs = Object.values(window.dataviz.portable?.view_inputs?.[viewId] || {});
        const upstream = (window.dataviz.portable?.selection_contract?.[viewId] || []).filter(candidate =>
          (datavizSelectionRank[candidate.origin] ?? 99) < targetRank
        );
        outputRefs.forEach(reference => {
          const raw = String(reference || '');
          const node = raw.includes(':') ? raw : `source:${raw}`;
          const canonical = node.includes('/') ? node : `${node}/main`;
          if (Object.prototype.hasOwnProperty.call(window.dataviz.portable?.outputs || {}, canonical)) observedSource = true;
          const rows = datavizTableRows(window.dataviz.portable?.outputs?.[canonical]);
          rows.forEach(row => {
            const included = upstream.every(candidate =>
              datavizSelectionMatches(row, candidate, window.dataviz.selections[candidate.key])
            );
            if (!included) return;
            const field = item.binding?.field || item.id;
            if (row[field] != null) available.add(String(row[field]));
          });
        });
      });
      if (!observedSource) return;
      if (!(targets[0]?.item?.definition?.choices || []).length) {
        const currentValue = window.dataviz.selections[control.dataset.selectionKey];
        const selected = new Set([
          ...Array.from(input.selectedOptions).map(option => String(option.value)),
          ...(Array.isArray(currentValue) ? currentValue.map(String) : []),
        ]);
        const options = [...available].sort((a, b) => a.localeCompare(b)).map(value => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = value;
          option.selected = selected.has(value);
          return option;
        });
        if (!input.multiple && control.querySelector('[data-empty-means-all="true"]')) {
          const empty = document.createElement('option');
          empty.value = '';
          empty.hidden = true;
          empty.dataset.emptyOption = 'true';
          empty.selected = currentValue == null || currentValue === '';
          options.unshift(empty);
        }
        input.replaceChildren(...options);
      }
      Array.from(input.options).forEach(option => {
        if (option.dataset.emptyOption === 'true') {
          option.disabled = false;
          return;
        }
        const enabled = available.has(String(option.value));
        option.disabled = !enabled;
        if (!enabled) option.selected = false;
      });
      control.dataset.cascadeAvailable = String(available.size);
      syncPortableChoices(control);
    });
    // Commit each scope before deriving the next one. A Dashboard change can
    // invalidate Section values, which must be visible to View selectors in
    // this same interaction rather than one event later.
    readSelectionInputs();
  });
};
const readSelectionInputs = () => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    const type = control.dataset.selectionType;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    let value;
    if (type === 'boolean' && input.tagName === 'SELECT') value = input.value === '' ? null : input.value === 'true';
    else if (type === 'boolean') value = input.checked;
    else if (type === 'multi_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option =>
          control.dataset.selectionPath === 'true' ? JSON.parse(option.value) : option.value
        )
      : (window.dataviz.selections[key] || []);
    else if (type === 'number') value = input.value === '' ? null : Number(input.value);
    else if (type === 'date_range') value = input.value.split(',', 2).map(item => item.trim());
    else value = input.value;
    window.dataviz.selections[key] = value;
  });
};
const datavizSelectionSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(String).sort() : value
);
const datavizChangedSelectionKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizSelectionSignature(previous[key]) !== datavizSelectionSignature(current[key])
  );
};
window.dataviz.applySelections = async () => {
  const previous = window.dataviz.appliedSelections || null;
  readSelectionInputs();
  const preliminaryKeys = datavizChangedSelectionKeys(previous, window.dataviz.selections);
  const changedOutputs = await datavizRuntime.runTransforms(preliminaryKeys);
  refreshCascadingSelections();
  readSelectionInputs();
  const changedSelectionKeys = datavizChangedSelectionKeys(previous, window.dataviz.selections);
  if (changedSelectionKeys != null && datavizSelectionSignature(preliminaryKeys) !== datavizSelectionSignature(changedSelectionKeys)) {
    (await datavizRuntime.runTransforms(changedSelectionKeys)).forEach(reference => changedOutputs.add(reference));
  }
  const affectedViewIds = datavizRuntime.affectedViews(changedSelectionKeys, changedOutputs);
  window.dataviz.appliedSelections = JSON.parse(JSON.stringify(window.dataviz.selections));
  window.dataviz.renderContext = {
    initial: changedSelectionKeys == null,
    changedSelectionKeys: changedSelectionKeys || Object.keys(window.dataviz.selections),
    affectedViewIds,
  };
  if (changedSelectionKeys?.length === 0 && changedOutputs.size === 0) return;
  datavizRuntime.renderViews(window.dataviz.renderContext);
  window.dispatchEvent(new CustomEvent('dataviz:selectionchange', {detail: window.dataviz.selections}));
  if (window.parent !== window) {
    window.parent.postMessage({type: 'dataviz:selections-changed', selections: window.dataviz.selections}, window.location.origin);
  }
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
    fetchOutput(event.data.reference);
  });
  ['node_failed', 'node_blocked'].forEach(name => source.addEventListener(name, message => {
    const event = JSON.parse(message.data);
    if (event.run_id !== live.run_id) return;
    const error = new Error(event.error?.message || `${event.node_id} failed`);
    error.details = event.error || {};
    datavizRuntime.failOutputs(event.data?.outputs || [], error);
  }));
  source.addEventListener('run_ready', () => {
    source.close();
    window.dataviz.status = 'ready';
    window.dispatchEvent(new CustomEvent('dataviz:runready', {detail:{run_id:live.run_id}}));
  });
  source.addEventListener('run_failed', () => source.close());
  window.dataviz.liveSource = source;
};
const setSelectionInputs = values => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    if (!(key in values)) return;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const value = values[key];
    if (control.dataset.selectionType === 'boolean' && input.tagName === 'SELECT') input.value = value == null ? '' : String(value);
    else if (control.dataset.selectionType === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(item => JSON.stringify(item)));
      Array.from(input.options).forEach(option => {
        const comparable = control.dataset.selectionPath === 'true' ? option.value : JSON.stringify(option.value);
        option.selected = selected.has(comparable);
      });
      syncPortableChoices(control);
    }
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  });
};
window.addEventListener('message', event => {
  if (event.origin !== window.location.origin) return;
  const values = event.data?.type === 'dataviz:set-selections' ? event.data.selections : null;
  if (!values) return;
  Object.assign(window.dataviz.selections, values);
  setSelectionInputs(values);
  window.dataviz.applySelections().catch(error => console.error('[dataviz:selections]', error));
});
let datavizSelectionTimer;
const scheduleDatavizSelection = () => {
  clearTimeout(datavizSelectionTimer);
  datavizSelectionTimer = setTimeout(() => window.dataviz.applySelections().catch(error => {
    console.error('[dataviz:selections]', error);
  }), 70);
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
document.addEventListener('pointerdown', () => {
  if (window.parent !== window) {
    window.parent.postMessage({type: 'dataviz:canvas-interaction'}, window.location.origin);
  }
}, {capture: true});
window.addEventListener('pagehide', () => datavizRuntime.dispose(), {once:true});
window.dispatchEvent(new CustomEvent('dataviz:runtime-ready', {detail: datavizRuntime}));
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
