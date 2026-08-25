(function registerInputNumber(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createInputNumber;
  if (api && create) api.register('input-number', create);
})(window);
