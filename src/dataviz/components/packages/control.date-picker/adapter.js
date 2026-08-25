(function registerDatePicker(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createDatePicker;
  if (api && create) api.register('date-picker', create);
})(window);
