// Owner: Selection binding, canonical commits, and parent-frame synchronization.
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
const datavizSelectionFields = item => {
  const pathFields = item.definition?.path_fields || [];
  return pathFields.length ? pathFields : [item.binding?.field || item.id];
};
const datavizSelectionCanApply = (row, item) => (
  row != null
  && typeof row === 'object'
  && datavizSelectionFields(item).every(field => Object.prototype.hasOwnProperty.call(row, field))
);
const datavizViewSelectionContract = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.selection_contract || []
);
const datavizSelectionDomainReferences = item => (
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
const datavizSelectionViewApplicability = (viewId, item) => {
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key];
  if (!dependency) return 'not_applicable';
  if ((dependency.declared_direct_views || []).includes(viewId)) return 'applies';
  const binding = dependency.direct_view_bindings?.[viewId];
  if (!binding || binding.applicability === 'not_applicable') return 'not_applicable';
  const fields = binding.fields?.length ? binding.fields : datavizSelectionFields(item);
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
).filter(([, dependency]) => dependency.kind === 'selection').map(([key, dependency]) => {
  const affected = new Set([
    ...(dependency.declared_direct_views || []),
    ...(dependency.derived_views || []),
    ...(dependency.content_views || []),
  ]);
  if (dependency.writer_view) affected.add(dependency.writer_view);
  let pending = false;
  (dependency.runtime_checked_views || []).forEach(viewId => {
    const item = datavizViewSelectionContract(viewId).find(candidate => candidate.key === key);
    if (!item) return;
    const applicability = datavizSelectionViewApplicability(viewId, item);
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
const datavizSelectionState = () => {
  if (!window.dataviz.selection_state || typeof window.dataviz.selection_state !== 'object') {
    window.dataviz.selection_state = {};
  }
  return window.dataviz.selection_state;
};
const datavizSelectionDefinition = key => (
  window.dataviz.dependency_contract?.controls?.[key]?.definition
  || Object.values(window.dataviz.dependency_contract?.views || {})
    .flatMap(view => view.selection_contract || [])
    .find(item => item.key === key)?.definition
  || {}
);
const datavizNormalizeSelectionState = (key, candidate = null) => {
  const definition = datavizSelectionDefinition(key);
  const initial = window.dataviz.dependency_contract?.controls?.[key]?.initial_state || {
    intent:'explicit', values:[],
  };
  const source = candidate && typeof candidate === 'object' ? candidate : initial;
  const intent = source.intent === 'all_available' && definition.type === 'multiple_select'
    ? 'all_available'
    : 'explicit';
  const values = Array.isArray(source.values) ? structuredClone(source.values) : [];
  if (!['multiple_input', 'multiple_select', 'range_input'].includes(definition.type) && values.length > 1) {
    throw datavizContractError(
      'selection_state_cardinality_invalid',
      `Selection ${key} contains more than one value`,
      {key},
    );
  }
  if (definition.type === 'range_input' && values.length > 1) {
    throw datavizContractError(
      'selection_state_cardinality_invalid',
      `Selection ${key} contains more than one date range`,
      {key},
    );
  }
  return {intent, values};
};
const datavizSelectionEntry = key => {
  const state = datavizSelectionState();
  if (!state[key]) state[key] = datavizNormalizeSelectionState(key);
  return state[key];
};
const datavizSelectionValueFromState = (definition, entry) => {
  const values = Array.isArray(entry?.values) ? entry.values : [];
  if (['multiple_input', 'multiple_select'].includes(definition?.type)) return structuredClone(values);
  if (definition?.type === 'range_input') return values.length ? structuredClone(values[0]) : [];
  return values.length ? structuredClone(values[0]) : null;
};
const datavizSelectionValue = key => datavizSelectionValueFromState(
  datavizSelectionDefinition(key),
  datavizSelectionEntry(key),
);
const datavizSelectionLogicalValues = (definition, value) => {
  if (datavizIsEmptyControlValue(value)) return [];
  if (['multiple_input', 'multiple_select'].includes(definition?.type)) return structuredClone(value);
  if (definition?.type === 'range_input') return [structuredClone(value)];
  return [structuredClone(value)];
};
const datavizSetSelectionValue = (key, value, {intent = null} = {}) => {
  const definition = datavizSelectionDefinition(key);
  const normalized = datavizNormalizeControlValue(definition, value, {
    namespace:'selection', key,
  });
  const previous = datavizSelectionEntry(key);
  datavizSelectionState()[key] = datavizNormalizeSelectionState(key, {
    intent:intent || previous.intent || 'explicit',
    values:datavizSelectionLogicalValues(definition, normalized),
  });
  return datavizSelectionState()[key];
};
const datavizSelectionStateSnapshot = () => {
  const validKeys = new Set(Object.entries(window.dataviz.dependency_contract?.controls || {})
    .filter(([, item]) => item.kind === 'selection')
    .map(([key]) => key));
  return Object.fromEntries([...validKeys].map(key => [
    key,
    structuredClone(datavizSelectionEntry(key)),
  ]));
};
const datavizSelectionValueSnapshot = () => Object.fromEntries(
  Object.keys(datavizSelectionStateSnapshot()).map(key => [key, datavizSelectionValue(key)]),
);
const datavizSelectionMatches = (row, item, state) => {
  // Dashboard and Section selections are inherited structurally. A View whose
  // dataset does not expose the selected field is outside that data contract;
  // it must remain visible instead of being reduced to an accidental empty set.
  if (!datavizSelectionCanApply(row, item)) return true;
  const value = datavizSelectionValueFromState(item.definition || {}, state || {
    intent:'explicit', values:[],
  });
  // Explicit empty is a real include-set with zero members. It is never All.
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return false;
  const pathFields = item.definition?.path_fields || [];
  if (pathFields.length) {
    const paths = Array.isArray(value?.[0]) ? value : [value];
    const matched = paths.some(path => pathFields.every((field, index) => String(row[field] ?? '') === String(path[index] ?? '')));
    return matched;
  }
  const field = item.binding?.field || item.id;
  const actual = row[field];
  const operator = item.binding?.operator === 'auto'
    ? (['multiple_input', 'multiple_select'].includes(item.definition?.type) ? 'in' : item.definition?.type === 'range_input' ? 'between' : 'equals')
    : item.binding?.operator;
  let matched;
  if (operator === 'in') matched = (Array.isArray(value) ? value : [value]).map(String).includes(String(actual));
  else if (operator === 'between') {
    const range = Array.isArray(value) ? value : [];
    const start = range[0];
    const end = range[1];
    matched = (!start || String(actual) >= String(start))
      && (!end || String(actual) <= String(end));
  }
  else if (operator === 'contains') matched = String(actual ?? '').includes(String(value ?? ''));
  else if (operator === 'gte') matched = Number(actual) >= Number(value);
  else if (operator === 'lte') matched = Number(actual) <= Number(value);
  else if (operator === 'gt') matched = Number(actual) > Number(value);
  else if (operator === 'lt') matched = Number(actual) < Number(value);
  else matched = String(actual ?? '') === String(value ?? '');
  return matched;
};
const datavizSelectionIntentKey = input => (
  input?.closest('[data-selection-key]')?.dataset.selectionKey || null
);
const datavizCaptureSelectionIntent = input => {
  const key = datavizSelectionIntentKey(input);
  const consume = window.datavizComponents?.controls?.consumeSelectionIntent;
  if (!key || !consume) return null;
  const intent = consume(input);
  if (intent) datavizSelectionEntry(key).intent = intent;
  return intent;
};
const datavizReconcileSelectionOptionDomain = (
  input,
  nextOptions,
  {selectedValues = [], required = input?.required === true} = {},
) => {
  const reconcile = window.datavizComponents?.controls?.reconcileOptionDomain;
  if (!reconcile) {
    input.replaceChildren(...Array.from(nextOptions || []));
    return {intent:null, selectedValues:[]};
  }
  const key = datavizSelectionIntentKey(input);
  const state = key ? datavizSelectionEntry(key) : {intent:'explicit', values:[]};
  const definition = key ? datavizSelectionDefinition(key) : {};
  const policy = definition.initial || {
    mode:definition.type === 'multiple_select' ? 'all' : 'first',
  };
  const rawInitialValues = policy.mode === 'values'
    ? (policy.values || [])
    : policy.mode === 'value'
      ? [policy.value]
      : [];
  const initialValues = rawInitialValues.map(value => datavizEncodeControlValue(input, value, {
    path:input.closest('[data-selection-key]')?.dataset.selectionPath === 'true',
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
window.dataviz.selection = {
  fields: datavizSelectionFields,
  canApply: datavizSelectionCanApply,
  matches: datavizSelectionMatches,
  captureIntent: datavizCaptureSelectionIntent,
  reconcileOptionDomain: datavizReconcileSelectionOptionDomain,
  state: datavizSelectionEntry,
  value: datavizSelectionValue,
  set: datavizSetSelectionValue,
  stateSnapshot: datavizSelectionStateSnapshot,
};
let datavizControlActionRevision = 0;
let datavizControlActionQueue = Promise.resolve();
const datavizControlBindingForView = viewId => (
  window.dataviz.dependency_contract?.views?.[viewId]?.control_binding || null
);
const datavizControlBindingValue = (binding, datum) => {
  if (datum && Object.prototype.hasOwnProperty.call(datum, '__datavizControlValue')) {
    return structuredClone(datum.__datavizControlValue);
  }
  if (!datum || typeof datum !== 'object') return structuredClone(datum);
  const values = (binding?.fields || []).map(field => datum[field]);
  return values.length === 1 ? values[0] : values;
};
const datavizDispatchControlAction = event => {
  const binding = datavizControlBindingForView(event?.view_id);
  if (!binding || binding.control !== event?.control) {
    return Promise.reject(datavizContractError(
      'control_action_binding_invalid',
      `View ${event?.view_id || 'unknown'} cannot write ${event?.control || 'unknown'}`,
    ));
  }
  const root = document.querySelector(
    `.dv-view[data-view-id="${CSS.escape(event.view_id)}"]`
  );
  if (!root || (
    event.generation != null
    && Number(event.generation) !== Number(root._datavizRenderGeneration || 0)
  )) {
    return Promise.resolve({status:'discarded', reason:'stale_view_generation'});
  }
  datavizControlActionQueue = datavizControlActionQueue.catch(() => undefined).then(async () => {
    const currentRoot = document.querySelector(
      `.dv-view[data-view-id="${CSS.escape(event.view_id)}"]`
    );
    if (!currentRoot || (
      event.generation != null
      && Number(event.generation) !== Number(currentRoot._datavizRenderGeneration || 0)
    )) {
      return {status:'discarded', reason:'stale_view_generation'};
    }
    const definition = datavizSelectionDefinition(binding.control);
    const current = datavizSelectionEntry(binding.control);
    let next;
    let value;
    if (event.action === 'reset') {
      next = datavizNormalizeSelectionState(binding.control);
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
    if (!next) next = datavizNormalizeSelectionState(binding.control, {
      intent:'explicit',
      values:datavizSelectionLogicalValues(
        definition,
        datavizNormalizeControlValue(definition, value, {
          namespace:'selection', key:binding.control,
        }),
      ),
    });
    if (JSON.stringify(current) === JSON.stringify(next)) {
      return {status:'noop', revision:datavizControlActionRevision};
    }
    const revision = ++datavizControlActionRevision;
    datavizSelectionState()[binding.control] = next;
    setSelectionInputs({[binding.control]:next});
    await window.dataviz.applySelections();
    return {status:'committed', revision};
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
    const selectionKey = control.closest('[data-selection-key]')?.dataset.selectionKey;
    if (!viewId || !levels?.length) {
      return Array.from(input.options).map(option => {
        try { return JSON.parse(option.value); } catch (_error) { return [option.value]; }
      });
    }
    const contract = datavizViewSelectionContract(viewId);
    const item = contract.find(candidate => candidate.key === selectionKey);
    const dependencyKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[selectionKey]?.dependency_ancestors || []
    );
    const upstreamSelections = contract.filter(candidate => dependencyKeys.has(candidate.key));
    const rows = datavizSelectionDomainReferences(item).flatMap(reference =>
      datavizTableRows(window.dataviz.portable?.outputs?.[canonicalOutputReference(reference)])
    ).filter(row => (
      upstreamSelections.length === dependencyKeys.size
      && upstreamSelections.every(item => (
        datavizSelectionCanApply(row, item)
        && datavizSelectionMatches(row, item, datavizSelectionEntry(item.key))
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
const datavizSelectionOccurrences = () => {
  const occurrences = new Map();
  Object.entries(window.dataviz.dependency_contract?.views || {}).forEach(([viewId, dependency]) => {
    const contract = dependency.selection_contract || [];
    contract.forEach(item => {
      if (!occurrences.has(item.key)) occurrences.set(item.key, []);
      occurrences.get(item.key).push({viewId, item});
    });
  });
  return occurrences;
};
const datavizAvailableSelectionOptions = targets => {
  const item = targets[0]?.item;
  const definition = item?.definition || {};
  const dependency = window.dataviz.dependency_contract?.controls?.[item?.key] || {};
  const hasDependencies = (dependency.depends_on || []).length > 0;
  const values = new Map();
  let observedSource = false;
  let observedDependencyRelation = !hasDependencies;
  targets.forEach(({viewId, item: target}) => {
    const outputRefs = datavizSelectionDomainReferences(target);
    const upstreamKeys = new Set(
      window.dataviz.dependency_contract?.controls?.[target.key]?.dependency_ancestors || []
    );
    const upstream = datavizViewSelectionContract(viewId)
      .filter(candidate => upstreamKeys.has(candidate.key));
    outputRefs.forEach(reference => {
      const canonical = canonicalOutputReference(reference);
      const rows = datavizTableRows(window.dataviz.portable?.outputs?.[canonical]);
      // Progressive query branches may publish in any order. An unrelated
      // table being present does not mean it can define this Selection's
      // option domain; otherwise a fast sibling branch can clear valid choices
      // before the actual field-bearing branch arrives.
      if (rows.some(row => datavizSelectionCanApply(row, target))) {
        observedSource = true;
      }
      rows.forEach(row => {
        const relationAvailable = (
          upstream.length === upstreamKeys.size
          && upstream.every(candidate => datavizSelectionCanApply(row, candidate))
        );
        if (hasDependencies && !relationAvailable) return;
        if (relationAvailable) observedDependencyRelation = true;
        if (!upstream.every(candidate =>
          datavizSelectionMatches(row, candidate, datavizSelectionEntry(candidate.key))
        )) return;
        const value = (definition.path_fields || []).length
          ? definition.path_fields.map(field => row[field])
          : row[target.binding?.field || target.id];
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
const publishDashboardSelectionOptions = occurrences => {
  if (window.parent === window) return;
  const controls = [];
  occurrences.forEach((targets, key) => {
    if (targets[0]?.item?.origin !== 'dashboard') return;
    controls.push({key, ...datavizAvailableSelectionOptions(targets)});
  });
  datavizPostToParent({type:'dataviz:selection-options-changed', controls});
};
const refreshSelectionOptionDomains = () => {
  const occurrences = datavizSelectionOccurrences();
  const controls = Array.from(document.querySelectorAll('[data-selection-key]'));
  const order = window.dataviz.dependency_contract?.control_order || [];
  order.forEach(key => {
    const targets = occurrences.get(key) || [];
    if (!targets.length || targets[0]?.item?.kind !== 'selection') return;
    controls.filter(control => control.dataset.selectionKey === key).forEach(control => {
      const input = control.querySelector('select');
      if (!input) return;
      const definition = targets[0]?.item?.definition || {};
      const dependency = window.dataviz.dependency_contract?.controls?.[key] || {};
      if (definition.value_type === 'boolean') {
        control.dataset.optionDomainState = 'static';
        syncPortableChoices(control);
        return;
      }
      const availability = datavizAvailableSelectionOptions(targets);
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
      const currentValue = datavizSelectionValue(control.dataset.selectionKey);
      const currentValues = input.multiple
        ? (Array.isArray(currentValue) ? currentValue : [])
        : [currentValue];
      const selectedValues = currentValues
        .filter(value => !datavizIsEmptyControlValue(value))
        .map(value => datavizEncodeControlValue(input, value, {
          path:control.dataset.selectionPath === 'true',
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
          path:control.dataset.selectionPath === 'true',
        });
        option.textContent = item.label ?? String(item.value);
        option.disabled = item.available === false;
        if (item.group) option.dataset.group = item.group;
        if (item.description) option.dataset.description = item.description;
        if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
        options.push(option);
      });
      datavizReconcileSelectionOptionDomain(input, options, {
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
    readSelectionInputs({keys:new Set([key])});
  });
  publishDashboardSelectionOptions(occurrences);
};
const readSelectionInputs = ({keys = null} = {}) => {
  document.querySelectorAll('[data-selection-key]').forEach(control => {
    const key = control.dataset.selectionKey;
    if (keys && !keys.has(key)) return;
    const input = control.querySelector('[data-selection-input]');
    if (!input) return;
    const definition = datavizSelectionDefinition(key);
    if (
      input.tagName === 'SELECT'
      && control.dataset.optionDomainState === 'pending'
      && Object.prototype.hasOwnProperty.call(datavizSelectionState(), key)
    ) return;
    const decode = raw => datavizDecodeControlValue(input, raw, {
      path:control.dataset.selectionPath === 'true',
    });
    const type = definition.type;
    const valueType = definition.value_type;
    let value;
    if (valueType === 'boolean' && input.tagName === 'SELECT') value = input.value === '' ? null : decode(input.value);
    else if (valueType === 'boolean') value = input.checked;
    else if (type === 'multiple_select') value = input.options.length
      ? Array.from(input.selectedOptions).map(option => decode(option.value))
      : (datavizSelectionValue(key) || []);
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
      datavizSetSelectionValue(key, value, {intent});
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
const datavizSelectionSignature = value => JSON.stringify(
  Array.isArray(value) ? [...value].map(datavizValueSignature).sort() : value
);
const datavizChangedSelectionKeys = (previous, current) => {
  if (previous == null) return null;
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...keys].filter(key =>
    datavizSelectionSignature(previous[key]) !== datavizSelectionSignature(current[key])
  );
};
const datavizContentBindings = window.dataviz.content_bindings || {};
const datavizContentAllLabel = () => (
  String(document.documentElement.lang || '').toLocaleLowerCase().startsWith('zh')
    ? '全部'
    : 'All'
);
const datavizContentControl = key => Array.from(
  document.querySelectorAll('[data-selection-key]')
).find(control => control.dataset.selectionKey === key) || null;
const datavizContentChoiceLabel = (reference, value, control = null) => {
  const input = control?.querySelector('[data-selection-input], [data-compute-input]');
  const option = Array.from(input?.options || []).find(candidate => (
    candidate.dataset.emptyOption !== 'true'
    && datavizValueSignature(datavizDecodeControlValue(input, candidate.value, {
      path:control?.dataset?.selectionPath === 'true',
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
  const isCompute = reference.kind === 'compute';
  const control = isCompute
    ? document.querySelector(`[data-compute-key="${CSS.escape(reference.key)}"]`)
    : datavizContentControl(reference.key);
  const value = isCompute
    ? (window.dataviz.compute_parameters?.[reference.key] ?? definition.default)
    : (datavizSelectionValue(reference.key) ?? definition.default);
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return isCompute ? '' : datavizContentAllLabel();
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
    const input = control?.querySelector('[data-selection-input], [data-compute-input]');
    const availableOptions = Array.from(input?.options || []).filter(option => (
      option.dataset.emptyOption !== 'true' && !option.disabled
    ));
    const available = availableOptions.map(option => datavizDecodeControlValue(input, option.value, {
      path:control?.dataset?.selectionPath === 'true',
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
const syncDatavizContentBindings = changedSelectionKeys => {
  const changed = changedSelectionKeys == null ? null : new Set(changedSelectionKeys);
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
