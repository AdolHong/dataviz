// Owner: Runtime protocol, manifest normalization, and shared constants.
const DATAVIZ_RUNTIME_PROTOCOL = 'dataviz/runtime/v5';
const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';
const DATAVIZ_DEPENDENCY_CONTRACT = 'dataviz/dependency-contract/v5';
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
const datavizControlInputSignature = inputs => JSON.stringify(
  Object.fromEntries(
    Object.entries(inputs || {})
      .map(([alias, key]) => [alias, String(key)])
      .sort(([left], [right]) => left.localeCompare(right))
  )
);
const datavizParameterBinding = binding => typeof binding === 'string'
  ? {parameter:String(binding)}
  : {
      parameter:String(binding?.parameter || ''),
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
    let value = window.dataviz.query_parameters?.[binding.parameter];
    if (binding.part) {
      if (!Array.isArray(value) || value.length !== 2) {
        throw new Error(`Query input ${alias} cannot read ${binding.part} from ${binding.parameter}`);
      }
      value = value[binding.part === 'start' ? 0 : 1];
    }
    return [alias, value];
  })
);
const datavizOutputContractSignature = (transformId, outputs) => JSON.stringify(
  Object.keys(outputs || {}).map(name => `interactive:${transformId}/${name}`).sort()
);
const datavizValueSignature = value => {
  if (value?.__datavizArrowOutput) return `arrow:${value.descriptor?.content_hash || value.descriptor?.row_count || 'table'}`;
  try { return JSON.stringify(value); }
  catch { return String(value); }
};
