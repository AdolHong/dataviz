(function installRendererContractQueue(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.rendererContracts = root.rendererContracts || [];
  root.installRendererContracts = runtime => {
    if (!runtime || runtime.testRenderer) return;
    runtime.testRenderer = async function testRenderer(rendererId, cases = [{}]) {
      const renderer = runtime.renderers.get(rendererId);
      if (!renderer) return {renderer: rendererId, valid: false, failures: [{phase: 'lookup', message: 'Renderer is not registered'}]};
      const failures = [];
      for (const [index, descriptor] of cases.entries()) {
        const rootNode = document.createElement('article');
        const body = document.createElement('div');
        rootNode.append(body);
        const context = {root: rootNode, body, viewId: `contract-${index}`, runtime, descriptor};
        let state;
        for (const phase of ['validate', 'mount', 'update', 'dispose']) {
          if (typeof renderer[phase] !== 'function') {
            if (phase !== 'validate') failures.push({case: index, phase, message: `Missing ${phase}()`});
            continue;
          }
          try {
            if (phase === 'validate') await renderer.validate(descriptor);
            else if (phase === 'mount') state = await renderer.mount(context, descriptor);
            else if (phase === 'update') state = await renderer.update(context, descriptor, state) ?? state;
            else await renderer.dispose(context, state);
          } catch (error) {
            failures.push({case: index, phase, message: error?.message || String(error), stack: error?.stack || null});
            break;
          }
        }
      }
      return {renderer: rendererId, valid: failures.length === 0, cases: cases.length, failures};
    };
  };
})(window);
