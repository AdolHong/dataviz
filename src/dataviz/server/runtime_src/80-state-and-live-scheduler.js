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
  const appliedStates = window.dataviz.consumer_applied_control_state || {};
  const appliedWriterProvenance = (
    window.dataviz.consumer_applied_writer_provenance || {}
  );
  const project = (consumerType, consumerId, bindings, trigger) => {
    const keys = [...new Set(
      Object.values(bindings || {}).map(binding => binding.control).filter(Boolean)
    )].sort();
    if (!keys.length) return null;
    const controls = Object.fromEntries(keys.map(key => {
      const effectiveRevision = datavizControlEntry(key)?.revision ?? 0;
      const rawApplied = applied?.[consumerType]?.[consumerId]?.[key];
      return [key, datavizNormalizeConsumerRevision(
        effectiveRevision,
        rawApplied ?? null,
      )];
    }));
    const captured = Object.fromEntries(keys.flatMap(key => {
      const state = appliedStates?.[consumerType]?.[consumerId]?.[key];
      return state ? [[key, structuredClone(state)]] : [];
    }));
    const writerProvenance = Object.fromEntries(keys.flatMap(key => {
      const item = appliedWriterProvenance?.[consumerType]?.[consumerId]?.[key];
      return item ? [[key, structuredClone(item)]] : [];
    }));
    return {
      trigger,
      stale:Object.values(controls).some(item => item.stale),
      controls,
      applied_control_state:captured,
      applied_writer_provenance:writerProvenance,
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
      // A Control may feed consumers at different applied revisions. The item
      // projection therefore reports canonical current state; exact result-
      // producing values live in consumer_revisions.applied_control_state.
      const committed = structuredClone(current);
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
      window.dataviz.query_parameter_state?.[item.id] ?? item.committed
    );
    const draft = structuredClone(
      window.dataviz.draft_query_parameter_state?.[item.id] ?? item.draft ?? committed
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
    schema:'dataviz/state-snapshot/v5',
    dashboard:window.dataviz.dashboard_id,
    query_stale:queryStale,
    items,
    applied_revisions:structuredClone(
      window.dataviz.applied_revisions || initial.applied_revisions || {}
    ),
    applied_control_state:structuredClone(
      window.dataviz.consumer_applied_control_state
      || initial.applied_control_state
      || {views:{}, transforms:{}}
    ),
    control_writer_provenance:structuredClone(
      window.dataviz.control_writer_provenance
      || initial.control_writer_provenance
      || {}
    ),
    applied_writer_provenance:structuredClone(
      window.dataviz.consumer_applied_writer_provenance
      || initial.applied_writer_provenance
      || {views:{}, transforms:{}}
    ),
    consumer_revisions:datavizConsumerRevisionEvidence(),
  };
  window.dataviz.state_snapshot = snapshot;
  return snapshot;
};
const datavizStateLogicalValue = (item, state = item.committed) => {
  if (item.entry_type === 'control') {
    return datavizControlValueFromState(item.definition || {}, state);
  }
  if (state && typeof state === 'object' && !Array.isArray(state) && 'value' in state) {
    return state.value;
  }
  return state;
};
const datavizStateChoiceLabel = (definition, value) => {
  const match = datavizStaticChoices(definition || {}).find(
    choice => datavizValueSignature(choice.value) === datavizValueSignature(value)
  );
  return match?.label || (Array.isArray(value) ? value.join(' / ') : String(value ?? ''));
};
const datavizStateValueParts = (
  item,
  rawValue,
  formatter = 'auto',
  state = item.committed,
) => {
  if (item.entry_type === 'control' && item.committed?.intent === 'all_available') {
    const values = Array.isArray(rawValue) ? rawValue : [];
    return [values.length ? `全部（${values.length}）` : '全部'];
  }
  if (item.entry_type === 'query_parameter' && item.type === 'multiple_select') {
    const selection = state?.selection || 'include';
    const values = Array.isArray(rawValue) ? rawValue : [];
    if (selection === 'all') return ['全部'];
    if (selection === 'none') return ['未选择'];
    if (selection === 'exclude') {
      return [values.length ? `全部（排除 ${values.length} 项）` : '全部'];
    }
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
    const draftParts = datavizStateValueParts(
      item,
      datavizStateLogicalValue(item, item.draft),
      formatter,
      item.draft,
    );
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
  const evidence = datavizConsumerRevisionEvidence();
  const changed = [...new Set(
    Object.values(evidence.transforms)
      .filter(consumer => consumer.trigger !== 'auto' && consumer.stale)
      .flatMap(consumer => Object.entries(consumer.controls)
        .filter(([, revision]) => revision.stale)
        .map(([key]) => key))
  )].sort();
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
window.dataviz.syncControlDirtyState = syncControlDirtyState;
const datavizManualTargetsForControlKeys = keys => {
  const selected = new Set(keys || []);
  return [...datavizRuntime.transforms.entries()]
    .filter(([id, item]) => (
      item.spec.trigger === 'manual'
      && Object.values(datavizRuntime.transformControlInputs(id))
        .some(binding => selected.has(binding.control))
    ))
    .map(([id]) => id);
};
window.dataviz.applyControls = async (options = {}) => {
  const previous = window.dataviz.current_control_state || null;
  const selectedKeys = options.keys ? new Set(options.keys) : null;
  // Dynamic selects are empty until their immutable option domain is hydrated;
  // preserve the compiled initial state during the first pass.
  if (previous != null && options.canonicalStateCommitted !== true) {
    readControlInputs({keys:selectedKeys});
  }
  refreshControlOptionDomains({
    canonicalKeys:options.canonicalStateCommitted === true ? selectedKeys : null,
  });
  if (options.canonicalStateCommitted === true) {
    const canonical = datavizControlStateSnapshot();
    setControlInputs(Object.fromEntries(
      Object.entries(canonical).filter(([key]) => !selectedKeys || selectedKeys.has(key))
    ));
  }
  readControlInputs({keys:selectedKeys});
  const current = datavizControlStateSnapshot();
  const changed = datavizChangedControlKeys(previous, current);
  window.dataviz.current_control_state = structuredClone(current);
  let affectedViewIds = datavizRuntime.affectedViews(changed, new Set());
  const contentAffected = syncDatavizContentBindings(changed);
  if (affectedViewIds != null) affectedViewIds = [...new Set([...affectedViewIds, ...contentAffected])];
  window.dataviz.draft_control_state = structuredClone(current);
  window.dataviz.renderContext = {
    initial:changed == null,
    changedControlKeys:changed || Object.keys(current),
    affectedViewIds,
  };
  syncControlDirtyState();
  if (changed == null || changed.length) datavizRuntime.renderViews(window.dataviz.renderContext);
  const transformPromise = datavizRuntime.runTransforms(changed, [], {
    apply:options.apply === true,
    manualTargets:options.apply === true
      ? datavizManualTargetsForControlKeys(options.keys || Object.keys(current))
      : [],
    targets:options.targets,
  });
  const changedOutputs = options.awaitConsumers === false
    ? new Set()
    : await transformPromise;
  if (options.awaitConsumers === false) {
    transformPromise.catch(error => console.error('[dataviz:consumers]', error));
  }
  window.dispatchEvent(new CustomEvent('dataviz:controlchange', {
    detail:{control_state:structuredClone(current), changed:changed || Object.keys(current), outputs:[...changedOutputs]},
  }));
  if (previous != null && changed?.length) {
    datavizControlChannel.controlVersion += 1;
  }
  datavizRuntime.publishControlImpacts();
  if (
    datavizControlChannel.phase === 'ready'
    && options.publishSnapshot !== false
  ) {
    return datavizPublishControlSnapshot(options.causedByActionId || null);
  }
  return datavizControlOperationalSnapshot(options.causedByActionId || null);
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
    if (
      input === document.activeElement
      && input.dataset.localDraftInvalid === 'true'
    ) {
      input._syncChoiceControl?.();
      return;
    }
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
const datavizControlChannel = {
  phase:window.parent === window ? 'portable' : 'awaiting_restore',
  controlVersion:0,
  restoreOpen:window.parent !== window,
  restorePromise:null,
  restoreResolve:null,
  actionResults:new Map(),
  actionQueue:Promise.resolve(),
};
const datavizRememberControlActionResult = (actionId, result) => {
  if (!actionId) return result;
  datavizControlChannel.actionResults.set(actionId, result);
  while (datavizControlChannel.actionResults.size > 256) {
    datavizControlChannel.actionResults.delete(
      datavizControlChannel.actionResults.keys().next().value,
    );
  }
  return result;
};
if (datavizControlChannel.restoreOpen) {
  datavizControlChannel.restorePromise = new Promise(resolve => {
    datavizControlChannel.restoreResolve = resolve;
  });
}
const datavizControlOperationalSnapshot = (
  causedByActionId = null,
  causedBySourceView = null,
) => {
  const impacts = datavizControlImpactSnapshot();
  const impactByKey = new Map(impacts.map(item => [item.key, item]));
  const occurrences = datavizControlOccurrences();
  const dashboardControls = [];
  occurrences.forEach((targets, key) => {
    if (targets[0]?.item?.origin !== 'dashboard') return;
    const availability = datavizAvailableControlOptions(targets);
    const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
    const domainPending = Boolean(
      datavizControlDomainReferences(targets[0]?.item).length
      && !availability.observed
    );
    const relationInvalid = availability.observed
      && !availability.dependencyRelationReady;
    dashboardControls.push({
      key,
      state:structuredClone(datavizControlEntry(key)),
      options:structuredClone(availability.options),
      availability:availability.observed ? 'ready' : domainPending ? 'loading' : 'static',
      validation:relationInvalid ? {
        code:'control_option_domain_dependency_fields_missing',
        message:'Option-domain rows do not expose every declared dependency field.',
      } : null,
      disabled:relationInvalid,
      loading:domainPending,
      impact:structuredClone(impactByKey.get(key) || null),
      depends_on:[...(dependency.depends_on || [])],
    });
  });
  return {
    control_version:datavizControlChannel.controlVersion,
    current_controls:datavizControlStateSnapshot(),
    dashboard_controls:dashboardControls,
    ...(causedByActionId ? {caused_by_action_id:causedByActionId} : {}),
    ...(causedByActionId ? {caused_by_source_view:causedBySourceView} : {}),
  };
};
const datavizPublishControlSnapshot = (causedByActionId, causedBySourceView = null) => {
  const snapshot = datavizControlOperationalSnapshot(
    causedByActionId,
    causedBySourceView,
  );
  datavizPostToParent({
    type:'dataviz:control-snapshot',
    source_view:causedBySourceView,
    snapshot,
  });
  return snapshot;
};
const datavizRejectControlAction = (
  actionId,
  code,
  {includeSnapshot = true, sourceView = null} = {},
) => {
  const payload = {
    type:'dataviz:action-rejected',
    action_id:actionId || null,
    source_view:sourceView,
    code,
    control_version:datavizControlChannel.controlVersion,
    ...(includeSnapshot ? {snapshot:datavizControlOperationalSnapshot()} : {}),
  };
  datavizPostToParent(payload);
  return payload;
};
const datavizCloseRestoreWindow = value => {
  if (!datavizControlChannel.restoreOpen) return false;
  datavizControlChannel.restoreOpen = false;
  datavizControlChannel.restoreResolve?.(value);
  datavizControlChannel.restoreResolve = null;
  return true;
};
const datavizNormalizeCheckpoint = checkpoint => {
  if (checkpoint == null) return null;
  if (
    typeof checkpoint !== 'object'
    || Array.isArray(checkpoint)
    || typeof checkpoint.controls !== 'object'
    || Array.isArray(checkpoint.controls)
  ) {
    throw datavizContractError(
      'control_checkpoint_invalid',
      'Control checkpoint must contain canonical controls',
    );
  }
  if (
    checkpoint.control_contract_hash
    !== window.dataviz.dependency_contract?.control_contract_hash
  ) {
    throw datavizContractError(
      'control_checkpoint_contract_mismatch',
      'Control checkpoint belongs to another Control contract',
    );
  }
  const expected = Object.keys(window.dataviz.dependency_contract?.controls || {}).sort();
  const actual = Object.keys(checkpoint.controls || {}).sort();
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    throw datavizContractError(
      'control_checkpoint_keys_mismatch',
      'Control checkpoint keys differ from the current contract',
    );
  }
  return Object.fromEntries(expected.map(key => [
    key,
    datavizNormalizeControlState(key, checkpoint.controls[key]),
  ]));
};
const datavizAwaitControlRestore = async () => {
  if (window.parent === window) return null;
  datavizPostToParent({
    type:'dataviz:control-hello',
    control_contract_hash:window.dataviz.dependency_contract?.control_contract_hash || null,
  });
  const timeout = new Promise(resolve => setTimeout(() => resolve({timeout:true}), 750));
  const received = await Promise.race([datavizControlChannel.restorePromise, timeout]);
  if (received?.timeout) datavizCloseRestoreWindow(null);
  return received?.timeout ? null : received;
};
const datavizMarkControlReady = () => {
  datavizControlChannel.phase = 'ready';
  return datavizControlOperationalSnapshot();
};
const datavizValidateHostControlCommand = data => {
  const actionId = typeof data?.action_id === 'string' ? data.action_id.trim() : '';
  if (!actionId || actionId.length > 128) {
    throw datavizContractError('control_action_id_invalid', 'Control action_id is required');
  }
  if (!Number.isSafeInteger(data.base_control_version) || data.base_control_version < 0) {
    throw datavizContractError(
      'control_base_version_invalid',
      'base_control_version must be a non-negative safe integer',
    );
  }
  if (data.source_view !== null) {
    throw datavizContractError(
      'control_action_source_invalid',
      'Host Control actions must declare source_view=null',
    );
  }
  return actionId;
};
const datavizHandleHostControlCommand = data => {
  const queued = async () => {
    let actionId = null;
    try {
      actionId = datavizValidateHostControlCommand(data);
      const previousResult = datavizControlChannel.actionResults.get(actionId);
      if (previousResult) {
        datavizPostToParent(previousResult);
        return previousResult;
      }
      if (datavizControlChannel.phase !== 'ready') {
        const rejected = datavizRejectControlAction(
          actionId,
          'control_runtime_not_ready',
          {sourceView:data.source_view},
        );
        datavizRememberControlActionResult(actionId, rejected);
        return rejected;
      }
      if (data.base_control_version !== datavizControlChannel.controlVersion) {
        const rejected = datavizRejectControlAction(
          actionId,
          'stale_control_version',
          {sourceView:data.source_view},
        );
        datavizRememberControlActionResult(actionId, rejected);
        return rejected;
      }
      if (data.type === 'dataviz:control-action') {
        const action = data.action;
        if (!action || action.type !== 'set' || typeof action.control !== 'string') {
          throw datavizContractError(
            'control_action_payload_invalid',
            'Host Control action must be a typed set action',
          );
        }
        const dependency = window.dataviz.dependency_contract?.controls?.[action.control];
        if (!dependency || dependency.origin !== 'dashboard') {
          throw datavizContractError(
            'control_action_scope_invalid',
            `Host cannot write Control ${action.control}`,
          );
        }
        if (
          action.intent != null
          && !['explicit', 'all_available'].includes(action.intent)
        ) {
          throw datavizContractError(
            'control_action_intent_invalid',
            'Host Control action intent must be explicit or all_available',
          );
        }
        const next = datavizSetControlValue(action.control, action.value, {
          intent:action.intent || 'explicit',
        });
        setControlInputs({[action.control]:next});
        await window.dataviz.applyControls({
          keys:[action.control],
          awaitConsumers:false,
          publishSnapshot:false,
        });
      } else if (data.type === 'dataviz:control-apply') {
        if (!Array.isArray(data.keys) || data.keys.some(key => {
          const dependency = window.dataviz.dependency_contract?.controls?.[key];
          return !dependency || dependency.origin !== 'dashboard';
        })) {
          throw datavizContractError(
            'control_apply_scope_invalid',
            'Host Apply keys must be declared Dashboard Controls',
          );
        }
        await window.dataviz.applyControls({
          keys:[...new Set(data.keys)],
          apply:true,
          awaitConsumers:false,
          publishSnapshot:false,
        });
      } else {
        throw datavizContractError('control_command_unknown', 'Unknown Host Control command');
      }
      const snapshot = datavizControlOperationalSnapshot(actionId, data.source_view);
      const response = {
        type:'dataviz:control-snapshot',
        source_view:data.source_view,
        snapshot,
      };
      datavizRememberControlActionResult(actionId, response);
      datavizPostToParent(response);
      return response;
    } catch (error) {
      const code = error?.code || error?.details?.code || 'control_action_invalid';
      const rejected = datavizRejectControlAction(actionId, code, {
        sourceView:data?.source_view ?? null,
      });
      datavizRememberControlActionResult(actionId, rejected);
      return rejected;
    }
  };
  datavizControlChannel.actionQueue = datavizControlChannel.actionQueue
    .catch(() => undefined)
    .then(queued);
  return datavizControlChannel.actionQueue;
};
window.addEventListener('message', event => {
  if (
    event.origin !== window.location.origin
    || window.parent === window
    || event.source !== window.parent
    || !datavizSameFrameIdentity(event.data)
  ) return;
  if (event.data?.type === 'dataviz:restore-checkpoint') {
    if (!datavizControlChannel.restoreOpen) {
      datavizRejectControlAction(null, 'restore_window_closed', {includeSnapshot:false});
      return;
    }
    try {
      datavizCloseRestoreWindow(datavizNormalizeCheckpoint(event.data.checkpoint));
    } catch (error) {
      datavizCloseRestoreWindow(null);
      datavizRejectControlAction(
        null,
        error?.code || error?.details?.code || 'control_checkpoint_invalid',
        {includeSnapshot:false},
      );
    }
    return;
  }
  if (
    event.data?.type === 'dataviz:control-action'
    || event.data?.type === 'dataviz:control-apply'
  ) {
    datavizHandleHostControlCommand(event.data);
    return;
  }
  if (event.data?.type === 'dataviz:set-query-draft') {
    window.dataviz.draft_query_parameter_state = structuredClone(
      event.data.query_parameter_state || {}
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
