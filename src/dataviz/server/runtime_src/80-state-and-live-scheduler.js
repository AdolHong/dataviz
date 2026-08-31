// Owner: analysis state projection and live Query/Interactive scheduling.
/*
 * Analysis state is evidence, not another editable control surface. The same
 * canonical snapshot drives Server canvases and exported reports.
 */
const datavizStateSummaryConfig = window.dataviz.state_summary || {
  enabled:false, max_values:3, items:{},
};
const datavizStateItemConfig = item => (
  datavizStateSummaryConfig.items?.[item.key]
  || datavizStateSummaryConfig.items?.[item.id]
  || {}
);
const datavizConsumerRevisionEvidence = () => {
  const contract = window.dataviz.dependency_contract || {};
  const applied = window.dataviz.applied_revisions || {};
  const project = (consumerType, consumerId, bindings, trigger) => {
    const keys = [...new Set(
      Object.values(bindings || {}).map(binding => binding.control).filter(Boolean)
    )].sort();
    if (!keys.length) return null;
    const controls = Object.fromEntries(keys.map(key => {
      const effectiveRevision = Number(datavizControlEntry(key)?.revision || 0);
      const rawApplied = applied?.[consumerType]?.[consumerId]?.[key];
      const appliedRevision = Number.isInteger(rawApplied) && rawApplied >= 0
        ? rawApplied
        : null;
      return [key, {
        effective_revision:effectiveRevision,
        applied_revision:appliedRevision,
        stale:appliedRevision !== effectiveRevision,
      }];
    }));
    return {
      trigger,
      stale:Object.values(controls).some(item => item.stale),
      controls,
    };
  };
  const views = {};
  Object.entries(contract.views || {}).forEach(([id, definition]) => {
    const evidence = project('views', id, definition.control_inputs, 'auto');
    if (evidence) views[id] = evidence;
  });
  const transforms = {};
  Object.entries(contract.interactive?.control_inputs || {}).forEach(([id, bindings]) => {
    const trigger = datavizRuntime.transforms.get(id)?.spec?.trigger || 'auto';
    const evidence = project('transforms', id, bindings, trigger);
    if (evidence) transforms[id] = evidence;
  });
  return {views, transforms};
};
const datavizBuildStateSnapshot = () => {
  const initial = window.dataviz.state_snapshot || {items:[]};
  const queryStale = Boolean(
    window.dataviz.query_stale ?? initial.query_stale
  );
  const items = (initial.items || []).map(item => {
    if (item.entry_type === 'control') {
      const current = structuredClone(datavizControlEntry(item.key));
      const committed = structuredClone(
        window.dataviz.applied_control_state?.[item.key] ?? current
      );
      const draft = structuredClone(
        window.dataviz.draft_control_state?.[item.key] ?? current
      );
      return {
        ...item,
        committed,
        draft,
        stale:datavizControlSignature(committed) !== datavizControlSignature(draft),
      };
    }
    const committed = structuredClone(
      window.dataviz.query_parameters?.[item.id] ?? item.committed
    );
    const draft = structuredClone(
      window.dataviz.draft_query_parameters?.[item.id] ?? item.draft ?? committed
    );
    return {
      ...item,
      committed,
      draft,
      stale:Boolean(window.dataviz.query_definition_stale)
        || datavizValueSignature(committed) !== datavizValueSignature(draft),
    };
  });
  const snapshot = {
    schema:'dataviz/state-snapshot/v2',
    dashboard:window.dataviz.dashboard_id,
    query_stale:queryStale,
    items,
    applied_revisions:structuredClone(
      window.dataviz.applied_revisions || initial.applied_revisions || {}
    ),
    consumer_revisions:datavizConsumerRevisionEvidence(),
  };
  window.dataviz.state_snapshot = snapshot;
  return snapshot;
};
const datavizStateLogicalValue = item => {
  if (item.entry_type !== 'control') return item.committed;
  return datavizControlValueFromState(item.definition || {}, item.committed);
};
const datavizStateChoiceLabel = (definition, value) => {
  const match = datavizStaticChoices(definition || {}).find(
    choice => datavizValueSignature(choice.value) === datavizValueSignature(value)
  );
  return match?.label || (Array.isArray(value) ? value.join(' / ') : String(value ?? ''));
};
const datavizStateValueParts = (item, rawValue, formatter = 'auto') => {
  if (item.entry_type === 'control' && item.committed?.intent === 'all_available') {
    const values = Array.isArray(rawValue) ? rawValue : [];
    return [values.length ? `全部（${values.length}）` : '全部'];
  }
  if (rawValue == null || rawValue === '' || (Array.isArray(rawValue) && rawValue.length === 0)) {
    return ['未选择'];
  }
  if (formatter === 'count') {
    return [String(Array.isArray(rawValue) ? rawValue.length : 1)];
  }
  const isDateRange = formatter === 'date_range'
    || item.type === 'range_input'
    || item.definition?.type === 'range_input';
  if (isDateRange && Array.isArray(rawValue)) return [rawValue.join(' ～ ')];
  const values = Array.isArray(rawValue) ? rawValue : [rawValue];
  return values.map(value => datavizStateChoiceLabel(item.definition, value));
};
const datavizStateItemVisibleIn = (item, scope, ownerId) => {
  if (scope === 'dashboard') return item.entry_type === 'query_parameter' || item.origin === 'dashboard';
  return item.origin === scope && item.owner_id === ownerId;
};
const datavizStateSummaryItem = item => {
  const config = datavizStateItemConfig(item);
  const formatter = config.formatter || 'auto';
  const parts = datavizStateValueParts(item, datavizStateLogicalValue(item), formatter);
  const max = Number(datavizStateSummaryConfig.max_values || 3);
  const label = config.label || item.label || item.id;
  const root = document.createElement(parts.length > max ? 'details' : 'span');
  root.className = 'dv-state-chip';
  root.dataset.stateKey = item.key;
  root.dataset.stateKind = item.entry_type;
  if (item.stale) root.dataset.stateStale = 'true';
  const visible = parts.slice(0, max).join('、');
  const suffix = parts.length > max ? ` +${parts.length - max}` : '';
  const main = document.createElement(parts.length > max ? 'summary' : 'span');
  main.className = 'dv-state-chip__main';
  const name = document.createElement('strong');
  name.textContent = label;
  const value = document.createElement('span');
  value.textContent = `${visible}${suffix}`;
  main.append(name, value);
  root.append(main);
  if (parts.length > max) {
    const expanded = document.createElement('span');
    expanded.className = 'dv-state-chip__expanded';
    expanded.textContent = parts.join('、');
    root.append(expanded);
  }
  if (item.stale) {
    const draftParts = datavizStateValueParts(item, item.draft, formatter);
    const pending = document.createElement('em');
    pending.className = 'dv-state-chip__pending';
    pending.textContent = `待应用：${draftParts.join('、')}`;
    root.append(pending);
  }
  return root;
};
const renderDatavizStateSummaries = () => {
  const snapshot = datavizBuildStateSnapshot();
  document.querySelectorAll('[data-state-summary-scope]').forEach(host => {
    const scope = host.dataset.stateSummaryScope;
    const ownerId = host.dataset.stateSummaryOwner;
    const items = snapshot.items
      .filter(item => datavizStateItemVisibleIn(item, scope, ownerId))
      .filter(item => !datavizStateItemConfig(item).hidden)
      .sort((left, right) => (
        Number(datavizStateItemConfig(left).order || 0)
        - Number(datavizStateItemConfig(right).order || 0)
      ));
    host.replaceChildren(...items.map(datavizStateSummaryItem));
    host.hidden = !datavizStateSummaryConfig.enabled || items.length === 0;
  });
  window.dispatchEvent(new CustomEvent('dataviz:state-snapshot', {
    detail:structuredClone(snapshot),
  }));
  return snapshot;
};
window.dataviz.stateSnapshot = datavizBuildStateSnapshot;
window.dataviz.renderStateSummaries = renderDatavizStateSummaries;
const syncControlDirtyState = () => {
  const changed = datavizChangedControlKeys(
    window.dataviz.applied_control_state || null,
    datavizControlStateSnapshot(),
  ) || [];
  document.querySelectorAll('[data-control-dirty-label]').forEach(node => {
    const button = node.parentElement?.querySelector('[data-control-apply]');
    const scopeKeys = new Set(JSON.parse(button?.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size ? changed.filter(key => scopeKeys.has(key)) : changed;
    node.textContent = localChanged.length
      ? `${localChanged.length} draft change${localChanged.length === 1 ? '' : 's'}`
      : 'Results are current';
  });
  document.querySelectorAll('[data-control-apply]').forEach(button => {
    const scopeKeys = new Set(JSON.parse(button.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size ? changed.filter(key => scopeKeys.has(key)) : changed;
    button.disabled = localChanged.length === 0 && button.dataset.analysisAlways !== 'true';
  });
  renderDatavizStateSummaries();
  return changed;
};
window.dataviz.applyControls = async (options = {}) => {
  const previous = window.dataviz.current_control_state || null;
  // Dynamic selects are empty until their immutable option domain is hydrated;
  // preserve the compiled initial state during the first pass.
  if (previous != null) readControlInputs({keys:options.keys ? new Set(options.keys) : null});
  refreshControlOptionDomains();
  readControlInputs({keys:options.keys ? new Set(options.keys) : null});
  const current = datavizControlStateSnapshot();
  const changed = datavizChangedControlKeys(previous, current);
  window.dataviz.current_control_state = structuredClone(current);
  let affectedViewIds = datavizRuntime.affectedViews(changed, new Set());
  const contentAffected = syncDatavizContentBindings(changed);
  if (affectedViewIds != null) affectedViewIds = [...new Set([...affectedViewIds, ...contentAffected])];
  if (previous == null) {
    window.dataviz.applied_control_state = structuredClone(current);
  } else if (options.apply === true) {
    const keys = options.keys?.length ? options.keys : Object.keys(current);
    window.dataviz.applied_control_state ||= {};
    keys.forEach(key => {
      if (current[key]) {
        window.dataviz.applied_control_state[key] = structuredClone(current[key]);
      }
    });
  } else {
    // Controls consumed only by immediate Views/auto Transforms have no pending
    // Apply lifecycle. Advance their evidence snapshot without committing keys
    // that still feed an apply/manual consumer.
    window.dataviz.applied_control_state ||= {};
    Object.keys(current).forEach(key => {
      const deferred = [...datavizRuntime.transforms].some(([id, item]) => (
        item.spec.trigger !== 'auto'
        && Object.values(datavizRuntime.transformControlInputs(id))
          .some(binding => binding.control === key)
      ));
      if (!deferred) {
        window.dataviz.applied_control_state[key] = structuredClone(current[key]);
      }
    });
  }
  window.dataviz.draft_control_state = structuredClone(current);
  window.dataviz.renderContext = {
    initial:changed == null,
    changedControlKeys:changed || Object.keys(current),
    affectedViewIds,
  };
  syncControlDirtyState();
  if (changed == null || changed.length) datavizRuntime.renderViews(window.dataviz.renderContext);
  const changedOutputs = await datavizRuntime.runTransforms(changed, [], {
    apply:options.apply === true,
    manualTargets:options.manualTargets || [],
    targets:options.targets,
  });
  window.dispatchEvent(new CustomEvent('dataviz:controlchange', {
    detail:{control_state:structuredClone(current), changed:changed || Object.keys(current), outputs:[...changedOutputs]},
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:controls-changed',
      control_state:structuredClone(current),
    });
  }
  datavizRuntime.publishControlImpacts();
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
          output_schemas: {
            [payload.reference]: payload.transport?.schema || payload.artifact?.schema || [],
          },
        });
      })
      .catch(error => {
        fetched.delete(reference);
        datavizSetViewPipelineNodeStatus(
          canonicalOutputReference(reference).split('/')[0],
          'error',
        );
        console.error(`[dataviz:live:${reference}]`, error);
      });
    fetched.set(reference, promise);
    return promise;
  };
  source.addEventListener('output_ready', message => {
    const event = JSON.parse(message.data);
    if (event.run_id !== live.run_id || !event.data?.reference) return;
    if (window.dataviz.interaction) {
      window.dataviz.interaction.query_snapshot_available = true;
    }
    fetchOutput(event.data.reference);
  });
  const queryNodeStatuses = {
    node_queued:'queued',
    node_started:'loading',
    node_progress:'loading',
    node_retrying:'loading',
    node_ready:'ready',
    node_error:'error',
    node_cancelled:'cancelled',
    node_unavailable:'unavailable',
  };
  Object.entries(queryNodeStatuses).forEach(([name, status]) => {
    source.addEventListener(name, message => {
      const event = JSON.parse(message.data);
      if (event.run_id !== live.run_id || !event.node_id) return;
      datavizSetViewPipelineNodeStatus(event.node_id, status);
    });
  });
  ['node_error', 'node_cancelled', 'node_unavailable'].forEach(name => source.addEventListener(name, message => {
    const event = JSON.parse(message.data);
    if (event.run_id !== live.run_id) return;
    if (window.dataviz.interaction) {
      window.dataviz.interaction.query_snapshot_available = true;
    }
    const error = datavizRuntimeError({
      ...(event.error || {}),
      code:event.error?.code || (name === 'node_cancelled' ? 'cancelled' : name === 'node_unavailable' ? 'unavailable' : 'node_failed'),
      message:event.error?.message || `${event.node_id} ${name.replace('node_', '')}`,
    });
    datavizRuntime.failOutputs(event.data?.outputs || [], error);
  }));
  source.addEventListener('run_ready', () => {
    source.close();
    window.dataviz.status = 'ready';
    window.dispatchEvent(new CustomEvent('dataviz:runready', {detail:{run_id:live.run_id}}));
  });
  source.addEventListener('run_error', () => {
    window.dataviz.status = 'error';
    source.close();
  });
  source.addEventListener('run_cancelled', () => {
    window.dataviz.status = 'cancelled';
    source.close();
  });
  source.addEventListener('stream_end', () => source.close());
  window.dataviz.liveSource = source;
};
const setControlInputs = states => {
  Object.entries(states || {}).forEach(([key, state]) => {
    if (!window.dataviz.dependency_contract?.controls?.[key]) return;
    datavizControlState()[key] = datavizNormalizeControlState(key, state);
  });
  window.dataviz.draft_control_state = structuredClone(datavizControlStateSnapshot());
  document.querySelectorAll('[data-control-key]').forEach(control => {
    const key = control.dataset.controlKey;
    if (!(key in (states || {}))) return;
    const input = control.querySelector('[data-control-state-input]');
    if (!input || input.disabled) return;
    const definition = datavizControlDefinition(key);
    const value = datavizControlValue(key);
    const encode = item => datavizEncodeControlValue(input, item, {
      path:control.dataset.controlPath === 'true',
    });
    if (definition.value_type === 'boolean' && input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (definition.value_type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(encode));
      Array.from(input.options).forEach(option => { option.selected = selected.has(option.value); });
      syncPortableChoices(control);
    } else if (definition.type === 'range_input' && Array.isArray(value)) input.value = value.length ? value.join(',') : '';
    else if (input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (definition.type === 'multiple_input' && Array.isArray(value)) input.value = JSON.stringify(value);
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  });
  syncControlDirtyState();
};
window.addEventListener('message', event => {
  if (
    event.origin !== window.location.origin
    || window.parent === window
    || event.source !== window.parent
    || !datavizSameFrameIdentity(event.data)
  ) return;
  if (event.data?.type === 'dataviz:set-controls') {
    const states = event.data.control_state || {};
    setControlInputs(states);
    if (event.data.commit !== false) {
      window.dataviz.applyControls({
        keys:event.data.control_keys || Object.keys(states),
        apply:event.data.apply !== false,
        manualTargets:event.data.manual_targets || [],
      }).catch(error => console.error('[dataviz:controls]', error));
    }
  }
  if (event.data?.type === 'dataviz:set-query-draft') {
    window.dataviz.draft_query_parameters = structuredClone(
      event.data.query_parameters || {}
    );
    window.dataviz.query_stale = Boolean(event.data.query_stale);
    window.dataviz.query_definition_stale = Boolean(
      event.data.query_definition_stale
    );
    renderDatavizStateSummaries();
  }
  if (event.data?.type === 'dataviz:set-interaction') {
    const previous = window.dataviz.interaction;
    const next = event.data.interaction || null;
    window.dataviz.interaction = next;
    const endpointChanged = [
      'run_id', 'session_id', 'start_url', 'status_url', 'outputs_url',
      'query_snapshot_available', 'query_complete',
    ].some(
      key => (previous?.[key] || null) !== (next?.[key] || null),
    );
    if (next && endpointChanged) {
      const targets = [...datavizRuntime.transforms.entries()]
        .filter(([, item]) => item.spec.runtime === 'server-python')
        .map(([id]) => id);
      datavizRuntime.runTransforms([], [], {targets})
        .catch(error => console.error('[dataviz:interaction]', error));
    }
  }
  if (event.data?.type === 'dataviz:collect-snapshot') {
    const requestId = event.data.request_id;
    try {
      const snapshot = datavizRuntime.collectSnapshotOutputs();
      event.source?.postMessage({
        type:'dataviz:snapshot-collected',
        request_id:requestId,
        ...datavizFrameIdentity(),
        ...snapshot,
        control_state:datavizControlStateSnapshot(),
        state_snapshot:datavizBuildStateSnapshot(),
      }, event.origin);
    } catch (error) {
      event.source?.postMessage({
        type:'dataviz:snapshot-collected',
        request_id:requestId,
        ...datavizFrameIdentity(),
        error:{message:error?.message || String(error)},
      }, event.origin);
    }
  }
});
