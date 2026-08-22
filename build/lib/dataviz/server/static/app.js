const state = { payload: null, dashboard: null, runId: null, eventSource: null, nodeErrors: {} };
const $ = (selector) => document.querySelector(selector);

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  return response.json();
}

function field(parameter, name = parameter.id) {
  const wrapper = document.createElement('div');
  wrapper.className = 'field';
  const label = document.createElement('label');
  const inputId = `input-${name.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  label.htmlFor = inputId;
  label.textContent = parameter.label || parameter.id;
  let input;
  if (['single_select', 'multi_select'].includes(parameter.type)) {
    input = document.createElement('select');
    if (parameter.type === 'multi_select') input.multiple = true;
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
  return wrapper;
}

function filterField(control) {
  const wrapper = document.createElement('div');
  wrapper.className = 'filter-scope';
  wrapper.dataset.origin = control.origin;
  const scopeNames = {dashboard: 'All views', section: `Section · ${control.owner_id}`, view: `View · ${control.owner_id}`};
  wrapper.innerHTML = `<div class="filter-scope__meta"><span>${escapeHtml(scopeNames[control.origin])}</span><span>${control.affected_views.length} view${control.affected_views.length === 1 ? '' : 's'}</span></div>`;
  wrapper.append(field(control.definition, control.key));
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
  state.dashboard = state.payload.dashboards.find((item) => item.id === id);
  state.runId = null;
  state.nodeErrors = {};
  document.querySelectorAll('.nav-button').forEach((node) => node.classList.toggle('active', node.dataset.id === id));
  $('#dashboard-title').textContent = state.dashboard.title;
  $('#parameter-form').replaceChildren(...state.dashboard.query_parameters.map((item) => field(item)));
  $('#filter-form').replaceChildren(...state.dashboard.filters.map(filterField));
  $('#node-list').replaceChildren(...state.dashboard.nodes.map(nodeRow));
  $('#run-message').textContent = 'Ready to execute.';
  $('#canvas-status').textContent = 'Waiting for execution';
  $('#canvas-frame').src = `/api/dashboards/${encodeURIComponent(id)}/canvas`;
  $('#run-button').disabled = false;
  $('#download-button').disabled = true;
}

function parameters() {
  return formValues($('#parameter-form'));
}

function filters() {
  return formValues($('#filter-form'));
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
  if (state.eventSource) state.eventSource.close();
  $('#run-button').disabled = true;
  $('#download-button').disabled = true;
  $('#run-message').textContent = 'Submitting execution plan…';
  document.querySelectorAll('.node').forEach((node) => node.dataset.status = 'not_run');
  try {
    const response = await request(`/api/dashboards/${encodeURIComponent(state.dashboard.id)}/runs`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({parameters: parameters(), filters: filters()})
    });
    state.runId = response.run_id;
    listen(response.run_id);
  } catch (error) {
    $('#run-message').textContent = error.message;
    $('#run-button').disabled = false;
  }
}

function listen(runId) {
  const source = new EventSource(`/api/runs/${runId}/events`);
  state.eventSource = source;
  const names = ['node_queued','node_started','node_succeeded','node_failed','node_blocked'];
  for (const name of names) source.addEventListener(name, (message) => updateEvent(JSON.parse(message.data)));
  source.addEventListener('run_ready', (message) => finishRun(JSON.parse(message.data)));
  source.addEventListener('run_failed', (message) => finishRun(JSON.parse(message.data)));
  source.addEventListener('stream_end', () => source.close());
  source.onerror = () => { if (source.readyState === EventSource.CLOSED) return; };
}

function updateEvent(event) {
  const statusMap = {node_queued:'queued', node_started:'running', node_succeeded:'succeeded', node_failed:'failed', node_blocked:'blocked'};
  const node = document.querySelector(`[data-node-id="${CSS.escape(event.node_id)}"]`);
  if (node) node.dataset.status = statusMap[event.event] || 'not_run';
  if (event.error) state.nodeErrors[event.node_id] = event.error;
  const label = event.node_id ? event.node_id.replace(':', ' · ') : 'run';
  $('#run-message').textContent = `${label} — ${statusMap[event.event] || event.event}${event.duration_ms ? ` · ${event.duration_ms}ms` : ''}`;
}

async function finishRun(event) {
  const record = await request(`/api/runs/${state.runId}`);
  const status = record.result?.status || record.status;
  $('#canvas-status').textContent = `Run ${status} · ${state.runId}`;
  $('#run-message').textContent = status === 'success' ? 'All required nodes completed.' : `Run finished with status: ${status}`;
  $('#run-button').disabled = false;
  $('#download-button').disabled = !record.result;
  if (record.result) $('#canvas-frame').src = `/api/dashboards/${encodeURIComponent(state.dashboard.id)}/canvas?run_id=${state.runId}`;
}

function showNodeError(nodeId, title) {
  const error = state.nodeErrors[nodeId];
  if (!error) return;
  $('#error-title').textContent = title;
  $('#error-content').textContent = JSON.stringify(error, null, 2);
  $('#error-dialog').showModal();
}

function escapeHtml(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML; }

async function boot() {
  state.payload = await request('/api/workspace');
  $('#workspace-title').textContent = state.payload.workspace.title;
  $('#workspace-description').textContent = state.payload.workspace.description || 'Workspace-first analysis';
  const buttons = state.payload.dashboards.map((dashboard, index) => {
    const button = document.createElement('button');
    button.className = 'nav-button';
    button.dataset.id = dashboard.id;
    button.innerHTML = `<strong>${escapeHtml(dashboard.title)}</strong><small>${String(index + 1).padStart(2,'0')} · ${dashboard.nodes.length} nodes</small>`;
    button.addEventListener('click', () => selectDashboard(dashboard.id));
    return button;
  });
  $('#dashboard-nav').replaceChildren(...buttons);
  if (state.payload.dashboards.length) selectDashboard(state.payload.dashboards[0].id);
}

$('#run-button').addEventListener('click', runDashboard);
$('#download-button').addEventListener('click', () => {
  if (state.runId) window.location.href = `/api/dashboards/${encodeURIComponent(state.dashboard.id)}/report?run_id=${state.runId}`;
});
$('#refresh-frame').addEventListener('click', () => { $('#canvas-frame').src = $('#canvas-frame').src; });
boot().catch((error) => { document.body.innerHTML = `<pre>${escapeHtml(error.stack || error.message)}</pre>`; });
