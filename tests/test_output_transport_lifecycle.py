"""Deterministic transport and initialization races against the real store."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('phase', ['download', 'publish'])
def test_current_transport_errors_propagate_and_release_pending_value(phase):
    script = r'''
const fs = require('node:fs'), assert = require('node:assert/strict');
global.window = {dataviz:{portable:{outputs:{}, output_transports:{}}}};
global.datavizRuntime = {};
global.canonicalOutputReference = value => value;
global.datavizValueSignature = JSON.stringify;
global.datavizRuntimeError = value => value;
const failure = new Error('current failure');
global.datavizLoadTransport = async () => { if (process.argv[1] === 'download') throw failure; return ['value']; };
eval(fs.readFileSync('src/dataviz/server/runtime_src/50-output-store.js', 'utf8'));
(async () => {
  let failures = 0;
  const runtime = Object.assign(datavizRuntime, {
    outputSignatures:new Map(), outputErrors:new Map(), transportPromises:new Map(),
    metrics:{transports:{started:0, completed:0, failed:0, arrowRows:0, arrowBytes:0, totalMs:0}},
    async publishOutputs(bundle) {
      for (const [key, value] of Object.entries(bundle.outputs)) this.commitOutput(key, value);
      throw failure;
    },
    async failOutputs() { failures++; }
  });
  runtime.registerOutputTransport('source:labels/main', {url:'current'});
  await assert.rejects(runtime.hydrateOutput('source:labels/main'), error => error === failure);
  assert.equal(runtime.transportPromises.size, 0);
  assert.equal(failures, process.argv[1] === 'download' ? 1 : 0, 'publication failures are not download failures');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script, phase], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('change', ['remove', 'replace', 'commit', 'dispose'])
@pytest.mark.parametrize('outcome', ['resolve', 'reject'])
def test_old_transport_cannot_restore_removed_or_replace_new_output(change, outcome):
    script = r'''
const fs = require('node:fs'), assert = require('node:assert/strict');
global.window = {dataviz:{portable:{outputs:{}, output_transports:{}}}};
global.datavizRuntime = {};
global.canonicalOutputReference = value => value;
global.datavizValueSignature = JSON.stringify;
global.datavizRuntimeError = value => value;
const gates = [];
global.datavizLoadTransport = () => new Promise((resolve, reject) => gates.push({resolve, reject}));
eval(fs.readFileSync('src/dataviz/server/runtime_src/50-output-store.js', 'utf8'));
(async () => {
  let failures = 0;
  const runtime = Object.assign(datavizRuntime, {
    outputSignatures:new Map(), outputErrors:new Map(), transportPromises:new Map(),
    metrics:{transports:{started:0, completed:0, failed:0, arrowRows:0, arrowBytes:0, totalMs:0}},
    async publishOutputs(bundle) { for (const [key, value] of Object.entries(bundle.outputs)) this.commitOutput(key, value); },
    async failOutputs() { failures++; }
  });
  const key = 'source:labels/main', change = process.argv[1];
  runtime.registerOutputTransport(key, {url:'old'});
  const old = runtime.hydrateOutput(key).catch(() => {});
  let next;
  if (change === 'remove') runtime.removeOutput(key);
  if (change === 'commit') runtime.commitOutput(key, ['saved']);
  if (change === 'dispose') runtime.disposed = true;
  if (change === 'replace') {
    runtime.registerOutputTransport(key, {url:'new'});
    next = runtime.hydrateOutput(key);
    assert.equal(gates.length, 2, 'replacement starts its own transport');
  }
  gates[0][process.argv[2] === 'resolve' ? 'resolve' : 'reject'](process.argv[2] === 'resolve' ? ['stale'] : new Error('old failed'));
  await old;
  assert.equal(failures, 0, 'obsolete failures never mark the current output failed');
  assert.deepEqual(window.dataviz.portable.outputs[key], change === 'commit' ? ['saved'] : undefined);
  if (next) {
    assert.equal(runtime.transportPromises.get(key), next, 'old settlement must not clear new work');
    gates[1].resolve(['new']);
    await next;
    assert.deepEqual(window.dataviz.portable.outputs[key], ['new']);
  }
  assert.equal(runtime.transportPromises.size, 0, 'settled transport promises release retained values');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script, change, outcome], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('phase', ['restore', 'hydrate', 'apply'])
def test_disposed_initialization_does_not_reconcile_or_announce_ready(phase):
    script = r'''
const fs = require('node:fs'), assert = require('node:assert/strict');
let release, entered, effects = [];
const gate = new Promise(resolve => { release = resolve; });
const started = new Promise(resolve => { entered = resolve; });
const step = async name => { effects.push(name); if (name === process.argv[1]) { entered(); await gate; } };
global.window = {dataviz:{applyControls:() => step('apply')}};
global.datavizRuntime = {};
global.datavizAwaitControlRestore = () => step('restore');
global.refreshControlOptionDomains = () => effects.push('domains');
global.datavizMarkControlReady = () => effects.push('ready');
global.datavizPostToParent = () => effects.push('message');
eval(fs.readFileSync('src/dataviz/server/runtime_src/50-output-store.js', 'utf8'));
(async () => {
  datavizRuntime.hydrateOutputTransports = () => step('hydrate');
  const pending = datavizRuntime.initializePortable();
  await started;
  const before = [...effects];
  datavizRuntime.disposed = true;
  release();
  await pending;
  assert.deepEqual(effects, before, 'no initialization effects after disposal');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script, phase], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
