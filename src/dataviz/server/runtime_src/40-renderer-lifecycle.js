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
    this.views.forEach((definition, id) => {
      if (affected && !affected.has(id)) return;
      const references = Object.values(definition.inputs).map(canonicalOutputReference);
      const failedReference = references.find(reference => {
        if (this.outputErrors.has(reference)) return true;
        const canonical = canonicalOutputReference(reference);
        return canonical.startsWith('interactive:') && this.transformErrors.has(canonical.slice('interactive:'.length).split('/')[0]);
      });
      if (failedReference) {
        const canonical = canonicalOutputReference(failedReference);
        const transformId = canonical.startsWith('interactive:') ? canonical.slice('interactive:'.length).split('/')[0] : null;
        const failure = this.outputErrors.get(canonical) || this.transformErrors.get(transformId);
        const failureCode = String(failure?.code || failure?.details?.code || '').toLocaleLowerCase();
        if (failureCode.includes('cancel')) {
          this.viewAdapter?.cancelled(
            this.viewAdapter.node(id),
            id,
            failure?.message || `Computation cancelled: ${canonical}`,
          );
          return;
        }
        if (failureCode.includes('unavailable')) {
          this.viewAdapter?.unavailable(
            this.viewAdapter.node(id),
            id,
            failure?.message || `Runtime unavailable: ${canonical}`,
          );
          return;
        }
        this.viewAdapter?.renderInto(this.viewAdapter.node(id), id, () => {
          throw failure || new Error(`Output failed: ${canonical}`);
        });
        return;
      }
      const missingReference = references.find(reference =>
        !Object.prototype.hasOwnProperty.call(window.dataviz.portable?.outputs || {}, reference)
      );
      if (missingReference) {
        this.viewAdapter?.waiting(
          this.viewAdapter.node(id),
          id,
          `Waiting for ${missingReference}`,
        );
        return;
      }
      definition.render(window.dataviz, context);
      window.dataviz.applied_revisions ||= {views:{}, transforms:{}};
      const bindings = window.dataviz.dependency_contract?.views?.[id]?.control_inputs || {};
      window.dataviz.applied_revisions.views[id] = Object.fromEntries(
        Object.values(bindings).map(binding => [
          binding.control,
          Number(datavizControlEntry(binding.control)?.revision || 0),
        ])
      );
    });
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
    this.renderViews({initial:false, changedControlKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[]},
    }));
    this.publishControlImpacts();
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
    this.renderViews({initial:false, changedControlKeys:[], affectedViewIds});
    const changedOutputs = await this.runTransforms([], changed);
    window.dispatchEvent(new CustomEvent('dataviz:outputschange', {
      detail:{changed:[...changedOutputs], failed:[...changed]},
    }));
    this.publishControlImpacts();
    return changedOutputs;
  },
});
