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
  executeBrowserRuntime(id, item, inputValues, options = {}) {
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
      const prepared = datavizPrepareControlInputs(
        this.transformControlInputs(id),
        inputValues,
        options.controlState,
      );
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
          control_state:structuredClone(options.controlState || {}),
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
  transformCacheKey(id, item, inputValues, controlState) {
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
          datavizControlEntryFrom(controlState, binding.control),
        ])
      ),
    });
  },
  async executeTransform(id, item, inputValues, generation, controlState) {
    const key = this.transformCacheKey(id, item, inputValues, controlState);
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
      const prepared = await adapter.prepare(item, inputValues, {controlState});
      const value = await adapter.execute(id, item, prepared, {generation, controlState});
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
          const executionControlState = datavizControlStateSnapshot();
          const capturedControlState = datavizCaptureConsumerControlState(
            this.transformControlInputs(id),
            executionControlState,
          );
          const capturedWriterProvenance = datavizCaptureConsumerWriterProvenance(
            this.transformControlInputs(id),
            capturedControlState,
          );
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
          const bundle = await this.executeTransform(
            id,
            item,
            inputValues,
            request,
            executionControlState,
          );
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
          datavizCommitConsumerControlState(
            'transforms',
            id,
            capturedControlState,
            capturedWriterProvenance,
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
