const datavizViewSpecs = window.dataviz.view_specs || [];
const datavizRepeatSpecs = window.dataviz.repeat_specs || [];
const datavizRepeatedViewIds = new Set(datavizRepeatSpecs.map(spec => spec.view));
const dvEscape = value => String(value ?? '').replace(/[&<>\"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[char]));
const dvSelectRows = (view, state) => {
  const contract = state.portable?.selection_contract?.[view.id] || [];
  const reference = view.input || view.inputs?.main;
  return state.data.table(reference).rows().filter(row => contract.every(item => (
    state.selection.matches(row, item, state.selections[item.key])
  )));
};
const dvAggregate = (rows, groupFields, valueFields, operation = 'sum') => {
  const groups = new Map();
  rows.forEach(row => {
    const key = JSON.stringify(groupFields.map(field => row[field]));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  return [...groups].map(([key, values]) => {
    const output = Object.fromEntries(groupFields.map((field, index) => [field, JSON.parse(key)[index]]));
    valueFields.forEach(valueField => {
      const numbers = values.map(row => Number(row[valueField] ?? 0));
      if (operation === 'count') output[valueField] = values.length;
      else if (operation === 'mean') output[valueField] = numbers.reduce((a,b) => a+b, 0) / Math.max(numbers.length, 1);
      else if (operation === 'min') output[valueField] = Math.min(...numbers);
      else if (operation === 'max') output[valueField] = Math.max(...numbers);
      else output[valueField] = numbers.reduce((a,b) => a+b, 0);
    });
    return output;
  });
};
const dvPreparedRows = (view, state) => {
  let rows = dvSelectRows(view, state);
  const valueFields = view.template === 'heatmap' ? [view.z] : (Array.isArray(view.y) ? view.y : [view.y || view.value || view.z]).filter(Boolean);
  const groups = (view.template === 'heatmap' ? [view.x, view.y] : [view.x || view.label, view.series]).filter(Boolean);
  const operation = view.template === 'metric'
    ? 'none'
    : (view.aggregate || (['scatter','table','perspective'].includes(view.template) ? 'none' : 'sum'));
  if (operation !== 'none' && valueFields.length && groups.length) rows = dvAggregate(rows, groups, valueFields, operation);
  if (view.sort) {
    const descending = view.sort.startsWith('-');
    const field = descending ? view.sort.slice(1) : view.sort;
    rows.sort((a,b) => (a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0) * (descending ? -1 : 1));
  }
  return view.limit ? rows.slice(0, view.limit) : rows;
};
const dvPlotlyDescriptor = (view, rows) => {
  const groups = view.series ? [...new Set(rows.map(row => row[view.series]))] : [null];
  const measures = Array.isArray(view.y) ? view.y : [view.y];
  const traces = groups.flatMap(group => measures.map(measure => {
    const selected = group == null ? rows : rows.filter(row => row[view.series] === group);
    const common = {name: [group, measures.length > 1 ? measure : null].filter(Boolean).join(' · ') || view.title, x: selected.map(row => row[view.x]), y: selected.map(row => row[measure])};
    if (view.template === 'line') return {...common, type:'scatter', mode:'lines+markers'};
    if (view.template === 'scatter') return {...common, type:'scatter', mode:'markers', marker:{size:view.size ? selected.map(row => row[view.size]) : 9, color:view.color ? selected.map(row => row[view.color]) : undefined}};
    return {...common, type:'bar'};
  }));
  if (view.template === 'pie') traces.splice(0, traces.length, {type:'pie', labels:rows.map(row => row[view.label || view.x]), values:rows.map(row => row[view.value || view.y]), hole:view.options?.hole || 0});
  if (view.template === 'heatmap') {
    const xs = [...new Set(rows.map(row => row[view.x]))], ys = [...new Set(rows.map(row => row[view.y]))];
    traces.splice(0, traces.length, {type:'heatmap', x:xs, y:ys, z:ys.map(y => xs.map(x => rows.find(row => row[view.x] === x && row[view.y] === y)?.[view.z] ?? null)), colorscale:view.options?.colorscale || 'Viridis'});
  }
  return {type:'plotly', data:traces, layout:{margin:{l:48,r:20,t:20,b:46}, paper_bgcolor:'transparent', plot_bgcolor:'transparent', barmode:view.template === 'stacked-bar' ? 'stack' : (view.options?.barmode || 'group'), legend:{orientation:'h', y:1.12}, ...view.options?.layout}, config:view.config};
};
const dvEchartsDescriptor = (view, rows) => {
  if (view.template === 'pie') return {type:'echarts', options:{tooltip:{trigger:'item'}, series:[{type:'pie', radius:['18%','72%'], data:rows.map(row => ({name:row[view.label || view.x], value:row[view.value || view.y]}))}], ...view.options}};
  if (view.template === 'heatmap') {
    const xs = [...new Set(rows.map(row => row[view.x]))], ys = [...new Set(rows.map(row => row[view.y]))];
    const data = rows.map(row => [xs.indexOf(row[view.x]), ys.indexOf(row[view.y]), row[view.z]]);
    const {colors, visualMap:visualMapOptions, ...heatmapOptions} = view.options || {};
    const visualMap = {min:Math.min(...data.map(item=>Number(item[2]))),max:Math.max(...data.map(item=>Number(item[2]))),calculable:true,orient:'horizontal',...(colors ? {inRange:{color:colors}} : {}),...(visualMapOptions || {})};
    return {type:'echarts', options:{tooltip:{}, xAxis:{type:'category',data:xs}, yAxis:{type:'category',data:ys}, visualMap, series:[{type:'heatmap',data}], ...heatmapOptions}};
  }
  if (view.template === 'scatter') return {type:'echarts', options:{tooltip:{trigger:'item'}, xAxis:{type:'value'}, yAxis:{type:'value'}, series:[{type:'scatter',data:rows.map(row => [row[view.x],row[view.y],view.size ? row[view.size] : undefined]),symbolSize:item => item[2] || 10}], ...view.options}};
  if (view.template === 'radar') {
    const maxima = view.columns.map(field => Math.max(1, ...rows.map(row => Number(row[field] ?? 0))));
    return {type:'echarts', options:{tooltip:{}, legend:{}, radar:{indicator:view.columns.map((field,index)=>({name:field,max:maxima[index]}))}, series:[{type:'radar',data:rows.map(row=>({name:String(row[view.label] ?? ''),value:view.columns.map(field=>row[field])}))}], ...view.options}};
  }
  const categories = [...new Set(rows.map(row => row[view.x]))];
  const groups = view.series ? [...new Set(rows.map(row => row[view.series]))] : [null];
  const measures = Array.isArray(view.y) ? view.y : [view.y];
  const {legend_interaction:legendInteraction = 'filter', legend:legendOptions = {}, ...chartOptions} = view.options || {};
  return {
    type:'echarts',
    legendInteraction,
    options:{
      tooltip:{trigger:'axis'},
      legend:{...legendOptions, selectedMode:legendInteraction === 'none' ? false : (legendOptions.selectedMode ?? true)},
      xAxis:{type:'category', data:categories},
      yAxis:{type:'value'},
      series:groups.flatMap(group => measures.map(measure => ({
        name:[group, measures.length > 1 ? measure : null].filter(Boolean).join(' · ') || view.title,
        type:view.template === 'line' ? 'line' : 'bar',
        stack:view.template === 'stacked-bar' ? 'total' : undefined,
        data:categories.map(category => rows.find(row => row[view.x] === category && (group == null || row[view.series] === group))?.[measure] ?? null)
      }))),
      ...chartOptions
    }
  };
};
const dvBuildView = (view, state, preparedRows = null) => {
  const rawInput = view.input ? state.data.output(view.input) : undefined;
  // Content Views may be completely self-contained. Resolve them before table
  // preparation so an absent input is not treated as an empty Output reference.
  if (view.template === 'markdown') {
    const content = view.text ?? rawInput ?? '';
    return {type:'html', html:`<div class="dv-prose">${dvEscape(content).replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>')}</div>`};
  }
  if (view.template === 'image') return {type:'html', html:`<img class="dv-image" src="${dvEscape(view.url || '')}" alt="${dvEscape(view.title || '')}">`};
  if (view.template === 'metric' && !Array.isArray(rawInput) && rawInput != null) {
    const formatted = typeof rawInput === 'number'
      ? new Intl.NumberFormat(undefined, view.options?.format || {maximumFractionDigits:2}).format(rawInput)
      : String(rawInput);
    return {type:'html', html:`<div class="dv-metric"><strong>${dvEscape(formatted)}</strong><span>${dvEscape(view.label || view.title || '')}</span></div>`};
  }
  const rows = preparedRows == null ? dvPreparedRows(view, state) : (() => {
    let values = preparedRows;
    const valueFields = view.template === 'heatmap' ? [view.z] : (Array.isArray(view.y) ? view.y : [view.y || view.value || view.z]).filter(Boolean);
    const groups = (view.template === 'heatmap' ? [view.x, view.y] : [view.x || view.label, view.series]).filter(Boolean);
    const operation = view.template === 'metric'
      ? 'none'
      : (view.aggregate || (['scatter','table','perspective'].includes(view.template) ? 'none' : 'sum'));
    if (operation !== 'none' && valueFields.length && groups.length) values = dvAggregate(values, groups, valueFields, operation);
    if (view.sort) {
      const descending = view.sort.startsWith('-');
      const field = descending ? view.sort.slice(1) : view.sort;
      values = [...values].sort((a,b) => (a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0) * (descending ? -1 : 1));
    }
    return view.limit ? values.slice(0, view.limit) : values;
  })();
  if (view.template === 'table') return {type:'table', rows, columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {}), limit:view.limit, options:view.options, config:view.config};
  if (view.template === 'perspective') return {type:'perspective', rows, columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {}), config:view.config, limit:view.limit};
  if (view.template === 'custom') return {type:view.renderer, rows, view, options:view.options, config:view.config};
  if (view.template === 'metric') {
    const field = view.value || view.y;
    const values = rows.map(row => Number(row[field] ?? 0));
    const operation = view.aggregate || 'sum';
    const value = operation === 'count' ? rows.length : operation === 'mean' ? values.reduce((a,b)=>a+b,0)/Math.max(values.length,1) : operation === 'min' ? Math.min(...values) : operation === 'max' ? Math.max(...values) : values.reduce((a,b)=>a+b,0);
    const formatted = Number.isFinite(value) ? new Intl.NumberFormat(undefined, view.options?.format || {maximumFractionDigits:2}).format(value) : '—';
    return {type:'html', html:`<div class="dv-metric"><strong>${dvEscape(formatted)}</strong><span>${dvEscape(view.label || field || '')}</span></div>`};
  }
  return view.engine === 'echarts' ? dvEchartsDescriptor(view, rows) : dvPlotlyDescriptor(view, rows);
};
const dvRepeatTitle = (template, row, fields) => String(template || '{value}').replace(/[{]([^}]+)[}]/g, (_, name) => {
  if (name === 'value') return fields.map(field => row[field] ?? '').join(' / ');
  return row[name] ?? '';
});
const dvRepeatInstances = (spec, view, state) => {
  const started = performance.now();
  if (!view) return [];
  const repeatedView = spec.input ? {...view, input:spec.input, inputs:{}} : view;
  const contract = state.portable?.selection_contract?.[view.id] || [];
  if (spec.template === 'selection-gallery') {
    const selection = contract.find(item => item.origin === 'section' && item.owner_id === spec.section && (!spec.selection || item.id === spec.selection));
    const value = selection ? state.selections[selection.key] : null;
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return [];
  }
  const grouped = new Map();
  dvSelectRows(repeatedView, state).forEach(row => {
    const values = spec.by.map(field => row[field]);
    const key = JSON.stringify(values);
    if (!grouped.has(key)) grouped.set(key, {key, values, row, rows:[]});
    grouped.get(key).rows.push(row);
  });
  let groups = [...grouped.values()];
  const direction = spec.order === 'desc' ? -1 : 1;
  groups.sort((left, right) => {
    if (spec.order_by) {
      const a = left.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
      const b = right.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
      if (a !== b) return (a - b) * direction;
    }
    return left.values.map(String).join('\\u0000').localeCompare(right.values.map(String).join('\\u0000')) * direction;
  });
  if (spec.limit) groups = groups.slice(0, spec.limit);
  const instances = groups.map(group => ({
    key: group.key,
    id: `${view.id}@${encodeURIComponent(spec.section)}/${group.values.map(value => encodeURIComponent(String(value ?? ''))).join('/')}`,
    title: dvRepeatTitle(spec.title, group.row, spec.by),
    searchText: [
      dvRepeatTitle(spec.title, group.row, spec.by),
      ...group.values,
      ...Object.values(group.row),
    ].map(value => String(value ?? '')).join(' '),
    signature: JSON.stringify(group.rows),
    render: () => dvBuildView(repeatedView, state, group.rows),
  }));
  instances.buildMs = performance.now() - started;
  return instances;
};
datavizViewSpecs
  .filter(view => !datavizRepeatedViewIds.has(view.id))
  .forEach(view => window.datavizRuntime.registerView(view.id, {
    inputs: {...(view.inputs || {}), ...(view.input ? {main:view.input} : {})},
    render: state => state.renderView(view.id, () => dvBuildView(view, state)),
  }));
datavizRepeatSpecs.forEach(spec => {
  const view = datavizViewSpecs.find(item => item.id === spec.view);
  if (!view) return;
  window.datavizRuntime.registerView(view.id, {
    inputs: {...(view.inputs || {}), ...(spec.input ? {main:spec.input} : view.input ? {main:view.input} : {})},
    render: state => {
      const instances = dvRepeatInstances(spec, view, state);
      state.renderRepeatedSection(spec, instances);
      const host = document.querySelector(`.dv-repeat[data-repeat-section="${CSS.escape(spec.section)}"]`);
      if (host) host.dataset.repeatBuildMs = Number(instances.buildMs || 0).toFixed(2);
    },
  });
});
