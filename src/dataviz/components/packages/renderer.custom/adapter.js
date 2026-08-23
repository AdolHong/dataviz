(function scheduleRendererContractAdapter(global) {
  const install = () => global.datavizComponents?.installRendererContracts?.(global.datavizRuntime);
  install();
  global.addEventListener('dataviz:runtime-ready', install, {once: true});
})(window);
