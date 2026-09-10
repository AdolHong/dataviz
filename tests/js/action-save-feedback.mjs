import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const scenario = process.argv[2];
const source = fs.readFileSync(new URL('../../src/dataviz/server/static/app.js', import.meta.url), 'utf8');
const code = source.slice(source.indexOf('async function handleServerActionMessage('), source.indexOf('\nfunction saveTabUiState()'));
const events = [];
const identity = {dashboard_id:'demo', run_id:'run1', frame_id:'frame1'};
const runtime = {runId:'run1'};
let ticks = 0;
let polls = 0;
const ready = {status:'succeeded', request_id:'save1', refresh:{status:'ready', run_id:'run1', views:['detail']}};
const context = {
  performance:{now:() => ++ticks}, Date, console, setTimeout:fn => fn(),
  state:{dashboard:{id:'demo', server_actions:['save']}, sessionId:'session'},
  activeRuntime:() => runtime, canvasIdentity:() => identity,
  sameCanvasIdentity:(a,b) => JSON.stringify(a) === JSON.stringify(b),
  sessionQuery:() => 'session_id=session',
  window:{location:{origin:'http://localhost'}},
  request:async (url, options) => {
    if (url.startsWith('/api/runs/')) return {result:{outputs:{}}};
    if (scenario === 'refresh_failure') return {...ready, refresh:{status:'failed'}};
    if (options && scenario === 'pending') return {...ready, refresh:{status:'running'}};
    if (!options) polls++;
    return ready;
  },
  $:() => ({contentWindow:{datavizRuntime:{applyActionRefresh:async () => {
    assert.ok(events.some(event => event.type === 'dataviz:server-action-progress' && event.receipt.status === 'succeeded'));
    if (scenario === 'transport_failure') throw new Error('transport failed');
    return {applied:true, timings:{data_prepare_ms:2, runtime_update_ms:3}};
  }}}}),
};
vm.createContext(context);
vm.runInContext(code, context);
await context.handleServerActionMessage({operation:'invoke', action:'save', request_id:'save1', bridge_id:'bridge'}, {
  postMessage:message => events.push(structuredClone(message)),
});
const result = events.at(-1);
assert.equal(result.type, 'dataviz:server-action-result');
assert.equal(result.receipt.status, 'succeeded');
assert.ok(result.receipt.client_timings.write_confirmed_ms >= 0);
assert.ok(result.receipt.client_timings.total_ms >= result.receipt.client_timings.write_confirmed_ms);
assert.equal(runtime.pendingServerAction, null);
if (scenario === 'transport_failure') {
  assert.equal(result.receipt.client_refresh.status, 'failed');
  assert.ok(result.error);
} else if (scenario === 'refresh_failure') assert.equal(result.receipt.refresh.status, 'failed');
else assert.equal(result.receipt.client_timings.runtime_update_ms, 3);
if (scenario === 'pending') assert.equal(polls, 1);
console.log(JSON.stringify({scenario}));
