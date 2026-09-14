from pathlib import Path
import subprocess


def test_worker_rows_are_transport_independent_and_invalid_aliases_are_errors():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let receive;
const messages = [];
const sandbox = {self:{addEventListener:(_, handler) => { receive = handler; }, postMessage:value => messages.push(value)}};
vm.runInNewContext(fs.readFileSync('src/dataviz/server/static/interactive-js-worker.js', 'utf8'), sandbox);
async function execute(inputs, code) {
  messages.length = 0;
  await receive({data:{protocol:'dataviz/interactive-worker/v1', type:'execute', request_id:'test',
    transform_id:'test', context:{inputs}, code}});
  return JSON.parse(JSON.stringify(messages.at(-1)));
}
const rows = [{item:'a', value:2}, {item:'b', value:8}, {item:'a', value:5}];
const columnar = {__datavizColumnarTable:true, length:3, columns:{item:['a','b','a'], value:[2,8,5]}};
for (const input of [rows, columnar]) {
  const result = await execute({rows:input}, `function transform(context) {
    const copy = context.rows('rows'); copy[0].value = 100;
    return {main:context.rows('rows').filter(r => r.item === 'a').sort((a,b) => b.value-a.value).slice(0,2),
      frame:context.table('rows').where('item','=', 'a').sort('value','desc').rows()};
  }`);
  assert.equal(result.type, 'result');
  assert.deepEqual(result.output.main, [{item:'a',value:5},{item:'a',value:2}]);
  assert.deepEqual(result.output.frame, result.output.main);
}
for (const input of [[], {__datavizColumnarTable:true,length:0,columns:{item:[],value:[]}}]) {
  const result = await execute({rows:input}, `function transform(c) { return c.rows('rows'); }`);
  assert.deepEqual(result.output, []);
}
for (const inputs of [{}, {rows:null}, {rows:7}, {rows:{value:7}}]) {
  for (const method of ['rows','table']) {
    const result = await execute(inputs, `function transform(c) { return c.${method}('rows'); }`);
    assert.equal(result.type, 'error');
    assert.equal(result.error.code, 'interactive_input_not_table');
    assert.equal(result.error.details.input_alias, 'rows');
  }
}
const frameResult = await execute({rows:columnar}, `function transform(c) {
  return {main:c.table('rows').where('item','=','a').sort('value','desc')};
}`);
assert.deepEqual(frameResult.output.main, [{item:'a',value:5},{item:'a',value:2}]);
'''], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
