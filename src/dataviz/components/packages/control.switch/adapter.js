(function registerSwitch(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createSwitch;
  if (api && create) api.register('switch', create);
})(window);
