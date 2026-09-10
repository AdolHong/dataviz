import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const parent = 'dashboard:demo/category';
const child = 'dashboard:demo/item';
const reference = 'source:choices/main';
const runtime = {outputErrors:new Map(), outputSignatures:new Map(), transportPromises:new Map()};
const portable = {outputs:{[reference]:[{category_nbr:'A', item:'A1'}, {category_nbr:'B', item:'B1'}]},
  output_kinds:{[reference]:'table'}, output_schemas:{}};
const sandbox = {datavizRuntime:runtime,
  window:{dataviz:{portable, dependency_contract:{
    controls:{
      [parent]:{definition:{id:'category', field:'category_nbr'}},
      [child]:{definition:{id:'item', field:'item'}, depends_on:[parent], dependency_ancestors:[parent], option_domain_references:[reference]},
    }, views:{detail:{filter_contract:[]}},
  }}},
  canonicalOutputReference:x=>x, datavizTableRows:x=>Array.isArray(x)?x:[],
  datavizValueSignature:JSON.stringify, datavizStaticChoices:()=>[],
  datavizControlEntry:key=>({value:key===parent?'A':'A1'}),
  datavizControlMatches:(row,item,state)=>row[item.consumer_binding.field]===state.value,
};
vm.createContext(sandbox);
const source = fs.readFileSync(new URL('../../src/dataviz/server/runtime_src/70-control-binding.js', import.meta.url), 'utf8');
for (const name of ['datavizControlFields','datavizControlCanApply','datavizViewControlContract',
  'datavizControlContractItem','datavizControlDomainReferences','datavizOutputFieldNames',
  'datavizControlViewApplicability','datavizAvailableControlOptions']) {
  const start = source.indexOf(`const ${name} =`);
  const end = source.indexOf('\nconst ', start + 1);
  assert(start >= 0 && end > start, name);
  vm.runInContext(source.slice(start,end), sandbox);
}
const availability = () => vm.runInContext(`datavizAvailableControlOptions([{viewId:'detail', item:datavizControlContractItem('${child}')}])`, sandbox);
assert.deepEqual(Array.from(availability().options, x=>x.value), ['A1']);
assert.equal(availability().dependencyRelationReady, true);
portable.outputs[reference] = [{item:'A1'}];
assert.equal(availability().diagnostic.status, 'field_mismatch');
assert.deepEqual(Array.from(availability().diagnostic.sources[0].missing_fields), ['category_nbr']);
delete portable.outputs[reference];
assert.equal(availability().diagnostic.status, 'pending');
portable.outputs[reference] = [];
assert.equal(availability().diagnostic.status, 'empty');
assert.equal(availability().observed, true);
runtime.outputErrors.set(reference, new Error('query failed'));
assert.equal(availability().diagnostic.status, 'error');
runtime.outputErrors.delete(reference);

vm.runInContext(fs.readFileSync(new URL('../../src/dataviz/server/runtime_src/50-output-store.js', import.meta.url), 'utf8'), sandbox);
const derived = 'interactive:small/main';
assert.equal(runtime.commitOutput(derived, [], {kind:'table', schema:[{name:'item', dtype:'str'}]}), true);
assert.equal(portable.output_kinds[derived], 'table');
assert.equal(portable.output_schemas[derived][0].name, 'item');
sandbox.window.dataviz.dependency_contract.controls[child].direct_view_bindings = {
  detail:{fields:['item'], input_references:[derived], applicability:'runtime'},
};
assert.equal(vm.runInContext(`datavizControlViewApplicability('detail', datavizControlContractItem('${child}'))`, sandbox), 'applies');
assert.equal(runtime.commitOutput(derived, [], {kind:'table', schema:[{name:'item', dtype:'str'}]}), false);
runtime.outputErrors.set(derived, new Error('failed'));
assert.equal(runtime.commitOutput(derived, [], {kind:'table', schema:[{name:'item', dtype:'str'}]}), true);
assert.equal(runtime.outputErrors.has(derived), false);
runtime.removeOutput(derived);
assert.equal(derived in portable.outputs, false);
assert.equal(derived in portable.output_kinds, false);
assert.equal(derived in portable.output_schemas, false);
assert.equal(runtime.outputSignatures.has(derived), false);
console.log('interaction state contracts passed');
