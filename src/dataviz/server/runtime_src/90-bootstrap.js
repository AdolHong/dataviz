// Owner: DOM/bootstrap event wiring after every Runtime owner is registered.
let datavizControlScheduled = false;
let datavizControlQueue = Promise.resolve();
const scheduleDatavizControl = event => {
  // Capture the user's native control value before asynchronous initialization
  // or option-domain reconciliation can rebuild the underlying <select>.
  try {
    datavizCaptureControlIntent(event?.currentTarget || event?.target);
    readControlInputs();
  } catch (error) {
    console.error('[dataviz:controls]', error);
    return;
  }
  if (datavizControlScheduled) return;
  datavizControlScheduled = true;
  queueMicrotask(() => {
    datavizControlScheduled = false;
    // A native select emits both input and change for one user action. Coalesce
    // that event pair in the current task, then serialize any later actions
    // behind the in-flight Interactive branch. Control state is an immediate data
    // contract; it must not depend on a browser timer being scheduled promptly.
    const initialization = datavizRuntime.initializationPromise || Promise.resolve();
    datavizControlQueue = Promise.all([
      datavizControlQueue.catch(() => undefined),
      initialization.catch(() => undefined),
    ])
      .then(() => window.dataviz.applyControls())
      .catch(error => console.error('[dataviz:controls]', error));
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
document.querySelectorAll('[data-control-state-input]').forEach(input => {
  input.addEventListener('input', scheduleDatavizControl);
  input.addEventListener('change', scheduleDatavizControl);
});
document.querySelectorAll('[data-control-apply]').forEach(button => {
  button.addEventListener('click', () => window.dataviz.applyControls({
    apply:true,
    keys:JSON.parse(button.dataset.controlKeys || '[]'),
  }).catch(error => {
    console.error('[dataviz:control:apply]', error);
  }));
});
syncControlDirtyState();
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
window.addEventListener('pagehide', () => {
  datavizAssets.dispose();
  datavizRuntime.dispose();
}, {once:true});
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
window.dataviz.getViewControls = viewId => {
  const contract = datavizViewControlContract(viewId);
  return Object.fromEntries(
    contract.map(item => [item.id, datavizControlValue(item.key)])
  );
};
const datavizAssetRecords = Object.freeze({...window.dataviz.assets});
const datavizAssetTextCache = new Map();
const datavizAssetJsonCache = new Map();
const datavizAssetBlobUrls = new Map();
const datavizAssetRecord = identifier => {
  const key = String(identifier || '');
  const record = datavizAssetRecords[key];
  if (!record) throw new Error(`Unknown Dashboard Asset: ${key}`);
  return [key, record];
};
const datavizAssetBytes = async identifier => {
  const [_key, record] = datavizAssetRecord(identifier);
  if (record.transport === 'url') {
    const response = await fetch(record.url, {credentials:'same-origin'});
    if (!response.ok) throw new Error(`Dashboard Asset request failed: ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  }
  if (record.transport === 'text') return new TextEncoder().encode(record.content || '');
  if (record.transport === 'base64') {
    const binary = atob(record.content || '');
    return Uint8Array.from(binary, value => value.charCodeAt(0));
  }
  throw new Error(`Unsupported Dashboard Asset transport: ${record.transport || 'missing'}`);
};
const datavizAssets = Object.freeze({
  list:() => Object.keys(datavizAssetRecords),
  describe:identifier => {
    const [id, record] = datavizAssetRecord(identifier);
    const {content:_content, url:_url, transport, ...metadata} = record;
    return {id, transport, ...metadata};
  },
  bytes:datavizAssetBytes,
  text:identifier => {
    const [key, record] = datavizAssetRecord(identifier);
    if (!datavizAssetTextCache.has(key)) {
      datavizAssetTextCache.set(key, record.transport === 'text'
        ? Promise.resolve(record.content || '')
        : datavizAssetBytes(key).then(value => new TextDecoder().decode(value)));
    }
    return datavizAssetTextCache.get(key);
  },
  json:identifier => {
    const [key] = datavizAssetRecord(identifier);
    if (!datavizAssetJsonCache.has(key)) {
      datavizAssetJsonCache.set(key, datavizAssets.text(key).then(JSON.parse));
    }
    return datavizAssetJsonCache.get(key);
  },
  blob:async identifier => {
    const [_key, record] = datavizAssetRecord(identifier);
    return new Blob([await datavizAssetBytes(identifier)], {type:record.media_type});
  },
  url:async identifier => {
    const [key, record] = datavizAssetRecord(identifier);
    if (record.transport === 'url') return record.url;
    if (!datavizAssetBlobUrls.has(key)) {
      datavizAssetBlobUrls.set(key, URL.createObjectURL(await datavizAssets.blob(key)));
    }
    return datavizAssetBlobUrls.get(key);
  },
  dispose:() => {
    datavizAssetBlobUrls.forEach(value => URL.revokeObjectURL(value));
    datavizAssetBlobUrls.clear();
  },
});
window.dataviz.assets = datavizAssets;
window.datavizRuntimeServices = Object.freeze({
  canonicalOutputReference,
  tableRows:datavizTableRows,
  numericAggregate:datavizNumericAggregate,
  workerValue:datavizWorkerValue,
  controlCanApply:datavizControlCanApply,
  controlMatches:datavizControlMatches,
  runtimeError:datavizRuntimeError,
  assets:datavizAssets,
  escape:datavizEscape,
  decodeSpec:node => JSON.parse(new TextDecoder().decode(Uint8Array.from(
    atob(node.dataset.spec),
    value => value.charCodeAt(0),
  ))),
});
window.dispatchEvent(new CustomEvent('dataviz:runtime-ready', {detail: datavizRuntime}));
window.dispatchEvent(new CustomEvent('dataviz:ready', {detail: window.dataviz}));
