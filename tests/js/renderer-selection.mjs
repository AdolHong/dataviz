import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const key = 'dashboard:demo/item';
const contract = {
  controls:{[key]:{direct_views:['filtered'], writer_edges:[{source_view:'writer'}]}},
  views:{
    writer:{control_binding:{control:key}},
    value:{control_inputs:{selected:{mode:'value', control:key}}},
    other:{control_inputs:{selected:{mode:'value', control:'dashboard:demo/other'}}},
    filtered:{filter_contract:[{key}]},
  },
};
const runtime = {outputViews:() => []};
const sandbox = {datavizRuntime:runtime, window:{dataviz:{dependency_contract:contract}},
  datavizViewControlContract:id => contract.views[id]?.filter_contract || [],
  datavizControlViewApplicability:() => 'applies',
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(new URL('../../src/dataviz/server/runtime_src/40-renderer-lifecycle.js', import.meta.url), 'utf8'), sandbox);
assert.deepEqual([...runtime.affectedViews([key])].sort(), ['filtered','value','writer']);
assert.deepEqual([...runtime.affectedViews([])], []);
assert.equal(runtime.affectedViews(null), null);
console.log('selection-only dependencies passed');
