// Owner: shared Runtime host state and public registration surface.
const datavizRuntime = window.datavizRuntime = {
  protocol: 'dataviz/runtime/v14',
  transforms: new Map(),
  views: new Map(),
  renderers: new Map(),
  outputSignatures: new Map(),
  outputErrors: new Map(),
  transformErrors: new Map(),
  rendererErrors: new Map(),
  interactiveTraces: new Map(),
  viewRefreshEvidence: new Map(),
  viewRenderEvidence: new Map(),
  rendererLifecycleEvidence: new Map(),
  activeTransforms: new Map(),
  inflightTransforms: new Map(),
  transformRequests: new Map(),
  transportPromises: new Map(),
  transformGenerations: new Map(),
  workerUrls: new Map(),
  interactionCache: new Map(),
  interactionCacheLimit: 64,
  transformCacheEvidence: new Map(),
  controlImpactSignatures: new Map(),
  initializing: false,
  initializationPromise: null,
  authorMode: false,
  interactiveAdapters: Object.create(null),
  metrics: {
    interactiveTransforms: {
      started:0, completed:0, cancelled:0, timedOut:0, failed:0,
      cacheHits:0, cacheMisses:0, cacheEvictions:0,
    },
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
