(function registerSelectSelector(global) {
  const api = global.datavizComponents?.selectors;
  const create = global.datavizComponents?.createSelectSelector;
  if (api && create) api.register('select', create);
})(window);
