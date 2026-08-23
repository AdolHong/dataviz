(function registerSectionPackage(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('section.declarative', {flow: 'document', coordinates: false});
})(window);
