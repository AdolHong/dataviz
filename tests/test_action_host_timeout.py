from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('phase', ['preflight', 'post', 'poll', 'output', 'status'])
def test_host_http_timeout_releases_slot_without_replaying_write(phase):
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('src/dataviz/server/static/app.js','utf8');
const code=source.slice(source.indexOf('async function handleServerActionMessage('),source.indexOf('\nfunction saveTabUiState()'));
const phase=process.argv[1], events=[],runtime={runId:'r1'};
const identity={dashboard_id:'d',run_id:'r1',frame_id:'f'};
let expire,signal,writes=0,cleared=0,recover=false;
const ready={status:'succeeded',request_id:'request',refresh:{status:'failed'}};
function hang(options){signal=options?.signal;assert.ok(signal,'host fetch requires an abort signal');
 return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Object.assign(new Error('AbortError'),{code:20}))));}
const context={AbortController,Date,performance,console,
 setTimeout:(fn,ms)=>{if(ms===290000){expire=fn;return 99;}assert.equal(ms,250);queueMicrotask(fn);return 1;},
 clearTimeout:id=>{assert.equal(id,99);cleared++;},
 state:{dashboard:{id:'d',server_actions:['save']}},activeRuntime:()=>runtime,
 canvasIdentity:()=>identity,sameCanvasIdentity:()=>true,sessionQuery:()=>'',
 window:{location:{origin:'http://localhost'}},
 request:async(url,options)=>{
   if(url.includes('/outputs/')) return hang(options);
   if(url.startsWith('/api/runs/r1')) return !recover&&phase==='preflight'?hang(options):{result:{outputs:{}}};
   if(url.startsWith('/api/runs/r2')) return {result:{outputs:{'source:data/main':{content_hash:'new'}}}};
   if(options?.method==='POST'){
     writes++;if(recover)return ready;
     if(phase==='post')return hang(options);
     if(phase==='poll')return {status:'running'};
     if(phase==='output')return {...ready,refresh:{status:'ready',run_id:'r2'}};
     return ready;
   }
   if(!recover&&['status','poll'].includes(phase))return hang(options);
   return ready;
 }};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{
 const data={operation:phase==='status'?'status':'invoke',action:'save',request_id:'request',bridge_id:'b'};
 const target={postMessage:value=>events.push(value)};
 const work=context.handleServerActionMessage(data,target);
 for(let i=0;i<12;i++)await Promise.resolve();
 assert.equal(typeof expire,'function','host must have a deadline, not only the Canvas RPC');
 assert.ok(signal);expire();await work;
 assert.ok(signal.aborted);assert.equal(cleared,1);assert.ok(!runtime.pendingServerAction);
 const reply=events.at(-1);assert.equal(reply.type,'dataviz:server-action-result');
 assert.equal(reply.error.code,phase==='preflight'?'action_not_submitted':'action_response_unknown');
 assert.equal(writes,['preflight','status'].includes(phase)?0:1);
 if(phase==='output'){assert.equal(reply.receipt.status,'succeeded');assert.equal(reply.receipt.client_refresh.status,'failed');}
 // A status check after recovery is allowed and never adds a write.
 recover=true;const before=writes;
 await context.handleServerActionMessage({...data,operation:'status',bridge_id:'b2'},target);
 assert.equal(events.at(-1).receipt.status,'succeeded');assert.equal(writes,before);assert.equal(cleared,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, phase],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
