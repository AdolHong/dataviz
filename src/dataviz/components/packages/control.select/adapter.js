(function registerSelectControl(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createSelectControl;
  if (api && create) api.register('select', create);
})(window);
