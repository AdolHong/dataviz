from pathlib import Path
import subprocess


def test_repeated_live_disposal_closes_connections_aborts_downloads_and_ignores_late_events():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const full=fs.readFileSync('src/dataviz/server/runtime_src/80-state-and-live-scheduler.js','utf8');
const live=full.slice(full.indexOf('window.dataviz.connectLive ='),full.indexOf('const setControlInputs ='));
const disposal=fs.readFileSync('src/dataviz/server/runtime_src/60-renderer-disposal.js','utf8');
let connections=0, mutations=0;
(async()=>{
for(let cycle=0;cycle<30;cycle++){
 let signal, release, source;
 const runtime={cancelTransforms(){},inflightTransforms:new Map(),workerUrls:new Map(),
  interactionCache:new Map(),transformCacheEvidence:new Map(),controlImpactSignatures:new Map(),
  interactiveAdapters:{},registerOutputTransport(){mutations++;},hydrateOutput(){mutations++;},
  publishOutputs(){mutations++;},failOutputs(){mutations++;}};
 const context={datavizRuntime:runtime,AbortController,
  window:{dataviz:{live:{run_id:'run',outputs_url:'/outputs'},portable:{}},dispatchEvent(){mutations++;}},
  EventSource:class{constructor(){connections++;this.listeners={};source=this;}
   addEventListener(name,fn){this.listeners[name]=fn;}
   close(){if(!this.closed){this.closed=true;connections--;}}},
  fetch:(url,options)=>{signal=options.signal;return new Promise(resolve=>{release=resolve;});},
  datavizSetViewPipelineNodeStatus(){mutations++;},console};
 vm.runInNewContext(live+disposal,context);
 context.window.dataviz.connectLive();
 assert.equal(connections,1);
 const event={data:JSON.stringify({run_id:'run',node_id:'source:raw',data:{reference:'source:raw/main'}})};
 source.listeners.output_ready(event);
 runtime.dispose();runtime.dispose();
 assert.equal(connections,0);
 assert.equal(signal.aborted,true);
 assert.equal(context.window.dataviz.liveSource,null);
 for(const callback of Object.values(source.listeners))callback(event);
 // Model an uncooperative fetch completing even after abort.
 release({ok:true,json:async()=>({reference:'source:raw/main',transport:{format:'arrow'}})});
 await new Promise(resolve=>setImmediate(resolve));
 context.window.dataviz.connectLive();
 assert.equal(connections,0);
 assert.equal(mutations,0);
}
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script], cwd=root, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
