import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const fixture = name => JSON.parse(
  fs.readFileSync(path.join(root, 'tests', 'conformance', `${name}.json`), 'utf8'),
).cases;

const runtimeWindow = {
  dataviz:{
    protocol:{schema:'dataviz/runtime/v10'},
    dependency_contract:{schema:'dataviz/dependency-contract/v11'},
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
  dataviz:{protocol:{schema:'dataviz/runtime/v10'}},
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
      };
  const consumerBinding = {
    mode:'filter',
    field:isPath ? ['level', 'value'] : 'value',
    inputs:['main'],
    empty:payload.empty || 'match_none',
    operator:isPath ? 'auto' : payload.operator,
  };
  const manifest = {
    protocol:{schema:'dataviz/runtime/v10'},
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
    control_state:{'dashboard:sample/filter':{value:payload.value, revision:0}},
  };
  const result = new adapterWindow.DatavizRuntimeV3Client(manifest).viewRows('sample');
  return isPath ? result.map(row => [row.level, row.value]) : result.map(row => row.value);
};

for (const item of fixture('control-filter')) {
  verify(item, () => {
    const payload = item.input;
    if (item.operation === 'path_filter') {
      return payload.rows.filter(([level, value]) => runtime.pathMatch({
        row:{level, value}, fields:['level', 'value'], value:payload.value,
      }));
    }
    if (payload.value == null || payload.value === ''
        || (Array.isArray(payload.value) && payload.value.length === 0)) {
      return payload.empty === 'passthrough' ? payload.rows : [];
    }
    const operator = payload.operator === 'auto'
      ? (['multiple_input', 'multiple_select'].includes(payload.control_type) ? 'in'
        : payload.control_type === 'range_input' ? 'between' : 'equals')
      : payload.operator;
    return payload.rows.filter(actual => runtime.match({
      actual,
      value:payload.value,
      operator,
      valueType:payload.value_type,
    }));
  });
  verify({...item, id:`web-component/${item.id}`}, () => runWebFilter(item));
}

process.stdout.write('protocol conformance passed\n');
