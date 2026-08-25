(function registerCheckboxGroup(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createCheckboxGroup;
  if (api && create) api.register('checkbox-group', create);
})(window);
