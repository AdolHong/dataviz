(function registerSegmentedSelector(global) {
  const api = global.datavizComponents?.selectors;
  const create = global.datavizComponents?.createSegmentedSelector;
  if (api && create) api.register('segmented', create);
})(window);
