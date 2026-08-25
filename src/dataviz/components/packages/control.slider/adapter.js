(function registerSlider(global) {
  const api = global.datavizComponents?.controls;
  const create = global.datavizComponents?.createSlider;
  if (api && create) api.register('slider', create);
})(window);
