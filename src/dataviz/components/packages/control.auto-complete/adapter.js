(function registerAutoComplete(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createAutoComplete;
  if (api && create) api.register('auto-complete', create);
})(window);
