"""Scheduler boundaries run in Node, with controllable adapter promises."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('phase', ['prepare', 'execute'])
def test_dispose_during_transform_does_not_start_or_cache_late_work(phase):
    script = r'''
const fs = require('node:fs');
const assert = require('node:assert/strict');
global.window = {dataviz:{}};
global.datavizRuntime = {};
global.datavizCacheClone = structuredClone;
eval(fs.readFileSync('src/dataviz/server/runtime_src/30-interactive-scheduler.js', 'utf8'));
eval(fs.readFileSync('src/dataviz/server/runtime_src/60-renderer-disposal.js', 'utf8'));
(async () => {
  const phase = process.argv[1];
  let release, entered, executions = 0;
  const gate = new Promise(resolve => { release = resolve; });
  const started = new Promise(resolve => { entered = resolve; });
  const runtime = Object.assign(global.datavizRuntime, {
    transformCacheKey:() => 'key', transformCacheEvidence:new Map(),
    interactionCache:new Map(), inflightTransforms:new Map(), interactionCacheLimit:10,
    activeTransforms:new Map(), workerUrls:new Map(), controlImpactSignatures:new Map(),
    metrics:{interactiveTransforms:{cacheMisses:0, cacheHits:0, cacheEvictions:0}},
    interactiveAdapters:{probe:{validate() {}, dispose() {},
      async prepare() { if (phase === 'prepare') { entered(); await gate; } return {}; },
      async execute() { executions++; if (phase === 'execute') { entered(); await gate; } return {main:[]}; }
    }}
  });
  const work = runtime.executeTransform('probe', {spec:{runtime:'probe'}}, {}, 1, {});
  await started;
  runtime.dispose();
  release();
  await work.catch(() => {});
  assert.equal(executions, phase === 'prepare' ? 0 : 1, 'no execution after disposal');
  assert.equal(runtime.interactionCache.size, 0, 'disposed cache stays empty');
  assert.equal(runtime.transformCacheEvidence.size, 0, 'no late cache evidence');
  assert.equal(runtime.inflightTransforms.size, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script, phase], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('operation', ['publishOutputs', 'failOutputs'])
def test_output_notifications_stop_after_disposal(operation):
    script = r'''
const fs = require('node:fs');
const assert = require('node:assert/strict');
let notifications = 0, release, entered;
global.window = {dataviz:{}, dispatchEvent() { notifications++; }};
global.datavizRuntime = {};
global.canonicalOutputReference = value => value;
global.refreshControlOptionDomains = () => {};
global.CustomEvent = class {};
global.datavizControlChannel = {phase:'ready'};
global.datavizPublishControlSnapshot = () => { notifications++; };
eval(fs.readFileSync('src/dataviz/server/runtime_src/40-renderer-lifecycle.js', 'utf8'));
(async () => {
  const started = new Promise(resolve => { entered = resolve; });
  let mutations = 0;
  const runtime = Object.assign(global.datavizRuntime, {
    outputErrors:new Map(), commitOutput() { mutations++; return true; },
    removeOutput() { mutations++; }, affectedViews:() => [], renderViews() {},
    publishControlImpacts() { notifications++; },
    runTransforms:() => new Promise(resolve => { release = () => resolve(new Set()); entered(); })
  });
  const call = () => process.argv[1] === 'publishOutputs'
    ? runtime.publishOutputs({outputs:{'source:probe/main':[]}})
    : runtime.failOutputs(['source:probe/main'], new Error('failed'));
  const first = call();
  await started;
  runtime.disposed = true;
  release();
  await first;
  assert.equal(notifications, 0, 'no late notifications or snapshots');
  const before = mutations;
  await call();
  assert.equal(mutations, before, 'no output changes after disposal');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script, operation], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
