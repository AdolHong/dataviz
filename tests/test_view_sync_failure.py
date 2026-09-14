from pathlib import Path
import subprocess


def test_transform_diagnosis_does_not_keep_previous_cache_success():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const messages=[];
const runtime={interactiveTraces:new Map()};
vm.runInNewContext(fs.readFileSync('src/dataviz/server/runtime_src/30-interactive-scheduler.js','utf8'),{
 datavizRuntime:runtime,structuredClone,datavizSetViewPipelineNodeStatus(){},
 datavizPostToParent:message=>messages.push(message),
});
runtime.publishTransformStatus('t','ready',{trace:{cache:{status:'hit'}}});
assert.equal(runtime.interactiveTraces.get('t').cache.status,'hit');
for(const status of ['queued','loading','cancelled','error']){
 runtime.publishTransformStatus('t',status,{error:{code:'test_reason',message:'reason'}});
 const trace=runtime.interactiveTraces.get('t');
 assert.equal(trace.status,status);
 assert.equal(trace.cache,null);
 assert.equal(trace.error_code,'test_reason');
 assert.equal(messages.at(-1).trace.status,status);
}
runtime.publishTransformStatus('t','ready',{trace:{cache:{status:'miss'}}});
assert.equal(runtime.interactiveTraces.get('t').error_code,null);
assert.equal(runtime.interactiveTraces.get('t').cache.status,'miss');
'''], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sync_render_failure_replaces_stale_success_and_records_reason():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--input-type=module', '-e', r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const node={status:'ready',text:'old chart'};
const runtime={views:new Map([['v',{inputs:{},render(){throw new Error('descriptor failed');}}]]),
 outputErrors:new Map(),transformErrors:new Map(),interactiveTraces:new Map(),viewRefreshEvidence:new Map(),
 viewAdapter:{node:()=>node,completion:()=>Promise.resolve({status:'ready',generation:0}),waiting(root){root.status='loading';},renderInto(root,id,produce){
   try{produce();}catch(error){root.status='error';root.text=error.message;}
 }}};
const context={datavizRuntime:runtime,window:{dataviz:{portable:{outputs:{}},dependency_contract:{views:{v:{}}}}},
 console:{error(){}},structuredClone,canonicalOutputReference:x=>x,
 datavizCaptureConsumerControlState:()=>({}),datavizCaptureConsumerWriterProvenance:()=>({}),
 datavizValueProfile:value=>({rows:Array.isArray(value)?value.length:null,bytes:0,transport:'json'}),
 datavizCommitConsumerControlState(){},
 datavizRuntimeError:payload=>Object.assign(new Error(payload.message),payload)};
vm.runInNewContext(fs.readFileSync('src/dataviz/server/runtime_src/40-renderer-lifecycle.js','utf8'),context);
await runtime.renderViews({initial:false});
assert.equal(node.status,'error','a failed update must not leave the old chart marked ready');
assert.match(node.text,/descriptor failed/);
assert.equal(runtime.viewRefreshEvidence.get('v').render_error.message,'descriptor failed');
runtime.views.set('v',{inputs:{main:'source:raw/main'},render(){node.status='ready';}});
await runtime.renderViews({initial:false});
assert.equal(node.status,'loading');
assert.equal(runtime.viewRefreshEvidence.get('v').input_profiles.main.status,'pending');
assert.equal(runtime.viewRefreshEvidence.get('v').input_profiles.main.rows,null);
context.window.dataviz.portable.outputs['source:raw/main']=[];
await runtime.renderViews({initial:false});
assert.equal(runtime.viewRefreshEvidence.get('v').input_profiles.main.status,'empty');
assert.equal(runtime.viewRefreshEvidence.get('v').input_profiles.main.rows,0);
await runtime.renderViews({affectedViewIds:[],changedControlKeys:['unrelated']});
assert.equal(runtime.viewRefreshEvidence.get('v').last_schedule.status,'not_affected');
'''], cwd=root, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
