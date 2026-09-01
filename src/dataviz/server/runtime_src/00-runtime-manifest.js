// Owner: Runtime protocol, manifest normalization, and shared constants.
const DATAVIZ_RUNTIME_PROTOCOL = 'dataviz/runtime/v10';
const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';
const DATAVIZ_DEPENDENCY_CONTRACT = 'dataviz/dependency-contract/v11';
if (window.dataviz.protocol?.schema !== DATAVIZ_RUNTIME_PROTOCOL) {
  throw new Error(`Unsupported Dataviz Runtime protocol: ${window.dataviz.protocol?.schema || 'missing'}`);
}
if (window.dataviz.dependency_contract?.schema !== DATAVIZ_DEPENDENCY_CONTRACT) {
  throw new Error(
    `Unsupported Dashboard dependency contract: ${window.dataviz.dependency_contract?.schema || 'missing'}`
  );
}
const datavizFrameIdentity = () => ({
  dashboard_id:window.dataviz.dashboard_id || null,
  run_id:window.dataviz.run_id || null,
  frame_id:window.dataviz.frame_id || null,
});
const datavizSameFrameIdentity = value => ['dashboard_id', 'run_id', 'frame_id'].every(
  key => (value?.[key] || null) === datavizFrameIdentity()[key],
);
const datavizPostToParent = payload => {
  if (window.parent === window) return;
  window.parent.postMessage({...payload, ...datavizFrameIdentity()}, window.location.origin);
};
const datavizViewPipelineVisibleStatuses = new Set([
  'queued', 'loading', 'stale', 'error', 'cancelled', 'unavailable',
]);
const datavizViewPipelineStatusLabel = status => ({
  not_run:'Not run',
  queued:'Queued',
  loading:'Running',
  ready:'Ready',
  empty:'Ready · empty',
  stale:'Stale',
  error:'Failed',
  cancelled:'Cancelled',
  unavailable:'Unavailable',
}[status] || status);
const datavizSetViewPipelineNodeStatus = (nodeId, status) => {
  const normalized = String(status || 'not_run');
  document.querySelectorAll(
    `[data-view-pipeline-node="${CSS.escape(String(nodeId))}"]`,
  ).forEach(signal => {
    signal.dataset.status = normalized;
    signal.hidden = !datavizViewPipelineVisibleStatuses.has(normalized);
    const title = signal.querySelector('.dv-view-pipeline-tooltip strong')?.textContent
      || String(nodeId);
    signal.setAttribute(
      'aria-label',
      `${title}: ${datavizViewPipelineStatusLabel(normalized)}`,
    );
    if (['queued', 'loading', 'stale'].includes(normalized)) {
      const root = signal.closest('.dv-view');
      const rendererSignal = root?.querySelector('[data-view-renderer-signal]');
      if (rendererSignal) {
        rendererSignal.dataset.status = 'not_run';
        rendererSignal.hidden = true;
        rendererSignal.setAttribute('aria-hidden', 'true');
      }
      if (root) delete root.dataset.rendererSignalActive;
    }
  });
};
const canonicalOutputReference = reference => {
  const raw = String(reference || '').trim();
  if (!raw) throw new Error('Output reference cannot be empty');
  if (!/^(source|dataset|interactive):[^/]+\/[^/]+$/.test(raw)) {
    throw new Error(`Output reference must be explicit: ${raw}`);
  }
  return raw;
};
const datavizInputContractSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([name, reference]) => [name, canonicalOutputReference(reference)])
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizCanonicalControlReference = reference => {
  const raw = String(reference || '').trim();
  if (raw.startsWith('dashboard.')) {
    return `dashboard:${window.dataviz.dashboard_id}/${raw.slice('dashboard.'.length)}`;
  }
  return raw;
};
const datavizControlInputSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([alias, raw]) => {
        const binding = typeof raw === 'string'
          ? {mode:'value', control:datavizCanonicalControlReference(raw), projection:'value'}
          : {
              mode:String(raw?.mode || 'value'),
              control:datavizCanonicalControlReference(raw?.control),
              ...((raw?.mode || 'value') === 'value'
                ? {projection:String(raw?.projection || 'value')}
                : raw?.projection ? {projection:String(raw.projection)} : {}),
              ...(raw?.field ? {field:raw.field} : {}),
              ...(raw?.inputs ? {inputs:[...raw.inputs]} : {}),
              ...(raw?.empty ? {empty:String(raw.empty)} : {}),
              ...(raw?.operator ? {operator:String(raw.operator)} : {}),
            };
        return [alias, binding];
      })
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizParameterBinding = binding => typeof binding === 'string'
  ? {parameter:String(binding)}
  : {
      parameter:String(binding?.parameter || ''),
      ...(binding?.projection && binding.projection !== 'value'
        ? {projection:String(binding.projection)} : {}),
      ...(binding?.part ? {part:String(binding.part)} : {}),
    };
const datavizParameterInputSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([alias, binding]) => [alias, datavizParameterBinding(binding)])
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizProjectParameterInputs = inputs => Object.fromEntries(
  Object.entries(inputs || {}).map(([alias, rawBinding]) => {
    const binding = datavizParameterBinding(rawBinding);
    const state = window.dataviz.query_parameter_state?.[binding.parameter] || {value:null};
    if (binding.projection === 'state') return [alias, structuredClone(state)];
    if (binding.projection === 'selection') return [alias, state.selection || null];
    if (binding.projection === 'active') {
      return [alias, state.selection ? state.selection !== 'all' : !datavizIsEmptyValue(state.value)];
    }
    let value = state.value;
    if (binding.part) {
      if (!Array.isArray(value) || value.length !== 2) {
        const error = new Error(
          `Query input ${alias} cannot read ${binding.part} from ${binding.parameter}`
        );
        error.code = 'query_input_projection_failed';
        throw error;
      }
      value = value[binding.part === 'start' ? 0 : 1];
    }
    return [alias, value];
  })
);
const datavizOutputContractSignature = (transformId, outputs) => JSON.stringify(
  Object.keys(outputs || {}).map(name => `interactive:${transformId}/${name}`).sort()
);
const datavizManifestContractError = (code, message, details = {}) => {
  const error = new Error(message);
  error.code = code;
  error.details = {code, ...details};
  return error;
};
const datavizIsEmptyValue = value => (
  value == null || value === '' || (Array.isArray(value) && value.length === 0)
);
const datavizCanonicalJsonValue = (value, stack = new WeakSet()) => {
  if (value == null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw datavizManifestContractError('invalid_number', 'numeric value must be finite');
    }
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw datavizManifestContractError(
        'unsafe_integer',
        'integer exceeds the exact JavaScript range; model identifiers as strings',
      );
    }
    return value;
  }
  if (value instanceof Date) return value.toISOString();
  if (typeof value !== 'object') {
    throw datavizManifestContractError('not_json_serializable', 'value must be JSON-serializable');
  }
  if (stack.has(value)) {
    throw datavizManifestContractError('not_json_serializable', 'value must not contain cycles');
  }
  stack.add(value);
  try {
    if (Array.isArray(value)) {
      return value.map(item => datavizCanonicalJsonValue(item, stack));
    }
    const result = {};
    Object.keys(value).sort().forEach(key => {
      const item = value[key];
      if (typeof item === 'undefined' || typeof item === 'function' || typeof item === 'symbol') {
        throw datavizManifestContractError('not_json_serializable', 'value must be JSON-serializable');
      }
      result[key] = datavizCanonicalJsonValue(item, stack);
    });
    return result;
  } finally {
    stack.delete(value);
  }
};
const datavizValueSignature = value => {
  if (value?.__datavizArrowOutput) return `arrow:${value.descriptor?.content_hash || value.descriptor?.row_count || 'table'}`;
  return JSON.stringify(datavizCanonicalJsonValue(value));
};
const datavizOrderedControlOperators = new Set(['between', 'gte', 'lte', 'gt', 'lt']);
const datavizControlOperatorsByType = {
  text:new Set(['equals', 'in', 'contains']),
  integer:new Set(['equals', 'in', ...datavizOrderedControlOperators]),
  number:new Set(['equals', 'in', ...datavizOrderedControlOperators]),
  date:new Set(['equals', 'in', ...datavizOrderedControlOperators]),
  boolean:new Set(['equals', 'in']),
};
const datavizValidateControlOperator = (operator, valueType) => {
  if (!datavizControlOperatorsByType[valueType]?.has(operator)) {
    throw datavizManifestContractError(
      'control_filter_operator_incompatible',
      `Control filter operator ${operator} is not valid for ${valueType}`,
      {operator, value_type:valueType},
    );
  }
};
const datavizCoerceFilterValue = (value, valueType, role) => {
  if (value == null) return null;
  const invalid = () => datavizManifestContractError(
    'control_filter_value_invalid',
    `Control filter ${role} cannot be converted to ${valueType}`,
    {value_type:valueType, role, value},
  );
  if (valueType === 'text') return String(value);
  if (valueType === 'boolean') {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string' && ['true', 'false'].includes(value.trim().toLowerCase())) {
      return value.trim().toLowerCase() === 'true';
    }
    throw invalid();
  }
  if (valueType === 'integer' || valueType === 'number') {
    if (typeof value === 'boolean' || value === '') throw invalid();
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || (valueType === 'integer' && !Number.isInteger(numeric))) {
      throw invalid();
    }
    return numeric;
  }
  if (valueType === 'date') {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value.toISOString().slice(0, 10);
    }
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) throw invalid();
    const normalized = value.trim();
    const parsed = new Date(`${normalized}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== normalized) throw invalid();
    return normalized;
  }
  throw invalid();
};
const datavizTypedControlMatch = ({actual, value, operator, valueType}) => {
  datavizValidateControlOperator(operator, valueType);
  if (actual == null) return false;
  const comparable = datavizCoerceFilterValue(actual, valueType, 'field');
  const bound = item => datavizCoerceFilterValue(item, valueType, 'bound');
  if (operator === 'in') {
    return (Array.isArray(value) ? value : [value]).map(bound).some(item => item === comparable);
  }
  if (operator === 'between') {
    const range = Array.isArray(value) ? value : [];
    const lower = range[0] == null || range[0] === '' ? null : bound(range[0]);
    const upper = range[1] == null || range[1] === '' ? null : bound(range[1]);
    return (lower == null || comparable >= lower) && (upper == null || comparable <= upper);
  }
  if (operator === 'contains') return comparable.includes(bound(value));
  const expected = bound(value);
  if (operator === 'gte') return comparable >= expected;
  if (operator === 'lte') return comparable <= expected;
  if (operator === 'gt') return comparable > expected;
  if (operator === 'lt') return comparable < expected;
  return comparable === expected;
};
const datavizPathControlMatch = ({row, fields, value}) => {
  const paths = Array.isArray(value?.[0]) ? value : [value];
  return paths.some(path => Array.isArray(path) && path.length === fields.length
    && fields.every((field, index) => String(row?.[field] ?? '') === String(path[index] ?? '')));
};
const datavizValidateOutputDestination = ({producerRuntime, outputKind, destination}) => {
  if (producerRuntime === 'browser-js'
      && ['image', 'file'].includes(outputKind)
      && ['portable_snapshot', 'cli_result'].includes(destination)) {
    throw datavizManifestContractError(
      'output_destination_unsupported',
      `${producerRuntime} ${outputKind} cannot be materialized for ${destination}`,
      {
        producer_runtime:producerRuntime,
        output_kind:outputKind,
        destination,
        required_capability:'browser_asset_materializer',
      },
    );
  }
  return 'supported';
};
const datavizNormalizeConsumerRevision = (effective, applied) => {
  const valid = value => Number.isInteger(value) && value >= 0;
  if (!valid(effective) || (applied != null && !valid(applied))) {
    throw datavizManifestContractError(
      'consumer_applied_revision_invalid',
      'Consumer applied revision must be a non-negative integer',
      {effective_revision:effective, applied_revision:applied},
    );
  }
  if (applied != null && applied > effective) {
    throw datavizManifestContractError(
      'consumer_applied_revision_ahead',
      'Consumer applied revision cannot exceed the effective revision',
      {effective_revision:effective, applied_revision:applied},
    );
  }
  return {
    effective_revision:effective,
    applied_revision:applied ?? null,
    stale:applied !== effective,
  };
};
