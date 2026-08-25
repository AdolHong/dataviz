(function registerInput(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createInput;
  if (api && create) api.register('input', create);
})(window);
