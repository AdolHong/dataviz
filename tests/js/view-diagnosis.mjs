import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source = fs.readFileSync(new URL('../../src/dataviz/server/static/app.js', import.meta.url), 'utf8');
const start = source.indexOf('function viewDiagnosis(');
const end = source.indexOf('\nfunction renderViewInspector(', start);
assert(start >= 0 && end > start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const diagnose = (evidence) => context.viewDiagnosis({id:'detail', title:'PRIVATE'}, evidence, {run:'run-1'});
assert.equal(diagnose({}).status, 'unknown');
assert.equal(diagnose({refresh:{waiting_input:{alias:'main',reference:'source:x/main'}}}).status, 'waiting');
assert.equal(diagnose({refresh:{failed_input:{message:'PRIVATE'}}}).status, 'error');
assert.equal(diagnose({status:'cancelled',refresh:{failed_input:{}}}).status, 'cancelled');
assert.equal(diagnose({status:'empty'}).status, 'empty');
assert.equal(diagnose({status:'ready'}).status, 'ready');
assert.equal(diagnose({status:'ready',refresh:{failed_input:{}}}).stage, 'ready');
assert.equal(diagnose({status:'cancelled',refresh:{failed_input:{}}}).stage, 'cancelled');
assert.equal(diagnose({controls:[{intent:'explicit'}]}).controls[0].intent, 'explicit');
assert.equal(diagnose({controls:[{intent:'include'}]}).controls[0].intent, null);
const result = diagnose({status:'error', refresh:{failed_input:{alias:'main', message:'PRIVATE'},
  control_revisions:{selection:3}, changed_controls:['selection']}, renderer:{
    inputs:{main:{rows:12,bytes:123,values:['PRIVATE']}},
    binding_revisions:{selection:2}, filtering:{operands:['PRIVATE']},
    lifecycle:{error:'PRIVATE'}, duration_ms:4,
  }});
assert.equal(result.control_revisions.selection,3);
assert.equal(result.binding_revisions.selection,2);
assert.equal(result.inputs.main.rows,12);
assert(!JSON.stringify(result).includes('PRIVATE'));
const controls = diagnose({controls:[{key:'item', value:'PRIVATE', revision:3, intent:'all_available',
  domain:{status:'pending', available_count:0, sources:[{reference:'source:catalog/main',
    status:'error', rows:0, missing_fields:['category'], error:{message:'PRIVATE'}}]}}]}).controls;
assert.equal(controls[0].domain.status,'pending');
assert.equal(controls[0].intent,'all_available');
assert(!JSON.stringify(controls).includes('PRIVATE'));
assert.equal(Object.keys(diagnose({renderer:{inputs:Object.fromEntries(Array.from({length:100},(_,i)=>[i,{rows:1}]))}}).inputs).length,50);
console.log('View diagnosis statuses, revisions, privacy and bounds passed');
const pending=diagnose({status:'loading',refresh:{waiting_input:{alias:'main',reference:'source:new/main'},
 input_profiles:{main:{reference:'source:new/main',status:'pending',rows:null,input_type:null}},
 last_schedule:{status:'waiting_input'}},renderer:{inputs:{main:{rows:999}}}});
assert.equal(pending.inputs.main.rows,null,'do not report the old render row count for pending input');
assert.equal(pending.inputs.main.status,'pending');
assert.equal(pending.stage,'waiting_input');
assert.equal(pending.scheduling.status,'waiting_input');
const failed=diagnose({refresh:{render_error:{code:'view_render_failed',message:'PRIVATE'}}});
assert.equal(failed.stage,'render_failed');
assert.equal(failed.error_code,'view_render_failed');
assert(!JSON.stringify(failed).includes('PRIVATE'));
const cached=diagnose({refresh:{control_state:{x:{value:'PRIVATE'}},
 interactive_transforms:{t:{status:'ready',cache:{status:'hit'},inputs:{raw:'PRIVATE'}}}}});
assert.equal(cached.transforms.t.cache,'hit');
assert.equal(cached.transforms.t.status,'ready');
assert(!JSON.stringify(cached).includes('PRIVATE'));
