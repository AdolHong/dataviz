(function installPathUtilities(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.controlPathOptions) return;
  root.controlPathOptions = ({input}) => Array.from(input.options).map(option => {
    try { return JSON.parse(option.value); } catch (_error) { return [option.value]; }
  });
})(window);
