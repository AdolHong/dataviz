(function registerOverlayAdapter(global) {
  const components = global.datavizComponents;
  if (!components?.overlay) return;
  components.adapters = components.adapters || new Map();
  components.adapters.set('runtime.overlay', {
    hydrate: scope => components.overlay.hydrate(scope || document),
    closeAll: options => components.overlay.closeAll(options || {}),
  });
})(window);
