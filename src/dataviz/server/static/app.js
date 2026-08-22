const state = {
  payload: null,
  dashboard: null,
  sessionId: null,
  dashboardStates: new Map(),
  preferredDashboardId: null,
  selectionTimer: null,
  draggedNavigation: null,
  sidebarWidth: 220,
  sidebarCollapsed: false,
};
const $ = (selector) => document.querySelector(selector);

function runtimeFor(dashboardId) {
  if (!state.dashboardStates.has(dashboardId)) {
    state.dashboardStates.set(dashboardId, {
      runId: null,
      pendingRunId: null,
      committedParameters: null,
      parameterValues: null,
      dashboardSelectionValues: null,
      eventSource: null,
      nodeErrors: {},
      nodeStatuses: {},
      canvasSelections: {},
      queryStatus: 'idle',
      queryLabel: 'Not run',
      message: 'Sources are ready to run.',
    });
  }
  return state.dashboardStates.get(dashboardId);
}

function activeRuntime() {
  return state.dashboard ? runtimeFor(state.dashboard.id) : null;
}

for (const property of ['runId', 'pendingRunId', 'committedParameters', 'eventSource', 'nodeErrors', 'canvasSelections']) {
  Object.defineProperty(state, property, {
    get() { return activeRuntime()?.[property] ?? (property.endsWith('Errors') || property.endsWith('Selections') ? {} : null); },
    set(value) { const runtime = activeRuntime(); if (runtime) runtime[property] = value; },
  });
}

async function resolveTabSessionId() {
  const storageKey = 'dataviz.tab-session.v1';
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

function saveTabUiState() {
  if (!state.sessionId) return;
  const dashboards = {};
  for (const [dashboardId, runtime] of state.dashboardStates) {
    dashboards[dashboardId] = {
      parameterValues: runtime.parameterValues,
      dashboardSelectionValues: runtime.dashboardSelectionValues,
      canvasSelections: runtime.canvasSelections,
    };
  }
  sessionStorage.setItem(
    `dataviz.tab-ui.${state.sessionId}`,
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
    const saved = JSON.parse(sessionStorage.getItem(`dataviz.tab-ui.${state.sessionId}`) || '{}');
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
    if (response.status === 404 && url.startsWith('/api/navigation/')) {
      message = '当前 Server 仍是旧进程，不支持目录管理。请在终端停止并重新运行 dataviz serve。';
    }
    throw new Error(message);
  }
  return response.json();
}

function selectorTemplate(parameter, presentation = {}) {
  if (presentation.template && presentation.template !== 'auto') return presentation.template;
  const count = (parameter.choices || []).length;
  if (parameter.type === 'multi_select') return count <= 8 ? 'chips' : 'searchable';
  if (parameter.type === 'single_select') return count <= 20 ? 'dropdown' : 'searchable';
  return 'auto';
}

function field(parameter, name = parameter.id, presentation = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  const label = document.createElement('label');
  const inputId = `input-${name.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  label.htmlFor = inputId;
  label.textContent = parameter.label || parameter.id;
  let input;
  if (['single_select', 'multi_select'].includes(parameter.type)) {
    input = document.createElement('select');
    if (parameter.type === 'multi_select') {
      input.multiple = true;
    }
    for (const choice of parameter.choices || []) {
      const option = document.createElement('option');
      option.value = choice.value;
      option.textContent = choice.label;
      const defaults = Array.isArray(parameter.default) ? parameter.default : [parameter.default];
      option.selected = defaults.map(String).includes(String(choice.value));
      input.append(option);
    }
  } else {
    input = document.createElement('input');
    input.type = parameter.type === 'boolean' ? 'checkbox' : parameter.type === 'number' ? 'number' : parameter.type === 'date' ? 'date' : 'text';
    if (parameter.type === 'date_range') input.placeholder = 'start,end';
    if (parameter.type === 'boolean') input.checked = Boolean(parameter.default);
    else if (Array.isArray(parameter.default)) input.value = parameter.default.join(',');
    else input.value = parameter.default ?? '';
  }
  input.id = inputId;
  input.name = name;
  input.dataset.type = parameter.type;
  wrapper.append(label, input);
  if (['single_select', 'multi_select'].includes(parameter.type)) {
    const template = selectorTemplate(parameter, presentation);
    wrapper.classList.add('field--selector');
    if (presentation.css_class) wrapper.classList.add(...presentation.css_class.split(/\s+/).filter(Boolean));
    if (template === 'chips' && parameter.type === 'multi_select') {
      input.classList.add('field__native-choice');
      wrapper.append(multiSelectChoices(input, presentation));
    } else if (['dropdown', 'searchable'].includes(template)) {
      input.classList.add('field__native-choice');
      wrapper.append(choicePicker(input, {...presentation, template}));
    }
  }
  return wrapper;
}

function multiSelectChoices(select, presentation = {}) {
  const control = document.createElement('div');
  control.className = 'choice-control';
  control.setAttribute('role', 'group');

  const all = document.createElement('button');
  all.type = 'button';
  all.className = 'choice-chip choice-chip--all';
  all.textContent = 'All';
  all.addEventListener('click', () => {
    if (select.disabled) return;
    for (const option of select.options) option.selected = true;
    sync();
    select.dispatchEvent(new Event('change', {bubbles: true}));
  });
  control.append(all);

  const choices = [...select.options].map((option) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'choice-chip';
    button.textContent = option.textContent;
    button.dataset.value = option.value;
    button.addEventListener('click', () => {
      if (select.disabled) return;
      option.selected = !option.selected;
      sync();
      select.dispatchEvent(new Event('change', {bubbles: true}));
    });
    control.append(button);
    return {button, option};
  });

  function sync() {
    const allSelected = choices.length > 0 && choices.every(({option}) => option.selected);
    all.classList.toggle('is-selected', allSelected);
    all.setAttribute('aria-pressed', String(allSelected));
    all.disabled = select.disabled;
    for (const {button, option} of choices) {
      button.classList.toggle('is-selected', option.selected);
      button.setAttribute('aria-pressed', String(option.selected));
      button.disabled = select.disabled || option.disabled;
      button.hidden = option.disabled && !presentation.show_unavailable;
    }
  }

  select._syncChoiceControl = sync;
  sync();
  return control;
}

function choicePicker(select, presentation = {}) {
  const picker = document.createElement('div');
  picker.className = 'choice-picker';
  picker.dataset.choicePicker = '';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'choice-picker__trigger';
  trigger.setAttribute('aria-expanded', 'false');
  const summary = document.createElement('span');
  const chevron = document.createElement('i');
  chevron.textContent = '⌄';
  trigger.append(summary, chevron);
  const panel = document.createElement('div');
  panel.className = 'choice-picker__panel';
  panel.hidden = true;
  let search = null;
  if (presentation.template === 'searchable') {
    search = document.createElement('input');
    search.type = 'search';
    search.className = 'choice-picker__search';
    search.placeholder = presentation.search_placeholder || 'Search options…';
    panel.append(search);
  }
  const options = document.createElement('div');
  options.className = 'choice-picker__options';
  const empty = document.createElement('div');
  empty.className = 'choice-picker__empty';
  empty.textContent = presentation.empty_text || 'No matching options';
  empty.hidden = true;
  const rows = [...select.options].map(option => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'choice-picker__option';
    button.dataset.value = option.value;
    button.innerHTML = `<span>${escapeHtml(option.textContent)}</span><i>✓</i>`;
    button.addEventListener('click', () => {
      if (select.disabled || option.disabled) return;
      if (select.multiple) option.selected = !option.selected;
      else {
        [...select.options].forEach(item => { item.selected = item === option; });
        close();
      }
      sync();
      select.dispatchEvent(new Event('change', {bubbles: true}));
    });
    options.append(button);
    return {button, option};
  });
  panel.append(options, empty);
  if (select.multiple) {
    const footer = document.createElement('footer');
    const all = document.createElement('button');
    all.type = 'button';
    all.textContent = 'Select all available';
    const count = document.createElement('small');
    all.addEventListener('click', () => {
      [...select.options].forEach(option => { option.selected = !option.disabled; });
      sync();
      select.dispatchEvent(new Event('change', {bubbles: true}));
    });
    footer.append(all, count);
    panel.append(footer);
    picker._availableCount = count;
  }
  const close = () => {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  };
  trigger.addEventListener('click', () => {
    document.querySelectorAll('[data-choice-picker]').forEach(item => { if (item !== picker) item._close?.(); });
    panel.hidden = !panel.hidden;
    trigger.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) search?.focus();
  });
  search?.addEventListener('input', sync);
  function sync() {
    const query = (search?.value || '').trim().toLocaleLowerCase();
    let visible = 0;
    const available = rows.filter(({option}) => !option.disabled);
    rows.forEach(({button, option}) => {
      const matches = !query || `${option.textContent} ${option.value}`.toLocaleLowerCase().includes(query);
      const unavailable = option.disabled;
      button.hidden = !matches || (unavailable && !presentation.show_unavailable);
      button.disabled = select.disabled || unavailable;
      button.classList.toggle('is-selected', option.selected && !unavailable);
      button.classList.toggle('is-unavailable', unavailable);
      button.setAttribute('aria-pressed', String(option.selected && !unavailable));
      if (!button.hidden) visible += 1;
    });
    empty.hidden = visible > 0;
    const selected = available.filter(({option}) => option.selected);
    summary.textContent = select.multiple
      ? selected.length === available.length && available.length ? `All (${available.length})` : `${selected.length} selected`
      : (selected[0]?.option.textContent || 'Choose…');
    if (picker._availableCount) picker._availableCount.textContent = `${available.length} available`;
    trigger.disabled = select.disabled;
  }
  picker._close = close;
  select._syncChoiceControl = sync;
  picker.append(trigger, panel);
  sync();
  return picker;
}

function selectionField(control) {
  const wrapper = document.createElement('div');
  wrapper.className = 'selection-scope';
  wrapper.dataset.origin = control.origin;
  const scopeNames = {dashboard: 'All views', section: `Section · ${control.owner_title}`, view: `View · ${control.owner_title}`};
  wrapper.innerHTML = `<div class="selection-scope__meta"><span>${escapeHtml(scopeNames[control.origin])}</span><span>${control.affected_views.length} view${control.affected_views.length === 1 ? '' : 's'}</span></div>`;
  wrapper.append(field(control.definition, control.key, control.presentation || {}));
  return wrapper;
}

function nodeRow(node) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'node';
  item.dataset.nodeId = node.id;
  item.dataset.status = 'not_run';
  item.title = node.description || node.title;
  item.innerHTML = `<span class="node-light"></span><strong>${escapeHtml(node.title)}</strong><small>${escapeHtml(node.subtype)}</small>`;
  item.addEventListener('click', () => showNodeError(node.id, node.title));
  return item;
}

function selectDashboard(id) {
  if (state.dashboard) {
    const previous = activeRuntime();
    previous.parameterValues = parameters();
    previous.dashboardSelectionValues = formValues($('#dashboard-selection-form'));
    saveTabUiState();
  }
  closeHeaderPopovers();
  state.dashboard = state.payload.dashboards.find((item) => item.id === id);
  state.preferredDashboardId = id;
  const runtime = activeRuntime();
  document.querySelectorAll('.nav-button').forEach((node) => node.classList.toggle('active', node.dataset.id === id));
  const runnable = Boolean(state.dashboard.runnable);
  $('#parameter-form').replaceChildren(...state.dashboard.query_parameters.map((item) => field(item)));
  const dashboardControls = state.dashboard.selections.filter((item) => item.origin === 'dashboard');
  $('#dashboard-selection-form').replaceChildren(...dashboardControls.map(selectionField));
  setFormValues($('#parameter-form'), runtime.parameterValues || runtime.committedParameters || {});
  setFormValues($('#dashboard-selection-form'), runtime.dashboardSelectionValues || {});
  updateDashboardSelectionSummary();
  $('#node-list').replaceChildren(...state.dashboard.nodes.map(nodeRow));
  document.querySelectorAll('.node').forEach((node) => {
    node.dataset.status = runtime.nodeStatuses[node.dataset.nodeId] || 'not_run';
  });
  $('#query-diagnostics').open = false;
  $('#query-diagnostics').dataset.status = runnable ? runtime.queryStatus : 'failed';
  $('#query-diagnostics-label').textContent = runnable ? runtime.queryLabel : state.dashboard.status;
  $('#run-message').textContent = runnable ? runtime.message : (state.dashboard.message || 'Dashboard unavailable.');
  setQueryState();
  setSelectionsEnabled(Boolean(runtime.runId));
  const run = runtime.runId ? `&run_id=${encodeURIComponent(runtime.runId)}` : '';
  $('#canvas-frame').src = `/api/dashboards/${encodeURIComponent(id)}/canvas?${sessionQuery()}${run}`;
  $('#run-button').disabled = !runnable || Boolean(runtime.pendingRunId);
  $('#download-button').disabled = !runtime.runId;
  saveTabUiState();
}

function setFormValues(form, values) {
  for (const input of form.elements) {
    if (!input.name || !(input.name in values)) continue;
    const value = values[input.name];
    if (input.dataset.type === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((Array.isArray(value) ? value : [value]).map(String));
      for (const option of input.options) option.selected = selected.has(String(option.value));
    } else if (Array.isArray(value)) input.value = value.join(',');
    else input.value = value ?? '';
    input._syncChoiceControl?.();
  }
}

function parameters() {
  return formValues($('#parameter-form'));
}

function selections() {
  return Object.assign({}, state.canvasSelections, formValues($('#dashboard-selection-form')));
}

function formValues(form) {
  const values = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    if (input.dataset.type === 'boolean') values[input.name] = input.checked;
    else if (input.multiple) values[input.name] = [...input.selectedOptions].map((item) => item.value);
    else values[input.name] = input.value;
  }
  return values;
}

async function runDashboard() {
  if (!state.dashboard) return;
  const dashboardId = state.dashboard.id;
  const runtime = runtimeFor(dashboardId);
  if (runtime.pendingRunId) return;
  closeHeaderPopovers();
  $('#run-button').disabled = true;
  $('#query-diagnostics').dataset.status = 'running';
  $('#query-diagnostics-label').textContent = 'Loading';
  $('#run-message').textContent = 'Querying a new dataset…';
  document.querySelectorAll('.node').forEach((node) => node.dataset.status = 'not_run');
  try {
    runtime.parameterValues = parameters();
    const response = await request(`/api/dashboards/${encodeURIComponent(dashboardId)}/runs`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({session_id: state.sessionId, parameters: runtime.parameterValues})
    });
    runtime.pendingRunId = response.run_id;
    runtime.queryStatus = 'running';
    runtime.queryLabel = 'Loading';
    runtime.message = 'Querying a new dataset…';
    listen(response.run_id, dashboardId);
  } catch (error) {
    runtime.queryStatus = 'failed';
    runtime.queryLabel = 'Failed';
    runtime.message = error.message;
    if (state.dashboard?.id === dashboardId) {
      $('#run-message').textContent = error.message;
      $('#query-diagnostics').dataset.status = 'failed';
      $('#query-diagnostics-label').textContent = 'Failed';
      $('#run-button').disabled = false;
    }
  }
}

function listen(runId, dashboardId) {
  const runtime = runtimeFor(dashboardId);
  runtime.eventSource?.close();
  const source = new EventSource(`/api/runs/${runId}/events?${sessionQuery()}`);
  runtime.eventSource = source;
  const names = ['node_queued','node_started','node_succeeded','node_failed','node_blocked'];
  for (const name of names) source.addEventListener(name, (message) => updateEvent(JSON.parse(message.data), dashboardId));
  source.addEventListener('run_ready', () => finishRun(runId, dashboardId));
  source.addEventListener('run_failed', () => finishRun(runId, dashboardId));
  source.addEventListener('stream_end', () => source.close());
  source.onerror = () => { if (source.readyState === EventSource.CLOSED) return; };
}

function updateEvent(event, dashboardId) {
  const runtime = runtimeFor(dashboardId);
  const statusMap = {node_queued:'queued', node_started:'running', node_succeeded:'succeeded', node_failed:'failed', node_blocked:'blocked'};
  runtime.nodeStatuses[event.node_id] = statusMap[event.event] || 'not_run';
  if (event.error) runtime.nodeErrors[event.node_id] = event.error;
  const label = event.node_id ? event.node_id.replace(':', ' · ') : 'run';
  runtime.message = `${label} — ${statusMap[event.event] || event.event}${event.duration_ms ? ` · ${event.duration_ms}ms` : ''}`;
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
  runtime.message = status === 'success' ? 'Dataset query completed.' : `Query finished with status: ${status}`;
  runtime.pendingRunId = null;
  if (record.result) {
    runtime.runId = runId;
    runtime.committedParameters = record.result.parameters;
    runtime.queryStatus = status === 'success' ? 'success' : 'failed';
    runtime.queryLabel = status === 'success' ? 'Ready' : status === 'partial' ? 'Partial' : 'Failed';
  } else {
    runtime.queryStatus = 'failed';
    runtime.queryLabel = 'Failed';
    runtime.message = 'Query failed. The previously loaded dataset is unchanged.';
  }
  if (state.dashboard?.id === dashboardId) {
    $('#run-message').textContent = runtime.message;
    $('#run-button').disabled = false;
    $('#download-button').disabled = !runtime.runId;
    $('#query-diagnostics').dataset.status = runtime.queryStatus;
    $('#query-diagnostics-label').textContent = runtime.queryLabel;
    setSelectionsEnabled(Boolean(runtime.runId));
    setQueryState(record.result ? null : runtime.message);
    if (record.result) {
      $('#canvas-frame').src = `/api/dashboards/${encodeURIComponent(dashboardId)}/canvas?${sessionQuery()}&run_id=${encodeURIComponent(runId)}`;
    }
  }
}

function setSelectionsEnabled(enabled) {
  for (const input of $('#dashboard-selection-form').elements) {
    input.disabled = !enabled;
    input._syncChoiceControl?.();
  }
}

function normalized(value) {
  if (Array.isArray(value)) return value.map(normalized);
  if (value === null || value === undefined) return '';
  return String(value);
}

function pendingParametersMatchDataset() {
  if (!state.committedParameters) return false;
  const pending = parameters();
  const keys = new Set([...Object.keys(pending), ...Object.keys(state.committedParameters)]);
  return [...keys].every((key) => JSON.stringify(normalized(pending[key])) === JSON.stringify(normalized(state.committedParameters[key])));
}

function setQueryState(message = null) {
  const node = $('#query-state');
  if (state.dashboard && !state.dashboard.runnable) {
    node.dataset.stale = 'true';
    node.textContent = state.dashboard.message || 'Dashboard unavailable.';
    $('#query-control-meta').textContent = state.dashboard.status;
    return;
  }
  if (message) {
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

function updateDashboardSelectionSummary() {
  const count = state.dashboard?.selections.filter((control) => control.origin === 'dashboard').length || 0;
  $('#dashboard-control-meta').textContent = count ? `${count} selector${count === 1 ? '' : 's'}` : 'None';
}

function closeHeaderPopovers(except = null) {
  document.querySelectorAll('[data-header-popover][open]').forEach((details) => {
    if (details !== except) details.open = false;
  });
}

function applyViewSelections() {
  if (!state.runId) return;
  $('#canvas-frame').contentWindow?.postMessage(
    {type: 'dataviz:set-selections', selections: selections()},
    window.location.origin,
  );
}

function scheduleViewSelections() {
  window.clearTimeout(state.selectionTimer);
  state.selectionTimer = window.setTimeout(applyViewSelections, 80);
}

function showNodeError(nodeId, title) {
  const error = state.nodeErrors[nodeId];
  if (!error) return;
  $('#error-title').textContent = title;
  $('#error-content').textContent = JSON.stringify(error, null, 2);
  $('#error-dialog').showModal();
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
    button.innerHTML = `<strong>${escapeHtml(dashboard.canvas_name || dashboard.title)}</strong>${status}`;
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

async function refreshNavigation(preferredPath = state.dashboard?.path) {
  state.payload = await request('/api/workspace');
  $('#workspace-title').textContent = 'Dashboards';
  $('#workspace-title').title = state.payload.workspace.title;
  renderNavigation();
  const preferred = state.payload.dashboards.find((item) => item.path === preferredPath);
  const remembered = state.payload.dashboards.find((item) => item.id === state.preferredDashboardId);
  const fallback = state.payload.dashboards.find((item) => item.runnable) || state.payload.dashboards[0];
  if (preferred || remembered || fallback) selectDashboard((preferred || remembered || fallback).id);
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
  if (!state.payload.capabilities?.navigation_management) return openServerRestartDialog();
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
  if (!state.payload.capabilities?.navigation_management) return openServerRestartDialog();
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
  if (!state.payload.capabilities?.navigation_management) return openServerRestartDialog();
  const dashboard = state.payload.dashboards.find((item) => item.id === dashboardId);
  showNavDialog({
    eyebrow: 'NAVIGATION / MOVE', title: `移动「${dashboard.canvas_name || dashboard.title}」`, submitLabel: '移动看板',
    body: `<label class="nav-dialog__field"><span>目标目录</span><select name="parent_id">${folderOptions(dashboard.parent_id)}</select></label><p class="nav-dialog__note">移动会把目录重命名为“目录##看板”；看板内容不会改变。</p>`,
    onSubmit: async (data) => {
      await request(`/api/navigation/dashboards/${encodeURIComponent(dashboardId)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:data.get('parent_id') || null})});
      await refreshNavigation(dashboard.path);
    },
  });
}

function openDeleteDialog(folderId) {
  if (!state.payload.capabilities?.navigation_management) return openServerRestartDialog();
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
  if (!state.payload.capabilities?.navigation_management) return openServerRestartDialog();
  const dashboard = state.payload.dashboards.find((item) => item.id === dashboardId);
  showNavDialog({
    eyebrow: 'NAVIGATION / TRASH', title: `把「${dashboard.canvas_name || dashboard.title}」移到回收站？`, submitLabel: '移到回收站', danger: true,
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

function openServerRestartDialog() {
  showNavDialog({
    eyebrow: 'SERVER / RESTART REQUIRED', title: '需要重启 Server', submitLabel: '知道了',
    body: '<p class="nav-dialog__note">页面资源已经更新，但当前 Python 进程仍是旧版本。请在终端按 Ctrl+C，再重新运行 dataviz serve。</p>',
    onSubmit: async () => {},
  });
}

async function boot() {
  state.sessionId = await resolveTabSessionId();
  restoreTabUiState();
  const remembered = await request(`/api/session/runs?${sessionQuery()}`);
  for (const record of remembered.runs || []) {
    const runtime = runtimeFor(record.dashboard_id);
    runtime.committedParameters = record.parameters;
    if (!runtime.parameterValues) runtime.parameterValues = record.parameters;
    if (!runtime.dashboardSelectionValues && record.selections) runtime.dashboardSelectionValues = record.selections;
    runtime.nodeStatuses = record.nodes || {};
    if (record.ready) {
      runtime.runId = record.run_id;
      runtime.queryStatus = record.status === 'success' ? 'success' : 'failed';
      runtime.queryLabel = record.status === 'success' ? 'Ready' : record.status === 'partial' ? 'Partial' : 'Failed';
      runtime.message = record.status === 'success' ? 'Dataset query completed.' : `Query finished with status: ${record.status}`;
    } else if (record.status === 'running') {
      runtime.pendingRunId = record.run_id;
      runtime.queryStatus = 'running';
      runtime.queryLabel = 'Loading';
      runtime.message = 'Querying a new dataset…';
      listen(record.run_id, record.dashboard_id);
    }
  }
  await refreshNavigation(null);
}

$('#run-button').addEventListener('click', runDashboard);
$('#download-button').addEventListener('click', () => {
  if (state.runId) {
    const initialSelections = encodeURIComponent(JSON.stringify(selections()));
    window.location.href = `/api/dashboards/${encodeURIComponent(state.dashboard.id)}/report?${sessionQuery()}&run_id=${encodeURIComponent(state.runId)}&selections=${initialSelections}`;
  }
});
$('#canvas-frame').addEventListener('load', applyViewSelections);
$('#parameter-form').addEventListener('input', () => setQueryState());
$('#parameter-form').addEventListener('input', () => {
  if (activeRuntime()) activeRuntime().parameterValues = parameters();
  saveTabUiState();
});
$('#parameter-form').addEventListener('change', () => {
  if (activeRuntime()) activeRuntime().parameterValues = parameters();
  saveTabUiState();
  setQueryState();
});
$('#dashboard-selection-form').addEventListener('input', () => {
  if (activeRuntime()) activeRuntime().dashboardSelectionValues = formValues($('#dashboard-selection-form'));
  saveTabUiState();
  updateDashboardSelectionSummary();
  scheduleViewSelections();
});
$('#dashboard-selection-form').addEventListener('change', () => {
  if (activeRuntime()) activeRuntime().dashboardSelectionValues = formValues($('#dashboard-selection-form'));
  saveTabUiState();
  updateDashboardSelectionSummary();
  scheduleViewSelections();
});
document.querySelectorAll('[data-header-popover]').forEach((details) => {
  details.addEventListener('toggle', () => {
    if (details.open) closeHeaderPopovers(details);
  });
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('[data-header-popover]')) closeHeaderPopovers();
  if (!event.target.closest('[data-choice-picker]')) {
    document.querySelectorAll('[data-choice-picker]').forEach(item => item._close?.());
  }
  if (!event.target.closest('#nav-context-menu')) hideNavMenu();
});
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  const open = document.querySelector('[data-header-popover][open]');
  document.querySelectorAll('[data-choice-picker]').forEach(item => item._close?.());
  closeHeaderPopovers();
  open?.querySelector('summary')?.focus();
});
window.addEventListener('message', (event) => {
  if (event.origin !== window.location.origin || event.data?.type !== 'dataviz:selections-changed') return;
  state.canvasSelections = {...state.canvasSelections, ...(event.data.selections || {})};
  saveTabUiState();
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
window.addEventListener('blur', hideNavMenu);
boot().catch((error) => { document.body.innerHTML = `<pre>${escapeHtml(error.stack || error.message)}</pre>`; });
