// Owner: Control binding, canonical commits, and parent-frame synchronization.
window.addEventListener('dataviz:interactionprogress', event => {
  const detail = event.detail || {};
  const percent = Number.isFinite(Number(detail.value))
    ? ` · ${Math.round(Number(detail.value) * 100)}%`
    : '';
  datavizRuntime.markTransformLoading(
    detail.transformId,
    `${detail.message || 'running analysis'}${percent}`,
  );
});

const DATAVIZ_OWNER_PACKAGE_RUNTIME = true;
const datavizControlFields = item => {
  const field = item.consumer_binding?.field;
  return Array.isArray(field) ? field : [field].filter(Boolean);
};
const datavizControlCanApply = (row, item) => (
  row != null
  && typeof row === 'object'
  && datavizControlFields(item).every(field => Object.prototype.hasOwnProperty.call(row, field))
);
const datavizViewControlContract = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.filter_contract || []
);
const datavizControlContractItem = key => {
  const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
  const definition = dependency.definition || {};
  return {
    key,
    id:definition.id || key?.split('/').at(-1),
    origin:dependency.origin,
    owner_id:dependency.owner_id,
    definition,
    consumer_binding:{
      field:(definition.path_fields || []).length
        ? definition.path_fields
        : (definition.field || definition.id),
      empty:'passthrough',
      operator:'auto',
    },
  };
};
const datavizControlDomainReferences = item => (
  window.dataviz.dependency_contract?.controls?.[item?.key]?.option_domain_references || []
).map(canonicalOutputReference);
const datavizOutputFieldNames = rawReference => {
  const reference = canonicalOutputReference(rawReference);
  if (datavizRuntime.outputErrors.has(reference)) return null;
  const schema = window.dataviz.portable?.output_schemas?.[reference];
  if (Array.isArray(schema) && schema.length) {
    return new Set(schema.map(column => column?.name).filter(Boolean));
  }
  const outputs = window.dataviz.portable?.outputs || {};
  if (!Object.prototype.hasOwnProperty.call(outputs, reference)) return null;
  const value = outputs[reference];
  if (value?.__datavizArrowOutput) {
    return new Set(value.table.schema.fields.map(field => field.name));
  }
  const rows = datavizTableRows(value);
  if (!rows.length) return null;
  return new Set(rows.flatMap(row => Object.keys(row || {})));
};
const datavizControlViewApplicability = (viewId, item) => {
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key];
  if (!dependency) return 'not_applicable';
  if ((dependency.declared_direct_views || []).includes(viewId)) return 'applies';
  const binding = dependency.direct_view_bindings?.[viewId];
  if (!binding || binding.applicability === 'not_applicable') return 'not_applicable';
  const fields = binding.fields?.length ? binding.fields : datavizControlFields(item);
  let pending = false;
  for (const reference of binding.input_references || []) {
    if (window.dataviz.portable?.output_kinds?.[canonicalOutputReference(reference)] !== 'table') {
      continue;
    }
    const names = datavizOutputFieldNames(reference);
    if (names == null) {
      pending = true;
      continue;
    }
    if (fields.every(field => names.has(field))) return 'applies';
  }
  return pending ? 'pending' : 'not_applicable';
};
const datavizControlImpactSnapshot = () => Object.entries(
  window.dataviz.dependency_contract?.controls || {}
).map(([key, dependency]) => {
  const affected = new Set([
    ...(dependency.declared_direct_views || []),
    ...(dependency.derived_views || []),
    ...(dependency.content_views || []),
  ]);
  (dependency.writer_edges || []).forEach(edge => affected.add(edge.source_view));
  let pending = false;
  (dependency.runtime_checked_views || []).forEach(viewId => {
    const item = datavizViewControlContract(viewId).find(candidate => candidate.key === key);
    if (!item) return;
    const applicability = datavizControlViewApplicability(viewId, item);
    if (applicability === 'applies') affected.add(viewId);
    if (applicability === 'pending') pending = true;
  });
  return {
    key,
    status:pending ? 'pending' : 'resolved',
    affected_views:[...affected].sort(),
    potential_views:[...(dependency.affected_views || [])].sort(),
  };
});
const datavizControlImpactLabel = impact => {
  const views = impact.status === 'pending' ? impact.potential_views : impact.affected_views;
  const count = views.length;
  return `${impact.status === 'pending' ? 'Up to ' : ''}${count} view${count === 1 ? '' : 's'}`;
};
const datavizControlState = () => {
  if (!window.dataviz.control_state || typeof window.dataviz.control_state !== 'object') {
    window.dataviz.control_state = {};
  }
  return window.dataviz.control_state;
};
const datavizControlWriterProvenance = () => {
  if (
    !window.dataviz.control_writer_provenance
    || typeof window.dataviz.control_writer_provenance !== 'object'
  ) window.dataviz.control_writer_provenance = {};
  return window.dataviz.control_writer_provenance;
};
const datavizControlDefinition = key => (
  window.dataviz.dependency_contract?.controls?.[key]?.definition
  || Object.values(window.dataviz.dependency_contract?.views || {})
    .flatMap(view => view.filter_contract || [])
    .find(item => item.key === key)?.definition
  || {}
);
const datavizNormalizeControlState = (key, candidate = null) => {
  const definition = datavizControlDefinition(key);
  const initial = window.dataviz.dependency_contract?.controls?.[key]?.initial_state || {
    value:null, revision:0,
  };
  const source = candidate && typeof candidate === 'object' ? candidate : initial;
  const revision = source.revision ?? 0;
  if (!Number.isSafeInteger(revision) || revision < 0) {
    throw datavizContractError(
      'control_state_revision_invalid',
      `Control ${key} revision must be a non-negative safe integer`,
    );
  }
  const value = datavizNormalizeControlValue(definition, source.value, {
    namespace:'control_state', key,
  });
  const intent = definition.type === 'multiple_select'
    ? (source.intent === 'all_available' ? 'all_available' : 'explicit')
    : null;
  return {value:structuredClone(value), revision, ...(intent ? {intent} : {})};
};
const datavizControlEntry = key => {
  const state = datavizControlState();
  if (!state[key]) state[key] = datavizNormalizeControlState(key);
  return state[key];
};
const datavizControlValueFromState = (_definition, entry) => structuredClone(entry?.value);
const datavizControlValue = key => datavizControlValueFromState(
  datavizControlDefinition(key),
  datavizControlEntry(key),
);
const datavizSetControlValue = (key, value, {intent = null} = {}) => {
  const definition = datavizControlDefinition(key);
  const normalized = datavizNormalizeControlValue(definition, value, {
    namespace:'control', key,
  });
  const previous = datavizControlEntry(key);
  const candidate = datavizNormalizeControlState(key, {
    intent:intent || previous.intent || 'explicit',
    value:normalized,
    revision:Number(previous.revision || 0),
  });
  if (
    datavizValueSignature(previous.value) === datavizValueSignature(candidate.value)
    && previous.intent === candidate.intent
  ) return previous;
  datavizControlState()[key] = {
    ...candidate,
    revision:Number(previous.revision || 0) + 1,
  };
  delete datavizControlWriterProvenance()[key];
  return datavizControlState()[key];
};
const datavizControlStateSnapshot = () => {
  const validKeys = new Set(Object.keys(window.dataviz.dependency_contract?.controls || {}));
  return Object.fromEntries([...validKeys].map(key => [
    key,
    structuredClone(datavizControlEntry(key)),
  ]));
};
const datavizControlValueSnapshot = () => Object.fromEntries(
  Object.keys(datavizControlStateSnapshot()).map(key => [key, datavizControlValue(key)]),
);
const datavizControlEntryFrom = (state, key) => (
  state?.[key] ? structuredClone(state[key]) : structuredClone(datavizControlEntry(key))
);
const datavizProjectControlBinding = (binding, controlState = null) => {
  const entry = datavizControlEntryFrom(controlState, binding.control);
  if (binding.projection === 'present') return !datavizIsEmptyControlValue(entry.value);
  if (binding.projection === 'intent') return entry.intent || 'explicit';
  return structuredClone(entry.value);
};
const datavizPrepareControlInputs = (bindings, rawInputs, controlState = null) => {
  const inputs = {...rawInputs};
  Object.entries(bindings || {}).forEach(([alias, binding]) => {
    if (binding.mode !== 'filter') return;
    const item = {
      key:binding.control,
      id:binding.control.split('/').at(-1),
      definition:datavizControlDefinition(binding.control),
      consumer_binding:binding,
    };
    (binding.inputs || []).forEach(inputAlias => {
      inputs[inputAlias] = datavizTableRows(inputs[inputAlias]).filter(row => (
        datavizControlMatches(row, item, datavizControlEntryFrom(controlState, binding.control))
      ));
    });
  });
  return {
    inputs,
    controlInputs:Object.fromEntries(
      Object.entries(bindings || {}).map(([alias, binding]) => [
        alias,
        datavizProjectControlBinding(binding, controlState),
      ])
    ),
  };
};
const datavizCaptureConsumerControlState = (bindings, controlState = null) => {
  const keys = [...new Set(
    Object.values(bindings || {}).map(binding => binding.control).filter(Boolean)
  )].sort();
  return Object.fromEntries(keys.map(key => [
    key,
    datavizControlEntryFrom(controlState, key),
  ]));
};
const datavizCaptureConsumerWriterProvenance = (
  bindings,
  capturedControlState,
  writerProvenance = null,
) => {
  const provenance = writerProvenance || datavizControlWriterProvenance();
  return Object.fromEntries(Object.keys(capturedControlState || {}).flatMap(key => {
    const item = provenance?.[key];
    const revision = capturedControlState?.[key]?.revision;
    return item && item.revision === revision
      ? [[key, structuredClone(item)]]
      : [];
  }));
};
const datavizCommitConsumerControlState = (
  consumerType,
  consumerId,
  capturedControlState,
  capturedWriterProvenance = {},
) => {
  if (!['views', 'transforms'].includes(consumerType)) {
    throw new Error(`Unknown Control consumer type: ${consumerType}`);
  }
  const captured = structuredClone(capturedControlState || {});
  window.dataviz.applied_revisions ||= {views:{}, transforms:{}};
  window.dataviz.consumer_applied_control_state ||= {views:{}, transforms:{}};
  window.dataviz.consumer_applied_writer_provenance ||= {views:{}, transforms:{}};
  window.dataviz.applied_revisions[consumerType] ||= {};
  window.dataviz.consumer_applied_control_state[consumerType] ||= {};
  window.dataviz.consumer_applied_writer_provenance[consumerType] ||= {};
  window.dataviz.applied_revisions[consumerType][consumerId] = Object.fromEntries(
    Object.entries(captured).map(([key, state]) => [key, Number(state.revision || 0)])
  );
  window.dataviz.consumer_applied_control_state[consumerType][consumerId] = captured;
  window.dataviz.consumer_applied_writer_provenance[consumerType][consumerId]
    = structuredClone(capturedWriterProvenance || {});
  if (window.dataviz.syncControlDirtyState) window.dataviz.syncControlDirtyState();
  else window.dataviz.renderStateSummaries?.();
  return captured;
};
const datavizControlMatches = (row, item, state) => {
  // Dashboard and Section controls are inherited structurally. A View whose
  // dataset does not expose the selected field is outside that data contract;
  // it must remain visible instead of being reduced to an accidental empty set.
  if (!datavizControlCanApply(row, item)) return true;
  const binding = item.consumer_binding || {};
  const value = datavizControlValueFromState(item.definition || {}, state || {value:null});
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return binding.empty === 'passthrough';
  }
  const pathFields = datavizControlFields(item);
  if (pathFields.length > 1) {
    return datavizPathControlMatch({row, fields:pathFields, value});
  }
  const field = pathFields[0];
  const actual = row[field];
  const operator = binding.operator === 'auto'
    ? (['multiple_input', 'multiple_select'].includes(item.definition?.type) ? 'in' : item.definition?.type === 'range_input' ? 'between' : 'equals')
    : binding.operator;
  return datavizTypedControlMatch({
    actual,
    value,
    operator,
    valueType:String(item.definition?.value_type || 'text'),
  });
};
const datavizControlIntentKey = input => (
  input?.closest('[data-control-key]')?.dataset.controlKey || null
);
const datavizCaptureControlIntent = input => {
  const key = datavizControlIntentKey(input);
  const consume = window.datavizComponents?.controls?.consumeSelectionIntent;
  if (!key || !consume) return null;
  const intent = consume(input);
  if (intent) datavizControlEntry(key).intent = intent;
  return intent;
};
const datavizReconcileControlOptionDomain = (
  input,
  nextOptions,
  {selectedValues = [], required = input?.required === true} = {},
) => {
  const reconcile = window.datavizComponents?.controls?.reconcileOptionDomain;
  if (!reconcile) {
    input.replaceChildren(...Array.from(nextOptions || []));
    return {intent:null, selectedValues:[]};
  }
  const key = datavizControlIntentKey(input);
  const state = key ? datavizControlEntry(key) : {intent:'explicit', value:[], revision:0};
  const definition = key ? datavizControlDefinition(key) : {};
  const policy = definition.initial || {
    mode:definition.type === 'multiple_select' ? 'all' : 'first',
  };
  const rawInitialValues = policy.mode === 'values'
    ? (policy.values || [])
    : policy.mode === 'value'
      ? [policy.value]
      : [];
  const initialValues = rawInitialValues.map(value => datavizEncodeControlValue(input, value, {
    path:input.closest('[data-control-key]')?.dataset.controlPath === 'true',
  }));
  const result = reconcile(input, nextOptions, {
    selectedValues,
    intent:state.intent,
    required,
    initial:{mode:policy.mode, values:initialValues},
  });
  if (key && result.intent) state.intent = result.intent;
  return result;
};
window.dataviz.control = {
  fields: datavizControlFields,
  canApply: datavizControlCanApply,
  matches: datavizControlMatches,
  captureIntent: datavizCaptureControlIntent,
  reconcileOptionDomain: datavizReconcileControlOptionDomain,
  state: datavizControlEntry,
  value: datavizControlValue,
  set: datavizSetControlValue,
  stateSnapshot: datavizControlStateSnapshot,
  captureConsumerState:datavizCaptureConsumerControlState,
  captureConsumerWriterProvenance:datavizCaptureConsumerWriterProvenance,
  commitConsumerState:datavizCommitConsumerControlState,
};
let datavizControlActionRevision = 0;
let datavizControlActionQueue = Promise.resolve();
const datavizControlBindingForView = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.control_binding || null
);
const datavizViewActionRejection = (event, code) => ({
  status:'rejected',
  code,
  action_id:typeof event?.action_id === 'string' ? event.action_id : null,
  source_view:typeof event?.source_view === 'string' ? event.source_view : null,
});
const datavizControlBindingValue = (binding, datum) => {
  if (datum && Object.prototype.hasOwnProperty.call(datum, '__datavizControlValue')) {
    return structuredClone(datum.__datavizControlValue);
  }
  if (!datum || typeof datum !== 'object') return structuredClone(datum);
  const values = (binding?.fields || []).map(field => datum[field]);
  return values.length === 1 ? values[0] : values;
};
const datavizDispatchControlAction = event => {
  const sourceView = typeof event?.source_view === 'string' ? event.source_view : '';
  const actionId = typeof event?.action_id === 'string' ? event.action_id.trim() : '';
  if (!actionId || actionId.length > 128) {
    return Promise.resolve(datavizViewActionRejection(event, 'control_action_id_invalid'));
  }
  const binding = datavizControlBindingForView(sourceView);
  if (!binding || binding.control !== event?.control) {
    return Promise.resolve(datavizViewActionRejection(
      event,
      'control_action_binding_invalid',
    ));
  }
  const root = document.querySelector(
    `.dv-view[data-view-id="${CSS.escape(sourceView)}"]`
  );
  if (!root || (
    event.generation != null
    && Number(event.generation) !== Number(root._datavizRenderGeneration || 0)
  )) {
    return Promise.resolve(datavizViewActionRejection(
      event,
      'stale_view_generation',
    ));
  }
  // This synchronous ingress check is the action's admission/linearization
  // point.  A previously admitted action can legitimately rerender the same
  // writer while later user actions wait in this queue; that generation
  // change must not retroactively invalidate those already-admitted actions.
  datavizControlActionQueue = datavizControlActionQueue.catch(() => undefined).then(async () => {
    const currentRoot = document.querySelector(
      `.dv-view[data-view-id="${CSS.escape(sourceView)}"]`
    );
    // Replacing/removing the writer is a different lifetime boundary from a
    // normal render-generation advance and still invalidates the admission.
    if (!currentRoot || currentRoot !== root) {
      return datavizViewActionRejection(event, 'stale_view_generation');
    }
    const definition = datavizControlDefinition(binding.control);
    const current = datavizControlEntry(binding.control);
    let next;
    let value;
    if (event.action === 'reset') {
      next = datavizNormalizeControlState(binding.control);
    } else if (event.action === 'clear') value = definition.type === 'range_input' ? [] : (
      ['multiple_input', 'multiple_select'].includes(definition.type) ? [] : null
    );
    else if (event.action === 'select_many') {
      value = (event.data || []).map(datum => datavizControlBindingValue(binding, datum));
    } else if (event.action === 'select') {
      const selected = datavizControlBindingValue(binding, event.data);
      value = ['multiple_input', 'multiple_select'].includes(definition.type) ? [selected] : selected;
    } else {
      throw datavizContractError(
        'control_action_unknown',
        `Unknown Control action: ${event.action}`,
      );
    }
    if (!next) next = datavizNormalizeControlState(binding.control, {
      intent:'explicit',
      value:datavizNormalizeControlValue(definition, value, {
        namespace:'control', key:binding.control,
      }),
      revision:Number(current.revision || 0),
    });
    if (JSON.stringify(current) === JSON.stringify(next)) {
      return {
        status:'noop',
        revision:Number(current.revision || 0),
        action_id:actionId,
        source_view:sourceView,
      };
    }
    next = {...next, revision:Number(current.revision || 0) + 1};
    const revision = ++datavizControlActionRevision;
    datavizControlState()[binding.control] = next;
    datavizControlWriterProvenance()[binding.control] = {
      revision:next.revision,
      action_id:actionId,
      source_view:sourceView,
      action:event.action,
    };
    setControlInputs({[binding.control]:next});
    await window.dataviz.applyControls({keys:[binding.control]});
    return {
      status:'committed',
      revision:next.revision,
      action_revision:revision,
      action_id:actionId,
      source_view:sourceView,
    };
  }).catch(error => {
    const code = error?.code || error?.details?.code || 'control_action_invalid';
    return datavizViewActionRejection(event, code);
  });
  return datavizControlActionQueue;
};
window.dataviz.controlActions = {
  dispatch:datavizDispatchControlAction,
  binding:datavizControlBindingForView,
  value:datavizControlBindingValue,
  get revision() { return datavizControlActionRevision; },
};
if (window.datavizComponents?.controls) {
  window.datavizComponents.controlPathOptions = ({control, input, levels}) => {
    const viewId = control.dataset.cascaderView;
    const controlKey = control.closest('[data-control-key]')?.dataset.controlKey;
    if (!viewId || !levels?.length) {
      return Array.from(input.options).map(option => {
        try { return JSON.parse(option.value); } catch (_error) { return [option.value]; }
      });
    }
    const contract = datavizViewControlContract(viewId);
    const item = contract.find(candidate => candidate.key === controlKey)
      || datavizControlContractItem(controlKey);
    const dependencyKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[controlKey]?.dependency_ancestors || []
    );
    const upstreamControls = [...dependencyKeys].map(key => (
      contract.find(candidate => candidate.key === key) || datavizControlContractItem(key)
    ));
    const rows = datavizControlDomainReferences(item).flatMap(reference =>
      datavizTableRows(window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)])
    ).filter(row => (
      upstreamControls.length === dependencyKeys.size
      && upstreamControls.every(item => (
        datavizControlCanApply(row, item)
        && datavizControlMatches(row, item, datavizControlEntry(item.key))
      ))
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
const datavizControlOccurrences = () => {
  const occurrences = new Map();
  Object.entries(window.dataviz.dependency_contract?.controls || {}).forEach(([key, dependency]) => {
    const definition = dependency.definition || {};
    (dependency.scope_views || []).forEach(viewId => {
      const filter = datavizViewControlContract(viewId).find(item => item.key === key);
      const item = filter || {
        key,
        id:definition.id || key.split('/').at(-1),
        origin:dependency.origin,
        definition,
        consumer_binding:{
          field:definition.path_fields?.length
            ? definition.path_fields
            : (definition.field || definition.id),
          empty:'passthrough',
          operator:'auto',
        },
      };
      if (!occurrences.has(key)) occurrences.set(key, []);
      occurrences.get(key).push({viewId, item});
    });
  });
  return occurrences;
};
const datavizAvailableControlOptions = targets => {
  const item = targets[0]?.item;
  const definition = item?.definition || {};
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key] || {};
  const hasDependencies = (dependency.depends_on || []).length > 0;
  const values = new Map();
  let observedSource = false;
  let observedDependencyRelation = !hasDependencies;
  targets.forEach(({viewId, item: target}) => {
    const outputRefs = datavizControlDomainReferences(target);
    const upstreamKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[target.key]?.dependency_ancestors || []
    );
    const upstream = datavizViewControlContract(viewId)
      .filter(candidate => upstreamKeys.has(candidate.key));
    outputRefs.forEach(reference => {
      const canonical = canonicalOutputReference(reference);
      const rows = datavizTableRows(window.dataviz.portable?.outputs?.[canonical]);
      // Progressive query branches may publish in any order. An unrelated
      // table being present does not mean it can define this Control's
      // option domain; otherwise a fast sibling branch can clear valid choices
      // before the actual field-bearing branch arrives.
      if (rows.some(row => datavizControlCanApply(row, target))) {
        observedSource = true;
      }
      rows.forEach(row => {
        const relationAvailable = (
          upstream.length === upstreamKeys.size
          && upstream.every(candidate => datavizControlCanApply(row, candidate))
        );
        if (hasDependencies && !relationAvailable) return;
        if (relationAvailable) observedDependencyRelation = true;
        if (!upstream.every(candidate =>
          datavizControlMatches(row, candidate, datavizControlEntry(candidate.key))
        )) return;
        const value = (definition.path_fields || []).length
          ? definition.path_fields.map(field => row[field])
          : row[definition.field || target.id];
        if (value == null || (Array.isArray(value) && value.some(part => part == null))) return;
        values.set(datavizValueSignature(value), value);
      });
    });
  });
  const staticChoices = datavizStaticChoices(definition);
  const options = staticChoices.length
    ? staticChoices.map(choice => ({
      value:choice.value,
      label:choice.label,
      group:choice.group || null,
      description:choice.description || '',
      keywords:choice.keywords || [],
      available:!hasDependencies || values.has(datavizValueSignature(choice.value)),
    }))
    : [...values.values()]
      .sort((left, right) => String(left).localeCompare(String(right)))
      .map(value => ({
        value,
        label:Array.isArray(value) ? value.join(' / ') : String(value),
        available:true,
      }));
  return {
    observed:observedSource,
    dependencyRelationReady:observedDependencyRelation,
    options,
  };
};
const publishDashboardControlOptions = occurrences => {
  // Header options are part of the same-version operational snapshot. Keeping
  // this hook makes local domain refresh ordering explicit without publishing a
  // second independently timed Host projection.
  return occurrences;
};
const datavizHydratedHeadlessControlDomains = new Set();
const datavizReconcileHeadlessControlDomain = (key, availability) => {
  if (!availability.observed || !availability.dependencyRelationReady) return;
  const definition = datavizControlDefinition(key);
  if (!['single_select', 'multiple_select'].includes(definition.type)) return;
  const candidates = availability.options
    .filter(option => option.available !== false)
    .map(option => option.value);
  const bySignature = new Map(
    candidates.map(value => [datavizValueSignature(value), value])
  );
  const current = datavizControlEntry(key);
  const currentValues = definition.type === 'multiple_select'
    ? (Array.isArray(current.value) ? current.value : [])
    : [current.value].filter(value => !datavizIsEmptyControlValue(value));
  const retained = currentValues
    .map(value => bySignature.get(datavizValueSignature(value)))
    .filter(value => value !== undefined);
  const firstHydration = !datavizHydratedHeadlessControlDomains.has(key);
  const policy = definition.initial || {
    mode:definition.type === 'multiple_select' ? 'all' : 'first',
  };
  const initialValues = () => {
    if (policy.mode === 'all' && definition.type === 'multiple_select') {
      return [...candidates];
    }
    if (policy.mode === 'first') return candidates.slice(0, 1);
    const requested = policy.mode === 'values'
      ? (policy.values || [])
      : policy.mode === 'value'
        ? [policy.value]
        : [];
    const requestedSignatures = new Set(requested.map(datavizValueSignature));
    return candidates.filter(value => requestedSignatures.has(datavizValueSignature(value)));
  };
  let intent = current.intent || 'explicit';
  let resolved = retained;
  if (definition.type === 'multiple_select' && intent === 'all_available') {
    resolved = [...candidates];
  } else if (firstHydration || (currentValues.length > 0 && retained.length === 0)) {
    resolved = retained.length ? retained : initialValues();
    if (definition.type === 'multiple_select' && policy.mode === 'all') {
      intent = 'all_available';
    }
  }
  if (definition.required && resolved.length === 0 && candidates.length) {
    resolved = candidates.slice(0, 1);
  }
  datavizHydratedHeadlessControlDomains.add(key);
  datavizSetControlValue(
    key,
    definition.type === 'multiple_select' ? resolved : (resolved[0] ?? null),
    {intent},
  );
};
const refreshControlOptionDomains = () => {
  const occurrences = datavizControlOccurrences();
  const controls = Array.from(document.querySelectorAll('[data-control-key]'));
  const order = window.dataviz.dependency_contract?.control_order || [];
  order.forEach(key => {
    const targets = occurrences.get(key) || [];
    if (!targets.length) return;
    const scopedControls = controls.filter(control => control.dataset.controlKey === key);
    const availability = datavizAvailableControlOptions(targets);
    if (!scopedControls.some(control => control.querySelector('select'))) {
      datavizReconcileHeadlessControlDomain(key, availability);
    }
    scopedControls.forEach(control => {
      const input = control.querySelector('select');
      if (!input) return;
      const definition = targets[0]?.item?.definition || {};
      const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
      if (definition.value_type === 'boolean') {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      if (availability.observed && !availability.dependencyRelationReady) {
        const message = 'Option-domain rows do not expose every declared dependency field.';
        control.dataset.optionDomainState = 'error';
        control.dataset.optionDomainError = message;
        input.disabled = true;
        input.setCustomValidity(message);
        syncPortableChoices(control);
        return;
      }
      delete control.dataset.optionDomainError;
      input.disabled = false;
      input.setCustomValidity('');
      if (control.querySelector('[data-control-component="cascader"], [data-control-component="tree-select"]')) {
        control.dataset.optionDomainState = availability.observed ? 'ready' : 'pending';
        syncPortableChoices(control);
        return;
      }
      if (!(dependency.depends_on || []).length && datavizStaticChoices(definition).length) {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      if (!availability.observed) {
        control.dataset.optionDomainState = 'pending';
        syncPortableChoices(control);
        return;
      }
      control.dataset.optionDomainState = 'ready';
      const typed = availability.options.some(option => typeof option.value !== 'string');
      input.dataset.valueEncoding = typed ? 'json' : 'string';
      const currentValue = datavizControlValue(control.dataset.controlKey);
      const currentValues = input.multiple
        ? (Array.isArray(currentValue) ? currentValue : [])
        : [currentValue];
      const selectedValues = currentValues
        .filter(value => !datavizIsEmptyControlValue(value))
        .map(value => datavizEncodeControlValue(input, value, {
          path:control.dataset.controlPath === 'true',
        }));
      const options = [];
      if (!input.multiple && !definition.required) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.hidden = true;
        empty.dataset.emptyOption = 'true';
        options.push(empty);
      }
      availability.options.forEach(item => {
        const option = document.createElement('option');
        option.value = datavizEncodeControlValue(input, item.value, {
          path:control.dataset.controlPath === 'true',
        });
        option.textContent = item.label ?? String(item.value);
        option.disabled = item.available === false;
        if (item.group) option.dataset.group = item.group;
        if (item.description) option.dataset.description = item.description;
        if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
        options.push(option);
      });
      datavizReconcileControlOptionDomain(input, options, {
        selectedValues,
        required:Boolean(definition.required),
      });
      control.dataset.optionAvailable = String(
        availability.options.filter(option => option.available !== false).length
      );
      syncPortableChoices(control);
    });
    // Commit each compiled Control before deriving its declared dependents.
    // The browser does not rebuild Control dependency edges from DOM order.
    readControlInputs({keys:new Set([key])});
  });
  publishDashboardControlOptions(occurrences);
};
const readControlInputs = ({keys = null} = {}) => {
  document.querySelectorAll('[data-control-key]').forEach(control => {
    const key = control.dataset.controlKey;
    if (keys && !keys.has(key)) return;
    const input = control.querySelector('[data-control-state-input]');
    if (!input) return;
    const definition = datavizControlDefinition(key);
    if (
      input.tagName === 'SELECT'
      && control.dataset.optionDomainState === 'pending'
      && Object.prototype.hasOwnProperty.call(datavizControlState(), key)
    ) return;
    const decode = raw => datavizDecodeControlValue(input, raw, {
      path:control.dataset.controlPath === 'true',
    });
    const type = definition.type;
    const valueType = definition.value_type;
    let value;
    if (valueType === 'boolean' && input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (valueType === 'boolean') value = input.checked;
    else if (type === 'multiple_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option => decode(option.value))
      : (datavizControlValue(key) || []);
    else if (type === 'multiple_input') {
      try { value = input.value ? JSON.parse(input.value) : []; }
      catch (_error) { value = input.value.split(',').map(item => item.trim()).filter(Boolean); }
    }
    else if (type === 'range_input') value = input.value
      ? input.value.split(',', 2).map(item => item.trim())
      : [];
    else if (input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (valueType === 'number' || valueType === 'integer') value = input.value === '' ? null : Number(input.value);
    else value = input.value;
    try {
      const intent = input.multiple
        ? (window.datavizComponents?.controls?.inferSelectionIntent(input) || 'explicit')
        : 'explicit';
      datavizSetControlValue(key, value, {intent});
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
};
const datavizControlSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(datavizValueSignature).sort() : value
);
const datavizChangedControlKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizControlSignature(previous[key]) !== datavizControlSignature(current[key])
  );
};
const datavizContentBindings = window.dataviz.content_bindings || {};
const datavizContentAllLabel = () => (
  String(document.documentElement.lang || '').toLocaleLowerCase().startsWith('zh')
    ? '全部'
    : 'All'
);
const datavizContentControl = key => Array.from(
  document.querySelectorAll('[data-control-key]')
).find(control => control.dataset.controlKey === key) || null;
const datavizContentChoiceLabel = (reference, value, control = null) => {
  const input = control?.querySelector('[data-control-state-input]');
  const option = Array.from(input?.options || []).find(candidate => (
    candidate.dataset.emptyOption !== 'true'
    && datavizValueSignature(datavizDecodeControlValue(input, candidate.value, {
      path:control?.dataset?.controlPath === 'true',
    })) === datavizValueSignature(value)
  ));
  if (option) return option.textContent?.trim() || String(value);
  const choice = datavizStaticChoices(reference.definition).find(candidate => (
    datavizValueSignature(candidate.value) === datavizValueSignature(value)
  ));
  return choice?.label ?? String(value);
};
const datavizContentPathValue = value => {
  if (typeof value !== 'string') return value;
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : value;
  } catch (_error) {
    return value;
  }
};
const datavizFormatContentReference = reference => {
  const definition = reference.definition || {};
  const control = datavizContentControl(reference.key);
  const value = datavizControlValue(reference.key) ?? definition.default;
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return '';
  }
  if (definition.type === 'range_input') {
    const range = Array.isArray(value) ? value : String(value).split(',', 2);
    return range.filter(item => item != null && item !== '').join(' 至 ');
  }
  if ((definition.path_fields || []).length) {
    const parsed = datavizContentPathValue(value);
    const paths = Array.isArray(parsed?.[0]) ? parsed : [parsed];
    const separator = control?.querySelector('.dv-control')?.dataset.pathSeparator || ' / ';
    return paths
      .filter(path => Array.isArray(path))
      .map(path => path.map(String).join(separator))
      .join('、') || String(value);
  }
  const values = Array.isArray(value) ? value : [value];
  if (Array.isArray(value)) {
    const input = control?.querySelector('[data-control-state-input]');
    const availableOptions = Array.from(input?.options || []).filter(option => (
      option.dataset.emptyOption !== 'true' && !option.disabled
    ));
    const available = availableOptions.map(option => datavizDecodeControlValue(input, option.value, {
      path:control?.dataset?.controlPath === 'true',
    }));
    const choices = datavizStaticChoices(reference.definition);
    const universe = available.length
      ? available
      : choices.map(choice => choice.value);
    if (
      universe.length
      && values.length === universe.length
      && universe.every(item => values.some(
        valueItem => datavizValueSignature(valueItem) === datavizValueSignature(item)
      ))
    ) return datavizContentAllLabel();
  }
  return values.map(item => datavizContentChoiceLabel(reference, item, control)).join('、');
};
const datavizRenderContentBinding = binding => {
  let value = String(binding.template ?? '');
  (binding.references || []).forEach(reference => {
    const escaped = String(reference.expression).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    value = value.replace(
      new RegExp(`{{\\s*${escaped}\\s*}}`, 'g'),
      () => datavizFormatContentReference(reference),
    );
  });
  return value;
};
const syncDatavizContentBindings = changedControlKeys => {
  const changed = changedControlKeys == null ? null : new Set(changedControlKeys);
  const affectedViews = new Set();
  Object.entries(datavizContentBindings).forEach(([field, binding]) => {
    if (changed && !(binding.references || []).some(reference => changed.has(reference.key))) return;
    const value = datavizRenderContentBinding(binding);
    document.querySelectorAll('[data-dv-content-field]').forEach(node => {
      if (node.dataset.dvContentField === field && node.textContent !== value) node.textContent = value;
    });
    const target = binding.target || {};
    if (target.scope === 'dashboard' && target.property === 'title') document.title = value;
    if (target.scope !== 'view' || !target.owner_id) return;
    const view = (window.dataviz.view_specs || []).find(item => item.id === target.owner_id);
    if (view && ['title', 'description', 'text'].includes(target.property)) {
      view[target.property] = value;
    }
    if (['title', 'text'].includes(target.property)) affectedViews.add(target.owner_id);
  });
  return affectedViews;
};
window.dataviz.syncContentBindings = syncDatavizContentBindings;
