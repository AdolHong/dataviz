(function installPresentationShellController(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  const statuses = new Set([
    'ready', 'loading', 'stale', 'empty', 'error', 'cancelled', 'unavailable',
  ]);
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
  const hydrate = (scope = document) => {
    const selector = '[data-component-status]';
    const nodes = scope.matches?.(selector) ? [scope] : [];
    nodes.push(...scope.querySelectorAll?.(selector) || []);
    nodes.forEach(node => apply(node, node.dataset.componentStatus, {
      label:node.dataset.componentStateLabel,
    }));
  };
  root.state = {statuses, apply, hydrate};
  root.presentationShell = {
    protocol:'dataviz/runtime/v2',
    coordinates:false,
    customCanvas:true,
    hydrate,
  };
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('presentation.shell', {
    coordinates:false,
    customCanvas:true,
    owns:['layout', 'theme', 'component-state'],
  });
})(window);
