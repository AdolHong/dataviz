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
const datavizBuildStateSnapshot = () => {
  const initial = window.dataviz.state_snapshot || {items:[]};
  const queryStale = Boolean(
    window.dataviz.query_stale ?? initial.query_stale
  );
  const items = (initial.items || []).map(item => {
    if (item.kind === 'selection') {
      const committed = structuredClone(datavizSelectionEntry(item.key));
      return {...item, committed, draft:structuredClone(committed), stale:false};
    }
    if (item.kind === 'compute') {
      const committed = structuredClone(
        window.dataviz.compute_parameters?.[item.key] ?? item.definition?.default
      );
      const draft = structuredClone(
        window.dataviz.draft_compute_parameters?.[item.key] ?? committed
      );
      return {
        ...item,
        committed,
        draft,
        stale:datavizValueSignature(committed) !== datavizValueSignature(draft),
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
    schema:'dataviz/state-snapshot/v1',
    dashboard:window.dataviz.dashboard_id,
    query_stale:queryStale,
    items,
  };
  window.dataviz.state_snapshot = snapshot;
  return snapshot;
};
const datavizStateLogicalValue = item => {
  if (item.kind !== 'selection') return item.committed;
  return datavizSelectionValueFromState(item.definition || {}, item.committed);
};
const datavizStateChoiceLabel = (definition, value) => {
  const match = datavizStaticChoices(definition || {}).find(
    choice => datavizValueSignature(choice.value) === datavizValueSignature(value)
  );
  return match?.label || (Array.isArray(value) ? value.join(' / ') : String(value ?? ''));
};
const datavizStateValueParts = (item, rawValue, formatter = 'auto') => {
  if (item.kind === 'selection' && item.committed?.intent === 'all_available') {
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
  if (scope === 'dashboard') return item.kind === 'query' || item.origin === 'dashboard';
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
  root.dataset.stateKind = item.kind;
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
const readComputeInputs = () => {
  const values = {...(window.dataviz.draft_compute_parameters || {})};
  document.querySelectorAll('[data-compute-key]').forEach(control => {
    const key = control.dataset.computeKey;
    const input = control.querySelector('[data-compute-input]');
    if (!input || input.disabled || control.dataset.computeFrozen === 'true') return;
    const definition = window.dataviz.compute_definitions?.[key] || {
      type:input.dataset.computeType,
      value_type:input.dataset.valueType || 'text',
    };
    const type = definition.type;
    const valueType = definition.value_type;
    const decode = raw => datavizDecodeControlValue(input, raw);
    if (type === 'range_input') {
      const range = input.value
        ? input.value.split(',', 2).map(item => item.trim())
        : [];
      values[key] = range.some(Boolean) ? range : [];
    } else if (valueType === 'boolean') values[key] = Boolean(input.checked);
    else if (type === 'multiple_select') values[key] = Array.from(input.selectedOptions).map(option => decode(option.value));
    else if (type === 'multiple_input') {
      try { values[key] = input.value ? JSON.parse(input.value) : []; }
      catch (_error) { values[key] = input.value.split(',').map(item => item.trim()).filter(Boolean); }
    }
    else if (input.tagName === 'SELECT') values[key] = input.value === '' ? null : decode(input.value);
    else if (valueType === 'number' || valueType === 'integer') values[key] = input.value === '' ? null : Number(input.value);
    else values[key] = input.value;
    try {
      values[key] = datavizNormalizeControlValue(
        definition,
        values[key],
        {namespace:'compute_parameter', key},
      );
      input.setCustomValidity?.('');
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = '';
        output.hidden = true;
      }
    } catch (error) {
      input.setCustomValidity?.(error.message);
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = error.message;
        output.hidden = false;
      }
      throw error;
    }
  });
  window.dataviz.draft_compute_parameters = values;
  return values;
};
const datavizChangedComputeKeys = (previous, current) => {
  const keys = new Set([...Object.keys(previous || {}), ...Object.keys(current || {})]);
  return [...keys].filter(key => datavizValueSignature(previous?.[key]) !== datavizValueSignature(current?.[key]));
};
const syncComputeDirtyState = () => {
  const changed = datavizChangedComputeKeys(
    window.dataviz.compute_parameters || {},
    window.dataviz.draft_compute_parameters || {},
  );
  document.querySelectorAll('[data-compute-dirty-label]').forEach(node => {
    const button = node.parentElement?.querySelector('[data-compute-apply]');
    const scopeKeys = new Set(JSON.parse(button?.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size
      ? changed.filter(key => scopeKeys.has(key))
      : changed;
    node.textContent = localChanged.length
      ? `${localChanged.length} draft change${localChanged.length === 1 ? '' : 's'}`
      : 'Results are current';
  });
  document.querySelectorAll('[data-compute-apply]').forEach(button => {
    const scopeKeys = new Set(JSON.parse(button.dataset.controlKeys || '[]'));
    const localChanged = scopeKeys.size
      ? changed.filter(key => scopeKeys.has(key))
      : changed;
    button.disabled = localChanged.length === 0 && button.dataset.analysisAlways !== 'true';
  });
  renderDatavizStateSummaries();
  return changed;
};
const renderComputeResult = async (changedKeys, options = {}) => {
  const contentAffected = syncDatavizContentBindings(changedKeys);
  if (contentAffected.size) {
    datavizRuntime.renderViews({
      initial:false,
      changedSelectionKeys:[],
      changedComputeKeys:changedKeys,
      affectedViewIds:[...contentAffected],
    });
  }
  const changedOutputs = await datavizRuntime.runTransforms([], [], {
    changedComputeKeys:changedKeys,
    apply:options.apply === true,
    manualTargets:options.manualTargets || [],
  });
  window.dispatchEvent(new CustomEvent('dataviz:computechange', {
    detail:{
      compute_parameters:window.dataviz.compute_parameters,
      changed:changedKeys,
      outputs:[...changedOutputs],
    },
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:compute-changed',
      compute_parameters:window.dataviz.compute_parameters,
      draft_compute_parameters:window.dataviz.draft_compute_parameters,
    });
  }
};
window.dataviz.applyCompute = async (options = {}) => {
  const draft = readComputeInputs();
  const requested = options.keys || datavizChangedComputeKeys(window.dataviz.compute_parameters || {}, draft);
  const changed = requested.filter(key => datavizValueSignature(window.dataviz.compute_parameters?.[key]) !== datavizValueSignature(draft[key]));
  const committed = {...(window.dataviz.compute_parameters || {})};
  changed.forEach(key => { committed[key] = structuredClone(draft[key]); });
  window.dataviz.compute_parameters = committed;
  syncComputeDirtyState();
  await renderComputeResult(changed, options);
};
window.dataviz.applyControls = async (options = {}) => {
  const requestedKeys = options.keys || [];
  const draft = readComputeInputs();
  const computeKeys = requestedKeys.filter(key => Object.prototype.hasOwnProperty.call(draft, key));
  const selectionKeys = requestedKeys.filter(key => Object.prototype.hasOwnProperty.call(datavizSelectionState(), key));
  const changedComputeKeys = computeKeys.filter(key => (
    datavizValueSignature(window.dataviz.compute_parameters?.[key])
    !== datavizValueSignature(draft[key])
  ));
  const committed = {...(window.dataviz.compute_parameters || {})};
  changedComputeKeys.forEach(key => { committed[key] = structuredClone(draft[key]); });
  window.dataviz.compute_parameters = committed;
  syncComputeDirtyState();
  const contentAffected = syncDatavizContentBindings(changedComputeKeys);
  if (contentAffected.size) {
    datavizRuntime.renderViews({
      initial:false,
      changedSelectionKeys:[],
      changedComputeKeys,
      affectedViewIds:[...contentAffected],
    });
  }
  const changedOutputs = await datavizRuntime.runTransforms(selectionKeys, [], {
    changedComputeKeys,
    apply:true,
    manualTargets:options.manualTargets || [],
  });
  window.dispatchEvent(new CustomEvent('dataviz:computechange', {
    detail:{
      compute_parameters:window.dataviz.compute_parameters,
      changed:changedComputeKeys,
      outputs:[...changedOutputs],
    },
  }));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:compute-changed',
      compute_parameters:window.dataviz.compute_parameters,
      draft_compute_parameters:window.dataviz.draft_compute_parameters,
    });
  }
};
window.dataviz.applySelections = async () => {
  const previous = window.dataviz.appliedSelectionState || null;
  // On first paint the canonical values come from the validated Query/report
  // snapshot. Dynamic <select> elements are intentionally empty until their
  // immutable option domains are available, so reading the DOM first would erase
  // a valid required default and abort every unrelated View.
  if (previous != null) readSelectionInputs();
  refreshSelectionOptionDomains();
  readSelectionInputs();
  const current = datavizSelectionStateSnapshot();
  const changedSelectionKeys = datavizChangedSelectionKeys(previous, current);
  let affectedViewIds = datavizRuntime.affectedViews(changedSelectionKeys, new Set());
  const contentAffectedViewIds = syncDatavizContentBindings(changedSelectionKeys);
  if (affectedViewIds != null) {
    affectedViewIds = [...new Set([...affectedViewIds, ...contentAffectedViewIds])];
  }
  window.dataviz.appliedSelectionState = structuredClone(current);
  renderDatavizStateSummaries();
  window.dataviz.renderContext = {
    initial: changedSelectionKeys == null,
    changedSelectionKeys: changedSelectionKeys || Object.keys(current),
    affectedViewIds,
  };
  if (changedSelectionKeys == null || changedSelectionKeys.length) {
    datavizRuntime.renderViews(window.dataviz.renderContext);
  }
  window.dispatchEvent(new CustomEvent('dataviz:selectionchange', {detail: structuredClone(current)}));
  if (window.parent !== window) {
    datavizPostToParent({
      type:'dataviz:selections-changed',
      selection_state:structuredClone(current),
      selection_epoch:Number(window.dataviz.selection_epoch || 0),
    });
  }
  await datavizRuntime.runTransforms(changedSelectionKeys, [], {
    changedComputeKeys: previous == null ? null : [],
  });
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
const setSelectionInputs = states => {
  // The parent owns Dashboard Controls, which deliberately have no duplicate
  // input inside the Canvas. Commit every canonical state first; DOM syncing is
  // only a projection for Controls that are actually rendered in this frame.
  const known = window.dataviz.dependency_contract?.controls || {};
  Object.entries(states || {}).forEach(([key, state]) => {
    if (known[key]?.kind !== 'selection') return;
    datavizSelectionState()[key] = datavizNormalizeSelectionState(key, state);
  });
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    if (!(key in states)) return;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const value = datavizSelectionValue(key);
    const encode = item => datavizEncodeControlValue(input, item, {
      path:control.dataset.selectionPath === 'true',
    });
    const definition = datavizSelectionDefinition(key);
    if (definition.value_type === 'boolean' && input.tagName === 'SELECT') {
      input.value = value == null ? '' : encode(value);
    }
    else if (definition.value_type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(encode));
      Array.from(input.options).forEach(option => {
        option.selected = selected.has(option.value);
      });
      syncPortableChoices(control);
    }
    else if (definition.type === 'range_input' && Array.isArray(value)) {
      input.value = value.length ? value.join(',') : '';
    }
    else if (input.tagName === 'SELECT') input.value = value == null ? '' : encode(value);
    else if (definition.type === 'multiple_input' && Array.isArray(value)) input.value = JSON.stringify(value);
    else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  });
};
const setComputeInputs = values => {
  window.dataviz.draft_compute_parameters = {
    ...(window.dataviz.draft_compute_parameters || {}),
    ...(values || {}),
  };
  document.querySelectorAll('[data-compute-key]').forEach(control => {
    const key = control.dataset.computeKey;
    if (!(key in (values || {}))) return;
    const input = control.querySelector('[data-compute-input]');
    if (!input || input.disabled) return;
    const value = values[key];
    const definition = window.dataviz.compute_definitions?.[key] || {
      type:input.dataset.computeType,
      value_type:input.dataset.valueType || 'text',
    };
    const type = definition.type;
    if (type === 'range_input') {
      const range = Array.isArray(value) ? value : String(value || '').split(',', 2);
      input.value = range.some(Boolean) ? `${range[0] || ''},${range[1] || ''}` : '';
    } else if (definition.value_type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((value || []).map(item => datavizEncodeControlValue(input, item)));
      Array.from(input.options).forEach(option => { option.selected = selected.has(option.value); });
    } else if (input.tagName === 'SELECT') {
      input.value = value == null ? '' : datavizEncodeControlValue(input, value);
    } else if (type === 'multiple_input') input.value = JSON.stringify(value || []);
    else input.value = value ?? '';
  });
  syncComputeDirtyState();
};
window.addEventListener('message', event => {
  if (
    event.origin !== window.location.origin
    || window.parent === window
    || event.source !== window.parent
    || !datavizSameFrameIdentity(event.data)
  ) return;
  if (event.data?.type === 'dataviz:set-selections') {
    const values = event.data.selection_state || {};
    window.dataviz.selection_epoch = Number(event.data.selection_epoch || 0);
    setSelectionInputs(values);
    window.dataviz.applySelections().catch(error => console.error('[dataviz:selections]', error));
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
      datavizRuntime.runTransforms([], [], {
        changedComputeKeys: [],
        targets,
      }).catch(error => console.error('[dataviz:interaction]', error));
    }
  }
  if (event.data?.type === 'dataviz:set-compute') {
    const values = event.data.compute_parameters || {};
    setComputeInputs(values);
    if (event.data.commit) {
      const apply = event.data.control_keys == null
        ? window.dataviz.applyCompute
        : window.dataviz.applyControls;
      apply({
        keys:event.data.control_keys || Object.keys(values),
        apply:event.data.apply !== false,
        manualTargets:event.data.manual_targets || [],
      }).catch(error => console.error('[dataviz:compute]', error));
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
        selection_state:datavizSelectionStateSnapshot(),
        compute_parameters:structuredClone(window.dataviz.compute_parameters || {}),
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
