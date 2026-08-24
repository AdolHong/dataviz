(function registerDataPipelineAdapter(global) {
  'use strict';
  const install = event => {
    const runtime = event?.detail || global.datavizRuntime;
    const components = global.datavizComponents;
    const services = global.datavizRuntimeServices;
    if (!runtime || !components?.dataPipeline || !services || runtime.dataPipeline) return;
    runtime.interactiveAdapters = components.dataPipeline.createInteractiveAdapters(
      runtime,
      services,
    );
    runtime.dataPipeline = components.dataPipeline;
    global.datavizInteractiveAdapters = runtime.interactiveAdapters;
    global.dataviz.data = components.dataPipeline.createDataApi(services);
    components.adapters = components.adapters || new Map();
    components.adapters.set('data.pipeline', components.dataPipeline);
  };
  install();
  global.addEventListener('dataviz:runtime-ready', install, {once:true});
})(window);
