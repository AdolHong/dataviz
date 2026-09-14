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
      // Writers consume their canonical binding state for selection feedback,
      // even though they do not filter their own candidate rows.
      (dependency?.writer_edges || []).forEach(edge => affected.add(edge.source_view));
      (dependency?.direct_views || []).forEach(viewId => {
        const item = datavizViewControlContract(viewId)
          .find(candidate => candidate.key === key);
        if (item && datavizControlViewApplicability(viewId, item) !== 'not_applicable') {
          affected.add(viewId);
        }
      });
      (dependency?.repeat_views || []).forEach(viewId => affected.add(viewId));
    });
    Object.entries(window.dataviz.dependency_contract?.views || {}).forEach(([id, view]) => {
      if (Object.values(view.control_inputs || {}).some(binding => (
        binding.mode === 'value' && changedControls.has(binding.control)
      ))) affected.add(id);
    });
    outputs.forEach(reference => this.outputViews(reference).forEach(viewId => affected.add(viewId)));
    return [...affected];
  },
  renderViews(context) {
    if (this.disposed) return Promise.resolve([]);
    const affected = context.affectedViewIds == null ? null : new Set(context.affectedViewIds);
    const changedOutputReferences = new Set(context.changedOutputReferences || []);
    const completions = [];
    this.views.forEach((definition, id) => {
      if (affected && !affected.has(id)) {
        this.viewRefreshEvidence.set(id, {
          ...this.viewRefreshEvidence.get(id),
          last_schedule:{status:'not_affected', changed_controls:[...(context.changedControlKeys || [])]},
        });
        return;
      }
      const inputReferences = Object.entries(definition.inputs).map(([alias, reference]) => ({
        alias,
        reference:canonicalOutputReference(reference),
      }));
      const references = inputReferences.map(item => item.reference);
      const portable = window.dataviz.portable || {};
      const inputProfiles = Object.fromEntries(inputReferences.map(({alias, reference}) => {
        const present = Object.prototype.hasOwnProperty.call(portable.outputs || {}, reference);
        const value = portable.outputs?.[reference];
        const failed = this.outputErrors.has(reference)
          || (reference.startsWith('interactive:') && this.transformErrors.has(reference.slice(12).split('/')[0]));
        const profile = present && !failed ? datavizValueProfile(value) : {rows:null,bytes:null,transport:null};
        return [alias, {
          reference, kind:portable.output_kinds?.[reference] || null,
          status:failed ? 'error' : !present ? 'pending' : profile.rows === 0 ? 'empty' : 'ready',
          input_type:!present ? null : value?.__datavizArrowOutput ? 'arrow-table' : Array.isArray(value) ? 'rows' : value === null ? 'null' : typeof value,
          ...profile,
        }];
      }));
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
          input_profiles:inputProfiles,
          last_schedule:{status:'input_failed'},
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
          input_profiles:inputProfiles,
          last_schedule:{status:'waiting_input'},
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
        input_profiles:inputProfiles,
        last_schedule:{status:'render'},
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
        control_revisions:Object.fromEntries(Object.entries(capturedControlState).map(([key, entry]) => [key, entry.revision])),
        control_state:structuredClone(capturedControlState),
      });
      if (root) {
        root._datavizInputProfiles = inputProfiles;
      }
      try {
        definition.render(window.dataviz, context);
      } catch (error) {
        const failure = {
          code:error?.code || 'view_render_failed',
          message:error?.message || String(error),
          view_id:id,
          phase:'dispatch',
        };
        this.viewRefreshEvidence.set(id, {
          ...this.viewRefreshEvidence.get(id), render_error:failure,
          last_schedule:{status:'render_failed'},
        });
        // Route synchronous dispatch/descriptor failures through the same
        // terminal rendering path as asynchronous renderer failures. Keeping
        // the previous chart marked ready would misrepresent the new state.
        this.viewAdapter?.renderInto(root, id, () => {
          throw datavizRuntimeError(failure);
        });
        console.error(`[dataviz:${id}:render]`, error);
        return;
      }
      const generation = Number(root?._datavizRenderGeneration || 0);
      const completion = this.viewAdapter?.completion(root, generation)
        || Promise.resolve({status:'ready', generation});
      completions.push(Promise.resolve(completion).then(outcome => {
        if (
          this.disposed || outcome?.status !== 'ready'
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
    const changed = new Set();
    if (this.disposed) return changed;
    Object.entries(bundle.outputs || {}).forEach(([rawReference, value]) => {
      const reference = canonicalOutputReference(rawReference);
      if (this.commitOutput(reference, value, {
        kind:bundle.output_kinds?.[reference], schema:bundle.output_schemas?.[reference],
      })) changed.add(reference);
    });
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
    if (this.disposed) return changedOutputs;
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
    const changed = new Set();
    if (this.disposed) return changed;
    (references || []).forEach(rawReference => {
      const reference = canonicalOutputReference(rawReference);
      this.removeOutput(reference);
      this.outputErrors.set(reference, error || new Error(`Output failed: ${reference}`));
      changed.add(reference);
    });
    if (this.initializing) return changed;
    refreshControlOptionDomains();
    const affectedViewIds = this.affectedViews([], changed);
    this.renderViews({
      initial:false,
      changedControlKeys:[],
      changedOutputReferences:[...changed],
      affectedViewIds,
    });
    const changedOutputs = await this.runTransforms([], changed);
    if (this.disposed) return changedOutputs;
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
    this.publishControlImpacts();
    if (datavizControlChannel.phase === 'ready') datavizPublishControlSnapshot(null);
    return changedOutputs;
  },
});
