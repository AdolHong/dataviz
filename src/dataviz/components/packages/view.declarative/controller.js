(function installDeclarativeViewController(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.viewDeclarative) return;

  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
  }[char]));
  const numericAggregate = (items, operation = 'sum', select = value => value) => {
    let count = 0;
    let sum = 0;
    let minimum = Infinity;
    let maximum = -Infinity;
    for (const item of items) {
      const value = Number(select(item) ?? 0);
      count += 1;
      sum += value;
      if (value < minimum) minimum = value;
      if (value > maximum) maximum = value;
    }
    if (operation === 'count') return count;
    if (operation === 'mean') return sum / Math.max(count, 1);
    if (operation === 'min') return minimum;
    if (operation === 'max') return maximum;
    return sum;
  };
  const inputReferences = (view, state) => (
    state.dependency_contract?.views?.[view.id]?.inputs || {}
  );
  const mainInputReference = (view, state) => {
    const references = inputReferences(view, state);
    return references.main || Object.values(references)[0];
  };
  const controlBinding = (view, state, layerId = null) => (
    layerId == null
      ? (state.dependency_contract?.views?.[view.id]?.control_binding || null)
      : (state.dependency_contract?.views?.[view.id]?.layer_control_bindings?.[layerId] || null)
  );
  const bindingValue = (binding, row, fields = binding?.fields || []) => {
    if (!binding || !row || typeof row !== 'object') return null;
    const values = fields.map(field => row[field]);
    return values.length === 1 ? values[0] : values;
  };
  const bindingDatum = (binding, row, sourceLayer = null) => {
    const value = bindingValue(binding, row);
    if (!(binding?.writes || []).length && sourceLayer == null) return value;
    return {
      __datavizControlValue:value,
      ...(sourceLayer == null ? {} : {__datavizSourceLayer:sourceLayer}),
      __datavizControlWrites:Object.fromEntries(
        (binding.writes || []).map(write => [
          write.control,
          bindingValue(binding, row, write.fields || []),
        ])
      ),
    };
  };
  const bindingDescriptor = (view, state, rows, layerId = null) => {
    const binding = controlBinding(view, state, layerId);
    if (!binding) return null;
    return {
      ...binding,
      state:structuredClone(state.control.state(binding.control)),
      values:rows.map(row => bindingValue(binding, row)),
    };
  };
  const bindingValueSignature = value => JSON.stringify(value);
  const bindingSelected = (binding, value) => new Set(
    (Array.isArray(binding?.state?.value) ? binding.state.value : [binding?.state?.value])
      .filter(value => value != null)
      .map(bindingValueSignature)
  ).has(bindingValueSignature(value));
  const mapViewportRevision = values => {
    let hash = 2166136261;
    const text = JSON.stringify(values);
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return `dataviz-map-${values.length}-${(hash >>> 0).toString(16)}`;
  };
  const selectRows = (view, state) => {
    const contract = state.dependency_contract?.views?.[view.id]?.filter_contract || [];
    const boundControl = controlBinding(view, state)?.control;
    const reference = mainInputReference(view, state);
    return state.data.table(reference).rows().filter(row => contract.every(item => (
      item.key === boundControl
      || state.control.matches(row, item, state.control.state(item.key))
    )));
  };
  const selectLayerRows = (view, layer, state) => {
    const contract = state.dependency_contract?.views?.[view.id]?.filter_contract || [];
    const boundControl = controlBinding(view, state, layer.id)?.control;
    const reference = inputReferences(view, state)[layer.id];
    let rows = state.data.table(reference).rows().filter(row => contract.every(item => (
      item.key === boundControl
      || state.control.matches(row, item, state.control.state(item.key))
    )));
    if (view.sort) {
      const descending = view.sort.startsWith('-');
      const field = descending ? view.sort.slice(1) : view.sort;
      rows.sort((a, b) => (
        a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0
      ) * (descending ? -1 : 1));
    }
    return view.limit ? rows.slice(0, view.limit) : rows;
  };
  const aggregate = (rows, groupFields, valueFields, operation = 'sum') => {
    const groups = new Map();
    rows.forEach(row => {
      const key = JSON.stringify(groupFields.map(field => row[field]));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    return [...groups].map(([key, values]) => {
      const parsed = JSON.parse(key);
      const output = Object.fromEntries(
        groupFields.map((field, index) => [field, parsed[index]])
      );
      valueFields.forEach(valueField => {
        output[valueField] = numericAggregate(values, operation, row => row[valueField]);
      });
      return output;
    });
  };
  const prepareRows = (view, state) => {
    let rows = selectRows(view, state);
    const valueFields = view.template === 'heatmap'
      ? [view.z]
      : (Array.isArray(view.y) ? view.y : [view.y || view.value || view.z]).filter(Boolean);
    const groups = (view.template === 'heatmap'
      ? [view.x, view.y]
      : [view.x || view.label, view.series]).filter(Boolean);
    const operation = view.template === 'metric'
      ? 'none'
      : (view.aggregate || (['scatter', 'map', 'table', 'perspective'].includes(view.template)
        ? 'none'
        : 'sum'));
    if (operation !== 'none' && valueFields.length && groups.length) {
      rows = aggregate(rows, groups, valueFields, operation);
    }
    if (view.sort) {
      const descending = view.sort.startsWith('-');
      const field = descending ? view.sort.slice(1) : view.sort;
      rows.sort((a, b) => (
        a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0
      ) * (descending ? -1 : 1));
    }
    return view.limit ? rows.slice(0, view.limit) : rows;
  };
  const mapPlotlyDescriptor = (view, rows, binding, traceOptions) => {
    const layoutOptions = view.options?.layout || {};
    const {geo: geoOptions = {}, ...layoutRest} = layoutOptions;
    const selectedpoints = binding ? rows.map((row, index) => (
      bindingSelected(binding, bindingValue(binding, row)) ? index : null
    )).filter(index => index != null) : undefined;
    const common = {
      name:view.title,
      text:view.label ? rows.map(row => row[view.label]) : undefined,
      customdata:binding ? rows.map(row => bindingDatum(binding, row)) : undefined,
      selectedpoints,
    };
    let trace;
    let viewportValues;
    if (view.mark === 'point') {
      const longitude = rows.map(row => Number(row[view.longitude]));
      const latitude = rows.map(row => Number(row[view.latitude]));
      viewportValues = longitude.map((value, index) => [value, latitude[index]]);
      const invalidIndex = longitude.findIndex((value, index) => (
        !Number.isFinite(value) || !Number.isFinite(latitude[index])
      ));
      if (invalidIndex >= 0) {
        throw new Error(
          `Map View ${view.id} requires finite longitude/latitude at row ${invalidIndex + 1}`
        );
      }
      trace = {
        ...common,
        type:'scattergeo',
        mode:'markers',
        lon:longitude,
        lat:latitude,
        hovertemplate:view.label ? '%{text}<extra></extra>' : undefined,
        ...traceOptions,
        marker:{
          size:view.size ? rows.map(row => row[view.size]) : 9,
          color:view.color ? rows.map(row => row[view.color]) : undefined,
          opacity:0.82,
          line:{width:0.8, color:'rgba(255,255,255,0.9)'},
          ...(traceOptions.marker || {}),
        },
      };
    } else {
      const locations = rows.map(row => row[view.data_key]);
      viewportValues = locations;
      const seen = new Map();
      locations.forEach((value, index) => {
        const key = JSON.stringify(value);
        if (seen.has(key)) {
          throw new Error(
            `Map View ${view.id} requires unique data_key ${view.data_key}; duplicate at rows ${seen.get(key) + 1} and ${index + 1}`
          );
        }
        seen.set(key, index);
      });
      trace = {
        ...common,
        type:'choropleth',
        locations,
        z:rows.map(row => row[view.color]),
        featureidkey:view.feature_key,
        hovertemplate:view.label
          ? '%{text}<br>%{z}<extra></extra>'
          : '%{location}<br>%{z}<extra></extra>',
        ...traceOptions,
        marker:{line:{width:0.7, color:'rgba(255,255,255,0.75)'}, ...(traceOptions.marker || {})},
      };
    }
    return {
      type:'plotly',
      data:[trace],
      layout:{
        margin:{l:8, r:8, t:8, b:8},
        paper_bgcolor:'transparent',
        plot_bgcolor:'transparent',
        showlegend:false,
        geo:{
          fitbounds:'locations',
          visible:false,
          bgcolor:'rgba(0,0,0,0)',
          uirevision:mapViewportRevision(viewportValues || []),
          ...geoOptions,
        },
        ...layoutRest,
      },
      config:view.config,
      controlBinding:binding,
      geojsonAsset:view.mark === 'region' ? view.geojson : undefined,
    };
  };
  const layeredMapPlotlyDescriptor = (view, state, layerRows) => {
    const traces = [];
    const viewportValues = [];
    const geojsonAssets = [];
    const controlBindings = {};
    view.layers.forEach((layer, layerIndex) => {
      const rows = layerRows[layer.id] || [];
      const binding = bindingDescriptor(view, state, rows, layer.id);
      if (binding) controlBindings[layer.id] = binding;
      const traceOptions = {
        ...(view.options?.trace || {}),
        ...(layer.options?.trace || {}),
      };
      const projected = mapPlotlyDescriptor(
        {...view, ...layer, layers:[]},
        rows,
        binding,
        traceOptions,
      );
      const trace = projected.data[0];
      trace.name = layer.options?.name || layer.id;
      if (binding && Array.isArray(trace.customdata)) {
        trace.customdata = rows.map(row => bindingDatum(binding, row, layer.id));
      }
      traces.push(trace);
      const layerViewport = layer.mark === 'point'
        ? rows.map(row => [Number(row[layer.longitude]), Number(row[layer.latitude])])
        : rows.map(row => row[layer.data_key]);
      viewportValues.push(...layerViewport.map(value => [layer.id, value]));
      if (layer.mark === 'region') {
        geojsonAssets.push({trace:layerIndex, asset:layer.geojson});
      }
    });
    const layoutOptions = view.options?.layout || {};
    const {geo: geoOptions = {}, ...layoutRest} = layoutOptions;
    const stableViewport = viewportValues
      .map(value => JSON.stringify(value))
      .sort()
      .map(value => JSON.parse(value));
    return {
      type:'plotly',
      data:traces,
      layout:{
        margin:{l:8, r:8, t:8, b:8},
        paper_bgcolor:'transparent',
        plot_bgcolor:'transparent',
        showlegend:view.options?.showlegend ?? traces.length > 1,
        geo:{
          fitbounds:'locations',
          visible:false,
          bgcolor:'rgba(0,0,0,0)',
          uirevision:mapViewportRevision(stableViewport),
          ...geoOptions,
        },
        ...layoutRest,
      },
      config:view.config,
      controlBindings,
      geojsonAssets,
    };
  };
  const plotlyDescriptor = (view, rows, binding = null) => {
    const groups = view.series ? [...new Set(rows.map(row => row[view.series]))] : [null];
    const measures = Array.isArray(view.y) ? view.y : [view.y];
    const traceOptions = view.options?.trace || {};
    if (view.template === 'map') {
      return mapPlotlyDescriptor(view, rows, binding, traceOptions);
    }
    const traces = groups.flatMap(group => measures.map(measure => {
      const selected = group == null ? rows : rows.filter(row => row[view.series] === group);
      const common = {
        name:[group, measures.length > 1 ? measure : null].filter(Boolean).join(' · ') || view.title,
        x:selected.map(row => row[view.x]),
        y:selected.map(row => row[measure]),
        customdata:binding ? selected.map(row => bindingDatum(binding, row)) : undefined,
        selectedpoints:binding ? selected.map((row, index) => (
          bindingSelected(binding, bindingValue(binding, row)) ? index : null
        )).filter(index => index != null) : undefined,
      };
      if (view.template === 'line') return {
        ...common,
        type:'scatter',
        mode:'lines+markers',
        ...traceOptions,
        line:{width:2.25, ...(traceOptions.line || {})},
        marker:{size:6, ...(traceOptions.marker || {})},
      };
      if (view.template === 'scatter') {
        const sizes = view.size
          ? selected.map(row => Number(row[view.size])).filter(Number.isFinite)
          : [];
        const maximumSize = sizes.length ? Math.max(...sizes) : 0;
        return {
        ...common,
        type:'scatter',
        mode:'markers',
        ...traceOptions,
        marker:{
          size:view.size ? selected.map(row => row[view.size]) : 9,
          color:view.color ? selected.map(row => row[view.color]) : undefined,
          ...(view.size && maximumSize > 0 ? {
            sizemode:'area',
            sizeref:(2 * maximumSize) / (30 ** 2),
            sizemin:6,
          } : {}),
          ...(traceOptions.marker || {}),
        },
      };
      }
      return {...common, type:'bar', ...traceOptions};
    }));
    if (view.template === 'pie') {
      traces.splice(0, traces.length, {
        type:'pie',
        labels:rows.map(row => row[view.label || view.x]),
        values:rows.map(row => row[view.value || view.y]),
        customdata:binding ? rows.map(row => bindingDatum(binding, row)) : undefined,
        pull:binding ? rows.map(row => (
          bindingSelected(binding, bindingValue(binding, row)) ? 0.08 : 0
        )) : undefined,
        hole:view.options?.hole || 0,
      });
    }
    if (view.template === 'heatmap') {
      const xs = [...new Set(rows.map(row => row[view.x]))];
      const ys = [...new Set(rows.map(row => row[view.y]))];
      traces.splice(0, traces.length, {
        type:'heatmap', x:xs, y:ys,
        z:ys.map(y => xs.map(x => rows.find(row => (
          row[view.x] === x && row[view.y] === y
        ))?.[view.z] ?? null)),
        colorscale:view.options?.colorscale || 'Viridis',
      });
    }
    if (view.template === 'radar') {
      const theta = [...view.columns, view.columns[0]];
      traces.splice(0, traces.length, ...rows.map(row => ({
        type:'scatterpolar',
        mode:'lines+markers',
        fill:view.options?.fill || 'toself',
        name:String(row[view.label] ?? ''),
        theta,
        r:[...view.columns.map(field => row[field]), row[view.columns[0]]],
        customdata:binding
          ? theta.map(() => bindingDatum(binding, row))
          : undefined,
        ...traceOptions,
      })));
    }
    return {
      type:'plotly',
      data:traces,
      layout:{
        margin:{l:48, r:20, t:20, b:46},
        paper_bgcolor:'transparent',
        plot_bgcolor:'transparent',
        barmode:view.template === 'stacked-bar' ? 'stack' : (view.options?.barmode || 'group'),
        legend:{orientation:'h', y:1.12},
        ...(view.template === 'radar' ? {
          polar:{radialaxis:{visible:true, rangemode:'tozero'}},
        } : {}),
        ...view.options?.layout,
      },
      config:view.config,
      controlBinding:binding,
    };
  };
  const build = (view, state, preparedRows = null) => {
    const references = inputReferences(view, state);
    const rawInputReference = references.main || Object.values(references)[0];
    const rawInput = rawInputReference ? state.data.output(rawInputReference) : undefined;
    if (view.template === 'markdown') {
      const content = view.text ?? rawInput ?? '';
      return {
        type:'html',
        html:`<div class="dv-prose">${escape(content).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>')}</div>`,
      };
    }
    if (view.template === 'image') return {
      type:'html',
      html:`<img class="dv-image" src="${escape(view.url || '')}" alt="${escape(view.title || '')}">`,
    };
    if (
      view.template === 'metric'
      && !Array.isArray(rawInput)
      && !rawInput?.__datavizArrowOutput
      && rawInput != null
    ) {
      const formatted = typeof rawInput === 'number'
        ? new Intl.NumberFormat(undefined, view.options?.format || {maximumFractionDigits:2}).format(rawInput)
        : String(rawInput);
      return {
        type:'html',
        html:`<div class="dv-metric"><strong>${escape(formatted)}</strong><span>${escape(view.label || view.title || '')}</span></div>`,
      };
    }
    if (view.template === 'map' && (view.layers || []).length) {
      const layerRows = Object.fromEntries(
        view.layers.map(layer => [layer.id, selectLayerRows(view, layer, state)])
      );
      const descriptor = layeredMapPlotlyDescriptor(view, state, layerRows);
      const empty = Object.values(layerRows).every(rows => rows.length === 0);
      return {
        ...descriptor,
        empty,
        emptyMessage:view.options?.empty_text || 'No rows match the current selections.',
      };
    }
    let rows = preparedRows == null ? prepareRows(view, state) : [...preparedRows];
    if (preparedRows != null) {
      const valueFields = view.template === 'heatmap'
        ? [view.z]
        : (Array.isArray(view.y) ? view.y : [view.y || view.value || view.z]).filter(Boolean);
      const groups = (view.template === 'heatmap'
        ? [view.x, view.y]
        : [view.x || view.label, view.series]).filter(Boolean);
      const operation = view.template === 'metric'
        ? 'none'
        : (view.aggregate || (['scatter', 'map', 'table', 'perspective'].includes(view.template)
          ? 'none'
          : 'sum'));
      if (operation !== 'none' && valueFields.length && groups.length) {
        rows = aggregate(rows, groups, valueFields, operation);
      }
      if (view.sort) {
        const descending = view.sort.startsWith('-');
        const field = descending ? view.sort.slice(1) : view.sort;
        rows.sort((a, b) => (
          a[field] > b[field] ? 1 : a[field] < b[field] ? -1 : 0
        ) * (descending ? -1 : 1));
      }
      if (view.limit) rows = rows.slice(0, view.limit);
    }
    const binding = bindingDescriptor(view, state, rows);
    if (view.template === 'table') return {
      type:'table', rows,
      empty:rows.length === 0,
      emptyMessage:view.options?.empty_text || 'No rows match the current selections.',
      columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {}),
      limit:view.limit, options:view.options, config:view.config,
      controlBinding:binding,
    };
    if (view.template === 'perspective') return {
      type:'perspective', rows,
      empty:rows.length === 0,
      emptyMessage:view.options?.empty_text || 'No rows match the current selections.',
      columns:view.columns?.length ? view.columns : Object.keys(rows[0] || {}),
      config:view.config, limit:view.limit,
    };
    if (view.template === 'custom') {
      const inputs = Object.fromEntries(
        Object.entries(references).map(([name, reference]) => [name, state.data.output(reference)])
      );
      return {
        type:view.renderer, rows, inputs, view, options:view.options, config:view.config,
        controlBinding:binding,
      };
    }
    if (view.template === 'metric') {
      const field = view.value || view.y;
      const operation = view.aggregate || 'sum';
      const value = numericAggregate(rows, operation, row => row[field]);
      const formatted = Number.isFinite(value)
        ? new Intl.NumberFormat(undefined, view.options?.format || {maximumFractionDigits:2}).format(value)
        : '—';
      return {
        type:'html',
        html:`<div class="dv-metric"><strong>${escape(formatted)}</strong><span>${escape(view.label || field || '')}</span></div>`,
      };
    }
    const descriptor = plotlyDescriptor(view, rows, binding);
    return {
      ...descriptor,
      empty:rows.length === 0,
      emptyMessage:view.options?.empty_text || 'No rows match the current selections.',
    };
  };

  function registerViews(runtime) {
    const views = global.dataviz?.view_specs || [];
    const repeated = new Set((global.dataviz?.repeat_specs || []).map(spec => spec.view));
    views.filter(view => !repeated.has(view.id)).forEach(view => runtime.registerView(view.id, {
      inputs:(view.layers || []).length
        ? Object.fromEntries(view.layers.map(layer => [layer.id, layer.input]))
        : {...(view.inputs || {}), ...(view.input ? {main:view.input} : {})},
      render:state => state.renderView(view.id, () => build(view, state)),
    }));
  }

  root.viewDeclarative = {
    protocol:'dataviz/runtime/v14',
    escape,
    numericAggregate,
    inputReferences,
    mainInputReference,
    selectRows,
    controlBinding,
    bindingValue,
    bindingDatum,
    prepareRows,
    mapPlotlyDescriptor,
    layeredMapPlotlyDescriptor,
    build,
    registerViews,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('view.declarative', {
    protocol:'dataviz/runtime/v14',
    owns:['descriptor-builders', 'renderer-lifecycle'],
  });
})(window);
