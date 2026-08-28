(function registerMultipleInput(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createMultipleInput;
  if (api && create) api.register('multiple-input', create);
})(window);
