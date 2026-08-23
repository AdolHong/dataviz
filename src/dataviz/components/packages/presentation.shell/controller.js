(function registerPresentationPackage(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.descriptors = root.descriptors || new Map();
  root.descriptors.set('presentation.shell', {coordinates: false, customCanvas: true});
})(window);
