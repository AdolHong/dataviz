import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {randomUUID} from 'node:crypto';

const source = fs.readFileSync(new URL('../../src/dataviz/server/runtime_src/85-server-actions.js', import.meta.url), 'utf8');
const listeners = {};
const sent = [];
const parent = {};
const window = {parent, location:{origin:'test'}, dataviz:{run_id:'one', server_actions:['save']},
  addEventListener:(name, fn) => { listeners[name] = fn; }};
const context = {window, crypto:{randomUUID}, console, TextEncoder, setTimeout, clearTimeout,
  datavizRuntime:{disposed:false}, datavizSameFrameIdentity:() => true,
  datavizPostToParent:message => sent.push(message)};
vm.createContext(context);
vm.runInContext(source.slice(0, source.indexOf('\nObject.assign(datavizRuntime')), context);
const actions = window.dataviz.serverActions;
const tick = () => new Promise(resolve => setImmediate(resolve));
const respond = (message, error = null, receipt = error ? null : {status:'succeeded'}) => listeners.message({origin:'test', source:parent,
  data:{type:'dataviz:server-action-result', bridge_id:message.bridge_id,
    receipt, error}});
const progress = [];
const payload = {id:'B'};
const first = actions.invoke('save', {id:'A'});
const second = actions.invoke('save', payload, {onProgress:r => progress.push(r)});
payload.id = 'WRONG';
assert.equal(sent.length, 1);
assert.equal(progress[0].status, 'queued');
// Status bypasses the queue.
const status = actions.status('save', sent[0].request_id);
assert.equal(sent.length, 2);
respond(sent[1]); await status;
respond(sent[0]); await first; await tick();
assert.equal(sent[2].payload.id, 'B');
assert.notEqual(sent[0].request_id, sent[2].request_id);
respond(sent[2]); await second;

const active = actions.invoke('save', {});
const stale = actions.invoke('save', {}).catch(e => e.code);
window.dataviz.run_id = 'new-query';
respond(sent.at(-1)); await active;
assert.equal(await stale, 'action_not_submitted');

const unknown = actions.invoke('save', {}).catch(e => e.code);
const unsent = actions.invoke('save', {}).catch(e => e.code);
const count = sent.length;
respond(sent.at(-1), {code:'action_response_unknown', message:'lost response'});
assert.equal(await unknown, 'action_response_unknown');
assert.equal(await unsent, 'action_not_submitted');
assert.equal(sent.length, count);

// A definitive rejected write does not block independent rows.
const conflict = actions.invoke('save', {}).catch(e => e.code);
const independent = actions.invoke('save', {id:'independent'});
respond(sent.at(-1), {code:'revision_conflict', message:'stale revision'}, {status:'failed'});
assert.equal(await conflict, 'revision_conflict');
await tick();
assert.equal(sent.at(-1).payload.id, 'independent');
respond(sent.at(-1)); await independent;

const saved = actions.invoke('save', {});
const needsSync = actions.invoke('save', {}).catch(e => e.code);
respond(sent.at(-1), null, {status:'succeeded', refresh:{status:'failed'}});
assert.equal((await saved).status, 'succeeded');
assert.equal(await needsSync, 'action_not_submitted');

const blocker = actions.invoke('save', {}).catch(e => e.code);
const waiting = Array.from({length:50}, () => actions.invoke('save', {}).catch(e => e.code));
assert.equal(await actions.invoke('save', {}).catch(e => e.code), 'action_not_submitted');
actions.dispose();
await blocker;
assert.ok((await Promise.all(waiting)).every(code => code === 'action_not_submitted'));
await tick();

const closing = actions.invoke('save', {}).catch(e => e.code);
const queued = actions.invoke('save', {}).catch(e => e.code);
actions.dispose();
assert.equal(await closing, 'action_response_unknown');
assert.equal(await queued, 'action_not_submitted');
console.log('queue checks passed');
