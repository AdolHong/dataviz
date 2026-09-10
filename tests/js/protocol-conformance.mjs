import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const fixture = name => JSON.parse(
  fs.readFileSync(path.join(root, 'tests', 'conformance', `${name}.json`), 'utf8'),
).cases;

const runtimeWindow = {
  dataviz:{
    protocol:{schema:'dataviz/runtime/v15'},
    dependency_contract:{schema:'dataviz/dependency-contract/v13'},
    query_parameter_state:{},
  },
  location:{origin:'http://localhost'},
};
runtimeWindow.parent = runtimeWindow;
const runtimeSource = fs.readFileSync(
  path.join(root, 'src', 'dataviz', 'server', 'runtime_src', '00-runtime-manifest.js'),
  'utf8',
);
const runtime = new Function('window', 'document', 'CSS', `${runtimeSource}
  return {
    project:datavizProjectParameterInputs,
    parameterBinding:datavizParameterBinding,
    parameterSignature:datavizParameterInputSignature,
    signature:datavizValueSignature,
    match:datavizTypedControlMatch,
    pathMatch:datavizPathControlMatch,
    revision:datavizNormalizeConsumerRevision,
    output:datavizValidateOutputDestination,
  };
`)(runtimeWindow, {querySelectorAll:() => []}, {escape:String});

const viewWindow = {
  dataviz:{
    query_parameter_state:{
      holiday_date:{value:'2026-10-01'},
      visible_range:{value:['2026-09-01', '2026-10-07']},
    },
  },
  datavizComponents:{},
};
const viewControllerSource = fs.readFileSync(
  path.join(
    root,
    'src',
    'dataviz',
    'components',
    'packages',
    'view.declarative',
    'controller.js',
  ),
  'utf8',
);
const viewRuntime = new Function(
  'window',
  `${viewControllerSource}\nreturn window.datavizComponents.viewDeclarative;`,
)(viewWindow);
assert.deepEqual(
  viewRuntime.resolvePlotlyLayout({
    shapes:[{
      x0:'{{ parameters.holiday_date }}',
      x1:'{{parameters.holiday_date}}',
    }],
    xaxis:{range:'{{ parameters.visible_range }}'},
  }),
  {
    shapes:[{x0:'2026-10-01', x1:'2026-10-01'}],
    xaxis:{range:['2026-09-01', '2026-10-07']},
  },
);
assert.throws(
  () => viewRuntime.resolvePlotlyLayout({title:'Holiday {{ parameters.holiday_date }}'}),
  error => error.code === 'plotly_layout_template_invalid',
);
assert.throws(
  () => viewRuntime.resolvePlotlyLayout({shapes:[{x0:'{{ parameters.missing }}'}]}),
  error => error.code === 'plotly_layout_parameter_unknown',
);

const decode = value => {
  if (Array.isArray(value)) return value.map(decode);
  if (!value || typeof value !== 'object') return value;
  if ('$integer' in value) return Number(value.$integer);
  if ('$number' in value) return Number.NaN;
  if ('$boolean' in value) return Boolean(value.$boolean);
  if ('$unsupported' in value) return () => null;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, decode(item)]));
};

const verify = (caseValue, operation) => {
  try {
    const actual = operation();
    assert.ok(!('expected_error_code' in caseValue), `${caseValue.id} should fail`);
    assert.deepEqual(actual, caseValue.expected, caseValue.id);
  } catch (error) {
    if (!('expected_error_code' in caseValue)) throw error;
    assert.equal(error.code, caseValue.expected_error_code, caseValue.id);
  }
};

for (const item of fixture('input-binding')) {
  verify(item, () => {
    const payload = item.input;
    if (item.operation === 'canonicalize') return runtime.parameterBinding(payload.binding);
    if (item.operation === 'signature') return runtime.parameterSignature(payload.inputs);
    runtimeWindow.dataviz.query_parameter_state = {[payload.binding.parameter]:payload.state};
    return runtime.project({result:payload.binding}).result;
  });
}

for (const item of fixture('value-signature')) {
  verify(item, () => runtime.signature(decode(item.input)));
}

for (const item of fixture('consumer-revision')) {
  verify(item, () => {
    const payload = decode(item.input);
    return runtime.revision(payload.effective, payload.applied);
  });
}

for (const item of fixture('output-capability')) {
  verify(item, () => runtime.output({
    producerRuntime:item.input.producer_runtime,
    outputKind:item.input.output_kind,
    destination:item.input.destination,
  }));
}

const adapterWindow = {
  dataviz:{protocol:{schema:'dataviz/runtime/v15'}},
  customElements:{get:() => null, define:() => {}},
  addEventListener:() => {},
};
class HTMLElementStub {}
const adapterSource = fs.readFileSync(
  path.join(root, 'src', 'dataviz', 'server', 'static', 'runtime-web-component-adapter.js'),
  'utf8',
);
new Function('window', 'HTMLElement', adapterSource)(adapterWindow, HTMLElementStub);

const runWebFilter = item => {
  const payload = item.input;
  const isPath = item.operation === 'path_filter';
  const rows = isPath
    ? payload.rows.map(([level, value]) => ({level, value}))
    : payload.rows.map(value => ({value}));
  const definition = isPath
    ? {type:'multiple_select', value_type:'text'}
    : {
        type:payload.control_type || (payload.operator === 'between' ? 'range_input'
          : payload.operator === 'in' ? 'multiple_select' : 'single_input'),
        value_type:payload.value_type,
        options:payload.options,
      };
  const consumerBinding = {
    mode:'filter',
    field:isPath ? ['level', 'value'] : 'value',
    inputs:['main'],
    empty:payload.empty || 'match_none',
    operator:isPath ? 'auto' : payload.operator,
  };
  const manifest = {
    protocol:{schema:'dataviz/runtime/v15'},
    portable:{outputs:{'source:rows/main':rows}},
    dependency_contract:{
      views:{sample:{
        inputs:{main:'source:rows/main'},
        filter_contract:[{
          key:'dashboard:sample/filter',
          definition,
          consumer_binding:consumerBinding,
        }],
      }},
    },
    control_state:{'dashboard:sample/filter':{
      value:payload.value,
      revision:0,
      ...(payload.intent ? {intent:payload.intent} : {}),
    }},
  };
  const result = new adapterWindow.DatavizRuntimeV3Client(manifest).viewRows('sample');
  return isPath ? result.map(row => [row.level, row.value]) : result.map(row => row.value);
};

// Exercise the production matcher, not a second implementation of its policy.
const controlSource = fs.readFileSync(
  path.join(root, 'src/dataviz/server/runtime_src/70-control-binding.js'), 'utf8',
);
const controlMatch = new Function('datavizTypedControlMatch', 'datavizPathControlMatch', `
  ${controlSource.slice(controlSource.indexOf('const datavizControlFields ='), controlSource.indexOf('const datavizViewControlContract ='))}
  const datavizControlValueFromState = (_definition, state) => state?.value;
  ${controlSource.slice(controlSource.indexOf('const datavizControlMatches ='), controlSource.indexOf('const datavizControlIntentKey ='))}
  return datavizControlMatches;
`)(runtime.match, runtime.pathMatch);

for (const item of fixture('control-filter')) {
  verify(item, () => {
    const payload = item.input;
    const isPath = item.operation === 'path_filter';
    return payload.rows.filter(actual => controlMatch(
      isPath ? {level:actual[0], value:actual[1]} : {value:actual},
      {
        definition:{type:payload.control_type || 'multiple_select', value_type:payload.value_type, options:payload.options},
        consumer_binding:{field:isPath ? ['level', 'value'] : 'value', operator:isPath ? 'auto' : payload.operator, empty:payload.empty || 'match_none'},
      },
      {value:payload.value, intent:payload.intent},
    ));
  });
  verify({...item, id:`web-component/${item.id}`}, () => runWebFilter(item));
}

// Named inputs apply only their own bindings; the main alias equals legacy rows.
const inputRows = [{region:'north'}, {region:'south'}];
const namedState = {
  dependency_contract:{views:{sample:{
    inputs:{main:'source:stores/main', geography:'source:geography/main', metadata:'source:metadata/main'},
    filter_contract:[{
      key:'region', definition:{type:'multiple_select'},
      consumer_binding:{field:'region', operator:'in', inputs:['main'], empty:'match_none'},
    }],
  }}},
  data:{output:ref => ref === 'source:metadata/main' ? {title:'Map'} : inputRows, table:() => ({rows:() => inputRows})},
  control:{state:() => ({value:['north'], intent:'explicit'}), canApply:() => true, matches:controlMatch},
};
const customView = {id:'sample', template:'custom', renderer:'sample'};
const mainFiltered = viewRuntime.build(customView, namedState);
assert.deepEqual(mainFiltered.rows, [{region:'north'}]);
assert.deepEqual(mainFiltered.inputs.main, mainFiltered.rows);
assert.equal(mainFiltered.inputs.geography, inputRows);
assert.deepEqual(mainFiltered.inputs.metadata, {title:'Map'});
namedState.dependency_contract.views.sample.filter_contract[0].consumer_binding.inputs = ['geography'];
const geographyFiltered = viewRuntime.build(customView, namedState);
assert.deepEqual(geographyFiltered.rows, inputRows);
assert.deepEqual(geographyFiltered.inputs.main, inputRows);
assert.deepEqual(geographyFiltered.inputs.geography, [{region:'north'}]);
assert.deepEqual(inputRows, [{region:'north'}, {region:'south'}]);
const namedClient = new adapterWindow.DatavizRuntimeV3Client({
  protocol:{schema:'dataviz/runtime/v15'},
  portable:{outputs:{'source:stores/main':inputRows, 'source:geography/main':inputRows}},
  dependency_contract:namedState.dependency_contract,
  control_state:{region:{value:['north'], intent:'explicit'}},
});
assert.deepEqual(namedClient.viewRows('sample', 'main'), inputRows);
assert.deepEqual(namedClient.viewRows('sample', 'geography'), [{region:'north'}]);
namedState.control.state = () => ({value:[], intent:'explicit'});
const emptyGeography = viewRuntime.build(customView, namedState);
assert.deepEqual(emptyGeography.inputs.geography, []);
assert.deepEqual(emptyGeography.inputs.main, inputRows);
namedState.data.output = () => 42;
namedState.data.table = () => ({rows:() => []});
namedState.dependency_contract.views.sample.filter_contract = [];
assert.equal(viewRuntime.build(customView, namedState).inputs.main, 42);

process.stdout.write('protocol conformance passed\n');
