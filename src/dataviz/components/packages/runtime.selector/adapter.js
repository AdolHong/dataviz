(function registerSelectorRuntimeAdapter(global) {
  const components = global.datavizComponents;
  if (!components?.selectors) return;
  components.adapters = components.adapters || new Map();
  components.adapters.set('runtime.selector', components.selectors);
})(window);
