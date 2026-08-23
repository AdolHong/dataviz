(function registerDataPackage(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('data.pipeline', {protocol: 'dataviz/runtime/v1'});
})(window);
