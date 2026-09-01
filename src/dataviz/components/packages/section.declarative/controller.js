(function installDeclarativeSectionController(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.sectionDeclarative) return;

  const repeatTitle = (template, row, fields) => String(template || '{value}').replace(
    /[{]([^}]+)[}]/g,
    (_, name) => name === 'value'
      ? fields.map(field => row[field] ?? '').join(' / ')
      : row[name] ?? '',
  );
  const repeatInstances = (spec, view, state) => {
    const started = performance.now();
    if (!view) return [];
    const viewController = root.viewDeclarative;
    const repeatedView = spec.input ? {...view, input:spec.input, inputs:{}} : view;
    let selectedGroups = null;
    if (spec.template === 'selection-gallery') {
      const controlKey = spec.control ? `section:${spec.section}/${spec.control}` : null;
      const entry = controlKey ? state.control.state(controlKey) : null;
      const values = Array.isArray(entry?.value) ? entry.value : [];
      if (!values.length) {
        return [];
      }
      const definition = state.dependency_contract?.controls?.[controlKey]?.definition || {};
      const fields = definition.path_fields?.length
        ? definition.path_fields
        : [definition.field || definition.id].filter(Boolean);
      const indexes = spec.by.map(field => fields.indexOf(field));
      selectedGroups = new Set(values.map(value => {
        const path = Array.isArray(value) ? value : [value];
        const projected = indexes.every(index => index >= 0)
          ? indexes.map(index => path[index])
          : path.slice(-spec.by.length);
        return JSON.stringify(projected.length === 1 ? projected[0] : projected);
      }));
    }
    const grouped = new Map();
    viewController.selectRows(repeatedView, state).forEach(row => {
      const values = spec.by.map(field => row[field]);
      const key = JSON.stringify(values);
      if (!grouped.has(key)) grouped.set(key, {key, values, row, rows:[]});
      grouped.get(key).rows.push(row);
    });
    let groups = [...grouped.values()];
    if (selectedGroups) {
      groups = groups.filter(group => selectedGroups.has(JSON.stringify(
        group.values.length === 1 ? group.values[0] : group.values
      )));
    }
    const direction = spec.order === 'desc' ? -1 : 1;
    groups.sort((left, right) => {
      if (spec.order_by) {
        const a = left.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
        const b = right.rows.reduce((sum, row) => sum + Number(row[spec.order_by] ?? 0), 0);
        if (a !== b) return (a - b) * direction;
      }
      return left.values.map(String).join('\u0000').localeCompare(
        right.values.map(String).join('\u0000')
      ) * direction;
    });
    if (spec.limit) groups = groups.slice(0, spec.limit);
    const instances = groups.map(group => ({
      key:group.key,
      id:`${view.id}@${encodeURIComponent(spec.section)}/${group.values.map(value => (
        encodeURIComponent(String(value ?? ''))
      )).join('/')}`,
      sourceViewId:view.id,
      title:repeatTitle(spec.title, group.row, spec.by),
      description:view.description || '',
      searchText:[
        repeatTitle(spec.title, group.row, spec.by),
        ...group.values,
        ...Object.values(group.row),
      ].map(value => String(value ?? '')).join(' '),
      signature:JSON.stringify(group.rows),
      render:() => viewController.build(repeatedView, state, group.rows),
    }));
    instances.buildMs = performance.now() - started;
    return instances;
  };
  const registerRepeatedViews = runtime => {
    const viewSpecs = global.dataviz?.view_specs || [];
    (global.dataviz?.repeat_specs || []).forEach(spec => {
      const view = viewSpecs.find(item => item.id === spec.view);
      if (!view) return;
      runtime.registerView(view.id, {
        inputs:{
          ...(view.inputs || {}),
          ...(spec.input ? {main:spec.input} : view.input ? {main:view.input} : {}),
        },
        render:state => {
          const instances = repeatInstances(spec, view, state);
          state.renderRepeatedSection(spec, instances);
          const host = document.querySelector(
            `.dv-repeat[data-repeat-section="${CSS.escape(spec.section)}"]`
          );
          if (host) host.dataset.repeatBuildMs = Number(instances.buildMs || 0).toFixed(2);
        },
      });
    });
  };

  root.sectionDeclarative = {
    protocol:'dataviz/runtime/v12',
    flow:'document',
    coordinates:false,
    repeatTitle,
    repeatInstances,
    registerRepeatedViews,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('section.declarative', {
    flow:'document',
    coordinates:false,
    owns:['repeat-orchestration', 'section-state'],
  });
})(window);
