(function installPresentationShellController(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  const statuses = new Set([
    'ready', 'loading', 'stale', 'empty', 'error', 'cancelled', 'unavailable',
  ]);
  const panelWidths = Object.freeze({compact:460, regular:680, wide:880});
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
      ? (count <= 1 ? 'stack' : 'grid')
      : requestedTemplate;
    const configuredColumns = Object.prototype.hasOwnProperty.call(config, 'columns')
      ? config.columns
      : owner.dataset.controlColumns;
    const columns = Number(configuredColumns || 0);
    const density = config.density || owner.dataset.controlDensity || 'comfortable';
    const widthName = config.width || owner.dataset.controlWidth || 'auto';
    const width = resolvedPanelWidth(role, widthName, count, template);
    owner.dataset.dvControlPanel = '';
    owner.dataset.controlRole = role;
    owner.dataset.controlCount = String(count);
    owner.dataset.controlTemplate = template;
    owner.dataset.controlColumns = String(template === 'stack' ? 1 : (columns || 'auto'));
    owner.dataset.controlDensity = density;
    owner.dataset.controlWidth = widthName;
    owner.dataset.overlayWidth = String(width);
    const panel = owner.querySelector(':scope > summary + *');
    if (panel) panel.dataset.overlayWidth = String(width);
    const record = owner._datavizOverlayRecord;
    if (record) {
      record.width = width;
      if (record.api?.isOpen()) record.api.reposition();
    }
    return {role, count, template, columns: columns || null, density, width:widthName};
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
    protocol:'dataviz/runtime/v2',
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
