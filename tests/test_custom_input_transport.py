from pathlib import Path
import subprocess


def test_custom_named_tables_do_not_leak_arrow_wrappers():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '-e', r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const window={};
vm.runInNewContext(fs.readFileSync('src/dataviz/components/packages/view.declarative/controller.js','utf8'),{window,structuredClone});
for(const rows of [[],[{n:1}]]) {
 for(const raw of [rows,{__datavizArrowOutput:true,rows:()=>rows}]) {
  const values={a:raw,b:raw,metadata:{count:rows.length},scalar:0};
  const state={dependency_contract:{views:{audit:{inputs:{main:'a',extra:'b',meta:'metadata',total:'scalar'}}}},
    data:{output:ref=>values[ref],table:ref=>({rows:()=>values[ref]?.__datavizArrowOutput?values[ref].rows():values[ref]})},
    control:{state:()=>({intent:'include',value:1}),canApply:()=>true,matches:row=>row.n===1}};
  const d=window.datavizComponents.viewDeclarative.build({id:'audit',template:'custom',renderer:'audit'},state,rows);
  assert(Array.isArray(d.inputs.main));
  assert(Array.isArray(d.inputs.extra));
  assert.deepEqual(d.inputs.extra,rows);
  assert.equal(d.inputs.meta,values.metadata);
  assert.equal(d.inputs.total,0);
  state.dependency_contract.views.audit.filter_contract=[{key:'test',consumer_binding:{inputs:['extra']}}];
  const filtered=window.datavizComponents.viewDeclarative.build({id:'audit',template:'custom',renderer:'audit'},state);
  assert.deepEqual(JSON.parse(JSON.stringify(filtered.inputs.extra)),rows);
 }
}
'''], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
