// Owner: affected-view resolution and Renderer mount/update lifecycle.
Object.assign(datavizRuntime, {
  affectedViews(changedControlKeys, changedOutputs = new Set()) {
    // A null Control delta is the first render, not an empty update. Render
    // every registered host so input-free Markdown/Image Views become ready and
    // data-backed Views can enter their branch-local waiting state.
    if (changedControlKeys == null) return null;
    const changedControls = new Set(changedControlKeys || []);
    const outputs = changedOutputs || new Set();
    const affected = new Set();
    changedControls.forEach(key => {
      const dependency = window.dataviz.dependency_contract?.controls?.[key];
      (dependency?.direct_views || []).forEach(viewId => {
        const item = datavizViewControlContract(viewId)
          .find(candidate => candidate.key === key);
        if (item && datavizControlViewApplicability(viewId, item) !== 'not_applicable') {
          affected.add(viewId);
        }
      });
      (dependency?.repeat_views || []).forEach(viewId => affected.add(viewId));
    });
    outputs.forEach(reference => this.outputViews(reference).forEach(viewId => affected.add(viewId)));
    return [...affected];
  },
  renderViews(context) {
    const affected = context.affectedViewIds == null ? null : new Set(context.affectedViewIds);
    const changedOutputReferences = new Set(context.changedOutputReferences || []);
    const completions = [];
    this.views.forEach((definition, id) => {
      if (affected && !affected.has(id)) return;
      const inputReferences = Object.entries(definition.inputs).map(([alias, reference]) => ({
        alias,
        reference:canonicalOutputReference(reference),
      }));
      const references = inputReferences.map(item => item.reference);
      const failedInput = inputReferences.find(({reference}) => {
        if (this.outputErrors.has(reference)) return true;
        const canonical = canonicalOutputReference(reference);
        return canonical.startsWith('interactive:') && this.transformErrors.has(canonical.slice('interactive:'.length).split('/')[0]);
      });
      if (failedInput) {
        const {alias, reference:canonical} = failedInput;
        const transformId = canonical.startsWith('interactive:') ? canonical.slice('interactive:'.length).split('/')[0] : null;
        const failure = this.outputErrors.get(canonical) || this.transformErrors.get(transformId);
        this.viewRefreshEvidence.set(id, {
          initial:Boolean(context.initial),
          query_executed:Boolean(context.queryExecuted),
          failed_input:{
            alias,
            reference:canonical,
            code:failure?.code || failure?.details?.code || 'view_input_failed',
            message:failure?.message || String(failure || 'Output failed'),
          },
        });
        const failureCode = String(failure?.code || failure?.details?.code || '').toLocaleLowerCase();
        if (failureCode.includes('cancel')) {
          this.viewAdapter?.cancelled(
            this.viewAdapter.node(id),
            id,
            `Input ${alias} cancelled: ${failure?.message || canonical}`,
          );
          return;
        }
        if (failureCode.includes('unavailable')) {
          this.viewAdapter?.unavailable(
            this.viewAdapter.node(id),
            id,
            `Input ${alias} unavailable: ${failure?.message || canonical}`,
          );
          return;
        }
        this.viewAdapter?.renderInto(this.viewAdapter.node(id), id, () => {
          throw datavizRuntimeError({
            code:failure?.code || failure?.details?.code || 'view_input_failed',
            message:`Input ${alias} failed: ${failure?.message || canonical}`,
            input_alias:alias,
            input_reference:canonical,
            cause:failure || null,
          });
        });
        return;
      }
      const missingInput = inputReferences.find(({reference}) =>
        !Object.prototype.hasOwnProperty.call(window.dataviz.portable?.outputs || {}, reference)
      );
      if (missingInput) {
        this.viewRefreshEvidence.set(id, {
          initial:Boolean(context.initial),
          query_executed:Boolean(context.queryExecuted),
          waiting_input:{alias:missingInput.alias, reference:missingInput.reference},
        });
        this.viewAdapter?.waiting(
          this.viewAdapter.node(id),
          id,
          `Waiting for input ${missingInput.alias}: ${missingInput.reference}`,
        );
        return;
      }
      const bindings = window.dataviz.dependency_contract?.views?.[id]?.control_inputs || {};
      const capturedControlState = datavizCaptureConsumerControlState(bindings);
      const capturedWriterProvenance = datavizCaptureConsumerWriterProvenance(
        bindings,
        capturedControlState,
      );
      const root = this.viewAdapter?.node(id);
      const transformTraces = Object.fromEntries(references.flatMap(reference => {
        const canonical = canonicalOutputReference(reference);
        if (!canonical.startsWith('interactive:')) return [];
        const transformId = canonical.slice('interactive:'.length).split('/')[0];
        const trace = this.interactiveTraces.get(transformId);
        return trace ? [[transformId, structuredClone(trace)]] : [];
      }));
      this.viewRefreshEvidence.set(id, {
        initial:Boolean(context.initial),
        changed_controls:[...(context.changedControlKeys || [])],
        changed_inputs:references.filter(reference => (
          changedOutputReferences.has(canonicalOutputReference(reference))
        )),
        changed_input_aliases:inputReferences
          .filter(({reference}) => changedOutputReferences.has(reference))
          .map(({alias}) => alias),
        input_aliases:Object.fromEntries(
          inputReferences.map(({alias, reference}) => [alias, reference])
        ),
        interactive_transforms:transformTraces,
        query_executed:Boolean(context.queryExecuted),
      });
      if (root) {
        root._datavizInputProfiles = Object.fromEntries(
          Object.entries(definition.inputs).map(([name, reference]) => {
            const canonical = canonicalOutputReference(reference);
            const value = window.dataviz.portable?.outputs?.[canonical];
            return [name, {
              reference:canonical,
              ...datavizValueProfile(value),
            }];
          })
        );
      }
      try {
        definition.render(window.dataviz, context);
      } catch (error) {
        console.error(`[dataviz:${id}:render]`, error);
        return;
      }
      const generation = Number(root?._datavizRenderGeneration || 0);
      const completion = this.viewAdapter?.completion(root, generation)
        || Promise.resolve({status:'ready', generation});
      completions.push(Promise.resolve(completion).then(outcome => {
        if (
          outcome?.status !== 'ready'
          || Number(root?._datavizRenderGeneration || 0) !== generation
        ) return outcome;
        datavizCommitConsumerControlState(
          'views',
          id,
          capturedControlState,
          capturedWriterProvenance,
        );
        return outcome;
      }));
    });
    return Promise.allSettled(completions);
  },
  async publishOutputs(bundle) {
    const outputs = window.dataviz.portable?.outputs || {};
    window.dataviz.portable.output_schemas ||= {};
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
    Object.assign(window.dataviz.portable.output_schemas, bundle.output_schemas || {});
    if (!changed.size || this.initializing) return changed;
    refreshControlOptionDomains();
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({
      initial:false,
      changedControlKeys:[],
      changedOutputReferences:[...changed],
      queryExecuted:Boolean(bundle.query_executed),
      affectedViewIds,
    });
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[]},
    }));
    this.publishControlImpacts();
    if (datavizControlChannel.phase === 'ready') datavizPublishControlSnapshot(null);
    return changedOutputs;
  },
  collectSnapshotOutputs() {
    const outputs = window.dataviz.portable?.outputs || {};
    const values = {};
    const missing = [];
    this.transforms.forEach((item, id) => {
      if (item.spec.export?.mode !== 'snapshot' || item.spec.runtime === 'server-python') return;
      Object.entries(item.spec.outputs || {}).forEach(([name, definition]) => {
        const reference = `interactive:${id}/${name}`;
        if (!Object.prototype.hasOwnProperty.call(outputs, reference)) {
          if (definition.required !== false) missing.push(reference);
          return;
        }
        values[reference] = datavizSnapshotValue(outputs[reference]);
      });
    });
    return {outputs:values, missing};
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
    if (this.initializing) return changed;
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({
      initial:false,
      changedControlKeys:[],
      changedOutputReferences:[...changed],
      affectedViewIds,
    });
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
    this.publishControlImpacts();
    if (datavizControlChannel.phase === 'ready') datavizPublishControlSnapshot(null);
    return changedOutputs;
  },
});
