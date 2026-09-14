from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('status', ['transport-error', 'queued', 'loading', 'timeout'])
def test_failed_completion_read_is_retryable_without_post_or_delete(status):
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('src/dataviz/server/static/app.js','utf8');
const runtime={pendingRunId:'run',pageId:'one'};
const nodes=new Map();let reads=0, timer, cleared=0;
const ctx={state:{dashboard:{id:'d'},navigationPending:false},runtimeFor:()=>runtime,
 AbortController,setTimeout:(callback,ms)=>{assert.equal(ms,30000);timer=callback;return 1;},
 clearTimeout:()=>{cleared++;},
 activeRuntime:()=>runtime,sessionQuery:()=>'',
 $:id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},classList:{remove(){}},textContent:''});return nodes.get(id);},
 setRunButtonLabel:label=>{ctx.label=label;},request:async(url,options)=>{
  assert.equal(options?.method,undefined,'retry must only GET the same receipt');
  assert.match(url,/\/api\/runs\/run\?/);reads++;
  if(process.argv[1]==='transport-error') throw new Error('503');
  if(process.argv[1]==='timeout') {
    assert.ok(options?.signal,'status read must be abortable');
    return new Promise((resolve,reject)=>{
      options.signal.addEventListener('abort',()=>reject(options.signal.reason));
      queueMicrotask(()=>timer());
    });
  }
  return {status:process.argv[1]};
 }};
vm.runInNewContext(source.slice(source.indexOf('async function runDashboard()'),source.indexOf('\nfunction listen('))+
 source.slice(source.indexOf('async function finishRun('),source.indexOf('\nfunction setControlsEnabled(')),ctx);
(async()=>{
 await ctx.finishRun('run','d','one');
 assert.equal(runtime.pendingRunId,'run');assert.equal(runtime.finishRunError,true);
 assert.equal(runtime.queryLabel,'Unconfirmed');assert.equal(ctx.label,'Retry status');
 await ctx.runDashboard();assert.equal(reads,2);
 assert.equal(runtime.pendingRunId,'run');
 assert.equal(cleared,2,'both attempts release their timeout');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, status], cwd=root, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_closed_run_stream_rechecks_only_current_pending_run():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('src/dataviz/server/static/app.js','utf8');
const runtime={pendingRunId:'run'};const checked=[];
class Events {static CLOSED=2;readyState=0;addEventListener(){}close(){this.readyState=2;}}
const ctx={runtimeFor:()=>runtime,EventSource:Events,sessionQuery:()=>'',
 finishRun:async(...args)=>checked.push(args)};
vm.runInNewContext(source.slice(source.indexOf('function listen('),source.indexOf('\nfunction updateEvent(')),ctx);
(async()=>{
 ctx.listen('run','dashboard','page');const first=runtime.eventSource;
 await first.onerror();assert.equal(checked.length,0,'reconnecting stream must keep native retry');
 first.readyState=2;await first.onerror();assert.equal(checked.length,1);
 assert.deepEqual(checked[0],['run','dashboard','page']);
 ctx.listen('run','dashboard','page');await first.onerror();assert.equal(checked.length,1,'replaced stream is stale');
 runtime.pendingRunId='new';runtime.eventSource.readyState=2;
 await runtime.eventSource.onerror();assert.equal(checked.length,1,'old Run is stale');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script], cwd=root, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('outcome', ['success', 'failure'])
@pytest.mark.parametrize('destination', ['other-page', 'new-run'])
def test_cancel_reply_cannot_change_another_pages_header(outcome, destination):
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('src/dataviz/server/static/app.js','utf8');
let resolve, reject;
const gate=new Promise((yes,no)=>{resolve=yes;reject=no;});
const old={pendingRunId:'old',pageId:'one'}, next={pageId:'two'};
let active=old;
const nodes={'#run-button':{disabled:false},'#run-message':{textContent:''}};
const ctx={state:{dashboard:{id:'d'},navigationPending:false},runtimeFor:()=>old,
 activeRuntime:()=>active,$:id=>nodes[id],sessionQuery:()=>'',request:()=>gate,
 setRunButtonLabel:label=>{nodes.label=label;}};
vm.runInNewContext(source.slice(source.indexOf('async function runDashboard()'),source.indexOf('\nfunction listen(')),ctx);
(async()=>{
 const work=ctx.runDashboard();
 active=next;
 if(process.argv[2]==='new-run'){active=old;old.pendingRunId='new';}
 nodes['#run-message'].textContent='new page';nodes.label='Run';nodes['#run-button'].disabled=false;
 if(process.argv[1]==='failure') reject(new Error('old cancel failed'));else resolve({});
 await work;
 assert.equal(nodes['#run-message'].textContent,'new page');
 assert.equal(nodes.label,'Run');
 assert.equal(nodes['#run-button'].disabled,false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, outcome, destination], cwd=root, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
