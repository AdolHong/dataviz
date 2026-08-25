(function registerCheckbox(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createCheckbox;
  if (api && create) api.register('checkbox', create);
})(window);
