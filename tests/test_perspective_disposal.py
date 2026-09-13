"""The real disposal function must await the client's asynchronous termination."""
from pathlib import Path
import subprocess


def test_perspective_disposed_metric_waits_for_worker_termination():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs = require('node:fs'), assert = require('node:assert/strict');
const source = fs.readFileSync('src/dataviz/components/packages/view.declarative/adapter.js', 'utf8');
const runtime = {metrics:{perspective:{disposed:0}}};
const tableService = {tanstack:{dispose() {}}};
const awaitPerspectiveOperation = (_state, _name, operation) => operation;
const body = source.slice(source.indexOf('const disposePerspective ='), source.indexOf('const createPerspective ='));
eval(body + '; global.disposePerspective = disposePerspective;');
(async () => {
  let release, entered;
  const started = new Promise(resolve => { entered = resolve; });
  const state = {countedCreated:true, worker:{terminate:() => new Promise(resolve => { release = resolve; entered(); })}};
  disposePerspective(state);
  await started;
  assert.equal(runtime.metrics.perspective.disposed, 0, 'termination pending is not disposed');
  release();
  await state.pending;
  assert.equal(runtime.metrics.perspective.disposed, 1);
  disposePerspective(state);
  assert.equal(runtime.metrics.perspective.disposed, 1, 'disposal is idempotent');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(['node', '-e', script], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
