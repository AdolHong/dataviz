(function registerControlRuntimeAdapter(global) {
  const components = global.datavizComponents;
  if (!components?.controls) return;
  components.adapters = components.adapters || new Map();
  components.adapters.set('runtime.control', components.controls);
})(window);
