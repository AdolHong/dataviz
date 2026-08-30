const state = {
  payload: null,
  dashboard: null,
  sessionId: null,
  dashboardStates: new Map(),
  preferredDashboardId: null,
  selectionTimer: null,
  computeTimer: null,
  draggedNavigation: null,
  sidebarWidth: 250,
  sidebarWidthCustomized: false,
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
      queryParametersOpen: null,
      committedComputeParameters: null,
      draftComputeParameters: null,
      selectionState: {},
      controlImpacts: {},
      selectionEpoch: 0,
      eventSource: null,
      nodeErrors: {},
      nodeStatuses: {},
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
  'selectionState',
]) {
  Object.defineProperty(state, property, {
    get() { return activeRuntime()?.[property] ?? (property.endsWith('Errors') || property.endsWith('State') ? {} : null); },
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

function dashboardIdFromLocation(pathname = window.location.pathname) {
  const match = pathname.match(/^\/dashboards\/([^/]+)\/?$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch (_) { return null; }
}

function queryParameterScalar(parameter, raw) {
  if (raw == null) return null;
  if (parameter.value_type === 'number' || parameter.value_type === 'integer') {
    const value = Number(raw);
    return Number.isFinite(value) ? value : raw;
  }
  if (parameter.value_type === 'boolean') {
    if (raw === 'true' || raw === '1') return true;
    if (raw === 'false' || raw === '0') return false;
    return raw;
  }
  const choice = (parameter.options?.choices || []).find((item) => {
    const encoded = typeof item.value === 'object'
      ? JSON.stringify(item.value)
      : String(item.value);
    return encoded === raw;
  });
  return choice ? structuredClone(choice.value) : raw;
}

function queryParameterValuesFromLocation(dashboard, search = window.location.search) {
  const params = new URLSearchParams(search);
  const values = {};
  for (const parameter of dashboard.query_parameters || []) {
    if (!params.has(parameter.id)) continue;
    const raw = params.getAll(parameter.id);
    if (
      parameter.type === 'multiple_input'
      || parameter.type === 'multiple_select'
      || parameter.type === 'range_input'
      || (parameter.path_fields || []).length > 0
    ) {
      values[parameter.id] = raw.map(item => queryParameterScalar(parameter, item));
    } else {
      values[parameter.id] = queryParameterScalar(parameter, raw.at(-1));
    }
  }
  return values;
}

function dashboardLocation(dashboardId, parameters = {}) {
  const dashboard = state.payload?.dashboards?.find(item => item.id === dashboardId);
  const search = new URLSearchParams();
  for (const definition of dashboard?.query_parameters || []) {
    const value = parameters[definition.id];
    if (value == null || value === '') continue;
    const items = Array.isArray(value) ? value : [value];
    for (const item of items) {
      if (item == null || item === '') continue;
      search.append(definition.id, typeof item === 'object' ? JSON.stringify(item) : String(item));
    }
  }
  const query = search.toString();
  return `/dashboards/${encodeURIComponent(dashboardId)}${query ? `?${query}` : ''}`;
}

function syncDashboardLocation(mode = 'replace') {
  if (!state.dashboard || mode === 'none') return;
  const url = dashboardLocation(state.dashboard.id, queryParameters());
  const activeLink = document.querySelector(
    `.nav-button[data-id="${CSS.escape(state.dashboard.id)}"]`,
  );
  if (activeLink instanceof HTMLAnchorElement) activeLink.href = url;
  if (`${window.location.pathname}${window.location.search}` === url) return;
  const method = mode === 'push' ? 'pushState' : 'replaceState';
  window.history[method]({dashboardId:state.dashboard.id}, '', url);
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

function syncCanvasQueryDraft() {
  const runtime = activeRuntime();
  if (!runtime) return false;
  const hasCommittedDataset = Boolean(runtime.runId);
  const valuesMatch = hasCommittedDataset && pendingParametersMatchDataset();
  return postCanvasMessage({
    type: 'dataviz:set-query-draft',
    query_parameters: structuredClone(runtime.queryParameterValues || queryParameters()),
    query_stale: Boolean(
      runtime.queryDefinitionStale || (hasCommittedDataset && !valuesMatch)
    ),
    query_definition_stale: Boolean(runtime.queryDefinitionStale),
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
      queryParametersOpen: runtime.queryParametersOpen,
      committedComputeParameters: runtime.committedComputeParameters,
      draftComputeParameters: runtime.draftComputeParameters,
      selectionState: runtime.selectionState,
    };
  }
  sessionStorage.setItem(
    `dataviz.tab-ui.v3.${state.sessionId}`,
    JSON.stringify({
      activeDashboardId: state.dashboard?.id || state.preferredDashboardId,
      sidebar: {
        width: state.sidebarWidth,
        customized: state.sidebarWidthCustomized,
        collapsed: state.sidebarCollapsed,
      },
      dashboards,
    }),
  );
}

function sidebarWidthBounds() {
  return {min: 180, max: Math.max(180, Math.min(480, window.innerWidth - 420))};
}

function applySidebarState({persist = false} = {}) {
  const bounds = sidebarWidthBounds();
  state.sidebarWidth = Math.round(Math.min(bounds.max, Math.max(bounds.min, state.sidebarWidth || 250)));
  document.documentElement.style.setProperty('--sidebar-width', `${state.sidebarWidth}px`);
  document.body.classList.toggle('sidebar-collapsed', state.sidebarCollapsed);
  const toggle = $('#sidebar-toggle');
  toggle.setAttribute('aria-expanded', String(!state.sidebarCollapsed));
  toggle.setAttribute('aria-label', state.sidebarCollapsed ? '展开导航栏' : '收起导航栏');
  toggle.title = `${state.sidebarCollapsed ? '展开导航栏' : '收起导航栏'} (B)`;
  const resizer = $('#sidebar-resizer');
  resizer.setAttribute('aria-valuemin', String(bounds.min));
  resizer.setAttribute('aria-valuemax', String(bounds.max));
  resizer.setAttribute('aria-valuenow', String(state.sidebarWidth));
  resizer.tabIndex = state.sidebarCollapsed ? -1 : 0;
  if (persist) saveTabUiState();
}

function restoreTabUiState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(`dataviz.tab-ui.v3.${state.sessionId}`) || '{}');
    state.preferredDashboardId = saved.activeDashboardId || null;
    state.sidebarWidthCustomized = Boolean(saved.sidebar?.customized);
    state.sidebarWidth = state.sidebarWidthCustomized
      ? Number(saved.sidebar?.width) || 250
      : 250;
    state.sidebarCollapsed = typeof saved.sidebar?.collapsed === 'boolean'
      ? saved.sidebar.collapsed
      : window.innerWidth <= 980;
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

function keyboardTargetIsEditable(target) {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]'));
}

function keyboardShortcutCommand(event) {
  if (event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229) return null;
  if (document.querySelector('dialog[open]')) return null;
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key === 'Enter') return 'run-query';
  if (event.ctrlKey || event.metaKey || event.altKey || keyboardTargetIsEditable(event.target)) return null;
  if (event.key.toLowerCase() === 'q') return 'toggle-query-parameters';
  if (event.key.toLowerCase() === 'b') return 'toggle-sidebar';
  if (event.key === '?') return 'show-shortcuts';
  return null;
}

let shortcutToastTimer = null;
function showShortcutToast(message) {
  const toast = $('#shortcut-toast');
  window.clearTimeout(shortcutToastTimer);
  toast.textContent = message;
  toast.hidden = false;
  window.requestAnimationFrame(() => toast.classList.add('is-visible'));
  shortcutToastTimer = window.setTimeout(() => {
    toast.classList.remove('is-visible');
    shortcutToastTimer = window.setTimeout(() => { toast.hidden = true; }, 160);
  }, 1800);
}

function executeKeyboardShortcut(command) {
  if (command === 'toggle-query-parameters') {
    if (Number($('#query-parameters-control').dataset.controlCount || 0) <= 0) {
      showShortcutToast('当前看板没有查询参数');
      return true;
    }
    closeHeaderPopovers();
    toggleQueryParameters();
    return true;
  }
  if (command === 'run-query') {
    if ($('#run-button').disabled) return false;
    runDashboard();
    return true;
  }
  if (command === 'toggle-sidebar') {
    closeHeaderPopovers();
    toggleSidebar();
    return true;
  }
  if (command === 'show-shortcuts') {
    closeHeaderPopovers();
    const dialog = $('#keyboard-shortcuts-dialog');
    if (!dialog.open) dialog.showModal();
    return true;
  }
  return false;
}

function handleKeyboardShortcut(event) {
  const command = keyboardShortcutCommand(event);
  if (!command || !executeKeyboardShortcut(command)) return;
  event.preventDefault();
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
    state.sidebarWidthCustomized = true;
    state.sidebarWidth = startWidth + event.clientX - startX;
    applySidebarState();
  });
  resizer.addEventListener('pointerup', finish);
  resizer.addEventListener('pointercancel', finish);
  resizer.addEventListener('dblclick', () => {
    state.sidebarWidth = 250;
    state.sidebarWidthCustomized = false;
    applySidebarState({persist: true});
  });
  resizer.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const bounds = sidebarWidthBounds();
    state.sidebarWidthCustomized = true;
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

function editorValueSignature(value) {
  return JSON.stringify(value);
}

function editorTypedValue(item, raw, label = '值') {
  if (item.value_type === 'text') return String(raw);
  if (item.value_type === 'date') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(raw))) throw new Error(`${label}必须是 YYYY-MM-DD 日期`);
    const date = new Date(`${raw}T00:00:00Z`);
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== raw) {
      throw new Error(`${label}不是有效日期`);
    }
    return raw;
  }
  if (item.value_type === 'boolean') {
    if (raw === true || raw === 'true') return true;
    if (raw === false || raw === 'false') return false;
    throw new Error(`${label}必须是 true 或 false`);
  }
  if (['integer', 'number'].includes(item.value_type)) {
    if (raw === '') throw new Error(`${label}不能为空`);
    const value = Number(raw);
    if (!Number.isFinite(value) || (item.value_type === 'integer' && !Number.isInteger(value))) {
      throw new Error(`${label}必须是${item.value_type === 'integer' ? '整数' : '数字'}`);
    }
    return value;
  }
  return raw;
}

function editorTypedInput(item, value = '', {label = '值'} = {}) {
  if ((item.path_fields || []).length) {
    const input = document.createElement('input');
    input.type = 'text';
    input.value = JSON.stringify(value ?? []);
    input.dataset.editorJsonValue = '';
    input.setAttribute('aria-label', label);
    return input;
  }
  if (item.value_type === 'boolean') {
    const input = document.createElement('select');
    input.innerHTML = '<option value="true">True</option><option value="false">False</option>';
    input.value = String(Boolean(value));
    input.setAttribute('aria-label', label);
    return input;
  }
  const input = document.createElement('input');
  input.type = item.value_type === 'date' ? 'date'
    : ['integer', 'number'].includes(item.value_type) ? 'number' : 'text';
  input.value = value ?? '';
  input.setAttribute('aria-label', label);
  if (item.value_type === 'integer') input.step = String(item.step ?? 1);
  else if (item.value_type === 'number') input.step = String(item.step ?? 'any');
  if (item.min != null) input.min = String(item.min);
  if (item.max != null) input.max = String(item.max);
  if (item.min_date) input.min = item.min_date;
  if (item.max_date) input.max = item.max_date;
  if (item.max_length) input.maxLength = Number(item.max_length);
  return input;
}

function editorChoiceValue(row, item) {
  const input = row.querySelector('[data-choice-value]');
  const raw = input.value;
  if (input.dataset.editorJsonValue != null) {
    try { return JSON.parse(raw); }
    catch (_) { throw new Error(`候选值“${raw}”不是有效 JSON`); }
  }
  return editorTypedValue(item, raw, `候选值“${raw}”`);
}

function moveEditorNode(node, direction) {
  const sibling = direction < 0 ? node.previousElementSibling : node.nextElementSibling;
  if (!sibling) return;
  if (direction < 0) node.parentElement.insertBefore(node, sibling);
  else node.parentElement.insertBefore(sibling, node);
  syncEditorMoveButtons(node.parentElement);
  notifyEditorChanged(node);
}

function notifyEditorChanged(node) {
  node.dispatchEvent(new CustomEvent('dataviz:editor-change', {bubbles:true}));
}

function syncEditorMoveButtons(container) {
  const rows = [...container.children].filter(node => node.matches('[data-editor-item], [data-editor-choice]'));
  rows.forEach((row, index) => {
    const up = row.querySelector('[data-move="up"]');
    const down = row.querySelector('[data-move="down"]');
    if (up) up.disabled = index === 0;
    if (down) down.disabled = index === rows.length - 1;
  });
}

function editorMoveActions(kind, removable = false) {
  const actions = document.createElement('div');
  actions.className = `parameter-editor__${kind}-actions`;
  const up = document.createElement('button');
  up.type = 'button';
  up.dataset.move = 'up';
  up.setAttribute('aria-label', '向前移动');
  up.textContent = '↑';
  const down = document.createElement('button');
  down.type = 'button';
  down.dataset.move = 'down';
  down.setAttribute('aria-label', '向后移动');
  down.textContent = '↓';
  actions.append(up, down);
  if (removable) {
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.dataset.remove = '';
    remove.setAttribute('aria-label', '删除候选项');
    remove.textContent = '×';
    actions.append(remove);
  }
  return actions;
}

function editorDateDefault(item) {
  const root = document.createElement('div');
  root.className = 'parameter-editor__date-default';
  const values = item.type === 'range_input'
    ? (Array.isArray(item.default) ? item.default : ['', ''])
    : [item.default ?? ''];
  const parts = item.type === 'range_input'
    ? [['start', '开始日期'], ['end', '结束日期']]
    : [['value', '日期']];

  for (const [index, [part, label]] of parts.entries()) {
    const atom = values[index];
    const relative = atom?.mode === 'relative' && atom?.anchor === 'today';
    const row = document.createElement('label');
    row.className = 'parameter-editor__date-atom';
    row.dataset.editorDateAtom = part;
    const name = document.createElement('span');
    name.textContent = label;
    const controls = document.createElement('span');
    controls.className = 'parameter-editor__date-atom-controls';
    const mode = document.createElement('select');
    mode.dataset.editorDateMode = part;
    mode.setAttribute('aria-label', `${label}默认值类型`);
    mode.innerHTML = '<option value="fixed">固定日期</option><option value="relative">相对今天</option>';
    mode.value = relative ? 'relative' : 'fixed';
    const valueHost = document.createElement('div');
    valueHost.className = 'parameter-editor__date-value-host';
    const fixedControl = document.createElement('div');
    fixedControl.className = 'dv-control parameter-editor__date-picker';
    fixedControl.dataset.controlComponent = 'date-picker';
    fixedControl.dataset.required = 'false';
    fixedControl.dataset.clearable = 'true';
    fixedControl.dataset.minDate = item.min_date || '';
    fixedControl.dataset.maxDate = item.max_date || '';
    fixedControl.dataset.clearLabel = '清空';
    const fixedInput = document.createElement('input');
    fixedInput.type = 'text';
    fixedInput.value = relative ? '' : String(atom || '');
    fixedInput.setAttribute('aria-label', label);
    const fixedMount = document.createElement('div');
    fixedMount.dataset.controlMount = '';
    const fixedError = document.createElement('small');
    fixedError.className = 'field__error';
    fixedError.dataset.controlError = '';
    fixedError.setAttribute('role', 'alert');
    fixedError.hidden = true;
    fixedControl.append(fixedMount, fixedError);
    const datePicker = window.datavizComponents?.createDatePicker?.({
      control:fixedControl,
      input:fixedInput,
      mount:fixedMount,
    });
    if (!datePicker) {
      fixedInput.className = 'parameter-editor__date-text-fallback';
      fixedInput.placeholder = 'YYYY-MM-DD';
      fixedInput.addEventListener('input', () => (
        window.datavizComponents?.calendarPrimitives?.formatIsoEntry?.(fixedInput)
      ));
      fixedMount.append(fixedInput);
    } else datePicker.sync();

    const relativeInput = document.createElement('input');
    relativeInput.type = 'number';
    relativeInput.step = '1';
    relativeInput.value = relative
      ? String(Number.parseInt(String(atom.offset || '0d').slice(0, -1), 10) || 0)
      : (part === 'start' ? '-7' : '-1');
    relativeInput.setAttribute('aria-label', `${label}相对今天的天数`);
    valueHost.append(fixedControl, relativeInput);
    const sync = () => {
      const relativeMode = mode.value === 'relative';
      fixedControl.hidden = relativeMode;
      relativeInput.hidden = !relativeMode;
      delete fixedInput.dataset.editorDateValue;
      delete relativeInput.dataset.editorDateValue;
      (relativeMode ? relativeInput : fixedInput).dataset.editorDateValue = part;
      if (!relativeMode) datePicker?.sync();
    };
    mode.addEventListener('change', () => {
      sync();
      notifyEditorChanged(root);
    });
    controls.append(mode, valueHost);
    row.append(name, controls);
    root.append(row);
    sync();
  }
  const hint = document.createElement('p');
  hint.textContent = '以 Workspace 时区的今天为基准；-1 表示昨天，0 表示今天。';
  root.append(hint);
  return root;
}

function editorDefaultField(item) {
  const field = document.createElement('label');
  field.className = 'parameter-editor__default';
  const caption = document.createElement('span');
  caption.textContent = '默认值';
  field.append(caption);
  if (
    item.kind === 'query'
    && item.value_type === 'date'
    && ['single_input', 'range_input'].includes(item.type)
  ) {
    field.classList.add('parameter-editor__default--relative');
    field.append(editorDateDefault(item));
    return field;
  }
  if (item.type === 'range_input') {
    field.classList.add('parameter-editor__default--range');
    const range = document.createElement('div');
    range.className = 'parameter-editor__date-range';
    const values = Array.isArray(item.default) ? item.default : ['', ''];
    for (const [index, part] of ['start', 'end'].entries()) {
      const input = editorTypedInput(item, values[index] ?? '', {
        label:part === 'start' ? '开始值' : '结束值',
      });
      input.dataset.editorDefaultPart = part;
      range.append(input);
    }
    field.append(range);
    return field;
  }
  if (item.type === 'multiple_input') {
    const list = document.createElement('div');
    list.className = 'parameter-editor__multiple-list';
    list.dataset.editorMultipleValues = '';
    const append = value => {
      const row = document.createElement('div');
      row.className = 'parameter-editor__multiple-row';
      const input = editorTypedInput(item, value, {label:'列表值'});
      input.dataset.editorMultipleValue = '';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', '删除该值');
      remove.addEventListener('click', () => {
        row.remove();
        notifyEditorChanged(list);
      });
      row.append(input, remove);
      list.append(row);
    };
    (Array.isArray(item.default) ? item.default : []).forEach(append);
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'parameter-editor__add-choice';
    add.textContent = '＋ 添加值';
    add.addEventListener('click', () => {
      append('');
      notifyEditorChanged(list);
      list.lastElementChild?.querySelector('input, select')?.focus();
    });
    field.append(list, add);
    return field;
  }
  let input = editorTypedInput(item, item.default ?? '', {label:'默认值'});
  if (item.value_type === 'boolean') {
    input.insertAdjacentHTML('afterbegin', '<option value="">未设置</option>');
    input.value = item.default == null ? '' : String(Boolean(item.default));
  }
  input.dataset.editorDefault = '';
  field.append(input);
  return field;
}

function editorChoiceRow(item, choice = {label:'', value:''}, selected = false) {
  const row = document.createElement('div');
  row.className = 'parameter-editor__choice';
  row.dataset.editorChoice = '';
  row._choiceMetadata = {
    group:choice.group ?? null,
    description:choice.description || '',
    keywords:[...(choice.keywords || [])],
  };
  const marker = document.createElement('input');
  marker.type = item.type === 'single_select' ? 'radio' : 'checkbox';
  marker.name = `default-${item.id}`;
  marker.dataset.choiceDefault = '';
  marker.checked = selected;
  marker.setAttribute('aria-label', '设为默认选项');
  const label = document.createElement('input');
  label.type = 'text';
  label.required = true;
  label.placeholder = '显示名称';
  label.value = choice.label || '';
  label.dataset.choiceLabel = '';
  const value = editorTypedInput(item, choice.value ?? '', {label:'参数值'});
  value.required = true;
  value.placeholder = '参数值';
  value.dataset.choiceValue = '';
  const actions = editorMoveActions('choice', true);
  actions.querySelector('[data-move="up"]').addEventListener('click', () => moveEditorNode(row, -1));
  actions.querySelector('[data-move="down"]').addEventListener('click', () => moveEditorNode(row, 1));
  actions.querySelector('[data-remove]').addEventListener('click', () => {
    const container = row.parentElement;
    row.remove();
    syncEditorMoveButtons(container);
    notifyEditorChanged(container);
  });
  row.append(marker, label, value, actions);
  return row;
}

function editorSelectInitialField(item, card, {staticChoices = false} = {}) {
  const field = document.createElement('label');
  field.className = 'parameter-editor__default';
  const caption = document.createElement('span');
  caption.textContent = '初始选择';
  const mode = document.createElement('select');
  mode.dataset.editorInitialMode = '';
  const modes = item.type === 'multiple_select'
    ? [['all', '全部候选'], ['empty', '空集'], ['values', '指定值']]
    : [['first', '第一个候选'], ['empty', '空值'], ['value', '指定值']];
  modes.forEach(([value, label]) => mode.append(new Option(label, value)));
  mode.value = item.initial?.mode || (item.type === 'multiple_select' ? 'all' : 'first');
  field.append(caption, mode);
  if (!staticChoices) {
    const value = document.createElement('input');
    value.type = 'text';
    value.dataset.editorInitialValue = '';
    value.placeholder = item.type === 'multiple_select' ? '使用逗号分隔多个值' : '参数值';
    value.value = item.type === 'multiple_select'
      ? (item.initial?.values || []).join(', ')
      : (item.initial?.value ?? '');
    field.append(value);
  }
  const sync = () => {
    const explicit = ['values', 'value'].includes(mode.value);
    card.querySelectorAll('[data-choice-default]').forEach(input => {
      input.disabled = !explicit;
    });
    const value = field.querySelector('[data-editor-initial-value]');
    if (value) value.hidden = !explicit;
  };
  mode.addEventListener('change', () => {
    sync();
    notifyEditorChanged(card);
  });
  queueMicrotask(sync);
  return field;
}

function editorItemCard(item) {
  const card = document.createElement('section');
  card.className = 'parameter-editor__item';
  card.dataset.editorItem = item.id;
  card.dataset.editorType = item.type;
  card.dataset.editorValueType = item.value_type;
  card.dataset.defaultEditable = String(item.default_editable);
  card.dataset.initialEditable = String(item.initial_editable);
  card.dataset.choicesEditable = String(item.choices_editable);
  const header = document.createElement('header');
  header.className = 'parameter-editor__item-summary';
  const drag = document.createElement('button');
  drag.type = 'button';
  drag.className = 'parameter-editor__drag-handle';
  drag.draggable = true;
  drag.setAttribute('aria-label', `拖动调整 ${item.label} 的顺序`);
  drag.title = '拖动排序';
  drag.innerHTML = '<span></span><span></span><span></span><span></span><span></span><span></span>';
  const title = document.createElement('div');
  title.className = 'parameter-editor__item-title';
  title.innerHTML = `<strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.id)} · ${escapeHtml(item.type)} / ${escapeHtml(item.value_type)}</small>`;
  const disclosure = document.createElement('button');
  disclosure.type = 'button';
  disclosure.className = 'parameter-editor__disclosure';
  disclosure.dataset.editorDisclosure = '';
  disclosure.setAttribute('aria-expanded', 'false');
  disclosure.setAttribute('aria-label', `展开 ${item.label} 的参数细节`);
  disclosure.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>';
  const detail = document.createElement('div');
  detail.className = 'parameter-editor__item-detail';
  detail.hidden = true;
  disclosure.addEventListener('click', () => {
    const expanded = disclosure.getAttribute('aria-expanded') !== 'true';
    disclosure.setAttribute('aria-expanded', String(expanded));
    disclosure.setAttribute('aria-label', `${expanded ? '折叠' : '展开'} ${item.label} 的参数细节`);
    detail.hidden = !expanded;
    card.classList.toggle('is-expanded', expanded);
  });
  drag.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    moveEditorNode(card, event.key === 'ArrowUp' ? -1 : 1);
    drag.focus();
  });
  drag.addEventListener('dragstart', event => {
    card.classList.add('is-dragging');
    card.parentElement._draggedEditorItem = card;
    card.parentElement._editorOrderBeforeDrag = [...card.parentElement.querySelectorAll(':scope > [data-editor-item]')]
      .map(node => node.dataset.editorItem).join('\u0000');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', item.id);
  });
  drag.addEventListener('dragend', () => {
    const container = card.parentElement;
    card.classList.remove('is-dragging');
    container?.querySelectorAll('.is-drop-target').forEach(node => node.classList.remove('is-drop-target'));
    if (container) {
      const after = [...container.querySelectorAll(':scope > [data-editor-item]')]
        .map(node => node.dataset.editorItem).join('\u0000');
      if (after !== container._editorOrderBeforeDrag) notifyEditorChanged(card);
      container._draggedEditorItem = null;
      container._editorOrderBeforeDrag = null;
    }
  });
  header.append(drag, title, disclosure);
  card.append(header, detail);

  if (item.choices_editable) {
    const selected = item.type === 'multiple_select'
      ? (item.initial?.values || [])
      : [item.initial?.value];
    const choiceSection = document.createElement('div');
    choiceSection.className = 'parameter-editor__choices';
    const legend = document.createElement('div');
    legend.className = 'parameter-editor__choices-heading';
    legend.innerHTML = '<span>默认</span><span>显示名称</span><span>参数值</span><span></span>';
    const rows = document.createElement('div');
    rows.className = 'parameter-editor__choice-list';
    rows.dataset.editorChoices = '';
    for (const choice of item.choices) {
      rows.append(editorChoiceRow(
        item,
        choice,
        selected.some(value => editorValueSignature(value) === editorValueSignature(choice.value)),
      ));
    }
    const footer = document.createElement('div');
    footer.className = 'parameter-editor__choice-footer';
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'parameter-editor__add-choice';
    add.textContent = '＋ 添加候选项';
    add.addEventListener('click', () => {
      const row = editorChoiceRow(item);
      rows.append(row);
      syncEditorMoveButtons(rows);
      notifyEditorChanged(rows);
      row.querySelector('[data-choice-label]').focus();
    });
    footer.append(add);
    choiceSection.append(editorSelectInitialField(item, card, {staticChoices:true}), legend, rows, footer);
    detail.append(choiceSection);
    syncEditorMoveButtons(rows);
  } else if (item.initial_editable) {
    detail.append(editorSelectInitialField(item, card));
  } else if (item.default_editable) {
    detail.append(editorDefaultField(item));
  } else {
    const note = document.createElement('p');
    note.className = 'parameter-editor__readonly';
    note.textContent = '候选项由数据自动推断；这里只能调整它在当前面板中的顺序。';
    detail.append(note);
  }
  return card;
}

function initializeEditorItemDrag(container) {
  container.addEventListener('dragover', event => {
    const dragged = container._draggedEditorItem;
    if (!dragged) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const target = event.target.closest('[data-editor-item]');
    container.querySelectorAll('.is-drop-target').forEach(node => node.classList.remove('is-drop-target'));
    if (!target || target === dragged || target.parentElement !== container) return;
    target.classList.add('is-drop-target');
    const before = event.clientY < target.getBoundingClientRect().top + target.offsetHeight / 2;
    container.insertBefore(dragged, before ? target : target.nextElementSibling);
  });
  container.addEventListener('drop', event => {
    const dragged = container._draggedEditorItem;
    if (!dragged) return;
    event.preventDefault();
    container.querySelectorAll('.is-drop-target').forEach(node => node.classList.remove('is-drop-target'));
    notifyEditorChanged(dragged);
  });
}

function serializeEditorDefault(card) {
  const type = card.dataset.editorType;
  const valueType = card.dataset.editorValueType;
  const item = {type, value_type:valueType};
  const dateAtoms = [...card.querySelectorAll('[data-editor-date-atom]')];
  if (dateAtoms.length) {
    const values = dateAtoms.map(row => {
      const mode = row.querySelector('[data-editor-date-mode]').value;
      const input = row.querySelector('[data-editor-date-value]');
      if (mode === 'relative') {
        if (input.value.trim() === '') {
          throw new Error(`${card.dataset.editorItem} 的相对日期不能为空`);
        }
        const offset = Number(input.value);
        if (!Number.isInteger(offset)) {
          throw new Error(`${card.dataset.editorItem} 的相对日期必须是整数天`);
        }
        return {
          mode:'relative',
          anchor:'today',
          offset:`${offset > 0 ? '+' : ''}${offset}d`,
        };
      }
      return input.value ? editorTypedValue(item, input.value, '固定日期') : '';
    });
    if (type === 'single_input') return values[0] || null;
    return values.every(value => value === '') ? [] : values;
  }
  const range = [...card.querySelectorAll('[data-editor-default-part]:not(:disabled)')];
  if (range.length) {
    const values = range.map((input, index) => (
      input.value === '' ? '' : editorTypedValue(item, input.value, index ? '结束值' : '开始值')
    ));
    return type === 'single_input' ? (values[0] || null) : values;
  }
  const multiple = [...card.querySelectorAll('[data-editor-multiple-value]')];
  if (multiple.length || card.querySelector('[data-editor-multiple-values]')) {
    return multiple.filter(input => input.value !== '').map((input, index) => (
      editorTypedValue(item, input.value, `第 ${index + 1} 个值`)
    ));
  }
  const input = card.querySelector('[data-editor-default]');
  if (!input) return null;
  if (input.value === '') return null;
  return editorTypedValue(item, input.value, `${card.dataset.editorItem} 的默认值`);
}

function serializeEditorGroup(group, container) {
  const cards = [...container.querySelectorAll(':scope > [data-editor-item]')];
  return {
    owner:group.owner,
    order:cards.map(card => card.dataset.editorItem),
    items:cards.map(card => {
      const item = group.items.find(candidate => candidate.id === card.dataset.editorItem);
      const initialMode = card.querySelector('[data-editor-initial-mode]')?.value || null;
      if (!item.choices_editable) {
        let initial = null;
        if (item.initial_editable) {
          initial = {mode:initialMode};
          if (initialMode === 'values') {
            const raw = card.querySelector('[data-editor-initial-value]').value;
            initial.values = raw.split(',').map(value => value.trim()).filter(Boolean)
              .map(value => editorTypedValue(item, value, '初始值'));
          } else if (initialMode === 'value') {
            const raw = card.querySelector('[data-editor-initial-value]').value.trim();
            initial.value = editorTypedValue(item, raw, '初始值');
          }
        }
        return {
          id:item.id,
          default:item.default_editable ? serializeEditorDefault(card) : null,
          initial,
          choices:[],
        };
      }
      const rows = [...card.querySelectorAll('[data-editor-choice]')];
      const choices = rows.map(row => {
        const metadata = row._choiceMetadata || {};
        return {
          label:row.querySelector('[data-choice-label]').value.trim(),
          value:editorChoiceValue(row, item),
          group:metadata.group ?? null,
          description:metadata.description || '',
          keywords:[...(metadata.keywords || [])],
        };
      });
      const selected = rows.filter(row => row.querySelector('[data-choice-default]').checked)
        .map(row => editorChoiceValue(row, item));
      const initial = {mode:initialMode};
      if (initialMode === 'values') initial.values = selected;
      else if (initialMode === 'value') initial.value = selected[0] ?? null;
      return {
        id:item.id,
        default:null,
        initial,
        choices,
      };
    }),
  };
}

async function openParameterEditor(owner) {
  if (!state.dashboard?.runnable) return;
  closeHeaderPopovers();
  const dialog = $('#parameter-editor-dialog');
  const contract = await request(
    `/api/dashboards/${encodeURIComponent(state.dashboard.id)}/parameter-editor`,
  );
  const group = contract.groups.find(candidate => candidate.owner === owner);
  if (!group) throw new Error(`当前看板没有 ${owner} 作用域`);
  dialog.innerHTML = `
    <form method="dialog" class="parameter-editor__form">
      <header class="parameter-editor__header">
        <div><h2 id="parameter-editor-title">${escapeHtml(group.title)}</h2><p>${group.items.length} 个参数</p></div>
        <button type="button" data-close aria-label="关闭">×</button>
      </header>
      <div class="parameter-editor__items" data-editor-items></div>
      <footer class="parameter-editor__footer">
        <p class="parameter-editor__error" role="alert"></p>
        <div><button type="button" class="button button--ghost" data-close>取消</button><button type="submit" class="button button--run" disabled>保存</button></div>
      </footer>
    </form>`;
  const items = dialog.querySelector('[data-editor-items]');
  if (group.items.length) items.replaceChildren(...group.items.map(editorItemCard));
  else items.innerHTML = '<p class="parameter-editor__empty">无参数</p>';
  initializeEditorItemDrag(items);
  dialog.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
  const form = dialog.querySelector('form');
  const submit = form.querySelector('[type="submit"]');
  const baseline = JSON.stringify(serializeEditorGroup(group, items));
  const syncDirtyState = () => {
    let dirty = false;
    let contractError = '';
    try { dirty = JSON.stringify(serializeEditorGroup(group, items)) !== baseline; }
    catch (failure) { contractError = failure.message; }
    const invalid = !form.checkValidity() || Boolean(contractError);
    submit.disabled = !dirty || invalid;
    dialog.querySelector('.parameter-editor__error').textContent = contractError;
  };
  form.addEventListener('input', syncDirtyState);
  form.addEventListener('change', syncDirtyState);
  form.addEventListener('dataviz:editor-change', syncDirtyState);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const error = dialog.querySelector('.parameter-editor__error');
    submit.disabled = true;
    error.textContent = '';
    try {
      const edited = serializeEditorGroup(group, items);
      await request(
        `/api/dashboards/${encodeURIComponent(state.dashboard.id)}/parameter-editor`,
        {
          method:'PATCH',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({revision:contract.revision, group:edited}),
        },
      );
      dialog.close();
      await refreshNavigation(state.dashboard.path, {
        reloadCanvas:true,
        requestedDashboardId:state.dashboard.id,
        historyMode:'replace',
      });
    } catch (failure) {
      error.textContent = failure.message;
      syncDirtyState();
    }
  });
  dialog.showModal();
  dialog.querySelector('[data-editor-disclosure], [data-close]')?.focus();
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
      else if (event.data.missing?.length) reject(new Error(`Run Query before export: ${event.data.missing.join(', ')}`));
      else resolve({
        outputs:event.data.outputs || {},
        selectionState:event.data.selection_state || {},
        computeParameters:event.data.compute_parameters || {},
      });
    };
    window.addEventListener('message', receive);
    requestSnapshot();
  });
}

async function reportRequestContext() {
  if (!state.runId || !state.dashboard) return;
  const identity = canvasIdentity();
  const dashboardId = state.dashboard.id;
  const runId = state.runId;
  const runtime = runtimeFor(dashboardId);
  if (identity.dashboard_id !== dashboardId || identity.run_id !== runId) {
    throw new Error('The active Canvas is not synchronized with the selected Query Run');
  }
  const snapshot = await collectCanvasSnapshot(identity);
  if (!sameCanvasIdentity(canvasIdentity(), identity)) {
    throw new Error('The active Canvas changed while the report snapshot was being prepared');
  }
  return {
    dashboardId,
    runId,
    runtime,
    payload:{
      session_id:state.sessionId,
      run_id:runId,
      // Canvas owns the canonical Section/View Controls and returns them in
      // the same atomic snapshot as Derived Outputs. Reading the parent's
      // asynchronous shadow before this handshake races on Firefox.
      selection_state:snapshot.selectionState,
      compute_parameters:snapshot.computeParameters,
      snapshot_outputs:snapshot.outputs,
    },
  };
}

async function copyPlainText(value) {
  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const fallback = document.createElement('textarea');
    fallback.value = value;
    fallback.style.position = 'fixed';
    fallback.style.opacity = '0';
    document.body.append(fallback);
    fallback.select();
    document.execCommand('copy');
    fallback.remove();
  }
}

function setShareEnabled(enabled) {
  const active = Boolean(enabled);
  const hasServerInteractive = (state.dashboard?.nodes || []).some(
    (node) => node.type === 'interactive_transform' && node.subtype === 'server-python'
  );
  $('#share-control').dataset.empty = String(!active);
  $('#share-button').setAttribute('aria-disabled', String(!active));
  $('#download-button').disabled = !active || hasServerInteractive;
  $('#download-button').title = hasServerInteractive
    ? '包含 Server Python 交互计算，请使用分享链接'
    : '';
  $('#copy-share-link').disabled = !active;
  if (!active) $('#share-control').open = false;
}

async function downloadReport() {
  if (!state.runId || !state.dashboard) return;
  const button = $('#download-button');
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = '正在导出…';
  $('#share-control').open = false;
  let runtime = activeRuntime();
  let dashboardId = state.dashboard.id;
  try {
    const context = await reportRequestContext();
    ({dashboardId, runtime} = context);
    const response = await fetch(
      `/api/dashboards/${encodeURIComponent(dashboardId)}/report`,
      {
        method:'POST',
        cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(context.payload),
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
      || `${dashboardId}-${context.runId}.html`;
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
    setShareEnabled(Boolean(state.runId));
  }
}

async function createSharedLink() {
  if (!state.runId || !state.dashboard) return;
  const button = $('#copy-share-link');
  const previous = button.textContent;
  button.disabled = true;
  button.textContent = '正在创建…';
  try {
    const context = await reportRequestContext();
    const response = await fetch(
      `/api/dashboards/${encodeURIComponent(context.dashboardId)}/share`,
      {
        method:'POST',
        cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(context.payload),
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
    const shared = await response.json();
    const url = new URL(shared.url, window.location.origin).href;
    await copyPlainText(url);
    $('#share-control').open = false;
    showShortcutToast('分享链接已复制');
  } catch (error) {
    const runtime = activeRuntime();
    if (runtime) runtime.message = error.message;
    showShortcutToast(`创建分享失败：${error.message}`);
  } finally {
    button.textContent = previous;
    setShareEnabled(Boolean(state.runId));
  }
}

function controlComponent(parameter, presentation = {}) {
  if (presentation.component && presentation.component !== 'auto') return presentation.component;
  if ((parameter.path_fields || []).length) return 'cascader';
  if (parameter.type === 'range_input') return parameter.value_type === 'date' ? 'range-picker' : 'slider';
  if (parameter.type === 'multiple_input') return 'multiple-input';
  if (parameter.value_type === 'date') return 'date-picker';
  if (['number', 'integer'].includes(parameter.value_type)) return 'input-number';
  if (parameter.value_type === 'boolean') return 'checkbox';
  if (parameter.value_type === 'text' && parameter.type === 'single_input') {
    return (parameter.suggestions || []).length ? 'auto-complete' : 'input';
  }
  const count = parameter.options?.mode === 'static'
    ? (parameter.options.choices || []).length
    : 0;
  if (parameter.type === 'multiple_select') return count > 0 && count <= 8 ? 'checkbox-group' : 'select';
  if (parameter.type === 'single_select') {
    return !parameter.clearable && count > 0 && count <= 4 ? 'radio-group' : 'select';
  }
  throw new Error(`No Data Entry component for ${parameter.type}/${parameter.value_type}`);
}

function field(parameter, name = parameter.id, presentation = {}, behavior = {}) {
  const defaultValue = Object.prototype.hasOwnProperty.call(parameter, 'resolved_default')
    ? parameter.resolved_default
    : parameter.default;
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  const label = document.createElement('label');
  const inputId = `input-${name.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  label.htmlFor = inputId;
  label.textContent = parameter.label || parameter.id;
  let input;
  const component = controlComponent(parameter, presentation);
  const clearable = parameter.clearable == null
    ? !parameter.required && ['single_input', 'multiple_input', 'single_select', 'multiple_select', 'range_input'].includes(parameter.type)
    : Boolean(parameter.clearable);
  if (['single_select', 'multiple_select'].includes(parameter.type)) {
    input = document.createElement('select');
    if (parameter.type === 'multiple_select') {
      input.multiple = true;
    }
    const choices = parameter.options?.mode === 'static'
      ? (parameter.options.choices || [])
      : [];
    const typedChoices = (parameter.path_fields || []).length > 0
      || choices.some(choice => typeof choice.value !== 'string');
    input.dataset.valueEncoding = typedChoices ? 'json' : 'string';
    if (parameter.type !== 'multiple_select') {
      const empty = document.createElement('option');
      empty.value = '';
      empty.hidden = true;
      empty.dataset.emptyOption = 'true';
      empty.selected = defaultValue == null || defaultValue === '';
      input.append(empty);
    }
    for (const choice of choices) {
      const option = document.createElement('option');
      option.value = typedChoices ? JSON.stringify(choice.value) : String(choice.value);
      option.textContent = choice.label;
      if (choice.group) option.dataset.group = choice.group;
      if (choice.description) option.dataset.description = choice.description;
      if (choice.keywords?.length) option.dataset.keywords = choice.keywords.join(' ');
      const hierarchicalSingle = parameter.type === 'single_select' && (parameter.path_fields || []).length;
      const defaults = parameter.type === 'multiple_select'
        ? (Array.isArray(defaultValue) ? defaultValue : [])
        : hierarchicalSingle
        ? [defaultValue]
        : [defaultValue];
      option.selected = defaults.map(value => typedChoices ? JSON.stringify(value) : String(value)).includes(option.value);
      input.append(option);
    }
    if (!input.multiple && defaultValue == null) {
      input.selectedIndex = -1;
    }
  } else {
    input = component === 'input' && presentation.multiline
      ? document.createElement('textarea')
      : document.createElement('input');
    if (input instanceof HTMLInputElement) {
      input.type = parameter.value_type === 'boolean'
        ? 'checkbox'
        : ['number', 'integer'].includes(parameter.value_type)
        ? component === 'slider' && parameter.type === 'single_input' ? 'range' : 'number'
        : parameter.value_type === 'date' && parameter.type === 'single_input'
        ? 'date'
        : 'text';
    }
    if (parameter.value_type === 'boolean') input.checked = Boolean(defaultValue);
    else if (parameter.type === 'multiple_input' && Array.isArray(defaultValue)) input.value = JSON.stringify(defaultValue);
    else if (Array.isArray(defaultValue)) input.value = defaultValue.join(',');
    else input.value = defaultValue ?? '';
  }
  input.required = Boolean(parameter.required && parameter.value_type !== 'boolean');
  if (parameter.placeholder) input.placeholder = parameter.placeholder;
  if (parameter.min != null) input.min = parameter.min;
  if (parameter.max != null) input.max = parameter.max;
  if (parameter.step != null) input.step = parameter.step;
  else if (parameter.value_type === 'integer') input.step = '1';
  if (parameter.min_date) input.min = parameter.min_date;
  if (parameter.max_date) input.max = parameter.max_date;
  if (parameter.max_length) input.maxLength = parameter.max_length;
  input.id = inputId;
  input.name = name;
  input.dataset.type = parameter.type;
  input.dataset.valueType = parameter.value_type;
  input.dataset.controlInput = '';
  if (behavior.selection === true) input.dataset.selectionInput = name;
  if (behavior.compute === true) input.dataset.computeInput = name;
  wrapper.append(label);
  wrapper.classList.add('field--control');
  wrapper.dataset.controlSpan = String(presentation.span || 1);
  if (presentation.css_class) wrapper.classList.add(...presentation.css_class.split(/\s+/).filter(Boolean));
  const control = document.createElement('div');
  control.className = 'dv-control';
  control.dataset.controlComponent = component;
  control.dataset.requestedComponent = presentation.requested_component || presentation.component || 'auto';
  control.dataset.autoReason = presentation.auto_reason || '';
  control.dataset.required = String(Boolean(parameter.required));
  control.dataset.clearable = String(clearable);
  control.dataset.showUnavailable = String(Boolean(presentation.show_unavailable));
  control.dataset.searchMode = presentation.search || 'auto';
  control.dataset.virtualMode = presentation.virtual || 'auto';
  control.dataset.searchThreshold = String(presentation.search_threshold ?? 9);
  control.dataset.virtualThreshold = String(presentation.virtual_threshold ?? 200);
  control.dataset.maxTagCount = String(presentation.max_tag_count ?? 2);
  control.dataset.maxSelected = String(parameter.max_selected || '');
  control.dataset.maxItems = String(parameter.max_items || '');
  control.dataset.controlType = parameter.type;
  control.dataset.valueType = parameter.value_type;
  control.dataset.hideSelected = String(Boolean(presentation.hide_selected));
  control.dataset.searchPlaceholder = presentation.search_placeholder || 'Search options…';
  control.dataset.emptyText = presentation.empty_text || 'No matching options';
  control.dataset.placeholder = parameter.placeholder || 'Choose…';
  control.dataset.selectAllLabel = presentation.select_all_label || 'Select all';
  control.dataset.invertLabel = presentation.invert_label || 'Invert';
  control.dataset.clearLabel = presentation.clear_label || 'Clear';
  control.dataset.pathSeparator = presentation.path_separator || ' / ';
  control.dataset.selectionStrategy = presentation.selection_strategy || 'leaf';
  control.dataset.showCheckedStrategy = presentation.show_checked_strategy || 'child';
  control.dataset.startLabel = presentation.start_label || 'Start';
  control.dataset.endLabel = presentation.end_label || 'End';
  control.dataset.minDate = parameter.min_date || '';
  control.dataset.maxDate = parameter.max_date || '';
  control.dataset.allowEmptyStart = String(Boolean(parameter.allow_empty?.[0]));
  control.dataset.allowEmptyEnd = String(Boolean(parameter.allow_empty?.[1]));
  control.dataset.presets = JSON.stringify(presentation.presets || []);
  control.dataset.itemHeight = String(presentation.item_height || 38);
  control.dataset.viewportHeight = String(presentation.viewport_height || 304);
  control.dataset.overscan = String(presentation.overscan || 5);
  control.dataset.defaultExpandDepth = String(presentation.default_expand_depth || 0);
  control.dataset.optionType = presentation.option_type || 'default';
  control.dataset.buttonStyle = presentation.button_style || 'outline';
  control.dataset.checkedLabel = presentation.checked_label || '';
  control.dataset.uncheckedLabel = presentation.unchecked_label || '';
  control.dataset.multiline = String(Boolean(presentation.multiline));
  control.dataset.minRows = String(presentation.min_rows || 2);
  control.dataset.maxRows = String(presentation.max_rows || 6);
  control.dataset.showCount = String(Boolean(presentation.show_count));
  control.dataset.prefix = presentation.prefix || '';
  control.dataset.suffix = presentation.suffix || '';
  control.dataset.numberControls = String(presentation.number_controls !== false);
  control.dataset.showInput = String(Boolean(presentation.show_input));
  control.dataset.tooltip = presentation.tooltip || 'auto';
  control.dataset.marks = JSON.stringify(presentation.marks || []);
  control.dataset.suggestions = JSON.stringify(parameter.suggestions || []);
  control.dataset.cascaderLevels = JSON.stringify((parameter.path_fields || []).map((field, index) => ({
      field,
      label: presentation.level_labels?.[index] || field,
  })));
  const hiddenNative = ['select', 'radio-group', 'checkbox-group', 'cascader', 'tree-select', 'range-picker', 'multiple-input', 'switch'].includes(component)
    || (component === 'slider' && parameter.type === 'range_input');
  input.dataset.controlNative = hiddenNative ? 'hidden' : 'visible';
  const mount = document.createElement('div');
  mount.dataset.controlMount = '';
  const error = document.createElement('small');
  error.className = 'field__error';
  error.dataset.controlError = '';
  error.setAttribute('role', 'alert');
  error.hidden = true;
  control.append(input, mount, error);
  wrapper.append(control);
  return wrapper;
}

function selectionField(control) {
  const wrapper = document.createElement('div');
  wrapper.className = 'selection-scope';
  wrapper.dataset.origin = control.origin;
  wrapper.dataset.controlKey = control.key;
  wrapper.dataset.controlSpan = String(control.presentation?.span || 1);
  const impact = activeRuntime()?.controlImpacts?.[control.key];
  wrapper.innerHTML = `<span hidden data-control-impact-count>${escapeHtml(controlImpactLabel(control, impact))}</span>`;
  wrapper.append(field(control.definition, control.key, control.presentation || {}, {selection: true}));
  return wrapper;
}

function controlImpactLabel(control, impact = null) {
  const pending = impact?.status === 'pending'
    || (!impact && (control.runtime_checked_views || []).length > 0);
  const views = pending
    ? (impact?.potential_views || control.affected_views || [])
    : (impact?.affected_views || control.affected_views || []);
  const count = views.length;
  return `${pending ? 'Up to ' : ''}${count} view${count === 1 ? '' : 's'}`;
}

function syncDashboardControlImpacts(impacts = []) {
  const runtime = activeRuntime();
  if (!runtime) return;
  for (const impact of impacts) {
    const control = selectionControl(impact?.key);
    if (!control || control.origin !== 'dashboard') continue;
    runtime.controlImpacts[impact.key] = impact;
    const wrapper = [...document.querySelectorAll('#dashboard-selection-form .selection-scope')]
      .find(candidate => candidate.dataset.controlKey === impact.key);
    const label = wrapper?.querySelector('[data-control-impact-count]');
    if (label) label.textContent = controlImpactLabel(control, impact);
  }
}

function dashboardControls(kind = null) {
  return (state.dashboard?.controls || []).filter(
    control => control.origin === 'dashboard' && (kind == null || control.kind === kind),
  );
}

function computeField(control) {
  const wrapper = field(
    control.definition,
    control.key,
    control.presentation || {},
    {compute: true},
  );
  wrapper.dataset.computeParameter = control.key;
  wrapper.dataset.computeTrigger = control.trigger || 'apply';
  wrapper.dataset.controlKind = 'compute';
  return wrapper;
}

function applyDashboardControlPresentation(dashboard) {
  const shell = window.datavizComponents?.presentationShell;
  if (!shell?.applyControlPanel) return;
  const controls = dashboard.presentation?.control_panels || {};
  shell.applyControlPanel($('#query-parameters-control'), controls.query, {
    role:'query', count:dashboard.query_parameters.length,
  });
  shell.applyControlPanel($('#dashboard-controls-control'), controls.dashboard, {
    role:'dashboard', count:dashboardControls().length,
  });
}

function setRunButtonLabel(label) {
  const target = $('#run-button [data-run-label]');
  if (target) target.textContent = label;
}

function setQueryParametersOpen(open, {persist = false} = {}) {
  const owner = $('#query-parameters-control');
  const panel = $('#query-parameters-panel');
  const toggle = $('#query-parameters-toggle');
  const hasParameters = Number(owner.dataset.controlCount || 0) > 0;
  const expanded = hasParameters && Boolean(open);
  owner.dataset.open = String(expanded);
  panel.hidden = !expanded;
  toggle.setAttribute('aria-expanded', String(expanded));
  toggle.setAttribute(
    'aria-label',
    expanded ? 'Collapse query parameters' : 'Expand query parameters',
  );
  toggle.title = `${expanded ? 'Collapse query parameters' : 'Expand query parameters'} (Q)`;
  $('#query-run-control').classList.toggle('is-parameters-open', expanded);
  const runtime = activeRuntime();
  if (runtime && hasParameters) runtime.queryParametersOpen = expanded;
  if (persist) saveTabUiState();
}

function toggleQueryParameters() {
  const expanded = $('#query-parameters-toggle').getAttribute('aria-expanded') === 'true';
  setQueryParametersOpen(!expanded, {persist: true});
}

function selectionControl(key) {
  return (state.dashboard?.controls || []).find(
    control => control.kind === 'selection' && control.key === key,
  ) || null;
}

function selectionValueFromState(definition, entry) {
  const values = Array.isArray(entry?.values) ? entry.values : [];
  if (['multiple_input', 'multiple_select'].includes(definition?.type)) return structuredClone(values);
  if (definition?.type === 'range_input') return values.length ? structuredClone(values[0]) : [];
  return values.length ? structuredClone(values[0]) : null;
}

function selectionStateFromValue(definition, value, intent = 'explicit') {
  const empty = value == null || value === '' || (Array.isArray(value) && value.length === 0);
  let values;
  if (empty) values = [];
  else if (['multiple_input', 'multiple_select'].includes(definition?.type)) values = structuredClone(value);
  else if (definition?.type === 'range_input') values = [structuredClone(value)];
  else values = [structuredClone(value)];
  return {
    intent: intent === 'all_available' && definition?.type === 'multiple_select'
      ? 'all_available'
      : 'explicit',
    values,
  };
}

function dashboardSelectionState() {
  const form = $('#dashboard-selection-form');
  const values = formValues(form);
  const runtime = activeRuntime();
  const remembered = runtime?.selectionState || {};
  for (const input of form.elements) {
    const control = selectionControl(input.name);
    if (!control) continue;
    if (
      input instanceof HTMLSelectElement
      && input.options.length === 0
      && Object.prototype.hasOwnProperty.call(remembered, input.name)
    ) continue;
    const intent = input instanceof HTMLSelectElement && input.multiple
      ? (window.datavizComponents?.controls?.inferSelectionIntent?.(input) || 'explicit')
      : 'explicit';
    remembered[input.name] = selectionStateFromValue(control.definition, values[input.name], intent);
  }
  return remembered;
}

function captureDashboardSelectionIntent(event) {
  const input = event?.target;
  if (!(input instanceof HTMLSelectElement) || !input.multiple || !input.name) return;
  const intent = window.datavizComponents?.controls?.consumeSelectionIntent?.(input);
  const runtime = activeRuntime();
  const control = selectionControl(input.name);
  if (intent && runtime && control) {
    runtime.selectionState[input.name] = selectionStateFromValue(
      control.definition,
      formValues($('#dashboard-selection-form'))[input.name],
      intent,
    );
  }
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
    const previousState = runtime?.selectionState?.[control.key] || control.initial_state || {
      intent:'explicit', values:[],
    };
    const previous = selectionValueFromState(definition, previousState);
    const previousValues = input.multiple && Array.isArray(previous) ? previous : [previous];
    const typed = options.some(option => typeof option.value !== 'string');
    input.dataset.valueEncoding = typed ? 'json' : 'string';
    const encode = value => typed ? JSON.stringify(value) : String(value);
    const selectedValues = previousValues
      .filter(value => value != null && value !== '')
      .map(encode);
    const initialPolicy = definition?.initial || {
      mode:definition?.type === 'multiple_select' ? 'all' : 'first',
    };
    const initialValues = (
      initialPolicy.mode === 'values'
        ? initialPolicy.values || []
        : initialPolicy.mode === 'value'
          ? [initialPolicy.value]
          : []
    ).map(encode);
    const nodes = [];
    if (!input.multiple) {
      const empty = document.createElement('option');
      empty.value = '';
      empty.hidden = true;
      empty.dataset.emptyOption = 'true';
      nodes.push(empty);
    }
    for (const item of options) {
      const option = document.createElement('option');
      option.value = typed ? JSON.stringify(item.value) : String(item.value);
      option.textContent = item.label ?? String(item.value);
      option.disabled = item.available === false;
      if (item.group) option.dataset.group = item.group;
      if (item.description) option.dataset.description = item.description;
      if (item.keywords?.length) option.dataset.keywords = item.keywords.join(' ');
      nodes.push(option);
    }
    const reconciled = window.datavizComponents?.controls?.reconcileOptionDomain?.(
      input,
      nodes,
      {
        selectedValues,
        intent:previousState.intent,
        required:Boolean(definition?.required),
        initial:{mode:initialPolicy.mode, values:initialValues},
      },
    );
    if (!reconciled) input.replaceChildren(...nodes);
    input.dataset.runtimeOptionsSignature = signature;
    input._syncChoiceControl?.();
    synchronized = true;
    const current = formValues(form)[control.key];
    if (JSON.stringify(previous) !== JSON.stringify(current)) changed = true;
  }
  if (!synchronized) return;
  const runtime = activeRuntime();
  if (runtime) dashboardSelectionState();
  updateDashboardControlSummary();
  saveTabUiState();
  if (changed) scheduleViewSelections();
}

function nodeRow(node) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'node pipeline-signal';
  item.dataset.nodeId = node.id;
  item.dataset.status = 'not_run';
  item.setAttribute('aria-label', `${node.title}: not run`);
  item.innerHTML = `<span class="node-light" aria-hidden="true"></span><span class="pipeline-signal__tooltip" role="tooltip"><strong>${escapeHtml(node.title)}</strong></span>`;
  item.addEventListener('click', () => {
    item.blur();
    showNodeInspector(node);
  });
  return item;
}

function setNodeStatus(node, status) {
  if (!node) return;
  const labels = {
    not_run:'Not run', queued:'Queued', loading:'Running', ready:'Ready', empty:'Ready · empty',
    error:'Failed', cancelled:'Cancelled', unavailable:'Unavailable', stale:'Stale',
  };
  node.dataset.status = status || 'not_run';
  const label = labels[node.dataset.status] || node.dataset.status;
  const title = state.dashboard?.nodes?.find(item => item.id === node.dataset.nodeId)?.title || node.dataset.nodeId;
  node.setAttribute('aria-label', `${title}: ${label}`);
}

function selectDashboard(id, {historyMode = 'push', locationSearch = null} = {}) {
  if (state.dashboard) {
    const previous = activeRuntime();
    previous.queryParameterValues = queryParameters();
    previous.draftComputeParameters = computeParameters();
    dashboardSelectionState();
    try { previous.canvasScrollY = $('#canvas-frame').contentWindow.scrollY || 0; } catch (_) { previous.canvasScrollY = 0; }
    saveTabUiState();
  }
  closeHeaderPopovers();
  state.dashboard = state.payload.dashboards.find((item) => item.id === id);
  state.preferredDashboardId = id;
  const runtime = activeRuntime();
  document.querySelectorAll('.nav-button').forEach((node) => node.classList.toggle('active', node.dataset.id === id));
  const runnable = Boolean(state.dashboard.runnable);
  $('#parameter-form').replaceChildren(...state.dashboard.query_parameters.map(
    item => field(item, item.id, item.presentation || {}, {query: true}),
  ));
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
  const queryParameterCount = state.dashboard.query_parameters.length;
  const hasQueryParameters = queryParameterCount > 0;
  $('#query-run-control').dataset.empty = String(!hasQueryParameters);
  $('#query-parameters-control').dataset.empty = String(!hasQueryParameters);
  if (runtime.queryParametersOpen == null && hasQueryParameters) {
    runtime.queryParametersOpen = true;
  }
  setQueryParametersOpen(runtime.queryParametersOpen);
  for (const control of dataControls) {
    if (!Object.prototype.hasOwnProperty.call(runtime.selectionState, control.key)) {
      runtime.selectionState[control.key] = structuredClone(
        control.initial_state || {intent:'explicit', values:[]},
      );
    }
  }
  window.datavizComponents?.hydrate(document);
  if (locationSearch != null) {
    runtime.queryParameterValues = {
      ...queryParameters(),
      ...queryParameterValuesFromLocation(state.dashboard, locationSearch),
    };
  }
  setFormValues(
    $('#parameter-form'),
    runtime.queryParameterValues || runtime.committedQueryParameters || {},
  );
  // Freeze resolved relative defaults as concrete tab-local values on first
  // hydration. A full page reload in the same tab must restore these values
  // instead of silently re-evaluating `today` from a newer Workspace payload.
  if (runtime.queryParameterValues == null) {
    runtime.queryParameterValues = queryParameters();
  }
  setFormValues(
    $('#compute-parameter-form'),
    runtime.draftComputeParameters || runtime.committedComputeParameters || {},
  );
  setFormValues(
    $('#dashboard-selection-form'),
    Object.fromEntries(dataControls.map(control => [
      control.key,
      selectionValueFromState(control.definition, runtime.selectionState[control.key]),
    ])),
  );
  updateDashboardControlSummary();
  const queryNodes = (state.dashboard.nodes || []).filter(
    node => node.type === 'source' || node.type === 'dataset_transform',
  );
  $('#node-list').replaceChildren(...queryNodes.map(nodeRow));
  document.querySelectorAll('.node').forEach((node) => {
    setNodeStatus(node, runtime.nodeStatuses[node.dataset.nodeId] || 'not_run');
  });
  $('#query-diagnostics').dataset.status = runnable ? runtime.queryStatus : 'error';
  $('#query-diagnostics-label').textContent = runnable ? runtime.queryLabel : state.dashboard.status;
  $('#run-message').textContent = runnable ? runtime.message : (state.dashboard.message || 'Dashboard unavailable.');
  setQueryState();
  setSelectionsEnabled(Boolean(runtime.runId));
  setComputeState();
  loadCanvasFrame(id, runtime.pendingRunId || runtime.runId);
  $('#run-button').disabled = !runnable;
  $('#run-button').classList.toggle('is-cancelling', Boolean(runtime.pendingRunId));
  setRunButtonLabel(runtime.pendingRunId ? '取消' : '查询');
  setShareEnabled(Boolean(runtime.runId));
  saveTabUiState();
  syncDashboardLocation(historyMode);
}

function setFormValues(form, values) {
  for (const input of form.elements) {
    if (!input.name || !(input.name in values)) continue;
    const value = values[input.name];
    if (input.dataset.valueType === 'boolean' && input.tagName === 'SELECT') input.value = value == null ? '' : JSON.stringify(value);
    else if (input.dataset.valueType === 'boolean') input.checked = Boolean(value);
    else if (input.multiple) {
      const selected = new Set((Array.isArray(value) ? value : [value]).map(item => input.dataset.valueEncoding === 'json' ? JSON.stringify(item) : String(item)));
      for (const option of input.options) option.selected = selected.has(option.value);
    } else if (input.dataset.type === 'multiple_input' && Array.isArray(value)) input.value = JSON.stringify(value);
    else if (Array.isArray(value)) input.value = value.join(',');
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

function formInputDefinition(input) {
  const control = input.closest('.dv-control');
  const number = value => value === '' || value == null ? null : Number(value);
  return {
    type:input.dataset.type || control?.dataset.controlType || 'single_input',
    value_type:input.dataset.valueType || control?.dataset.valueType || 'text',
    required:Boolean(input.required),
    min:number(input.min),
    max:number(input.max),
    step:input.step && input.step !== 'any' ? Number(input.step) : null,
    min_date:input.type === 'date' ? (input.min || null) : (control?.dataset.minDate || null),
    max_date:input.type === 'date' ? (input.max || null) : (control?.dataset.maxDate || null),
    max_length:input.maxLength > 0 ? input.maxLength : null,
    max_items:number(control?.dataset.maxItems),
    allow_empty:[
      control?.dataset.allowEmptyStart === 'true',
      control?.dataset.allowEmptyEnd === 'true',
    ],
  };
}

function setFormInputError(input, message = '') {
  input.setCustomValidity?.(message);
  const output = input.closest('.dv-control')?.querySelector('[data-control-error]');
  if (output) {
    output.textContent = message;
    output.hidden = !message;
  }
}

function normalizeFormScalar(definition, raw, label = '值') {
  const value = editorTypedValue(definition, raw, label);
  if (['integer', 'number'].includes(definition.value_type)) {
    if (definition.min != null && value < definition.min) throw new Error(`${label}不能小于 ${definition.min}`);
    if (definition.max != null && value > definition.max) throw new Error(`${label}不能大于 ${definition.max}`);
    if (definition.step != null) {
      const base = definition.min || 0;
      const quotient = (value - base) / definition.step;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) {
        throw new Error(`${label}必须按步长 ${definition.step} 递增`);
      }
    }
  }
  if (definition.value_type === 'date') {
    if (definition.min_date && value < definition.min_date) throw new Error(`${label}不能早于 ${definition.min_date}`);
    if (definition.max_date && value > definition.max_date) throw new Error(`${label}不能晚于 ${definition.max_date}`);
  }
  return value;
}

function normalizeFormInput(input) {
  const decode = value => input.dataset.valueEncoding === 'json' ? JSON.parse(value) : value;
  const definition = formInputDefinition(input);
  const {type, value_type:valueType} = definition;
  if (valueType === 'boolean' && input.tagName === 'SELECT') {
    return input.value === '' ? null : decode(input.value);
  }
  if (valueType === 'boolean') return input.checked;
  if (input.multiple) return [...input.selectedOptions].map(item => decode(item.value));
  if (type === 'multiple_input') {
    let values;
    try { values = input.value ? JSON.parse(input.value) : []; }
    catch (_error) { values = input.value.split(',').map(item => item.trim()).filter(Boolean); }
    if (!Array.isArray(values)) throw new Error('请输入多个值');
    const normalized = values.map((item, index) => normalizeFormScalar(definition, item, `第 ${index + 1} 个值`));
    if (definition.required && !normalized.length) throw new Error('至少输入一个值');
    if (definition.max_items != null && normalized.length > definition.max_items) {
      throw new Error(`最多输入 ${definition.max_items} 个值`);
    }
    if (new Set(normalized.map(editorValueSignature)).size !== normalized.length) {
      throw new Error('不能输入重复值');
    }
    return normalized;
  }
  if (type === 'range_input') {
    const values = input.value ? input.value.split(',', 2).map(item => item.trim()) : [];
    if (!values.length) {
      if (definition.required) throw new Error('范围不能为空');
      return [];
    }
    if (values.length !== 2) throw new Error('范围必须包含开始值和结束值');
    const normalized = values.map((raw, index) => raw === '' ? '' : normalizeFormScalar(
      definition, raw, index ? '结束值' : '开始值',
    ));
    if (normalized[0] === '' && !definition.allow_empty[0]) throw new Error('开始值不能为空');
    if (normalized[1] === '' && !definition.allow_empty[1]) throw new Error('结束值不能为空');
    if (normalized[0] !== '' && normalized[1] !== '' && normalized[0] > normalized[1]) {
      throw new Error('开始值不能大于结束值');
    }
    return normalized;
  }
  if (input.tagName === 'SELECT') return input.value === '' ? null : decode(input.value);
  if (input.value === '') return null;
  return normalizeFormScalar(definition, input.value);
}

function selectionState() {
  dashboardSelectionState();
  const values = activeRuntime()?.selectionState || {};
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
    setFormInputError(input, '');
    if (!input.checkValidity()) {
      setFormInputError(input, input.validationMessage);
      throw new Error(`${input.name}: ${input.validationMessage}`);
    }
    try {
      values[input.name] = normalizeFormInput(input);
    } catch (error) {
      setFormInputError(input, error.message);
      throw new Error(`${input.name}: ${error.message}`);
    }
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
    setRunButtonLabel('取消中…');
    try {
      await request(`/api/runs/${encodeURIComponent(runId)}?${sessionQuery()}`, {method:'DELETE'});
      runtime.message = 'Cancelling this Dashboard query…';
      $('#run-message').textContent = runtime.message;
    } catch (error) {
      $('#run-button').disabled = false;
      setRunButtonLabel('取消');
      runtime.message = error.message;
      $('#run-message').textContent = error.message;
    }
    return;
  }
  if (!$('#parameter-form').checkValidity()) {
    setQueryParametersOpen(true, {persist: true});
    window.requestAnimationFrame(() => $('#parameter-form').reportValidity());
    return;
  }
  let requestedParameters;
  try { requestedParameters = queryParameters(); }
  catch (_error) {
    setQueryParametersOpen(true, {persist:true});
    window.requestAnimationFrame(() => $('#parameter-form').reportValidity());
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
    runtime.queryParameterValues = requestedParameters;
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
    setRunButtonLabel('取消');
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
      setRunButtonLabel('查询');
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
    setNodeStatus(node, runtime.nodeStatuses[event.node_id]);
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
    setRunButtonLabel('查询');
    setShareEnabled(Boolean(runtime.runId));
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
  let pending;
  try { pending = queryParameters(); }
  catch (_error) { return false; }
  const keys = new Set([...Object.keys(pending), ...Object.keys(state.committedQueryParameters)]);
  return [...keys].every((key) => JSON.stringify(normalized(pending[key])) === JSON.stringify(normalized(state.committedQueryParameters[key])));
}

function setQueryState(message = null) {
  const owner = $('#query-parameters-control');
  const runtime = activeRuntime();
  const hasQueryParameters = Boolean(state.dashboard?.query_parameters?.length);
  let stale = false;
  let detail = '';
  let label = 'Not applied';
  if (state.dashboard && !state.dashboard.runnable) {
    stale = true;
    detail = state.dashboard.message || 'Dashboard unavailable.';
    label = state.dashboard.status;
  } else if (runtime?.queryDefinitionStale) {
    stale = true;
    detail = message || 'Dashboard query definition changed. Run query again to apply it.';
    label = 'Outdated';
  } else if (message) {
    stale = Boolean(state.runId);
    detail = message;
    label = 'Check values';
  } else if (!hasQueryParameters) {
    detail = state.runId ? 'Dataset loaded.' : 'This dashboard has no query parameters.';
    label = 'No parameters';
  } else if (!state.runId) {
    detail = 'No dataset loaded. Query parameters are pending.';
  } else if (pendingParametersMatchDataset()) {
    detail = 'Dataset loaded with these values.';
    label = 'Applied';
  } else {
    stale = true;
    detail = 'Pending query values differ from the loaded dataset. Query again to apply.';
    label = 'Changed';
  }
  owner.dataset.stale = String(stale);
  owner.title = detail;
  $('#query-control-meta').textContent = label;
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

function applyViewSelections({full = false} = {}) {
  if (!state.runId && !state.pendingRunId) return;
  dashboardSelectionState();
  const runtime = activeRuntime();
  const dashboardKeys = new Set(
    dashboardControls('selection').map(control => control.key),
  );
  const selectionPatch = Object.fromEntries(
    Object.entries(runtime?.selectionState || {}).filter(([key]) => dashboardKeys.has(key)),
  );
  postCanvasMessage({
    type:'dataviz:set-selections',
    // After bootstrap the Header owns Dashboard Controls only. Sending its
    // asynchronous full shadow would overwrite newer Section/View writes made
    // inside the Canvas. The Canvas merges this owner-scoped patch, reconciles
    // downstream domains, then returns one complete canonical snapshot.
    selection_state:full ? selectionState() : selectionPatch,
    selection_epoch:runtime?.selectionEpoch || 0,
  });
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

function bindOverflowTitle(owner, label, fullName) {
  const update = () => {
    const truncated = label.scrollWidth > label.clientWidth + 1;
    if (truncated) owner.title = fullName;
    else owner.removeAttribute('title');
  };
  owner.setAttribute('aria-label', fullName);
  owner.addEventListener('mouseenter', update);
  owner.addEventListener('focus', update);
  window.requestAnimationFrame(update);
}

function dashboardButton(dashboard) {
    const button = document.createElement('a');
    button.className = 'nav-button';
    button.href = dashboardLocation(dashboard.id, runtimeFor(dashboard.id).queryParameterValues || {});
    button.dataset.id = dashboard.id;
    button.dataset.navType = 'dashboard';
    button.dataset.status = dashboard.status;
    button.dataset.parentId = dashboard.parent_id || '';
    button.draggable = true;
    const status = dashboard.status === 'ready' ? '' : `<small>${escapeHtml(dashboard.status)}</small>`;
    button.innerHTML = `<strong>${escapeHtml(dashboard.canvas_name)}</strong>${status}`;
    bindOverflowTitle(button, button.querySelector('strong'), dashboard.canvas_name);
    button.addEventListener('click', (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      selectDashboard(dashboard.id, {historyMode:'push'});
    });
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
      bindOverflowTitle(toggle, toggle.querySelector('strong'), folder.title);
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
  const label = node.querySelector('strong');
  bindOverflowTitle(label, label, item.title);
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
  const trash = $('#nav-trash');
  const summary = trash.querySelector('summary');
  const count = $('#nav-trash-count');
  count.textContent = records.length;
  count.hidden = records.length === 0;
  trash.dataset.empty = records.length === 0 ? 'true' : 'false';
  summary.setAttribute('aria-disabled', records.length === 0 ? 'true' : 'false');
  if (!records.length) trash.open = false;
  const list = records.map((record) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'nav-trash-record';
    wrapper.dataset.navType = 'trash';
    wrapper.dataset.trashId = record.trash_id;
    wrapper.title = '右键恢复到原逻辑位置';
    wrapper.append(trashNode(record.item));
    return wrapper;
  });
  $('#nav-trash-list').replaceChildren(...list);
}

async function refreshNavigation(
  preferredPath = state.dashboard?.path,
  {
    reloadCanvas = true,
    requestedDashboardId = null,
    locationSearch = null,
    historyMode = 'replace',
  } = {},
) {
  const activeId = state.dashboard?.id || null;
  state.payload = await request('/api/workspace');
  state.workspaceRevision = Math.max(
    state.workspaceRevision,
    Number(state.payload.hot_reload?.revision || 0),
  );
  state.hotReloadEnabled = Boolean(state.payload.hot_reload?.enabled);
  const routed = state.payload.dashboards.find((item) => item.id === requestedDashboardId);
  const preferred = state.payload.dashboards.find((item) => item.path === preferredPath);
  const remembered = state.payload.dashboards.find((item) => item.id === state.preferredDashboardId);
  const fallback = state.payload.dashboards.find((item) => item.runnable) || state.payload.dashboards[0];
  const selected = routed || preferred || remembered || fallback;
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
  selectDashboard(selected.id, {
    historyMode,
    locationSearch: routed ? locationSearch : null,
  });
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
    actions.push(['×', '永久删除…', () => openPurgeTrashDialog(trashId)]);
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
    eyebrow: 'NAVIGATION / REMOVE', title: `删除「${folder.title}」？`, submitLabel: '继续', danger: true,
    body: '<p class="nav-dialog__note">若该目录树没有看板，将直接删除；否则所属看板会移入回收站，文件仍可恢复。</p>',
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

function openPurgeTrashDialog(trashId) {
  const record = (state.payload.trash || []).find(item => item.trash_id === trashId);
  const title = record?.item?.title || '该项目';
  showNavDialog({
    eyebrow: 'TRASH / DELETE FOREVER',
    title: `永久删除「${title}」？`,
    submitLabel: '永久删除',
    danger: true,
    body: '<p class="nav-dialog__note">这会删除磁盘中的看板目录及其文件，操作无法恢复。</p>',
    onSubmit: async () => {
      await request(`/api/navigation/trash/${encodeURIComponent(trashId)}`, {method:'DELETE'});
      await refreshNavigation(null);
    },
  });
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
  const requestedDashboardId = dashboardIdFromLocation();
  await refreshNavigation(null, {
    requestedDashboardId,
    locationSearch: requestedDashboardId ? window.location.search : null,
    historyMode:'replace',
  });
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
$('#query-parameters-toggle').addEventListener('click', toggleQueryParameters);
$('#download-button').addEventListener('click', downloadReport);
$('#copy-share-link').addEventListener('click', createSharedLink);
$('#dashboard-reload').addEventListener('click', reloadDashboardFromDisk);
$('#workspace-update-dismiss').addEventListener('click', hideWorkspaceUpdate);
$('#workspace-update-action').addEventListener('click', () => {
  if ($('#workspace-update-action').dataset.action === 'query') runDashboard();
  else reloadDashboardFromDisk();
});
const onQueryDraft = event => {
  event.target?.setCustomValidity?.('');
  let values;
  try { values = queryParameters(); }
  catch (_error) {
    setQueryState();
    return;
  }
  if (activeRuntime()) activeRuntime().queryParameterValues = values;
  saveTabUiState();
  syncDashboardLocation('replace');
  setQueryState();
  syncCanvasQueryDraft();
};
$('#parameter-form').addEventListener('input', onQueryDraft);
$('#parameter-form').addEventListener('change', onQueryDraft);
const onDashboardSelectionDraft = event => {
  if (activeRuntime()) activeRuntime().selectionEpoch += 1;
  captureDashboardSelectionIntent(event);
  try { dashboardSelectionState(); }
  catch (_error) { return; }
  saveTabUiState();
  updateDashboardControlSummary();
  scheduleViewSelections();
};
$('#dashboard-selection-form').addEventListener('input', onDashboardSelectionDraft);
const onComputeDraft = (event) => {
  const runtime = activeRuntime();
  if (!runtime) return;
  try { runtime.draftComputeParameters = computeParameters(); }
  catch (_error) { return; }
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
$('#dashboard-selection-form').addEventListener('change', onDashboardSelectionDraft);
document.addEventListener('click', (event) => {
  if (!event.target.closest('#nav-context-menu')) hideNavMenu();
});
window.addEventListener('message', (event) => {
  if (!isCurrentCanvasMessage(event)) return;
  if (event.data?.type === 'dataviz:canvas-ready') {
    const runtime = activeRuntime();
    const frame = $('#canvas-frame');
    if (!runtime) return;
    // Fresh Canvas defaults seed missing keys; remembered tab-local canonical
    // state wins on reload. Invalid/removed keys are filtered before sending.
    runtime.selectionState = {
      ...(event.data.selection_state || {}),
      ...(runtime.selectionState || {}),
    };
    frame.dataset.runtimeReady = 'true';
    saveTabUiState();
    applyViewSelections({full:true});
    const values = runtime.committedComputeParameters
      || runtime.draftComputeParameters
      || computeParameters();
    sendCompute(values, {commit:true});
    syncCanvasInteraction();
    syncCanvasQueryDraft();
    return;
  }
  if (event.data?.type === 'dataviz:canvas-interaction') {
    closeHeaderPopovers();
    return;
  }
  if (event.data?.type === 'dataviz:keyboard-shortcut') {
    executeKeyboardShortcut(String(event.data.command || ''));
    return;
  }
  if (event.data?.type === 'dataviz:open-parameter-editor') {
    openParameterEditor(String(event.data.owner || '')).catch(error => {
      console.error('[dataviz:parameter-editor]', error);
    });
    return;
  }
  if (event.data?.type === 'dataviz:view-pipeline-inspect') {
    const nodeId = String(event.data.node_id || '');
    const node = (state.dashboard?.nodes || []).find(item => item.id === nodeId);
    if (node) showNodeInspector(node);
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
  if (event.data?.type === 'dataviz:control-impact-changed') {
    syncDashboardControlImpacts(event.data.controls || []);
    return;
  }
  if (event.data?.type === 'dataviz:selections-changed') {
    const runtime = activeRuntime();
    // A Canvas event created before a newer parent-owned Dashboard Control
    // change must not restore the old full snapshot when its postMessage task
    // arrives late. The parent epoch advances only for parent-origin writes;
    // child View/Control actions remain serial within the current epoch.
    if (
      !runtime
      || Number(event.data.selection_epoch || 0) !== Number(runtime.selectionEpoch || 0)
    ) return;
    // Canvas messages contain the complete canonical state. Replacing it also
    // removes keys restored from sessionStorage after a Selection is renamed.
    state.selectionState = {...(event.data.selection_state || {})};
    runtime.selectionState = state.selectionState;
    const controls = dashboardControls('selection');
    setFormValues(
      $('#dashboard-selection-form'),
      Object.fromEntries(controls.map(control => [
        control.key,
        selectionValueFromState(control.definition, state.selectionState[control.key]),
      ])),
    );
    for (const input of $('#dashboard-selection-form').elements) {
      input._syncChoiceControl?.();
    }
    updateDashboardControlSummary();
    saveTabUiState();
  }
});
$('#sidebar-toggle').addEventListener('click', toggleSidebar);
document.addEventListener('keydown', handleKeyboardShortcut);
$('#run-button').addEventListener('contextmenu', event => {
  event.preventDefault();
  openParameterEditor('query').catch(error => console.error('[dataviz:parameter-editor]', error));
});
$('#dashboard-controls-control > summary').addEventListener('contextmenu', event => {
  event.preventDefault();
  openParameterEditor('dashboard').catch(error => console.error('[dataviz:parameter-editor]', error));
});
initializeSidebarResize();
window.addEventListener('resize', () => applySidebarState());
window.addEventListener('popstate', () => {
  if (!state.payload) return;
  const dashboardId = dashboardIdFromLocation();
  const dashboard = state.payload.dashboards.find(item => item.id === dashboardId);
  if (!dashboard) return;
  selectDashboard(dashboard.id, {
    historyMode:'none',
    locationSearch:window.location.search,
  });
});
$('#dashboard-nav').addEventListener('contextmenu', (event) => {
  const target = event.target.closest('[data-nav-type]');
  showNavMenu(event, target);
});
$('#nav-trash-list').addEventListener('contextmenu', (event) => {
  const target = event.target.closest('[data-nav-type="trash"]');
  if (target) showNavMenu(event, target);
});
$('#nav-trash > summary').addEventListener('click', (event) => {
  if ($('#nav-trash').dataset.empty !== 'true') return;
  event.preventDefault();
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
