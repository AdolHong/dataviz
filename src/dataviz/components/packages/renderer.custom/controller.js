(function installRendererContractQueue(global) {
  const root = global.datavizComponents = global.datavizComponents || {};
  root.rendererContracts = root.rendererContracts || [];
  root.installRendererContracts = runtime => {
    if (!runtime || runtime.testRenderer) return;
    runtime.testRenderer = async function testRenderer(rendererId, cases = [{}]) {
      const renderer = runtime.renderers.get(rendererId);
      if (!renderer) return {renderer: rendererId, valid: false, failures: [{phase: 'lookup', message: 'Renderer is not registered'}]};
      const failures = [];
      const warnings = [];
      const lifecycle = {mounts:0, updates:0, disposes:0};
      for (const [index, descriptor] of cases.entries()) {
        const rootNode = document.createElement('article');
        const body = document.createElement('div');
        rootNode.append(body);
        const context = {
          root:rootNode,
          body,
          viewId:`contract-${index}`,
          runtime,
          descriptor,
          assets:global.datavizRuntimeServices?.assets,
        };
        let state;
        let mountedChildren = 0;
        for (const phase of ['validate', 'mount', 'update', 'dispose']) {
          if (typeof renderer[phase] !== 'function') {
            if (phase !== 'validate') failures.push({case: index, phase, message: `Missing ${phase}()`});
            continue;
          }
          try {
            if (phase === 'validate') await renderer.validate(descriptor);
            else if (phase === 'mount') {
              state = await renderer.mount(context, descriptor);
              lifecycle.mounts += 1;
              mountedChildren = body.childElementCount;
              if (!mountedChildren) {
                failures.push({case:index, phase, message:'mount() completed without adding visible DOM content'});
                break;
              }
              if (state == null) {
                warnings.push({
                  case:index,
                  phase,
                  code:'custom_renderer_state_missing',
                  message:'mount() returned no view-scoped state for update/dispose',
                });
              }
            } else if (phase === 'update') {
              state = await renderer.update(context, descriptor, state) ?? state;
              lifecycle.updates += 1;
              if (body.childElementCount > Math.max(mountedChildren + 2, mountedChildren * 2)) {
                warnings.push({
                  case:index,
                  phase,
                  code:'custom_renderer_root_growth',
                  message:'update() added substantially more top-level DOM roots; check for repeated mounts',
                });
              }
            } else {
              await renderer.dispose(context, state);
              lifecycle.disposes += 1;
              await Promise.resolve();
              if (body.childElementCount) {
                failures.push({
                  case:index,
                  phase,
                  message:`dispose() left ${body.childElementCount} DOM root(s) mounted`,
                });
              }
            }
          } catch (error) {
            failures.push({case: index, phase, message: error?.message || String(error), stack: error?.stack || null});
            break;
          }
        }
      }
      return {
        renderer:rendererId,
        valid:failures.length === 0,
        cases:cases.length,
        lifecycle,
        warnings,
        failures,
      };
    };
  };
})(window);
