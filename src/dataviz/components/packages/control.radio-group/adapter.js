(function registerRadioGroup(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createRadioGroup;
  if (api && create) api.register('radio-group', create);
})(window);
