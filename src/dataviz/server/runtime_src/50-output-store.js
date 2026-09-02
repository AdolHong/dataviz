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
  hydrateOutput(reference, options = {}) {
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
          query_executed:Boolean(options.queryExecuted),
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
      const checkpoint = await datavizAwaitControlRestore();
      // Establish the immutable Base Output snapshot before reconciling dynamic
      // Control domains. Hydration may publish Arrow tables, but no View or
      // Interactive branch is allowed to observe a half-initialized Control state.
      this.initializing = true;
      try {
        await this.hydrateOutputTransports();
      } finally {
        this.initializing = false;
      }
      // Establish initial domains before applying the all-or-nothing checkpoint,
      // then reconcile descendants once against the restored parent values.
      refreshControlOptionDomains();
      if (checkpoint) setControlInputs(checkpoint);
      await window.dataviz.applyControls({
        awaitConsumers:false,
        publishSnapshot:false,
      });
      const snapshot = datavizMarkControlReady();
      // Canvas ready is a lifecycle contract, not a script-load notification.
      // Consumers may still be loading; readiness means typed actions are safe.
      datavizPostToParent({
        type:'dataviz:canvas-ready',
        snapshot,
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
    return controls;
  },
});
