(function registerPresentationShellAdapter(global) {
  'use strict';
  const install = event => {
    const runtime = event?.detail || global.datavizRuntime;
    const components = global.datavizComponents;
    const shell = components?.presentationShell;
    if (!runtime || !shell || runtime.presentationAdapter) return;
    const canvas = document.querySelector('.dv-canvas');
    if (canvas) {
      canvas.dataset.presentationPackage = 'presentation.shell';
      shell.hydrate(canvas);
    }
    const adapter = {
      protocol:'dataviz/runtime/v15',
      state:components.state,
      hydrate:shell.hydrate,
      dispose() {},
    };
    runtime.presentationAdapter = adapter;
    components.adapters = components.adapters || new Map();
    components.adapters.set('presentation.shell', adapter);
  };
  install();
  global.addEventListener('dataviz:runtime-ready', install, {once:true});
})(window);
