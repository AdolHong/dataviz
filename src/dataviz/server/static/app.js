const state = {
  payload: null,
  dashboard: null,
  sessionId: null,
  dashboardStates: new Map(),
  preferredDashboardId: null,
  selectionTimer: null,
  computeTimer: null,
  draggedNavigation: null,
  sidebarWidth: 220,
  sidebarCollapsed: false,
  workspaceRevision: 0,
  workspaceEventSource: null,
  workspaceNoticeTimer: null,
  hotReloadEnabled: false,
};
const $ = (selector) => document.querySelector(selector);

function runtimeFor(dashboardId) {
  if (!state.dashboardStates.has(dashboardId)) {
    state.dashboardStates.set(dashboardId, {
      runId: null,
      pendingRunId: null,
      committedQueryParameters: null,
      queryParameterValues: null,
      committedComputeParameters: null,
      draftComputeParameters: null,
      dashboardSelectionValues: null,
      eventSource: null,
      nodeErrors: {},
      nodeStatuses: {},
      canvasSelections: {},
      queryStatus: 'idle',
      queryLabel: 'Not run',
      message: 'Data pipeline is ready to run.',
      previousQueryState: null,
      canvasScrollY: 0,
      queryDefinitionStale: false,
      pendingQueryRevision: null,
      pendingRunOutdated: false,
      queryRequestInFlight: false,
      pendingQueryChangeRevision: 0,
    });
  }
  return state.dashboardStates.get(dashboardId);
}

function activeRuntime() {
  return state.dashboard ? runtimeFor(state.dashboard.id) : null;
}

for (const property of [
  'runId',
  'pendingRunId',
  'committedQueryParameters',
  'committedComputeParameters',
  'draftComputeParameters',
  'eventSource',
  'nodeErrors',
  'canvasSelections',
]) {
  Object.defineProperty(state, property, {
    get() { return activeRuntime()?.[property] ?? (property.endsWith('Errors') || property.endsWith('Selections') ? {} : null); },
    set(value) { const runtime = activeRuntime(); if (runtime) runtime[property] = value; },
  });
}

async function resolveTabSessionId() {
  const storageKey = 'dataviz.tab-session.v2';
  let sessionId = sessionStorage.getItem(storageKey) || crypto.randomUUID();
  if (!('BroadcastChannel' in window)) {
    sessionStorage.setItem(storageKey, sessionId);
    return sessionId;
  }
  const channel = new BroadcastChannel('dataviz-tab-session-claims');
  const nonce = crypto.randomUUID();
  let collision = false;
  channel.addEventListener('message', (event) => {
    if (event.data?.type === 'probe' && event.data.sessionId === sessionId) {
      channel.postMessage({type: 'occupied', sessionId, nonce: event.data.nonce});
    }
    if (event.data?.type === 'occupied' && event.data.sessionId === sessionId && event.data.nonce === nonce) {
      collision = true;
    }
  });
  channel.postMessage({type: 'probe', sessionId, nonce});
  await new Promise((resolve) => setTimeout(resolve, 80));
  if (collision) sessionId = crypto.randomUUID();
  sessionStorage.setItem(storageKey, sessionId);
  window.datavizTabSessionChannel = channel;
  return sessionId;
}

function sessionQuery() {
  return `session_id=${encodeURIComponent(state.sessionId)}`;
}

function canvasIdentity(frame = $('#canvas-frame')) {
  return {
    dashboard_id: frame.dataset.dashboardId || null,
    run_id: frame.dataset.runId || null,
    frame_id: frame.dataset.frameId || null,
  };
}

function sameCanvasIdentity(left, right) {
  return ['dashboard_id', 'run_id', 'frame_id'].every(
    key => (left?.[key] || null) === (right?.[key] || null),
  );
}

function loadCanvasFrame(dashboardId, runId = null) {
  const frame = $('#canvas-frame');
  const runtime = runtimeFor(dashboardId);
  const restoreScrollY = Number(runtime.canvasScrollY || 0);
  const frameId = `frame_${crypto.randomUUID().replaceAll('-', '')}`;
  frame.dataset.dashboardId = dashboardId;
  frame.dataset.runId = runId || '';
  frame.dataset.frameId = frameId;
  frame.dataset.runtimeReady = 'false';
  const run = runId ? `&run_id=${encodeURIComponent(runId)}` : '';
  frame.src = `/api/dashboards/${encodeURIComponent(dashboardId)}/canvas?${sessionQuery()}${run}&frame_id=${encodeURIComponent(frameId)}`;
  frame.addEventListener('load', () => {
    if (!restoreScrollY || frame.dataset.dashboardId !== dashboardId) return;
    const restore = () => {
      try { frame.contentWindow.scrollTo({top:restoreScrollY, behavior:'instant'}); } catch (_) { /* same-origin frame may still be initializing */ }
    };
    restore();
    window.setTimeout(restore, 180);
  }, {once:true});
}

function postCanvasMessage(payload) {
  const frame = $('#canvas-frame');
  const identity = canvasIdentity(frame);
  if (!identity.dashboard_id || !identity.frame_id || !frame.contentWindow) return false;
  frame.contentWindow.postMessage({...payload, ...identity}, window.location.origin);
  return true;
}

function syncCanvasInteraction() {
  const runtime = activeRuntime();
  const identity = canvasIdentity();
  if (!runtime?.runId || identity.run_id !== runtime.runId) return false;
  return postCanvasMessage({
    type: 'dataviz:set-interaction',
    interaction: {
      run_id: runtime.runId,
      session_id: state.sessionId,
      start_url: `/api/runs/${encodeURIComponent(runtime.runId)}/interactions`,
      status_url: '/api/interactions/{interaction_id}',
      outputs_url: '/api/interactions/{interaction_id}/outputs',
      query_snapshot_available: true,
      query_complete: true,
    },
  });
}

function isCurrentCanvasMessage(event) {
  const frame = $('#canvas-frame');
  const identity = canvasIdentity(frame);
  return event.origin === window.location.origin
    && event.source === frame.contentWindow
    && identity.dashboard_id === state.dashboard?.id
    && sameCanvasIdentity(event.data, identity);
}

function saveTabUiState() {
  if (!state.sessionId) return;
  const dashboards = {};
  for (const [dashboardId, runtime] of state.dashboardStates) {
    dashboards[dashboardId] = {
      queryParameterValues: runtime.queryParameterValues,
      committedComputeParameters: runtime.committedComputeParameters,
      draftComputeParameters: runtime.draftComputeParameters,
      dashboardSelectionValues: runtime.dashboardSelectionValues,
      canvasSelections: runtime.canvasSelections,
    };
  }
  sessionStorage.setItem(
    `dataviz.tab-ui.v2.${state.sessionId}`,
    JSON.stringify({
      activeDashboardId: state.dashboard?.id || state.preferredDashboardId,
      sidebar: {width: state.sidebarWidth, collapsed: state.sidebarCollapsed},
      dashboards,
    }),
  );
}

function sidebarWidthBounds() {
  return {min: 180, max: Math.max(180, Math.min(480, window.innerWidth - 420))};
}

function applySidebarState({persist = false} = {}) {
  const bounds = sidebarWidthBounds();
  state.sidebarWidth = Math.round(Math.min(bounds.max, Math.max(bounds.min, state.sidebarWidth || 220)));
  document.documentElement.style.setProperty('--sidebar-width', `${state.sidebarWidth}px`);
  document.body.classList.toggle('sidebar-collapsed', state.sidebarCollapsed);
  const toggle = $('#sidebar-toggle');
  toggle.setAttribute('aria-expanded', String(!state.sidebarCollapsed));
  toggle.title = state.sidebarCollapsed ? '展开导航栏' : '收起导航栏';
  const resizer = $('#sidebar-resizer');
  resizer.setAttribute('aria-valuemin', String(bounds.min));
  resizer.setAttribute('aria-valuemax', String(bounds.max));
  resizer.setAttribute('aria-valuenow', String(state.sidebarWidth));
  resizer.tabIndex = state.sidebarCollapsed ? -1 : 0;
  if (persist) saveTabUiState();
}

function restoreTabUiState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(`dataviz.tab-ui.v2.${state.sessionId}`) || '{}');
    state.preferredDashboardId = saved.activeDashboardId || null;
    state.sidebarWidth = Number(saved.sidebar?.width) || 220;
    state.sidebarCollapsed = Boolean(saved.sidebar?.collapsed);
    for (const [dashboardId, values] of Object.entries(saved.dashboards || {})) {
      Object.assign(runtimeFor(dashboardId), values);
    }
  } catch (_) {}
  applySidebarState();
}

function toggleSidebar() {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  applySidebarState({persist: true});
}

function initializeSidebarResize() {
  const resizer = $('#sidebar-resizer');
  let startX = 0;
  let startWidth = 0;
  const finish = (event) => {
    if (!document.body.classList.contains('sidebar-resizing')) return;
    document.body.classList.remove('sidebar-resizing');
    if (resizer.hasPointerCapture?.(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    saveTabUiState();
  };
  resizer.addEventListener('pointerdown', (event) => {
    if (state.sidebarCollapsed || event.button !== 0 || window.innerWidth <= 980) return;
    startX = event.clientX;
    startWidth = state.sidebarWidth;
    document.body.classList.add('sidebar-resizing');
    resizer.setPointerCapture(event.pointerId);
  });
  resizer.addEventListener('pointermove', (event) => {
    if (!document.body.classList.contains('sidebar-resizing')) return;
    state.sidebarWidth = startWidth + event.clientX - startX;
    applySidebarState();
  });
  resizer.addEventListener('pointerup', finish);
  resizer.addEventListener('pointercancel', finish);
  resizer.addEventListener('dblclick', () => {
    state.sidebarWidth = 220;
    applySidebarState({persist: true});
  });
  resizer.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const bounds = sidebarWidthBounds();
    if (event.key === 'Home') state.sidebarWidth = bounds.min;
    else if (event.key === 'End') state.sidebarWidth = bounds.max;
    else state.sidebarWidth += event.key === 'ArrowRight' ? 16 : -16;
    applySidebarState({persist: true});
  });
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      message = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || JSON.stringify(payload.detail || payload);
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function collectCanvasSnapshot(expectedIdentity) {
  const requestId = crypto.randomUUID();
  const frame = $('#canvas-frame');
  const targetWindow = frame.contentWindow;
  return new Promise((resolve, reject) => {
    if (!targetWindow || !sameCanvasIdentity(canvasIdentity(frame), expectedIdentity)) {
      reject(new Error('The active Canvas changed before snapshot collection started'));
      return;
    }
    const requestSnapshot = () => {
      if (!sameCanvasIdentity(canvasIdentity(frame), expectedIdentity)) return;
      targetWindow.postMessage(
        {type:'dataviz:collect-snapshot', request_id:requestId, ...expectedIdentity},
        window.location.origin,
      );
    };
    // Query completion and the final Canvas bootstrap are independent browser
    // events. Retry the idempotent request while a newly loaded iframe installs
    // its Runtime listener instead of losing the first postMessage in that gap.
    const retry = setInterval(requestSnapshot, 100);
    const timer = setTimeout(() => {
      clearInterval(retry);
      window.removeEventListener('message', receive);
      reject(new Error('Canvas did not provide snapshot Outputs in time'));
    }, 10_000);
    const receive = event => {
      if (
        event.origin !== window.location.origin
        || event.source !== targetWindow
        || event.data?.type !== 'dataviz:snapshot-collected'
        || event.data.request_id !== requestId
        || !sameCanvasIdentity(event.data, expectedIdentity)
        || !sameCanvasIdentity(canvasIdentity(frame), expectedIdentity)
      ) return;
      clearTimeout(timer);
      clearInterval(retry);
      window.removeEventListener('message', receive);
      if (event.data.error) reject(new Error(event.data.error.message || 'Snapshot collection failed'));
      else if (event.data.missing?.length) reject(new Error(`Run analysis before export: ${event.data.missing.join(', ')}`));
      else resolve(event.data.outputs || {});
    };
    window.addEventListener('message', receive);
    requestSnapshot();
  });
}

async function downloadReport() {
  if (!state.runId || !state.dashboard) return;
  const identity = canvasIdentity();
  const dashboardId = state.dashboard.id;
  const runId = state.runId;
  const runtime = runtimeFor(dashboardId);
  const selectionValues = selections();
  const computeValues = runtime.committedComputeParameters || computeParameters();
  const button = $('#download-button');
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = 'Preparing…';
  try {
    if (identity.dashboard_id !== dashboardId || identity.run_id !== runId) {
      throw new Error('The active Canvas is not synchronized with the selected Query Run');
    }
    const snapshotOutputs = await collectCanvasSnapshot(identity);
    if (!sameCanvasIdentity(canvasIdentity(), identity)) {
      throw new Error('The active Canvas changed while the report snapshot was being prepared');
    }
    const response = await fetch(
      `/api/dashboards/${encodeURIComponent(dashboardId)}/report`,
      {
        method:'POST',
        cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          session_id:state.sessionId,
          run_id:runId,
          selections:selectionValues,
          compute_parameters:computeValues,
          snapshot_outputs:snapshotOutputs,
        }),
      },
    );
    if (!response.ok) {
      let message = response.statusText;
      try {
        const payload = await response.json();
        message = typeof payload.detail === 'string'
          ? payload.detail
          : payload.detail?.message || JSON.stringify(payload.detail || payload);
      } catch (_) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
      || `${dashboardId}-${runId}.html`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    runtime.message = error.message;
    if (state.dashboard?.id === dashboardId) $('#run-message').textContent = error.message;
  } finally {
    button.textContent = previous;
    button.disabled = !state.runId;
  }
}

function selectorTemplate(parameter, presentation = {}) {
  if (presentation.template && presentation.template !== 'auto') return presentation.template;
  if (parameter.type === 'date_range') return 'date-range';
  if ((parameter.path_fields || []).length) return 'cascader';
  const count = (parameter.choices || []).length;
  if (parameter.type === 'boolean') return 'segmented';
  if (parameter.type === 'multi_select') return count > 0 && count <= 8 ? 'checkbox-group' : 'select';
  if (parameter.type === 'single_select') return count > 0 && count <= 4 ? 'segmented' : 'select';
  return 'auto';
}

function field(parameter, name = parameter.id, presentation = {}, behavior = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  const label = document.createElement('label');
  const inputId = `input-${name.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  label.htmlFor = inputId;
  label.textContent = parameter.label || parameter.id;
  let input;
  const template = selectorTemplate(parameter, presentation);
  const enhancedBoolean = parameter.type === 'boolean' && behavior.selection === true;
  if (['single_select', 'multi_select'].includes(parameter.type) || enhancedBoolean) {
    input = document.createElement('select');
    if (parameter.type === 'multi_select') {
      input.multiple = true;
    }
    const choices = enhancedBoolean && !(parameter.choices || []).length
      ? [{label: 'Yes', value: true}, {label: 'No', value: false}]
      : (parameter.choices || []);
    const typedChoices = choices.some(choice => typeof choice.value !== 'string');
    input.dataset.valueEncoding = typedChoices ? 'json' : 'string';
    if (behavior.selection === true && parameter.type !== 'multi_select') {
      const empty = document.createElement('option');
      empty.value = '';
      empty.hidden = true;
      empty.dataset.emptyOption = 'true';
      empty.selected = parameter.default == null || parameter.default === '';
      input.append(empty);
    }
    for (const choice of choices) {
      const option = document.createElement('option');
      option.value = typedChoices ? JSON.stringify(choice.value) : String(choice.value);
      option.textContent = choice.label;
      if (choice.group) option.dataset.group = choice.group;
      if (choice.description) option.dataset.description = choice.description;
      if (choice.keywords?.length) option.dataset.keywords = choice.keywords.join(' ');
      const defaults = Array.isArray(parameter.default) ? parameter.default : [parameter.default];
      option.selected = defaults.map(value => typedChoices ? JSON.stringify(value) : String(value)).includes(option.value);
      input.append(option);
    }
    if (!input.multiple && parameter.default == null && behavior.selection !== true) {
      input.selectedIndex = -1;
    }
  } else {
    input = document.createElement('input');
    input.type = parameter.type === 'boolean'
      ? 'checkbox'
      : ['number', 'integer'].includes(parameter.type)
      ? 'number'
      : parameter.type === 'date'
      ? 'date'
      : 'text';
    if (parameter.type === 'date_range') input.dataset.selectorNative = '';
    if (parameter.type === 'boolean') input.checked = Boolean(parameter.default);
    else if (Array.isArray(parameter.default)) input.value = parameter.default.join(',');
    else input.value = parameter.default ?? '';
  }
  input.required = Boolean(parameter.required);
  if (parameter.placeholder) input.placeholder = parameter.placeholder;
  if (parameter.min != null) input.min = parameter.min;
  if (parameter.max != null) input.max = parameter.max;
  if (parameter.step != null) input.step = parameter.step;
  else if (parameter.type === 'integer') input.step = '1';
  input.id = inputId;
  input.name = name;
  input.dataset.type = parameter.type;
  wrapper.append(label);
  if (['single_select', 'multi_select', 'date_range'].includes(parameter.type) || enhancedBoolean) {
    wrapper.classList.add('field--selector');
    if (presentation.css_class) wrapper.classList.add(...presentation.css_class.split(/\s+/).filter(Boolean));
    const selector = document.createElement('div');
    selector.className = 'dv-selector';
    selector.dataset.selectorTemplate = template;
    selector.dataset.requestedTemplate = presentation.requested_template || presentation.template || 'auto';
    selector.dataset.autoReason = presentation.auto_reason || '';
    selector.dataset.emptyMeansAll = String(Boolean(behavior.selection));
    selector.dataset.required = String(Boolean(parameter.required));
    selector.dataset.variant = presentation.variant || 'default';
    selector.dataset.showUnavailable = String(Boolean(presentation.show_unavailable));
    selector.dataset.searchMode = presentation.search || 'auto';
    selector.dataset.virtualMode = presentation.virtual || 'auto';
    selector.dataset.searchThreshold = String(presentation.search_threshold ?? 9);
    selector.dataset.virtualThreshold = String(presentation.virtual_threshold ?? 200);
    selector.dataset.maxVisibleTags = String(presentation.max_visible_tags ?? 2);
    selector.dataset.maxSelected = String(presentation.max_selected || '');
    selector.dataset.hideSelected = String(Boolean(presentation.hide_selected));
    selector.dataset.searchPlaceholder = presentation.search_placeholder || 'Search options…';
    selector.dataset.emptyText = presentation.empty_text || 'No matching options';
    selector.dataset.placeholder = presentation.placeholder || 'Choose…';
    selector.dataset.allLabel = presentation.all_label || 'All';
    selector.dataset.selectAllLabel = presentation.select_all_label || 'Select all';
    selector.dataset.invertLabel = presentation.invert_label || 'Invert';
    selector.dataset.clearLabel = presentation.clear_label || 'Clear';
    selector.dataset.pathSeparator = presentation.path_separator || ' / ';
    selector.dataset.hierarchySelection = presentation.hierarchy_selection || 'leaf';
    selector.dataset.checkedStrategy = presentation.checked_strategy || 'child';
    selector.dataset.startLabel = presentation.start_label || 'Start';
    selector.dataset.endLabel = presentation.end_label || 'End';
    selector.dataset.min = presentation.min || '';
    selector.dataset.max = presentation.max || '';
    selector.dataset.allowOpenRange = String(Boolean(presentation.allow_open_range));
    selector.dataset.presets = JSON.stringify(presentation.presets || []);
    selector.dataset.itemHeight = String(presentation.item_height || 38);
    selector.dataset.viewportHeight = String(presentation.viewport_height || 304);
    selector.dataset.overscan = String(presentation.overscan || 5);
    selector.dataset.defaultExpandDepth = String(presentation.default_expand_depth || 0);
    selector.dataset.cascaderLevels = JSON.stringify((parameter.path_fields || []).map((field, index) => ({
      field,
      label: presentation.level_labels?.[index] || field,
    })));
    const mount = document.createElement('div');
    mount.dataset.selectorMount = '';
    input.classList.add('field__native-choice');
    selector.append(input, mount);
    wrapper.append(selector);
  } else {
    wrapper.append(input);
  }
  return wrapper;
}

function selectionField(control) {
  const wrapper = document.createElement('div');
  wrapper.className = 'selection-scope';
  wrapper.dataset.origin = control.origin;
  const scopeNames = {dashboard: 'All views', section: `Section · ${control.owner_title}`, view: `View · ${control.owner_title}`};
  wrapper.innerHTML = `<div class="selection-scope__meta"><span>${escapeHtml(scopeNames[control.origin])}</span><span>${control.affected_views.length} view${control.affected_views.length === 1 ? '' : 's'}</span></div>`;
  wrapper.append(field(control.definition, control.key, control.presentation || {}, {selection: true}));
  return wrapper;
}

function dashboardControls(kind = null) {
  return (state.dashboard?.controls || []).filter(
    control => control.origin === 'dashboard' && (kind == null || control.kind === kind),
  );
}

function computeField(control) {
  const wrapper = field(control.definition, control.key);
  wrapper.dataset.computeParameter = control.key;
  wrapper.dataset.computeTrigger = control.trigger || 'apply';
  wrapper.dataset.controlKind = 'compute';
  return wrapper;
}

function applyDashboardControlPresentation(dashboard) {
  const shell = window.datavizComponents?.presentationShell;
  if (!shell?.applyControlPanel) return;
  const controls = dashboard.presentation?.controls || {};
  shell.applyControlPanel($('#query-parameters-control'), controls.query, {
    role:'query', count:dashboard.query_parameters.length,
  });
  shell.applyControlPanel($('#dashboard-controls-control'), controls.dashboard, {
    role:'dashboard', count:dashboardControls().length,
  });
}

function dashboardSelectionValues() {
  const form = $('#dashboard-selection-form');
  const values = formValues(form);
  const remembered = activeRuntime()?.dashboardSelectionValues || {};
  for (const input of form.elements) {
    if (
      input instanceof HTMLSelectElement
      && input.options.length === 0
      && Object.prototype.hasOwnProperty.call(remembered, input.name)
    ) values[input.name] = remembered[input.name];
  }
  return values;
}

function syncDashboardSelectionOptions(controls = []) {
  const form = $('#dashboard-selection-form');
  let changed = false;
  let synchronized = false;
  for (const control of controls) {
    if (!control.observed) continue;
    const input = form.elements.namedItem(control.key);
    if (!(input instanceof HTMLSelectElement)) continue;
    const definition = state.dashboard?.controls.find(
      item => item.kind === 'selection' && item.key === control.key,
    )?.definition;
    const options = control.options || [];
    const signature = JSON.stringify(options);
    if (input.dataset.runtimeOptionsSignature === signature) continue;
    const runtime = activeRuntime();
    const previous = runtime?.dashboardSelectionValues
      && Object.prototype.hasOwnProperty.call(runtime.dashboardSelectionValues, control.key)
      ? runtime.dashboardSelectionValues[control.key]
      : definition?.default ?? formValues(form)[control.key];
    const previousValues = input.multiple && Array.isArray(previous) ? previous : [previous];
    const selected = new Set(previousValues.filter(value => value != null && value !== '').map(value => JSON.stringify(value)));
    const typed = options.some(option => typeof option.value !== 'string');
    input.dataset.valueEncoding = typed ? 'json' : 'string';
    const nodes = [];
    if (!input.multiple) {
      const empty = document.createElement('option');
      empty.value = '';
      empty.hidden = true;
      empty.dataset.emptyOption = 'true';
      empty.selected = selected.size === 0;
      nodes.push(empty);
    }
    for (const item of options) {
      const option = document.createElement('option');
      option.value = typed ? JSON.stringify(item.value) : String(item.value);
      option.textContent = item.label ?? String(item.value);
      option.disabled = item.available === false;
      option.selected = !option.disabled && selected.has(JSON.stringify(item.value));
      if (item.group) option.dataset.group = item.group;
      if (item.description) option.dataset.description = item.description;
      if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
      nodes.push(option);
    }
    if (definition?.required && !nodes.some(option => option.selected && !option.disabled)) {
      const fallback = nodes.find(
        option => option.dataset.emptyOption !== 'true' && !option.disabled,
      );
      if (fallback) fallback.selected = true;
    }
    input.replaceChildren(...nodes);
    input.dataset.runtimeOptionsSignature = signature;
    input._syncChoiceControl?.();
    synchronized = true;
    const current = formValues(form)[control.key];
    if (JSON.stringify(previous) !== JSON.stringify(current)) changed = true;
  }
  if (!synchronized) return;
  const runtime = activeRuntime();
  if (runtime) runtime.dashboardSelectionValues = formValues(form);
  updateDashboardControlSummary();
  saveTabUiState();
  if (changed) scheduleViewSelections();
}

function nodeRow(node) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'node';
  item.dataset.nodeId = node.id;
  item.dataset.status = 'not_run';
  item.title = `Inspect ${node.title}${node.description ? ` — ${node.description}` : ''}`;
  item.innerHTML = `<span class="node-light"></span><strong>${escapeHtml(node.title)}</strong><small>${escapeHtml(node.subtype)} <i aria-hidden="true">↗</i></small>`;
  item.addEventListener('click', () => showNodeInspector(node));
  return item;
}

function selectDashboard(id) {
  if (state.dashboard) {
    const previous = activeRuntime();
    previous.queryParameterValues = queryParameters();
    previous.draftComputeParameters = computeParameters();
    previous.dashboardSelectionValues = dashboardSelectionValues();
    try { previous.canvasScrollY = $('#canvas-frame').contentWindow.scrollY || 0; } catch (_) { previous.canvasScrollY = 0; }
    saveTabUiState();
  }
  closeHeaderPopovers();
  state.dashboard = state.payload.dashboards.find((item) => item.id === id);
  state.preferredDashboardId = id;
  const runtime = activeRuntime();
  document.querySelectorAll('.nav-button').forEach((node) => node.classList.toggle('active', node.dataset.id === id));
  const runnable = Boolean(state.dashboard.runnable);
  $('#parameter-form').replaceChildren(...state.dashboard.query_parameters.map((item) => field(item)));
  const dataControls = dashboardControls('selection');
  const logicControls = dashboardControls('compute');
  $('#compute-parameter-form').replaceChildren(...logicControls.map(computeField));
  const hasAnalysisActions = (state.dashboard.nodes || []).some(
    (node) => node.type === 'interactive_transform' && node.trigger !== 'auto',
  );
  $('#dashboard-controls-control').dataset.empty = String(
    dataControls.length === 0 && logicControls.length === 0 && !hasAnalysisActions,
  );
  $('#dashboard-selection-group').hidden = dataControls.length === 0;
  $('#dashboard-compute-group').hidden = logicControls.length === 0;
  $('#dashboard-selection-form').replaceChildren(...dataControls.map(selectionField));
  applyDashboardControlPresentation(state.dashboard);
  if (runtime.dashboardSelectionValues == null) {
    runtime.dashboardSelectionValues = Object.fromEntries(
      dataControls.map(control => [control.key, structuredClone(control.definition.default)]),
    );
  }
  window.datavizComponents?.hydrate(document);
  setFormValues(
    $('#parameter-form'),
    runtime.queryParameterValues || runtime.committedQueryParameters || {},
  );
  setFormValues(
    $('#compute-parameter-form'),
    runtime.draftComputeParameters || runtime.committedComputeParameters || {},
  );
  setFormValues($('#dashboard-selection-form'), runtime.dashboardSelectionValues || {});
  updateDashboardControlSummary();
  $('#node-list').replaceChildren(...state.dashboard.nodes.map(nodeRow));
  document.querySelectorAll('.node').forEach((node) => {
    node.dataset.status = runtime.nodeStatuses[node.dataset.nodeId] || 'not_run';
  });
  $('#query-diagnostics').open = false;
  $('#query-diagnostics').dataset.status = runnable ? runtime.queryStatus : 'error';
  $('#query-diagnostics-label').textContent = runnable ? runtime.queryLabel : state.dashboard.status;
  $('#run-message').textContent = runnable ? runtime.message : (state.dashboard.message || 'Dashboard unavailable.');
  setQueryState();
  setSelectionsEnabled(Boolean(runtime.runId));
  setComputeState();
  loadCanvasFrame(id, runtime.pendingRunId || runtime.runId);
  $('#run-button').disabled = !runnable;
  $('#run-button').classList.toggle('is-cancelling', Boolean(runtime.pendingRunId));
  $('#run-button').lastChild.textContent = runtime.pendingRunId ? 'Cancel query' : 'Run query';
  $('#download-button').disabled = !runtime.runId;
  saveTabUiState();
}

function setFormValues(form, values) {
  for (const input of form.elements) {
    if (!input.name || !(input.name in values)) continue;
    const value = values[input.name];
    if (input.dataset.type === 'boolean' && input.tagName === 'SELECT') input.value = value == null ? '' : JSON.stringify(value);
    else if (input.dataset.type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((Array.isArray(value) ? value : [value]).map(item => input.dataset.valueEncoding === 'json' ? JSON.stringify(item) : String(item)));
      for (const option of input.options) option.selected = selected.has(option.value);
    } else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  }
}

function queryParameters() {
  return formValues($('#parameter-form'));
}

function computeParameters() {
  return formValues($('#compute-parameter-form'));
}

function selections() {
  const values = Object.assign({}, state.canvasSelections, dashboardSelectionValues());
  const validKeys = new Set(
    (state.dashboard?.controls || [])
      .filter(control => control.kind === 'selection')
      .map(control => control.key),
  );
  return Object.fromEntries(Object.entries(values).filter(([key]) => validKeys.has(key)));
}

function formValues(form) {
  const values = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    const decode = value => input.dataset.valueEncoding === 'json' ? JSON.parse(value) : value;
    if (input.dataset.type === 'boolean' && input.tagName === 'SELECT') values[input.name] = input.value === '' ? null : decode(input.value);
    else if (input.dataset.type === 'boolean') values[input.name] = input.checked;
    else if (input.multiple) values[input.name] = [...input.selectedOptions].map((item) => decode(item.value));
    else if (input.dataset.type === 'number') values[input.name] = input.value === '' ? null : Number(input.value);
    // Keep the raw numeric meaning. parseInt("1.5") would silently turn an
    // invalid integer into 1 before the shared value contract can reject it.
    else if (input.dataset.type === 'integer') values[input.name] = input.value === '' ? null : Number(input.value);
    else if (input.dataset.type === 'date_range') values[input.name] = input.value ? input.value.split(',', 2).map((item) => item.trim()) : [];
    else if (input.tagName === 'SELECT' && input.value !== '') values[input.name] = decode(input.value);
    else values[input.name] = input.value;
  }
  return values;
}

async function runDashboard() {
  if (!state.dashboard) return;
  const dashboardId = state.dashboard.id;
  const runtime = runtimeFor(dashboardId);
  if (runtime.pendingRunId) {
    const runId = runtime.pendingRunId;
    $('#run-button').disabled = true;
    $('#run-button').lastChild.textContent = 'Cancelling…';
    try {
      await request(`/api/runs/${encodeURIComponent(runId)}?${sessionQuery()}`, {method:'DELETE'});
      runtime.message = 'Cancelling this Dashboard query…';
      $('#run-message').textContent = runtime.message;
    } catch (error) {
      $('#run-button').disabled = false;
      $('#run-button').lastChild.textContent = 'Cancel query';
      runtime.message = error.message;
      $('#run-message').textContent = error.message;
    }
    return;
  }
  if (!$('#parameter-form').checkValidity()) {
    $('#parameter-form').reportValidity();
    return;
  }
  closeHeaderPopovers();
  const requestedWorkspaceRevision = state.workspaceRevision;
  runtime.queryRequestInFlight = true;
  runtime.pendingQueryChangeRevision = 0;
  runtime.previousQueryState = {
    status:runtime.queryStatus,
    label:runtime.queryLabel,
    message:runtime.message,
  };
  $('#run-button').disabled = true;
  $('#query-diagnostics').dataset.status = 'loading';
  $('#query-diagnostics-label').textContent = 'Loading';
  $('#run-message').textContent = 'Querying a new dataset…';
  document.querySelectorAll('.node').forEach((node) => node.dataset.status = 'not_run');
  try {
    runtime.queryParameterValues = queryParameters();
    const response = await request(`/api/dashboards/${encodeURIComponent(dashboardId)}/runs`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({
        session_id: state.sessionId,
        query_parameters: runtime.queryParameterValues,
      })
    });
    const runWorkspaceRevision = Number(
      response.workspace_revision ?? requestedWorkspaceRevision,
    );
    runtime.pendingRunId = response.run_id;
    runtime.pendingQueryRevision = runWorkspaceRevision;
    runtime.pendingRunOutdated = runtime.pendingQueryChangeRevision > runWorkspaceRevision;
    runtime.queryRequestInFlight = false;
    runtime.pendingQueryChangeRevision = 0;
    state.workspaceRevision = Math.max(state.workspaceRevision, runWorkspaceRevision);
    if (!runtime.pendingRunOutdated) {
      runtime.queryDefinitionStale = false;
      if ($('#workspace-update').dataset.impact === 'query') hideWorkspaceUpdate();
    }
    runtime.queryStatus = 'loading';
    runtime.queryLabel = 'Loading';
    runtime.message = 'Querying a new dataset…';
    $('#run-button').disabled = false;
    $('#run-button').classList.add('is-cancelling');
    $('#run-button').lastChild.textContent = 'Cancel query';
    if (state.dashboard?.id === dashboardId) {
      loadCanvasFrame(dashboardId, response.run_id);
    }
    listen(response.run_id, dashboardId);
  } catch (error) {
    runtime.queryRequestInFlight = false;
    runtime.pendingQueryChangeRevision = 0;
    runtime.queryStatus = 'error';
    runtime.queryLabel = 'Failed';
    runtime.message = error.message;
    if (state.dashboard?.id === dashboardId) {
      $('#run-message').textContent = error.message;
      $('#query-diagnostics').dataset.status = 'error';
      $('#query-diagnostics-label').textContent = 'Failed';
      $('#run-button').disabled = false;
      $('#run-button').classList.remove('is-cancelling');
      $('#run-button').lastChild.textContent = 'Run query';
    }
  }
}

function listen(runId, dashboardId) {
  const runtime = runtimeFor(dashboardId);
  runtime.eventSource?.close();
  const source = new EventSource(`/api/runs/${runId}/events?${sessionQuery()}`);
  runtime.eventSource = source;
  const names = ['node_queued','node_started','node_progress','node_retrying','node_ready','node_error','node_cancelled','node_unavailable'];
  for (const name of names) source.addEventListener(name, (message) => updateEvent(JSON.parse(message.data), dashboardId));
  source.addEventListener('run_ready', () => finishRun(runId, dashboardId));
  source.addEventListener('run_error', () => finishRun(runId, dashboardId));
  source.addEventListener('run_cancelled', () => finishRun(runId, dashboardId));
  source.addEventListener('stream_end', () => source.close());
  source.onerror = () => { if (source.readyState === EventSource.CLOSED) return; };
}

function updateEvent(event, dashboardId) {
  const runtime = runtimeFor(dashboardId);
  const statusMap = {
    node_queued: 'queued',
    node_started: 'loading',
    node_progress: 'loading',
    node_retrying: 'loading',
    node_ready: 'ready',
    node_error: 'error',
    node_cancelled: 'cancelled',
    node_unavailable: 'unavailable',
  };
  runtime.nodeStatuses[event.node_id] = statusMap[event.event] || 'not_run';
  if (event.error) runtime.nodeErrors[event.node_id] = event.error;
  const label = event.node_id ? event.node_id.replace(':', ' · ') : 'run';
  const progress = event.event === 'node_progress' && Number.isFinite(Number(event.data?.value))
    ? ` · ${Math.round(Number(event.data.value) * 100)}%`
    : '';
  runtime.message = `${event.message || `${label} — ${statusMap[event.event] || event.event}`}${progress}${event.duration_ms ? ` · ${event.duration_ms}ms` : ''}`;
  if (state.dashboard?.id === dashboardId) {
    const node = document.querySelector(`[data-node-id="${CSS.escape(event.node_id)}"]`);
    if (node) node.dataset.status = runtime.nodeStatuses[event.node_id];
    $('#run-message').textContent = runtime.message;
  }
}

async function finishRun(runId, dashboardId) {
  const runtime = runtimeFor(dashboardId);
  if (runId !== runtime.pendingRunId) return;
  const record = await request(`/api/runs/${runId}?${sessionQuery()}`);
  const status = record.result?.status || record.status;
  runtime.message = status === 'ready' ? 'Dataset query completed.' : `Query finished with status: ${status}`;
  runtime.pendingRunId = null;
  const outdated = runtime.pendingRunOutdated;
  runtime.pendingRunOutdated = false;
  runtime.pendingQueryRevision = null;
  const committed = record.result && ['ready', 'partial'].includes(status) && !outdated;
  if (committed) {
    runtime.runId = runId;
    runtime.committedQueryParameters = record.result.query_parameters;
    runtime.queryStatus = ['ready', 'partial'].includes(status) ? status : 'error';
    runtime.queryLabel = status === 'ready' ? 'Ready' : status === 'partial' ? 'Partial' : 'Failed';
    runtime.queryDefinitionStale = false;
  } else if (outdated) {
    runtime.queryDefinitionStale = true;
    runtime.queryStatus = 'stale';
    runtime.queryLabel = 'Outdated';
    runtime.message = 'Query finished with an older Dashboard definition. Run query again.';
  } else {
    const previous = runtime.previousQueryState;
    runtime.queryStatus = previous?.status || (runtime.runId ? 'ready' : status);
    runtime.queryLabel = previous?.label || (runtime.runId ? 'Ready' : status === 'cancelled' ? 'Cancelled' : 'Failed');
    runtime.message = status === 'cancelled'
      ? 'Query cancelled. The previously loaded dataset is unchanged.'
      : 'Query failed. The previously loaded dataset is unchanged.';
  }
  runtime.previousQueryState = null;
  if (state.dashboard?.id === dashboardId) {
    $('#run-message').textContent = runtime.message;
    $('#run-button').disabled = false;
    $('#run-button').classList.remove('is-cancelling');
    $('#run-button').lastChild.textContent = 'Run query';
    $('#download-button').disabled = !runtime.runId;
    $('#query-diagnostics').dataset.status = runtime.queryStatus;
    $('#query-diagnostics-label').textContent = runtime.queryLabel;
    setSelectionsEnabled(Boolean(runtime.runId));
    setComputeState();
    setQueryState(committed ? null : runtime.message);
    if (committed && $('#workspace-update').dataset.impact === 'query') {
      hideWorkspaceUpdate();
    }
    if (committed) {
      const frame = $('#canvas-frame');
      if (frame.dataset.runId !== runId || frame.dataset.dashboardId !== dashboardId) {
        loadCanvasFrame(dashboardId, runId);
      }
      // A progressive Canvas can finish loading before this Query Run commits.
      // Always publish the interaction endpoint after commit; the Canvas-ready
      // handshake below covers the inverse ordering without reloading the frame.
      syncCanvasInteraction();
    } else {
      loadCanvasFrame(dashboardId, runtime.runId);
    }
  }
}

function setSelectionsEnabled(enabled) {
  for (const input of $('#dashboard-selection-form').elements) {
    input.disabled = !enabled;
    input._syncChoiceControl?.();
  }
}

function setComputeEnabled(enabled) {
  for (const input of $('#compute-parameter-form').elements) {
    input.disabled = !enabled;
    input._syncChoiceControl?.();
  }
}

function changedComputeParameters() {
  const runtime = activeRuntime();
  if (!runtime) return [];
  const committed = runtime.committedComputeParameters || Object.fromEntries(
    dashboardControls('compute').map(
      control => [control.key, structuredClone(control.definition.default)],
    ),
  );
  const draft = computeParameters();
  const keys = new Set([...Object.keys(committed), ...Object.keys(draft)]);
  return [...keys].filter(
    (key) => JSON.stringify(normalized(committed[key])) !== JSON.stringify(normalized(draft[key])),
  );
}

function setComputeState() {
  const definitions = dashboardControls('compute');
  const runtime = activeRuntime();
  const changed = changedComputeParameters();
  const actionable = (state.dashboard?.nodes || []).some(
    (node) => node.type === 'interactive_transform' && node.trigger !== 'auto',
  );
  const enabled = Boolean(runtime?.runId) && (definitions.length > 0 || actionable);
  setComputeEnabled(Boolean(runtime?.runId) && definitions.length > 0);
  $('#dashboard-compute-actions').hidden = definitions.length === 0 && !actionable;
  const status = $('#compute-state');
  status.dataset.stale = String(changed.length > 0);
  status.textContent = !runtime?.runId
    ? 'Run query before analysis.'
    : changed.length
    ? `${changed.length} value${changed.length === 1 ? '' : 's'} not applied.`
    : actionable ? 'Ready to run on demand.' : 'Results are current.';
  $('#compute-apply').disabled = !enabled;
  updateDashboardControlSummary();
}

function sendCompute(
  values,
  {commit = false, apply = false, manualTargets = [], controlKeys = null} = {},
) {
  if (!state.runId && !state.pendingRunId) return;
  postCanvasMessage({
    type: 'dataviz:set-compute',
    compute_parameters: values,
    commit,
    apply,
    manual_targets: manualTargets,
    control_keys: controlKeys,
  });
}

function applyDashboardControls() {
  const runtime = activeRuntime();
  if (!runtime?.runId) return;
  runtime.draftComputeParameters = computeParameters();
  const controlKeys = dashboardControls().map(control => control.key);
  const manualTargets = (state.dashboard?.nodes || [])
    .filter((node) => node.type === 'interactive_transform' && node.trigger === 'manual')
    .map((node) => node.local_id);
  applyViewSelections();
  sendCompute(runtime.draftComputeParameters, {
    commit: true,
    apply: true,
    manualTargets,
    controlKeys,
  });
}

function normalized(value) {
  if (Array.isArray(value)) return value.map(normalized);
  if (value === null || value === undefined) return '';
  return String(value);
}

function pendingParametersMatchDataset() {
  if (!state.committedQueryParameters) return false;
  const pending = queryParameters();
  const keys = new Set([...Object.keys(pending), ...Object.keys(state.committedQueryParameters)]);
  return [...keys].every((key) => JSON.stringify(normalized(pending[key])) === JSON.stringify(normalized(state.committedQueryParameters[key])));
}

function setQueryState(message = null) {
  const node = $('#query-state');
  const runtime = activeRuntime();
  if (state.dashboard && !state.dashboard.runnable) {
    node.dataset.stale = 'true';
    node.textContent = state.dashboard.message || 'Dashboard unavailable.';
    $('#query-control-meta').textContent = state.dashboard.status;
    return;
  }
  if (runtime?.queryDefinitionStale) {
    node.dataset.stale = 'true';
    node.textContent = message || 'Dashboard query definition changed. Run query again to apply it.';
    $('#query-control-meta').textContent = 'Outdated';
  } else if (message) {
    node.dataset.stale = state.runId ? 'true' : 'false';
    node.textContent = message;
    $('#query-control-meta').textContent = 'Check values';
  } else if (!state.runId) {
    node.dataset.stale = 'false';
    node.textContent = 'No dataset loaded. Query parameters are pending.';
    $('#query-control-meta').textContent = 'Not applied';
  } else if (pendingParametersMatchDataset()) {
    node.dataset.stale = 'false';
    node.textContent = `Loaded dataset · ${state.runId}`;
    $('#query-control-meta').textContent = 'Applied';
  } else {
    node.dataset.stale = 'true';
    node.textContent = 'Pending query values differ from the loaded dataset. Query again to apply.';
    $('#query-control-meta').textContent = 'Changed';
  }
}

function updateDashboardControlSummary() {
  const dataCount = dashboardControls('selection').length;
  const logicCount = dashboardControls('compute').length;
  const changed = changedComputeParameters().length;
  const summary = [];
  if (dataCount) summary.push(`${dataCount} data`);
  if (logicCount) summary.push(changed ? `${changed} logic changed` : `${logicCount} logic`);
  $('#dashboard-control-meta').textContent = summary.join(' · ') || 'None';
}

function closeHeaderPopovers(except = null) {
  window.datavizComponents?.overlay.closeAll({except, group: 'popover'});
}

function applyViewSelections() {
  if (!state.runId && !state.pendingRunId) return;
  postCanvasMessage({type: 'dataviz:set-selections', selections: selections()});
}

function scheduleViewSelections() {
  window.clearTimeout(state.selectionTimer);
  state.selectionTimer = window.setTimeout(applyViewSelections, 80);
}

function inspectorElement(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = String(text);
  return node;
}

function inspectorFact(label, value) {
  const item = inspectorElement('div', 'node-inspector__fact');
  item.append(inspectorElement('span', '', label), inspectorElement('strong', '', value ?? '—'));
  return item;
}

async function copyEvidence(text, button) {
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const fallback = document.createElement('textarea');
    fallback.value = text;
    fallback.style.position = 'fixed';
    fallback.style.opacity = '0';
    document.body.append(fallback);
    fallback.select();
    document.execCommand('copy');
    fallback.remove();
  }
  button.textContent = 'Copied';
  window.setTimeout(() => { button.textContent = original; }, 1400);
}

function inspectorCodeSection({eyebrow, title, note, code, copyLabel = 'Copy'}) {
  const section = inspectorElement('section', 'node-inspector__section node-inspector__section--code');
  const heading = inspectorElement('header', 'node-inspector__section-heading');
  const copy = inspectorElement('button', 'node-inspector__copy', copyLabel);
  copy.type = 'button';
  copy.addEventListener('click', () => copyEvidence(code, copy));
  const copyBlock = inspectorElement('div');
  copyBlock.append(inspectorElement('span', 'micro-label', eyebrow), inspectorElement('h4', '', title));
  heading.append(copyBlock, copy);
  section.append(heading);
  if (note) section.append(inspectorElement('p', 'node-inspector__note', note));
  const pre = inspectorElement('pre', 'node-inspector__code');
  pre.append(inspectorElement('code', '', code || '—'));
  section.append(pre);
  return section;
}

function renderNodeInspector(node, record, runNode, failure = null) {
  const body = $('#node-inspector-body');
  body.replaceChildren();
  $('#node-inspector-title').textContent = node.title;
  $('#node-inspector-subtitle').textContent = node.description || `${node.type.replace('_', ' ')} · ${node.subtype}`;

  const summary = inspectorElement('section', 'node-inspector__summary');
  const status = runNode?.status || (record ? record.status : 'not run');
  const stamp = inspectorElement('div', 'node-inspector__status', status);
  stamp.dataset.status = String(status).replace('_', '-');
  const facts = inspectorElement('div', 'node-inspector__facts');
  facts.append(
    inspectorFact('Node', node.id),
    inspectorFact('Run', record?.run_id || 'Not run'),
    inspectorFact('Result', runNode?.result_origin || '—'),
    inspectorFact('Duration', runNode?.duration_ms == null ? '—' : `${runNode.duration_ms} ms`),
  );
  summary.append(stamp, facts);
  body.append(summary);

  if (failure) {
    const message = inspectorElement('section', 'node-inspector__section node-inspector__section--failure');
    message.append(inspectorElement('span', 'micro-label', 'INSPECTION FAILED'), inspectorElement('h4', '', failure));
    body.append(message);
    return;
  }

  if (!record) {
    const empty = inspectorElement('section', 'node-inspector__section node-inspector__section--empty');
    empty.append(
      inspectorElement('span', 'micro-label', 'NO RUN EVIDENCE'),
      inspectorElement('h4', '', 'Run this dashboard to inspect committed query evidence.'),
      inspectorElement('p', 'node-inspector__note', 'Evidence is isolated by browser tab and Dashboard run; another user or tab cannot replace it.'),
    );
    body.append(empty);
    return;
  }

  const query = runNode?.diagnostics?.query;
  if (query) {
    body.append(inspectorCodeSection({
      eyebrow: 'READABLE PREVIEW',
      title: 'Resolved SQL',
      note: 'For review only. Dataviz still sends a parameterized statement and bound values to the database; it does not execute this literalized preview.',
      code: query.resolved_sql,
      copyLabel: 'Copy SQL',
    }));

    const queryFacts = inspectorElement('section', 'node-inspector__section');
    queryFacts.append(inspectorElement('span', 'micro-label', 'QUERY CONTEXT'));
    const grid = inspectorElement('div', 'node-inspector__facts node-inspector__facts--query');
    grid.append(
      inspectorFact('Adapter reference', query.adapter_reference),
      inspectorFact('Adapter', `${query.adapter_name || query.adapter_reference} · ${query.adapter_type}`),
      inspectorFact('Source file', query.source_file),
      inspectorFact('Timeout policy', `${query.timeout_seconds ?? 'none'}s · ${query.timeout_retries ?? 0} retries`),
      inspectorFact('Query hash', query.query_hash),
    );
    queryFacts.append(grid);
    if (query.inspection_warning) queryFacts.append(inspectorElement('p', 'node-inspector__warning', query.inspection_warning));
    body.append(queryFacts);

    const driver = inspectorElement('details', 'node-inspector__driver');
    driver.append(inspectorElement('summary', '', 'Driver statement & bound parameters'));
    const driverBody = inspectorElement('div', 'node-inspector__driver-body');
    driverBody.append(inspectorCodeSection({
      eyebrow: 'PARAMETERIZED EXECUTION',
      title: 'Driver statement',
      note: 'This statement shape, together with the bound values below, is what the SQL driver receives.',
      code: query.statement,
      copyLabel: 'Copy statement',
    }));
    const params = inspectorElement('section', 'node-inspector__section');
    params.append(inspectorElement('span', 'micro-label', 'BOUND PARAMETERS'));
    const paramsCode = inspectorElement('pre', 'node-inspector__code node-inspector__code--parameters');
    paramsCode.append(inspectorElement('code', '', JSON.stringify(query.parameters || {}, null, 2)));
    params.append(paramsCode);
    driverBody.append(params);
    driver.append(driverBody);
    body.append(driver);
  } else {
    const noSql = inspectorElement('section', 'node-inspector__section node-inspector__section--empty');
    const inspectionError = runNode?.diagnostics?.inspection_error;
    noSql.append(
      inspectorElement('span', 'micro-label', 'NODE EVIDENCE'),
      inspectorElement('h4', '', node.subtype === 'sql' ? 'SQL evidence is unavailable for this run.' : 'This node does not execute SQL.'),
      inspectorElement(
        'p',
        'node-inspector__note',
        inspectionError?.message || 'Status, duration, cache origin, outputs and failures remain available in the run record.',
      ),
    );
    body.append(noSql);
  }

  const error = runNode?.error || state.nodeErrors[node.id];
  if (error) {
    const failed = inspectorElement('section', 'node-inspector__section node-inspector__section--failure');
    failed.append(inspectorElement('span', 'micro-label', 'EXECUTION ERROR'), inspectorElement('h4', '', error.message || 'Node execution failed'));
    const details = inspectorElement('pre', 'node-inspector__code node-inspector__code--error');
    details.append(inspectorElement('code', '', JSON.stringify(error, null, 2)));
    failed.append(details);
    body.append(failed);
  }
}

async function appendNodeLog(runId, runNode, requestId) {
  const artifactId = runNode?.log?.artifact_id;
  if (!artifactId) return;
  const body = $('#node-inspector-body');
  try {
    const response = await fetch(
      `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}?${sessionQuery()}`,
      {cache: 'no-store'},
    );
    if (!response.ok) throw new Error(`Execution log is unavailable (${response.status})`);
    const raw = await response.text();
    let code = raw;
    try { code = JSON.stringify(JSON.parse(raw), null, 2); } catch (_) {}
    const dialog = $('#node-inspector');
    if (!dialog.open || dialog.dataset.requestId !== requestId) return;
    body.append(inspectorCodeSection({
      eyebrow: 'EXECUTION LOG',
      title: 'Structured node log',
      note: 'Saved dataviz/execution-log/v1 evidence, including context.log records and complete Python failure tracebacks.',
      code,
      copyLabel: 'Copy log',
    }));
  } catch (error) {
    const dialog = $('#node-inspector');
    if (!dialog.open || dialog.dataset.requestId !== requestId) return;
    const warning = inspectorElement('section', 'node-inspector__section node-inspector__section--failure');
    warning.append(
      inspectorElement('span', 'micro-label', 'LOG UNAVAILABLE'),
      inspectorElement('h4', '', error.message),
    );
    body.append(warning);
  }
}

async function showNodeInspector(node) {
  closeHeaderPopovers();
  const dialog = $('#node-inspector');
  const requestId = crypto.randomUUID();
  dialog.dataset.requestId = requestId;
  renderNodeInspector(node, null, null);
  dialog.showModal();
  const runtime = activeRuntime();
  const runId = runtime?.pendingRunId || runtime?.runId;
  if (!runId) return;
  const dashboardId = state.dashboard?.id;
  $('#node-inspector-body').classList.add('is-loading');
  try {
    const record = await request(`/api/runs/${encodeURIComponent(runId)}?${sessionQuery()}`);
    const run = record.result || record.snapshot;
    let runNode = run?.nodes?.[node.id] || null;
    if (node.type === 'interactive_transform' && runtime?.nodeStatuses[node.id]) {
      runNode = {
        ...(runNode || {}),
        status:runtime.nodeStatuses[node.id],
        error:runtime.nodeErrors[node.id] || runNode?.error || null,
      };
    }
    if (dialog.dataset.requestId !== requestId) return;
    renderNodeInspector(node, record, runNode);
    await appendNodeLog(runId, runNode, requestId);
  } catch (error) {
    if (dialog.dataset.requestId !== requestId) return;
    renderNodeInspector(node, {run_id: runId, status: 'error'}, null, error.message);
  } finally {
    if (dialog.dataset.requestId === requestId) {
      $('#node-inspector-body').classList.remove('is-loading');
      if (state.dashboard?.id !== dashboardId && dialog.open) dialog.close();
    }
  }
}

function escapeHtml(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML; }

function dashboardButton(dashboard) {
    const button = document.createElement('button');
    button.className = 'nav-button';
    button.dataset.id = dashboard.id;
    button.dataset.navType = 'dashboard';
    button.dataset.status = dashboard.status;
    button.dataset.parentId = dashboard.parent_id || '';
    button.draggable = true;
    const status = dashboard.status === 'ready' ? '' : `<small>${escapeHtml(dashboard.status)}</small>`;
    button.innerHTML = `<strong>${escapeHtml(dashboard.canvas_name)}</strong>${status}`;
    button.title = dashboard.message || dashboard.title || dashboard.logical_path || dashboard.path;
    button.addEventListener('click', () => selectDashboard(dashboard.id));
    button.addEventListener('dragstart', (event) => beginNavigationDrag(event, {
      type: 'dashboard', id: dashboard.id, parentId: dashboard.parent_id, path: dashboard.path,
    }));
    button.addEventListener('dragend', endNavigationDrag);
    return button;
}

function renderNavigation() {
  const root = document.createElement('div');
  root.className = 'nav-tree';
  const foldersByParent = new Map();
  const dashboardsByParent = new Map();
  const appendTo = (map, parent, value) => {
    const key = parent || '__root__';
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(value);
  };
  for (const folder of state.payload.folders || []) appendTo(foldersByParent, folder.parent_id, folder);
  for (const dashboard of state.payload.dashboards) appendTo(dashboardsByParent, dashboard.parent_id, dashboard);

  const renderLevel = (parentId = null, depth = 0) => {
    const level = document.createElement('div');
    level.className = 'nav-level';
    level.dataset.depth = depth;
    for (const folder of foldersByParent.get(parentId || '__root__') || []) {
      const group = document.createElement('div');
      group.className = 'nav-folder';
      group.dataset.folderId = folder.id;
      group.dataset.navType = 'folder';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'nav-folder__toggle';
      toggle.dataset.navType = 'folder';
      toggle.dataset.folderId = folder.id;
      toggle.dataset.parentId = folder.parent_id || '';
      toggle.draggable = true;
      toggle.innerHTML = `<i>›</i><strong>${escapeHtml(folder.title)}</strong>`;
      const children = renderLevel(folder.id, depth + 1);
      toggle.addEventListener('click', () => group.classList.toggle('is-collapsed'));
      toggle.addEventListener('dragstart', (event) => beginNavigationDrag(event, {
        type: 'folder', id: folder.id, parentId: folder.parent_id,
      }));
      toggle.addEventListener('dragend', endNavigationDrag);
      toggle.addEventListener('dragover', (event) => navigationDragOver(event, folder.id, group));
      toggle.addEventListener('dragleave', () => group.classList.remove('is-drop-target'));
      toggle.addEventListener('drop', (event) => navigationDrop(event, folder.id, group));
      group.append(toggle, children);
      level.append(group);
    }
    for (const dashboard of dashboardsByParent.get(parentId || '__root__') || []) {
      level.append(dashboardButton(dashboard));
    }
    return level;
  };
  root.append(renderLevel());
  $('#dashboard-nav').replaceChildren(root);
  renderTrash();
}

function beginNavigationDrag(event, payload) {
  state.draggedNavigation = payload;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', `${payload.type}:${payload.id}`);
  event.currentTarget.classList.add('is-dragging');
  document.body.dataset.navDragging = payload.type;
  $('#nav-root-drop').setAttribute('aria-hidden', 'false');
}

function endNavigationDrag(event) {
  event.currentTarget.classList.remove('is-dragging');
  document.querySelectorAll('.is-drop-target').forEach((item) => item.classList.remove('is-drop-target'));
  delete document.body.dataset.navDragging;
  $('#nav-root-drop').setAttribute('aria-hidden', 'true');
  state.draggedNavigation = null;
}

function folderIsInside(folderId, possibleAncestorId) {
  let current = (state.payload.folders || []).find((item) => item.id === folderId);
  while (current?.parent_id) {
    if (current.parent_id === possibleAncestorId) return true;
    current = state.payload.folders.find((item) => item.id === current.parent_id);
  }
  return false;
}

function canDropNavigation(parentId) {
  const dragged = state.draggedNavigation;
  if (!dragged || dragged.parentId === parentId) return false;
  if (dragged.type === 'folder') {
    if (dragged.id === parentId || folderIsInside(parentId, dragged.id)) return false;
  }
  return true;
}

function navigationDragOver(event, parentId, target) {
  if (!canDropNavigation(parentId)) return;
  event.preventDefault();
  event.stopPropagation();
  event.dataTransfer.dropEffect = 'move';
  target.classList.add('is-drop-target');
}

async function navigationDrop(event, parentId, target) {
  event.preventDefault();
  event.stopPropagation();
  target?.classList.remove('is-drop-target');
  if (!canDropNavigation(parentId)) return;
  const dragged = state.draggedNavigation;
  try {
    if (dragged.type === 'dashboard') {
      await request(`/api/navigation/dashboards/${encodeURIComponent(dragged.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:parentId})});
    } else {
      await request(`/api/navigation/folders/${encodeURIComponent(dragged.id)}/placement`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:parentId})});
    }
    await refreshNavigation(dragged.path);
  } catch (error) {
    showNavigationError('移动失败', error.message);
  }
}

function showNavigationError(title, message) {
  showNavDialog({
    eyebrow: 'NAVIGATION / MOVE FAILED', title, submitLabel: '知道了',
    body: `<p class="nav-dialog__note">${escapeHtml(message)}</p>`, onSubmit: async () => {},
  });
}

function trashNode(item, depth = 0) {
  const node = document.createElement('div');
  node.className = `nav-trash-item nav-trash-item--${item.kind}`;
  node.style.setProperty('--trash-depth', depth);
  node.innerHTML = `<span>${item.kind === 'folder' ? '◇' : '·'}</span><strong>${escapeHtml(item.title)}</strong>`;
  if (item.kind === 'folder' && item.children?.length) {
    const children = document.createElement('div');
    children.className = 'nav-trash-item__children';
    children.replaceChildren(...item.children.map((child) => trashNode(child, depth + 1)));
    node.append(children);
  }
  return node;
}

function renderTrash() {
  const records = state.payload.trash || [];
  $('#nav-trash-count').textContent = records.length;
  const list = records.map((record) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'nav-trash-record';
    wrapper.dataset.navType = 'trash';
    wrapper.dataset.trashId = record.trash_id;
    wrapper.title = '右键恢复到原逻辑位置';
    wrapper.append(trashNode(record.item));
    return wrapper;
  });
  if (!list.length) {
    const empty = document.createElement('p');
    empty.className = 'nav-trash__empty';
    empty.textContent = '暂无项目';
    list.push(empty);
  }
  $('#nav-trash-list').replaceChildren(...list);
}

async function refreshNavigation(preferredPath = state.dashboard?.path, {reloadCanvas = true} = {}) {
  const activeId = state.dashboard?.id || null;
  state.payload = await request('/api/workspace');
  state.workspaceRevision = Math.max(
    state.workspaceRevision,
    Number(state.payload.hot_reload?.revision || 0),
  );
  state.hotReloadEnabled = Boolean(state.payload.hot_reload?.enabled);
  $('#workspace-title').textContent = 'Dashboards';
  $('#workspace-title').title = state.payload.workspace.title;
  const preferred = state.payload.dashboards.find((item) => item.path === preferredPath);
  const remembered = state.payload.dashboards.find((item) => item.id === state.preferredDashboardId);
  const fallback = state.payload.dashboards.find((item) => item.runnable) || state.payload.dashboards[0];
  const selected = preferred || remembered || fallback;
  if (!selected) {
    state.dashboard = null;
    renderNavigation();
    return null;
  }
  if (!reloadCanvas && activeId && selected.id === activeId) {
    state.dashboard = selected;
    renderNavigation();
    document.querySelectorAll('.nav-button').forEach(
      (node) => node.classList.toggle('active', node.dataset.id === selected.id),
    );
    return selected;
  }
  renderNavigation();
  selectDashboard(selected.id);
  return selected;
}

function hideWorkspaceUpdate() {
  window.clearTimeout(state.workspaceNoticeTimer);
  state.workspaceNoticeTimer = null;
  $('#workspace-update').hidden = true;
}

function showWorkspaceUpdate({impact, title, message, action = null, transient = false}) {
  const notice = $('#workspace-update');
  const button = $('#workspace-update-action');
  window.clearTimeout(state.workspaceNoticeTimer);
  notice.dataset.impact = impact;
  $('#workspace-update-title').textContent = title;
  $('#workspace-update-message').textContent = message;
  button.hidden = !action;
  button.dataset.action = action || '';
  button.textContent = action === 'query' ? 'Run query' : 'Reload';
  notice.hidden = false;
  if (transient) {
    state.workspaceNoticeTimer = window.setTimeout(hideWorkspaceUpdate, 4200);
  }
}

function markAnalysisStale(runtime) {
  for (const nodeId of Object.keys(runtime.nodeStatuses)) {
    if (nodeId.startsWith('interactive:')) runtime.nodeStatuses[nodeId] = 'stale';
  }
}

async function handleWorkspaceChange(change) {
  const revision = Number(change.revision || 0);
  if (revision <= state.workspaceRevision) return;
  state.workspaceRevision = revision;
  if (change.status === 'invalid') {
    const first = change.diagnostics?.[0];
    showWorkspaceUpdate({
      impact:'invalid',
      title:'Dashboard update has errors',
      message:first?.message || change.message || 'The previous Canvas remains active.',
      action:'reload',
    });
    return;
  }

  const activeId = state.dashboard?.id;
  const activeChange = (change.changes || []).find((item) => item.dashboard_id === activeId);
  const currentPath = state.dashboard?.path || null;
  if (!activeChange) {
    if (change.navigation_changed) await refreshNavigation(currentPath, {reloadCanvas:false});
    if ($('#workspace-update').dataset.impact === 'invalid') {
      showWorkspaceUpdate({
        impact:'canvas',
        title:'Dashboard definition restored',
        message:'The Workspace is valid again; the last valid Canvas remained active.',
        transient:true,
      });
    }
    return;
  }

  if (activeChange.impact === 'server') {
    await refreshNavigation(currentPath, {reloadCanvas:false});
    showWorkspaceUpdate({
      impact:'server',
      title:'Server settings changed',
      message:'Restart dataviz serve to apply Workspace Runtime or process-level settings.',
    });
    return;
  }

  const runtime = activeRuntime();
  if (activeChange.impact === 'query' && runtime) {
    if (runtime.queryRequestInFlight || runtime.pendingRunId) {
      runtime.pendingQueryChangeRevision = Math.max(
        runtime.pendingQueryChangeRevision,
        revision,
      );
    }
    if (
      runtime.pendingRunId
      && Number(runtime.pendingQueryRevision || 0) < revision
    ) {
      runtime.pendingRunOutdated = true;
    }
    runtime.queryDefinitionStale = true;
    runtime.queryStatus = runtime.runId ? 'stale' : 'idle';
    runtime.queryLabel = runtime.runId ? 'Outdated' : 'Not run';
    runtime.message = runtime.runId
      ? 'Query definition changed. Run query again before trusting this dashboard.'
      : 'Query definition changed. Run query to create the dataset.';
  } else if (activeChange.impact === 'analysis' && runtime) {
    markAnalysisStale(runtime);
    runtime.message = 'Interactive analysis changed and is recomputing from the existing dataset.';
  }

  await refreshNavigation(currentPath, {reloadCanvas:true});
  if (activeChange.impact === 'query') {
    const coveredByPendingRun = Boolean(
      runtime?.pendingRunId
      && Number(runtime.pendingQueryRevision || 0) >= revision
      && !runtime.pendingRunOutdated
    );
    if (coveredByPendingRun) {
      runtime.queryDefinitionStale = false;
      runtime.queryStatus = 'loading';
      runtime.queryLabel = 'Loading';
      runtime.message = 'Querying the updated Dashboard definition…';
      setQueryState();
      hideWorkspaceUpdate();
      return;
    }
    setQueryState('Dashboard query definition changed. Run query again to apply it.');
    showWorkspaceUpdate({
      impact:'query',
      title:'Query definition changed',
      message:'Existing Source Outputs are retained as history, but cannot be used as current results.',
      action:'query',
    });
  } else if (activeChange.impact === 'analysis') {
    showWorkspaceUpdate({
      impact:'analysis',
      title:'Analysis reloaded',
      message:'Interactive branches are recomputing from the existing Source Outputs.',
      transient:true,
    });
  } else {
    showWorkspaceUpdate({
      impact:'canvas',
      title:'Canvas reloaded',
      message:'Presentation changes are active; the current Query Run and Controls were preserved.',
      transient:true,
    });
  }
}

function listenWorkspaceChanges() {
  state.workspaceEventSource?.close();
  state.workspaceEventSource = null;
  if (!state.hotReloadEnabled) return;
  const source = new EventSource(
    `/api/workspace/events?${sessionQuery()}&after=${encodeURIComponent(state.workspaceRevision)}`,
  );
  state.workspaceEventSource = source;
  source.addEventListener('workspace_changed', (message) => {
    let change;
    try { change = JSON.parse(message.data); } catch (_) { return; }
    handleWorkspaceChange(change).catch((error) => {
      showWorkspaceUpdate({
        impact:'invalid',
        title:'Hot reload failed',
        message:error.message,
        action:'reload',
      });
    });
  });
}

async function reloadDashboardFromDisk() {
  const path = state.dashboard?.path || null;
  try {
    await refreshNavigation(path, {reloadCanvas:true});
    const latest = state.payload?.hot_reload?.last_event;
    if (latest?.status === 'invalid') {
      const first = latest.diagnostics?.[0];
      showWorkspaceUpdate({
        impact:'invalid',
        title:'Dashboard update has errors',
        message:first?.message || latest.message || 'The previous valid Canvas remains active.',
        action:'reload',
      });
      return;
    }
    showWorkspaceUpdate({
      impact:'canvas',
      title:'Dashboard reloaded',
      message:'Workspace files were read from disk. Query compatibility is checked by the Canvas.',
      transient:true,
    });
  } catch (error) {
    showWorkspaceUpdate({
      impact:'invalid',
      title:'Dashboard reload failed',
      message:error.message,
      action:'reload',
    });
  }
}

function hideNavMenu() { $('#nav-context-menu').hidden = true; }

function showNavMenu(event, target) {
  event.preventDefault();
  const menu = $('#nav-context-menu');
  const actions = [];
  const folderId = target?.dataset.folderId;
  const dashboardId = target?.dataset.id;
  const trashId = target?.dataset.trashId;
  if (!target) actions.push(['＋', '新建目录', () => openFolderDialog(null)]);
  if (trashId) {
    actions.push(['↟', '恢复到原位置', () => restoreTrashItem(trashId)]);
  }
  if (folderId) {
    actions.push(['＋', '新建子目录', () => openFolderDialog(folderId)]);
    actions.push(['✎', '重命名', () => openRenameDialog(folderId)]);
    actions.push(['⌫', '移到回收站', () => openDeleteDialog(folderId)]);
  }
  if (dashboardId) {
    actions.push(['↳', '移动看板…', () => openMoveDialog(dashboardId)]);
    actions.push(['⌫', '移到回收站', () => openTrashDashboardDialog(dashboardId)]);
  }
  menu.replaceChildren(...actions.map(([icon, label, action]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.role = 'menuitem';
    button.innerHTML = `<span>${icon}</span>${label}`;
    button.addEventListener('click', () => { hideNavMenu(); action(); });
    return button;
  }));
  menu.hidden = false;
  const width = 176, height = actions.length * 39 + 12;
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - width - 8)}px`;
  menu.style.top = `${Math.min(event.clientY, window.innerHeight - height - 8)}px`;
}

function folderOptions(selected = null, excluded = null) {
  const options = [{id: '', title: '根目录'}, ...(state.payload.folders || []).filter((item) => item.id !== excluded)];
  return options.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === (selected || '') ? 'selected' : ''}>${escapeHtml(item.logical_path || item.title)}</option>`).join('');
}

function showNavDialog({eyebrow, title, body, submitLabel, onSubmit, danger = false}) {
  const dialog = $('#nav-dialog');
  dialog.innerHTML = `<form method="dialog"><header><span>${escapeHtml(eyebrow)}</span><button type="button" data-close aria-label="关闭">×</button></header><h2>${escapeHtml(title)}</h2>${body}<footer><button type="button" class="button button--ghost" data-close>取消</button><button type="submit" class="button ${danger ? 'button--danger' : 'button--run'}">${escapeHtml(submitLabel)}</button></footer><p class="nav-dialog__error" role="alert"></p></form>`;
  dialog.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => dialog.close()));
  dialog.querySelector('form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = dialog.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await onSubmit(new FormData(event.currentTarget));
      dialog.close();
    } catch (error) {
      dialog.querySelector('.nav-dialog__error').textContent = error.message;
      submit.disabled = false;
    }
  });
  dialog.showModal();
  dialog.querySelector('input, select, [type="submit"]')?.focus();
}

function openFolderDialog(parentId) {
  showNavDialog({
    eyebrow: 'NAVIGATION / NEW', title: '新建目录', submitLabel: '创建目录',
    body: `<label class="nav-dialog__field"><span>目录名称</span><input name="title" required maxlength="80" autocomplete="off"></label><label class="nav-dialog__field"><span>所在位置</span><select name="parent_id">${folderOptions(parentId)}</select></label>`,
    onSubmit: async (data) => {
      await request('/api/navigation/folders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:data.get('title'), parent_id:data.get('parent_id') || null})});
      await refreshNavigation();
    },
  });
}

function openRenameDialog(folderId) {
  const folder = state.payload.folders.find((item) => item.id === folderId);
  showNavDialog({
    eyebrow: 'NAVIGATION / RENAME', title: '重命名目录', submitLabel: '保存名称',
    body: `<label class="nav-dialog__field"><span>目录名称</span><input name="title" required maxlength="80" value="${escapeHtml(folder.title)}"></label>`,
    onSubmit: async (data) => {
      await request(`/api/navigation/folders/${encodeURIComponent(folderId)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:data.get('title')})});
      await refreshNavigation();
    },
  });
}

function openMoveDialog(dashboardId) {
  const dashboard = state.payload.dashboards.find((item) => item.id === dashboardId);
  showNavDialog({
    eyebrow: 'NAVIGATION / MOVE', title: `移动「${dashboard.canvas_name}」`, submitLabel: '移动看板',
    body: `<label class="nav-dialog__field"><span>目标目录</span><select name="parent_id">${folderOptions(dashboard.parent_id)}</select></label><p class="nav-dialog__note">移动会把目录重命名为“目录##看板”；看板内容不会改变。</p>`,
    onSubmit: async (data) => {
      await request(`/api/navigation/dashboards/${encodeURIComponent(dashboardId)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:data.get('parent_id') || null})});
      await refreshNavigation(dashboard.path);
    },
  });
}

function openDeleteDialog(folderId) {
  const folder = state.payload.folders.find((item) => item.id === folderId);
  showNavDialog({
    eyebrow: 'NAVIGATION / TRASH', title: `把「${folder.title}」移到回收站？`, submitLabel: '移到回收站', danger: true,
    body: '<p class="nav-dialog__note">所属看板目录会加上 __TRASH__## 前缀并隐藏；内容不会删除，可完整恢复。</p>',
    onSubmit: async () => {
      await request(`/api/navigation/folders/${encodeURIComponent(folderId)}`, {method:'DELETE'});
      await refreshNavigation();
    },
  });
}

function openTrashDashboardDialog(dashboardId) {
  const dashboard = state.payload.dashboards.find((item) => item.id === dashboardId);
  showNavDialog({
    eyebrow: 'NAVIGATION / TRASH', title: `把「${dashboard.canvas_name}」移到回收站？`, submitLabel: '移到回收站', danger: true,
    body: '<p class="nav-dialog__note">目录会加上 __TRASH__## 前缀并隐藏；看板文件和数据不会删除。</p>',
    onSubmit: async () => {
      await request(`/api/navigation/dashboards/${encodeURIComponent(dashboardId)}`, {method:'DELETE'});
      await refreshNavigation(null);
    },
  });
}

async function restoreTrashItem(trashId) {
  try {
    await request(`/api/navigation/trash/${encodeURIComponent(trashId)}/restore`, {method:'POST'});
    await refreshNavigation(null);
  } catch (error) {
    showNavDialog({
      eyebrow: 'TRASH / RESTORE FAILED', title: '无法恢复', submitLabel: '知道了',
      body: `<p class="nav-dialog__note">${escapeHtml(error.message)}</p>`, onSubmit: async () => {},
    });
  }
}

async function boot() {
  state.sessionId = await resolveTabSessionId();
  restoreTabUiState();
  const remembered = await request(`/api/session/runs?${sessionQuery()}`);
  for (const record of remembered.runs || []) {
    const runtime = runtimeFor(record.dashboard_id);
    runtime.committedQueryParameters = record.query_parameters;
    if (!runtime.queryParameterValues) runtime.queryParameterValues = record.query_parameters;
    runtime.nodeStatuses = record.nodes || {};
    runtime.queryDefinitionStale = Boolean(record.query_outdated);
    if (record.ready) {
      runtime.runId = record.run_id;
      runtime.queryStatus = record.query_outdated
        ? 'stale'
        : ['ready', 'partial'].includes(record.status) ? record.status : 'error';
      runtime.queryLabel = record.query_outdated
        ? 'Outdated'
        : record.status === 'ready' ? 'Ready' : record.status === 'partial' ? 'Partial' : 'Failed';
      runtime.message = record.query_outdated
        ? 'Dashboard query definition changed. Run query again.'
        : record.status === 'ready' ? 'Dataset query completed.' : `Query finished with status: ${record.status}`;
    } else if (['queued', 'loading'].includes(record.status)) {
      runtime.pendingRunId = record.run_id;
      runtime.pendingRunOutdated = Boolean(record.query_outdated);
      runtime.queryStatus = 'loading';
      runtime.queryLabel = 'Loading';
      runtime.message = 'Querying a new dataset…';
      listen(record.run_id, record.dashboard_id);
    }
  }
  await refreshNavigation(null);
  if (activeRuntime()?.queryDefinitionStale) {
    showWorkspaceUpdate({
      impact:'query',
      title:'Query definition changed',
      message:'This tab remembers an older Query Run. Run query again to use the current Dashboard.',
      action:'query',
    });
  }
  listenWorkspaceChanges();
}

$('#run-button').addEventListener('click', runDashboard);
$('#download-button').addEventListener('click', downloadReport);
$('#dashboard-reload').addEventListener('click', reloadDashboardFromDisk);
$('#workspace-update-dismiss').addEventListener('click', hideWorkspaceUpdate);
$('#workspace-update-action').addEventListener('click', () => {
  if ($('#workspace-update-action').dataset.action === 'query') runDashboard();
  else reloadDashboardFromDisk();
});
$('#parameter-form').addEventListener('input', () => setQueryState());
$('#parameter-form').addEventListener('input', () => {
  if (activeRuntime()) activeRuntime().queryParameterValues = queryParameters();
  saveTabUiState();
});
$('#parameter-form').addEventListener('change', () => {
  if (activeRuntime()) activeRuntime().queryParameterValues = queryParameters();
  saveTabUiState();
  setQueryState();
});
$('#dashboard-selection-form').addEventListener('input', () => {
  if (activeRuntime()) activeRuntime().dashboardSelectionValues = dashboardSelectionValues();
  saveTabUiState();
  updateDashboardControlSummary();
  scheduleViewSelections();
});
const onComputeDraft = (event) => {
  const runtime = activeRuntime();
  if (!runtime) return;
  runtime.draftComputeParameters = computeParameters();
  saveTabUiState();
  setComputeState();
  sendCompute(runtime.draftComputeParameters);
  const control = event.target.closest('[data-compute-parameter]');
  if (control?.dataset.computeTrigger !== 'auto') return;
  window.clearTimeout(state.computeTimer);
  const definition = dashboardControls('compute').find(
    item => item.key === control.dataset.computeParameter,
  );
  const consumers = (state.dashboard.nodes || []).filter(
    (node) => node.type === 'interactive_transform'
      && (definition?.consumers || []).includes(node.local_id),
  );
  const delay = Math.max(0, ...consumers.map((node) => Number(node.debounce_ms || 300)));
  state.computeTimer = window.setTimeout(() => {
    sendCompute({[control.dataset.computeParameter]: runtime.draftComputeParameters[control.dataset.computeParameter]}, {
      commit: true,
    });
  }, delay);
};
$('#compute-parameter-form').addEventListener('input', onComputeDraft);
$('#compute-parameter-form').addEventListener('change', onComputeDraft);
$('#compute-apply').addEventListener('click', applyDashboardControls);
$('#dashboard-selection-form').addEventListener('change', () => {
  if (activeRuntime()) activeRuntime().dashboardSelectionValues = dashboardSelectionValues();
  saveTabUiState();
  updateDashboardControlSummary();
  scheduleViewSelections();
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('#nav-context-menu')) hideNavMenu();
});
window.addEventListener('message', (event) => {
  if (!isCurrentCanvasMessage(event)) return;
  if (event.data?.type === 'dataviz:canvas-ready') {
    const runtime = activeRuntime();
    const frame = $('#canvas-frame');
    if (!runtime) return;
    // Fresh Canvas defaults seed an empty tab state; remembered tab-local state
    // wins on reload. selections() applies the current v3 contract allow-list
    // before anything is sent back to the iframe.
    runtime.canvasSelections = {
      ...(event.data.selections || {}),
      ...(runtime.canvasSelections || {}),
    };
    frame.dataset.runtimeReady = 'true';
    saveTabUiState();
    applyViewSelections();
    const values = runtime.committedComputeParameters
      || runtime.draftComputeParameters
      || computeParameters();
    sendCompute(values, {commit:true});
    syncCanvasInteraction();
    return;
  }
  if (event.data?.type === 'dataviz:canvas-interaction') {
    closeHeaderPopovers();
    return;
  }
  if (event.data?.type === 'dataviz:interactive-status') {
    const runtime = activeRuntime();
    const nodeId = String(event.data.node_id || '');
    const allowed = new Set([
      'not_run', 'queued', 'loading', 'ready', 'stale', 'error', 'cancelled', 'unavailable',
    ]);
    if (!runtime || !nodeId.startsWith('interactive:') || !allowed.has(event.data.status)) return;
    runtime.nodeStatuses[nodeId] = event.data.status;
    if (event.data.error) runtime.nodeErrors[nodeId] = event.data.error;
    else if (event.data.status === 'ready') delete runtime.nodeErrors[nodeId];
    const node = document.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`);
    if (node) node.dataset.status = event.data.status;
    if (event.data.message && ['error', 'cancelled', 'unavailable'].includes(event.data.status)) {
      runtime.message = `${nodeId.replace(':', ' · ')} — ${event.data.message}`;
      $('#run-message').textContent = runtime.message;
    }
    return;
  }
  if (event.data?.type === 'dataviz:compute-changed') {
    const runtime = activeRuntime();
    if (!runtime) return;
    runtime.committedComputeParameters = {...(event.data.compute_parameters || {})};
    runtime.draftComputeParameters = {...(event.data.draft_compute_parameters || {})};
    setFormValues($('#compute-parameter-form'), runtime.draftComputeParameters);
    setComputeState();
    saveTabUiState();
    return;
  }
  if (event.data?.type === 'dataviz:selection-options-changed') {
    syncDashboardSelectionOptions(event.data.controls || []);
    return;
  }
  if (event.data?.type === 'dataviz:selections-changed') {
    // Canvas messages contain the complete canonical state. Replacing it also
    // removes keys restored from sessionStorage after a Selection is renamed.
    state.canvasSelections = {...(event.data.selections || {})};
    saveTabUiState();
  }
});
$('#add-root-folder').addEventListener('click', () => openFolderDialog(null));
$('#sidebar-toggle').addEventListener('click', toggleSidebar);
initializeSidebarResize();
window.addEventListener('resize', () => applySidebarState());
$('#dashboard-nav').addEventListener('contextmenu', (event) => {
  const target = event.target.closest('[data-nav-type]');
  showNavMenu(event, target);
});
$('#nav-trash-list').addEventListener('contextmenu', (event) => {
  const target = event.target.closest('[data-nav-type="trash"]');
  if (target) showNavMenu(event, target);
});
$('#nav-root-drop').addEventListener('dragover', (event) => navigationDragOver(event, null, event.currentTarget));
$('#nav-root-drop').addEventListener('dragleave', (event) => event.currentTarget.classList.remove('is-drop-target'));
$('#nav-root-drop').addEventListener('drop', (event) => navigationDrop(event, null, event.currentTarget));
$('.rail').addEventListener('contextmenu', (event) => {
  if (event.target.closest('#dashboard-nav, #nav-trash')) return;
  showNavMenu(event, null);
});
window.addEventListener('blur', () => {
  hideNavMenu();
  closeHeaderPopovers();
});
boot().catch((error) => { document.body.innerHTML = `<pre>${escapeHtml(error.stack || error.message)}</pre>`; });
