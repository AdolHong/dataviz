(function registerViewPackage(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('view.declarative', {protocol: 'dataviz/runtime/v2'});
})(window);
