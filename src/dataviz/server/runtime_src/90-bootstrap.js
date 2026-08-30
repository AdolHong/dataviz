// Owner: DOM/bootstrap event wiring after every Runtime owner is registered.
let datavizSelectionScheduled = false;
let datavizSelectionQueue = Promise.resolve();
const scheduleDatavizSelection = event => {
  // Capture the user's native control value before asynchronous initialization
  // or option-domain reconciliation can rebuild the underlying <select>.
  try {
    datavizCaptureSelectionIntent(event?.currentTarget || event?.target);
    readSelectionInputs();
  } catch (error) {
    console.error('[dataviz:selections]', error);
    return;
  }
  if (datavizSelectionScheduled) return;
  datavizSelectionScheduled = true;
  queueMicrotask(() => {
    datavizSelectionScheduled = false;
    // A native select emits both input and change for one user action. Coalesce
    // that event pair in the current task, then serialize any later actions
    // behind the in-flight Interactive branch. Selection is an immediate data
    // contract; it must not depend on a browser timer being scheduled promptly.
    const initialization = datavizRuntime.initializationPromise || Promise.resolve();
    datavizSelectionQueue = Promise.all([
      datavizSelectionQueue.catch(() => undefined),
      initialization.catch(() => undefined),
    ])
      .then(() => window.dataviz.applySelections())
      .catch(error => console.error('[dataviz:selections]', error));
  });
};
const datavizEscape = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

// The Server shell and Canvas iframe form one vertical reading surface. While
// the shell still has scrollable Header content (for example an expanded Query
// tray), consume downward wheel movement there before scrolling the iframe.
// On the way back, reveal the Header only after the Canvas has reached its top.
// Portable reports run at the top level and therefore bypass this bridge.
const routeDatavizCanvasWheelToShell = event => {
  if (window.parent === window || event.ctrlKey || !event.deltaY) return;
  let parentWindow;
  let parentDocument;
  try {
    parentWindow = window.parent;
    parentDocument = parentWindow.document;
    const frame = parentDocument.querySelector('#canvas-frame');
    if (frame?.contentWindow !== window) return;
  } catch (_) {
    return;
  }
  const shellScroller = parentDocument.scrollingElement;
  const canvasScroller = document.scrollingElement;
  if (!shellScroller || !canvasScroller) return;
  const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
    ? 16
    : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
      ? parentWindow.innerHeight
      : 1;
  const delta = event.deltaY * unit;
  const shellMax = Math.max(0, shellScroller.scrollHeight - parentWindow.innerHeight);
  const shellTop = shellScroller.scrollTop;
  const canvasTop = canvasScroller.scrollTop;
  const routeDown = delta > 0 && shellTop < shellMax - 1;
  const routeUp = delta < 0 && canvasTop <= 1 && shellTop > 1;
  if (!routeDown && !routeUp) return;
  event.preventDefault();
  parentWindow.scrollBy({top: delta, left: 0, behavior: 'auto'});
};
window.addEventListener('wheel', routeDatavizCanvasWheelToShell, {
  capture: true,
  passive: false,
});

const syncPortableChoices = control => control.querySelector('.dv-control')?._syncControl?.();
const datavizRuntimeQueryToggle = document.querySelector('[data-runtime-query-toggle]');
const datavizRuntimeQueryPanel = document.querySelector('#dv-runtime-query-panel');
const datavizRuntimeShortcutHelp = document.querySelector('[data-runtime-shortcut-help]');
const datavizRuntimeShortcutToast = document.querySelector('[data-runtime-shortcut-toast]');
let datavizRuntimeShortcutToastTimer;
const showDatavizRuntimeShortcutToast = message => {
  if (!datavizRuntimeShortcutToast) return;
  clearTimeout(datavizRuntimeShortcutToastTimer);
  datavizRuntimeShortcutToast.textContent = message;
  datavizRuntimeShortcutToast.hidden = false;
  requestAnimationFrame(() => datavizRuntimeShortcutToast.classList.add('is-visible'));
  datavizRuntimeShortcutToastTimer = setTimeout(() => {
    datavizRuntimeShortcutToast.classList.remove('is-visible');
    datavizRuntimeShortcutToastTimer = setTimeout(() => {
      datavizRuntimeShortcutToast.hidden = true;
    }, 160);
  }, 1800);
};
const setDatavizRuntimeQueryOpen = open => {
  if (!datavizRuntimeQueryToggle || !datavizRuntimeQueryPanel) return false;
  const expanded = Boolean(open);
  const tray = datavizRuntimeQueryPanel.closest('.dv-runtime-query-tray');
  datavizRuntimeQueryToggle.setAttribute('aria-expanded', String(expanded));
  datavizRuntimeQueryToggle.setAttribute(
    'aria-label',
    expanded ? 'Collapse query parameters' : 'Expand query parameters',
  );
  datavizRuntimeQueryToggle.title = `${expanded ? 'Collapse query parameters' : 'Expand query parameters'} (Q)`;
  if (tray) tray.dataset.open = String(expanded);
  datavizRuntimeQueryPanel.hidden = !expanded;
  return expanded;
};
datavizRuntimeQueryToggle?.addEventListener('click', () => {
  setDatavizRuntimeQueryOpen(
    datavizRuntimeQueryToggle.getAttribute('aria-expanded') !== 'true',
  );
});
const datavizKeyboardTargetIsEditable = target => target instanceof Element && Boolean(
  target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')
);
const datavizKeyboardShortcutCommand = event => {
  if (event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229) return null;
  if (document.querySelector('dialog[open]')) return null;
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key === 'Enter') return 'run-query';
  if (event.ctrlKey || event.metaKey || event.altKey || datavizKeyboardTargetIsEditable(event.target)) return null;
  if (event.key.toLowerCase() === 'q') return 'toggle-query-parameters';
  if (event.key.toLowerCase() === 'b') return 'toggle-sidebar';
  if (event.key === '?') return 'show-shortcuts';
  return null;
};
document.addEventListener('keydown', event => {
  const command = datavizKeyboardShortcutCommand(event);
  if (!command) return;
  if (window.parent !== window) {
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    event.preventDefault();
    datavizPostToParent({type:'dataviz:keyboard-shortcut', command});
    return;
  }
  if (command === 'toggle-query-parameters' && datavizRuntimeQueryToggle) {
    event.preventDefault();
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    const tray = datavizRuntimeQueryPanel?.closest('.dv-runtime-query-tray');
    if (Number(tray?.dataset.controlCount || 0) <= 0) {
      showDatavizRuntimeShortcutToast('当前报告没有查询参数');
      return;
    }
    setDatavizRuntimeQueryOpen(
      datavizRuntimeQueryToggle.getAttribute('aria-expanded') !== 'true',
    );
  } else if (command === 'show-shortcuts' && datavizRuntimeShortcutHelp) {
    event.preventDefault();
    window.datavizComponents?.overlay.closeAll({group:'popover'});
    datavizRuntimeShortcutHelp.showModal();
  }
});
window.datavizComponents?.hydrate(document);
document.querySelectorAll('[data-selection-input]').forEach(input => {
  input.addEventListener('input', scheduleDatavizSelection);
  input.addEventListener('change', scheduleDatavizSelection);
});
let datavizComputeTimer;
document.querySelectorAll('[data-compute-input]').forEach(input => {
  const onDraft = () => {
    readComputeInputs();
    const changed = syncComputeDirtyState();
    const key = input.closest('[data-compute-key]')?.dataset.computeKey || input.dataset.computeInput;
    const trigger = input.dataset.computeTrigger || input.closest('[data-compute-trigger]')?.dataset.computeTrigger;
    if (trigger !== 'auto' || !key || !changed.includes(key)) return;
    clearTimeout(datavizComputeTimer);
    const consumers = (
      window.dataviz.dependency_contract?.controls?.[key]?.transform_consumers || []
    ).map(id => datavizRuntime.transforms.get(id)).filter(
      item => item?.spec.trigger === 'auto'
    );
    const delay = Math.max(0, ...consumers.map(item => Number(item.spec.debounce_ms || 0)));
    datavizComputeTimer = setTimeout(() => window.dataviz.applyCompute({keys:[key]}).catch(error => {
      console.error('[dataviz:compute:auto]', error);
    }), delay);
  };
  input.addEventListener('input', onDraft);
  input.addEventListener('change', onDraft);
});
document.querySelectorAll('[data-compute-apply]').forEach(button => {
  button.addEventListener('click', () => window.dataviz.applyControls({
    apply:true,
    keys:JSON.parse(button.dataset.controlKeys || '[]'),
    manualTargets:JSON.parse(button.dataset.manualTargets || '[]'),
  }).catch(error => {
    console.error('[dataviz:compute:apply]', error);
  }));
});
syncComputeDirtyState();
if (window.dataviz.asset_mode === 'server') {
  document.querySelectorAll('.dv-context-controls[data-editor-owner] > summary').forEach(trigger => {
    trigger.addEventListener('contextmenu', event => {
      event.preventDefault();
      event.stopPropagation();
      datavizPostToParent({
        type:'dataviz:open-parameter-editor',
        owner:trigger.parentElement.dataset.editorOwner,
      });
    });
  });
}
document.addEventListener('pointerdown', () => {
  if (window.parent !== window) {
    datavizPostToParent({type: 'dataviz:canvas-interaction'});
  }
}, {capture: true});
document.addEventListener('click', event => {
  const signal = event.target.closest('[data-view-pipeline-signal]');
  if (!signal) return;
  signal.blur();
  const title = signal.getAttribute('title');
  signal.removeAttribute('title');
  signal.addEventListener('pointerleave', () => {
    if (title) signal.setAttribute('title', title);
  }, {once:true});
  datavizPostToParent({
    type:'dataviz:view-pipeline-inspect',
    node_id:signal.dataset.viewPipelineNode,
  });
});
window.addEventListener('pagehide', () => datavizRuntime.dispose(), {once:true});
Object.entries(window.dataviz.portable?.outputs || {}).forEach(([reference, value]) => {
  datavizRuntime.outputSignatures.set(
    canonicalOutputReference(reference),
    datavizValueSignature(value),
  );
});
Object.entries(window.dataviz.portable?.output_errors || {}).forEach(([reference, failure]) => {
  datavizRuntime.outputErrors.set(
    canonicalOutputReference(reference),
    datavizRuntimeError(failure),
  );
});
window.dataviz.getViewSelections = viewId => {
  const contract = datavizViewSelectionContract(viewId);
  return Object.fromEntries(
    contract.map(item => [item.id, datavizSelectionValue(item.key)])
  );
};
window.datavizRuntimeServices = Object.freeze({
  canonicalOutputReference,
  tableRows:datavizTableRows,
  numericAggregate:datavizNumericAggregate,
  workerValue:datavizWorkerValue,
  selectionCanApply:datavizSelectionCanApply,
  selectionMatches:datavizSelectionMatches,
  runtimeError:datavizRuntimeError,
  escape:datavizEscape,
  decodeSpec:node => JSON.parse(new TextDecoder().decode(Uint8Array.from(
    atob(node.dataset.spec),
    value => value.charCodeAt(0),
  ))),
});
window.dispatchEvent(new CustomEvent('dataviz:runtime-ready', {detail: datavizRuntime}));
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
