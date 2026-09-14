from pathlib import Path
import subprocess


def test_cache_snapshot_and_json_validation_share_lossless_rules():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('fs'),vm=require('vm');
const context={require};
vm.runInNewContext(fs.readFileSync('src/dataviz/server/runtime_src/10-value-contracts.js','utf8')+`
const assert=require('assert/strict');
const shared={n:1};
const valid={a:shared,b:shared,empty:[],zero:0,no:false,nil:null};
assert.deepEqual(datavizTableRows(undefined),[]);
assert.deepEqual(datavizTableRows([]),[]);
for(const bad of [null,0,false,'text',{},[1],[null]]) {
 assert.throws(()=>datavizTableRows(bad),e=>e.code==='input_not_table');
}
assert(datavizDtypeMatches('9007199254740993','int64'));
assert(!datavizDtypeMatches('-9007199254740993','uint64'));
assert(!datavizDtypeMatches('12','int64'));
assert(datavizDtypeMatches('1.20','decimal128'));
assert(datavizJsonCompatible(valid));
assert.deepEqual(datavizCacheClone(valid),valid);
assert.deepEqual(datavizSnapshotValue(valid),valid);
assert.notEqual(datavizCacheClone(valid).a,shared);
const cycle={};cycle.self=cycle;
for(const bad of [new Date(),new Map(),new Set(),new Uint8Array([1]),NaN,Infinity,1n,undefined,cycle,Array(1)]) {
 assert.equal(datavizJsonCompatible({bad}),false);
 for(const clone of [datavizCacheClone,datavizSnapshotValue]) {
  assert.throws(()=>clone({main:[{bad}]}),e=>e.code==='interactive_output_not_json_serializable' && e.path.startsWith('$'));
 }
}
`,context);
'''
    result = subprocess.run(['node', '-e', script], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
