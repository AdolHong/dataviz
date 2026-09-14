from pathlib import Path
import subprocess


def test_live_download_failure_propagates_and_success_can_recover():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const all=fs.readFileSync('src/dataviz/server/runtime_src/80-state-and-live-scheduler.js','utf8');
const source=all.slice(all.indexOf('window.dataviz.connectLive ='),all.indexOf('const setControlInputs ='));
const listeners={}; const failures=[]; const outputs=[]; let failed=true;
const context={window:{dataviz:{live:{run_id:'run',session_id:'session',outputs_url:'/outputs'},portable:{}}},
 AbortController,EventSource:class{addEventListener(name,fn){listeners[name]=fn;}close(){}},
 fetch:async()=>failed?{ok:false,status:503}:{ok:true,json:async()=>({reference:'source:raw/main',kind:'table',value:[]})},
 datavizRuntime:{failOutputs:async(refs,error)=>failures.push({refs,code:error.code}),
   publishOutputs:async bundle=>outputs.push(bundle)},
 datavizRuntimeError:payload=>Object.assign(new Error(payload.message),payload),
 canonicalOutputReference:x=>x,datavizSetViewPipelineNodeStatus(){},console:{error(){}}};
vm.runInNewContext(source,context); context.window.dataviz.connectLive();
const event={data:JSON.stringify({run_id:'run',data:{reference:'source:raw/main'}})};
listeners.output_ready(event); await new Promise(resolve=>setImmediate(resolve));
assert.equal(failures.length,1,'failed download must reach Output state, not only console');
assert.equal(failures[0].code,'output_fetch_failed');
failed=false;listeners.output_ready(event);await new Promise(resolve=>setImmediate(resolve));
assert.equal(outputs.length,1,'a later ready event must recover');
assert.deepEqual(JSON.parse(JSON.stringify(outputs[0].outputs)),{'source:raw/main':[]});
'''], cwd=root, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
