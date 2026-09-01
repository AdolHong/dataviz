(function installPresentationShellController(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  const statuses = new Set([
    'ready', 'loading', 'stale', 'empty', 'error', 'cancelled', 'unavailable',
  ]);
  const panelWidths = Object.freeze({compact:460, regular:680, wide:880});
  const queryGridSelector = [
    ':scope > .header-control__popover > .parameter-form',
    ':scope > .dv-runtime-query-panel > .dv-runtime-query-values',
    ':scope > .dv-query-card > .dv-query-card__body > .parameter-form',
    ':scope > .dv-query-card > .dv-query-card__body > .dv-runtime-query-values',
  ].join(',');
  const apply = (node, status, options = {}) => {
    if (!node || !statuses.has(status)) {
      throw new Error(`Unknown component state: ${status}`);
    }
    node.dataset.componentStatus = status;
    if (status === 'loading') node.setAttribute('aria-busy', 'true');
    else node.removeAttribute('aria-busy');
    if (status === 'error') node.setAttribute('aria-invalid', 'true');
    else node.removeAttribute('aria-invalid');
    if (status === 'unavailable') node.setAttribute('aria-disabled', 'true');
    else node.removeAttribute('aria-disabled');
    const label = node.querySelector?.('[data-component-state-label]');
    if (label) label.textContent = options.label || status;
    node.dispatchEvent(new CustomEvent('dataviz:component-state', {
      bubbles:false,
      detail:{status, label:options.label || status},
    }));
    return status;
  };
  const resolvedPanelWidth = (role, width, count, template) => {
    if (panelWidths[width]) return panelWidths[width];
    if (template === 'stack' || count <= 1) return role === 'dashboard' ? 560 : 480;
    if (count <= 4) return 680;
    return 880;
  };
  const applyControlPanel = (owner, config = {}, options = {}) => {
    if (!owner) return null;
    const role = options.role || owner.dataset.controlRole || 'query';
    const count = Math.max(0, Number(options.count ?? owner.dataset.controlCount ?? 0));
    const requestedTemplate = config.template || owner.dataset.controlTemplate || 'auto';
    const template = requestedTemplate === 'auto'
      ? (role === 'query' && count > 1 ? 'grid' : 'stack')
      : requestedTemplate;
    const configuredColumns = Object.prototype.hasOwnProperty.call(config, 'columns')
      ? config.columns
      : owner.dataset.controlColumns;
    const columns = Number(configuredColumns || (role === 'query' ? 6 : 1));
    const configuredColumnWidth = Object.prototype.hasOwnProperty.call(config, 'column_width')
      ? config.column_width
      : owner.dataset.controlColumnWidth;
    const columnWidth = Number(configuredColumnWidth || (role === 'query' ? 280 : 240));
    const density = config.density || owner.dataset.controlDensity || 'comfortable';
    const widthName = config.width || owner.dataset.controlWidth || 'auto';
    const width = resolvedPanelWidth(role, widthName, count, template);
    owner.dataset.dvControlPanel = '';
    owner.dataset.controlRole = role;
    owner.dataset.controlCount = String(count);
    owner.dataset.controlTemplate = template;
    owner.dataset.controlColumns = String(template === 'stack' ? 1 : columns);
    owner.dataset.controlColumnWidth = String(columnWidth);
    owner.style.setProperty('--dv-control-column-width', `${columnWidth}px`);
    owner.dataset.controlDensity = density;
    owner.dataset.controlWidth = widthName;
    owner.dataset.overlayWidth = String(width);
    const panel = owner.querySelector(':scope > [data-control-panel-body]')
      || owner.querySelector(':scope > .dv-query-card > [data-control-panel-body]')
      || owner.querySelector(':scope > summary + *');
    if (panel) panel.dataset.overlayWidth = String(width);
    const record = owner._datavizOverlayRecord;
    if (record) {
      record.width = width;
      if (record.api?.isOpen()) record.api.reposition();
    }
    owner._datavizControlPanelResizeObserver?.disconnect();
    owner._datavizControlPanelResizeObserver = null;
    if (role === 'query' && template === 'grid') {
      const updateColumns = () => {
        const grid = owner.querySelector(queryGridSelector);
        if (!grid) return;
        const available = grid.clientWidth;
        if (available <= 0) return;
        const gap = Number.parseFloat(global.getComputedStyle(grid).columnGap) || 10;
        const fitting = Math.max(1, Math.floor((available + gap) / (columnWidth + gap)));
        const effective = Math.max(1, Math.min(count || 1, columns, fitting));
        owner.style.setProperty('--dv-control-columns', String(effective));
        owner.dataset.controlEffectiveColumns = String(effective);
      };
      updateColumns();
      if (typeof global.ResizeObserver === 'function') {
        owner._datavizControlPanelResizeObserver = new global.ResizeObserver(updateColumns);
        owner._datavizControlPanelResizeObserver.observe(owner);
        const grid = owner.querySelector(queryGridSelector);
        if (grid) owner._datavizControlPanelResizeObserver.observe(grid);
      }
    } else {
      owner.style.setProperty('--dv-control-columns', String(template === 'stack' ? 1 : columns));
      owner.dataset.controlEffectiveColumns = String(template === 'stack' ? 1 : columns);
    }
    return {
      role, count, template, columns, columnWidth, density, width:widthName,
    };
  };
  const hydrate = (scope = document) => {
    const selector = '[data-component-status]';
    const nodes = scope.matches?.(selector) ? [scope] : [];
    nodes.push(...scope.querySelectorAll?.(selector) || []);
    nodes.forEach(node => apply(node, node.dataset.componentStatus, {
      label:node.dataset.componentStateLabel,
    }));
    const panelSelector = '[data-dv-control-panel]';
    const panels = scope.matches?.(panelSelector) ? [scope] : [];
    panels.push(...scope.querySelectorAll?.(panelSelector) || []);
    panels.forEach(node => applyControlPanel(node));
  };
  root.state = {statuses, apply, hydrate};
  root.presentationShell = {
    protocol:'dataviz/runtime/v13',
    coordinates:false,
    customCanvas:true,
    applyControlPanel,
    hydrate,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('presentation.shell', {
    coordinates:false,
    customCanvas:true,
    owns:['layout', 'theme', 'component-state', 'control-panel'],
  });
})(window);
