// Owner: explicit Server Action bridge and atomic adoption of refreshed Base Outputs.
const datavizServerActionRequests = new Map();
// In-memory FIFO, not a durable job queue. Only dispatch starts the RPC timeout.
const datavizServerActionQueue = [];
let datavizServerActionActive = false;
const datavizCancelQueuedActions = message => {
  datavizServerActionQueue.splice(0).forEach(item => item.reject(
    datavizServerActionError(message, {code:'action_not_submitted', requestId:item.requestId})
  ));
};
const datavizDrainActions = async () => {
  if (datavizServerActionActive) return;
  datavizServerActionActive = true;
  try {
    while (datavizServerActionQueue.length) {
      const item = datavizServerActionQueue.shift();
      if (datavizRuntime.disposed || item.runId !== window.dataviz.run_id) {
        item.reject(datavizServerActionError('Query context changed; Action was not submitted.', {
          code:'action_not_submitted', requestId:item.requestId,
        }));
        continue;
      }
      try {
        const receipt = await item.dispatch();
        item.resolve(receipt);
        if (['failed', 'superseded'].includes(receipt?.refresh?.status)
            || receipt?.client_refresh?.status === 'failed') {
          datavizCancelQueuedActions('Page sync needs recovery; queued Action was not submitted.');
        }
      } catch (error) {
        item.reject(error);
        if (error.receipt?.status === 'succeeded' || error.code === 'action_response_unknown'
            || (!error.receipt && error.code !== 'action_not_submitted')) {
          datavizCancelQueuedActions('Previous Action needs receipt verification; queued Action was not submitted.');
        }
      }
    }
  } finally { datavizServerActionActive = false; }
};
window.addEventListener('beforeunload', event => {
  if (datavizServerActionActive || datavizServerActionQueue.length) {
    event.preventDefault();
    event.returnValue = '';
  }
});
const datavizServerActionError = (message, properties = {}) => Object.assign(new Error(message), properties);
const datavizServerActionCall = (operation, action, payload, options = {}) => {
  if ((operation !== 'invoke' && !options.requestId)
      || (options.requestId !== undefined && (typeof options.requestId !== 'string'
        || !options.requestId || options.requestId.length > 128))) {
    return Promise.reject(new TypeError('A valid Action requestId is required'));
  }
  const requestId = options.requestId || crypto.randomUUID();
  if (!window.dataviz.serverActions.available || !(window.dataviz.server_actions || []).includes(action)) {
    return Promise.reject(datavizServerActionError('Server Action is unavailable in this report.', {
      code:'server_action_unavailable', requestId,
    }));
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return Promise.reject(new TypeError('Server Action payload must be an object'));
  }
  let copied;
  try {
    const encoded = JSON.stringify(payload, (_key, value) => {
      if (typeof value === 'undefined' || typeof value === 'function'
          || typeof value === 'symbol' || (typeof value === 'number' && !Number.isFinite(value))) {
        throw new TypeError('Server Action payload must contain only JSON values');
      }
      return value;
    });
    if (new TextEncoder().encode(encoded).length > 1_048_576) throw new RangeError('Server Action payload is too large');
    copied = JSON.parse(encoded);
  } catch (error) {
    return Promise.reject(error);
  }
  const dispatch = () => new Promise((resolve, reject) => {
    const bridgeId = crypto.randomUUID();
    if (operation !== 'status') {
      try { options.onProgress?.({status:'submitting', request_id:requestId}); }
      catch (error) { console.error('[dataviz:action:progress]', error); }
    }
    const timer = setTimeout(() => {
      datavizServerActionRequests.delete(bridgeId);
      reject(datavizServerActionError('Action response timed out. Check its receipt; do not submit a new write.', {
        code:'action_response_unknown', requestId,
      }));
    }, 300_000);
    datavizServerActionRequests.set(bridgeId, {resolve, reject, timer, requestId, onProgress:options.onProgress});
    datavizPostToParent({type:'dataviz:server-action', operation, action,
      request_id:requestId, bridge_id:bridgeId, payload:copied});
  });
  if (operation === 'status') return dispatch();
  if (datavizServerActionQueue.length >= 50) {
    return Promise.reject(datavizServerActionError('Action queue is full; request was not submitted.', {
      code:'action_not_submitted', requestId,
    }));
  }
  return new Promise((resolve, reject) => {
    datavizServerActionQueue.push({dispatch, resolve, reject, requestId, runId:window.dataviz.run_id});
    try { options.onProgress?.({status:'queued', request_id:requestId,
      position:datavizServerActionQueue.length, submitted:false}); }
    catch (error) { console.error('[dataviz:action:progress]', error); }
    void datavizDrainActions();
  });
};
window.dataviz.serverActions = {
  get available() {
    return !datavizRuntime.disposed && window.parent !== window
      && window.dataviz.asset_mode !== 'inline' && Boolean(window.dataviz.run_id)
      && (window.dataviz.server_actions || []).length > 0;
  },
  invoke:(action, payload = {}, options = {}) => datavizServerActionCall('invoke', action, payload, options),
  status:(action, requestId) => datavizServerActionCall('status', action, {}, {requestId}),
  refresh:(action, requestId, options = {}) => datavizServerActionCall('refresh', action, {}, {...options, requestId}),
  dispose() {
    datavizCancelQueuedActions('Canvas closed; queued Action was not submitted.');
    datavizServerActionRequests.forEach(item => {
      clearTimeout(item.timer);
      item.reject(datavizServerActionError('Canvas closed. The Action may still complete; check its receipt.', {
        code:'action_response_unknown', requestId:item.requestId,
      }));
    });
    datavizServerActionRequests.clear();
  },
};
window.addEventListener('message', event => {
  if (event.origin !== window.location.origin || event.source !== window.parent
      || window.parent === window || !datavizSameFrameIdentity(event.data)) return;
  const data = event.data;
  if (!['dataviz:server-action-result', 'dataviz:server-action-progress'].includes(data?.type)) return;
  const pending = datavizServerActionRequests.get(data.bridge_id);
  if (!pending) return;
  if (data.type === 'dataviz:server-action-progress') {
    try { pending.onProgress?.(data.receipt); } catch (error) { console.error('[dataviz:action:progress]', error); }
    return;
  }
  clearTimeout(pending.timer);
  datavizServerActionRequests.delete(data.bridge_id);
  if (data.error) pending.reject(datavizServerActionError(data.error.message, {
    code:data.error.code, receipt:data.receipt, requestId:pending.requestId,
  }));
  else pending.resolve(data.receipt);
});

Object.assign(datavizRuntime, {
  async applyActionRefresh({result, payloads = [], views = [], interaction}, {isCurrent, commit}) {
    const prepareStarted = performance.now();
    // Prepare all changed data before touching visible state. A failed transport
    // leaves the old Canvas intact and can be retried without repeating Python.
    const prepared = await Promise.all(payloads.map(async payload => ({
      payload,
      value:payload.transport ? await datavizLoadTransport(payload.transport)
        : (payload.value == null && ['image', 'file'].includes(payload.kind) && payload.artifact_url
          ? {url:payload.artifact_url} : payload.value),
    })));
    const timings = {data_prepare_ms:performance.now() - prepareStarted};
    if (this.disposed || !isCurrent()) return {applied:false, timings};
    const updateStarted = performance.now();
    const previousRunId = window.dataviz.run_id;
    if (result && result.run_id !== previousRunId) {
      // publishOutputs uses the existing dependency scheduler to supersede only
      // affected transforms. Unrelated in-flight work still has valid inputs.
      window.dataviz.liveSource?.close();
      window.dataviz.liveSource = null;
      window.dataviz.live = null;
      window.dataviz.run_id = result.run_id;
      // Only Action refresh adoption may advance a queued request's snapshot.
      // An unrelated Query Run must never silently retarget queued writes.
      datavizServerActionQueue.forEach(item => {
        if (item.runId === previousRunId) item.runId = result.run_id;
      });
      window.dataviz.status = result.status;
      window.dataviz.interaction = interaction;
      // Unchanged data remains hydrated, but its transport must refer to the new
      // owned artifact copy rather than a Run that retention may later remove.
      Object.entries(window.dataviz.portable.output_transports || {}).forEach(([reference, transport]) => {
        if (!result.outputs?.[reference]) return;
        const encoded = reference.split('/').map(encodeURIComponent).join('/');
        transport.url = `/api/runs/${encodeURIComponent(result.run_id)}/outputs/${encoded}`
          + `?session_id=${encodeURIComponent(interaction.session_id)}&format=arrow`;
      });
      Object.values(window.dataviz.portable.outputs || {}).forEach(value => {
        const prefix = `/api/runs/${previousRunId}/artifacts/`;
        if (value && typeof value.url === 'string' && value.url.startsWith(prefix)) {
          value.url = value.url.replace(prefix, `/api/runs/${result.run_id}/artifacts/`);
        }
      });
      // No await between the freshness check, Canvas identity and Shell identity.
      // Subsequent messages and server-python transforms now address the same Run.
      commit(result);
    }
    const bundle = {outputs:{}, output_kinds:{}, output_schemas:{}, query_executed:Boolean(result)};
    prepared.forEach(({payload, value}) => {
      const reference = canonicalOutputReference(payload.reference);
      this.transportPromises.delete(reference);
      if (payload.transport) this.registerOutputTransport(reference, payload.transport);
      bundle.outputs[reference] = value;
      bundle.output_kinds[reference] = payload.kind;
      bundle.output_schemas[reference] = payload.transport?.schema || payload.artifact?.schema || [];
    });
    const changed = await this.publishOutputs(bundle);
    if (!this.disposed && isCurrent()) {
      const alreadyAffected = new Set(this.affectedViews([], new Set(changed || [])) || []);
      await this.renderViews({initial:false, changedControlKeys:[], changedOutputReferences:[],
        queryExecuted:false, affectedViewIds:views.filter(id => !alreadyAffected.has(id))});
    }
    timings.runtime_update_ms = performance.now() - updateStarted;
    return {applied:true, timings};
  },
});
