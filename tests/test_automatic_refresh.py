"""Deterministic lifecycle tests for the real automatic scheduling functions."""
from pathlib import Path
import subprocess


def test_hidden_during_debounce_retains_one_latest_refresh():
    script = r'''
const fs = require('node:fs'), assert = require('node:assert/strict');
const source = fs.readFileSync('src/dataviz/server/static/app.js', 'utf8');
const runtime = {queryDomainReady:true};
const state = {payload:{standalone_execution:{mode:'auto', auto_allowed:true}}, dashboard:{runnable:true}};
const activeRuntime = () => runtime;
const listeners = {}, timers = new Map();
let serial = 0;
const setTimeout = callback => { timers.set(++serial, callback); return serial; };
const clearTimeout = id => timers.delete(id);
const document = {hidden:false, addEventListener:(name, callback) => { listeners[name] = callback; }};
const $ = () => ({checkValidity:() => true});
const setQueryState = () => {};
const submitted = [];
const runDashboard = options => submitted.push(options);
const body = source.slice(source.indexOf('function automaticExecution()'), source.indexOf('function updateSourceFreshness('));
eval(body + '; global.scheduleAutomaticRun = scheduleAutomaticRun;');
function fire() { const [id, callback] = timers.entries().next().value; timers.delete(id); callback(); }
scheduleAutomaticRun({refresh:true});
document.hidden = true;
listeners.visibilitychange();
fire();
assert.equal(submitted.length, 0);
assert.equal(runtime.autoRunQueued, true);
document.hidden = false;
listeners.visibilitychange();
fire();
assert.deepEqual(submitted, [{automatic:true, refresh:true}]);
assert.equal(runtime.autoRunQueued, false);
'''
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
