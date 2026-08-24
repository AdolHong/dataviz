(function installDatavizOverlay(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.overlay) return;

  const records = new Set();
  let sequence = 0;
  const pathFor = event => typeof event.composedPath === 'function' ? event.composedPath() : [];
  const contains = (record, path, target) => path.includes(record.owner)
    || path.includes(record.trigger)
    || path.includes(record.panel)
    || record.owner?.contains?.(target)
    || record.panel?.contains?.(target);

  function position(record) {
    if (!record.floating || !record.panel || record.panel.hidden) return;
    const gutter = Number(record.gutter || 12);
    const gap = Number(record.gap || 6);
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const triggerRect = record.trigger.getBoundingClientRect();
    const preferredWidth = Number(record.width || record.panel.dataset.overlayWidth || 420);
    const width = Math.max(1, Math.min(preferredWidth, viewportWidth - gutter * 2));
    record.panel.style.position = 'fixed';
    // Overlay geometry and stacking are runtime guarantees, not theme concerns.
    // Keep floating panels above later sibling controls in every browser.
    record.panel.style.zIndex = String(
      record.zIndex || record.panel.dataset.overlayZIndex || 1000,
    );
    record.panel.style.width = `${width}px`;
    record.panel.style.maxHeight = `${Math.max(120, viewportHeight - gutter * 2)}px`;
    record.panel.style.right = 'auto';
    record.panel.style.left = '0px';
    record.panel.style.top = '0px';
    const height = Math.min(record.panel.scrollHeight, viewportHeight - gutter * 2);
    const roomBelow = viewportHeight - triggerRect.bottom - gutter;
    const roomAbove = triggerRect.top - gutter;
    const above = height > roomBelow && roomAbove > roomBelow;
    const align = record.align || 'end';
    const rawLeft = align === 'start' ? triggerRect.left : triggerRect.right - width;
    const left = Math.max(gutter, Math.min(rawLeft, viewportWidth - width - gutter));
    const rawTop = above ? triggerRect.top - height - gap : triggerRect.bottom + gap;
    const top = Math.max(gutter, Math.min(rawTop, viewportHeight - height - gutter));
    record.panel.style.left = `${left}px`;
    record.panel.style.top = `${top}px`;
    record.panel.dataset.overlayPlacement = above ? 'top' : 'bottom';
  }

  function isOpen(record) {
    return record.kind === 'details' ? Boolean(record.owner.open) : !record.panel.hidden;
  }

  function close(record, options = {}) {
    if (!isOpen(record)) return;
    record.silent = true;
    if (record.kind === 'details') record.owner.open = false;
    else record.panel.hidden = true;
    record.silent = false;
    record.trigger?.setAttribute('aria-expanded', 'false');
    record.owner?.classList.remove('is-overlay-open');
    record.onClose?.();
    if (options.returnFocus) record.trigger?.focus({preventScroll: true});
  }

  function closeAll(options = {}) {
    const except = options.except || null;
    const group = options.group || null;
    [...records].forEach(record => {
      if (record === except || record.owner === except || (group && record.group !== group)) return;
      close(record, options);
    });
  }

  function open(record, options = {}) {
    closeAll({except: record, group: record.group});
    record.silent = true;
    if (record.kind === 'details') record.owner.open = true;
    else record.panel.hidden = false;
    record.silent = false;
    record.openedAt = ++sequence;
    record.trigger?.setAttribute('aria-expanded', 'true');
    record.owner?.classList.add('is-overlay-open');
    position(record);
    record.onOpen?.();
    const focusTarget = options.focus || record.focus;
    if (focusTarget) requestAnimationFrame(() => focusTarget.focus({preventScroll: true}));
  }

  function register(options) {
    const owner = options.owner;
    if (!owner || owner._datavizOverlayRecord) return owner?._datavizOverlayRecord || null;
    const record = {
      kind: options.kind || 'floating',
      owner,
      trigger: options.trigger,
      panel: options.panel,
      group: options.group || 'global',
      floating: Boolean(options.floating),
      width: options.width,
      zIndex: options.zIndex,
      align: options.align,
      focus: options.focus || null,
      onOpen: options.onOpen,
      onClose: options.onClose,
      silent: false,
      openedAt: 0,
    };
    owner._datavizOverlayRecord = record;
    records.add(record);
    if (record.trigger && record.panel) {
      if (!record.panel.id) record.panel.id = `dv-overlay-${Math.random().toString(36).slice(2, 10)}`;
      record.trigger.setAttribute('aria-controls', record.panel.id);
      record.trigger.setAttribute('aria-haspopup', options.ariaHaspopup || 'dialog');
      record.trigger.setAttribute('aria-expanded', String(isOpen(record)));
    }
    if (record.kind === 'details') {
      owner.addEventListener('toggle', () => {
        if (record.silent) return;
        if (owner.open) open(record);
        else close(record);
      });
    } else if (options.toggleOnTrigger !== false) {
      record.trigger?.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        isOpen(record) ? close(record) : open(record);
      });
    }
    record.api = {
      open: value => open(record, value),
      close: value => close(record, value),
      toggle: value => isOpen(record) ? close(record, value) : open(record, value),
      reposition: () => position(record),
      isOpen: () => isOpen(record),
      destroy: () => records.delete(record),
    };
    return record;
  }

  function registerDetails(details, options = {}) {
    const trigger = details.querySelector(':scope > summary');
    const panel = trigger?.nextElementSibling || details.querySelector('[data-overlay-panel]');
    return register({
      ...options,
      kind: 'details',
      owner: details,
      trigger,
      panel,
      group: details.dataset.overlayGroup || options.group || 'popover',
      floating: details.dataset.overlayFloating === 'true' || options.floating,
      width: Number(details.dataset.overlayWidth || options.width || 420),
      align: details.dataset.overlayAlign || options.align || 'end',
    });
  }

  function hydrate(scope = document) {
    const selector = '[data-dv-overlay], [data-header-popover], [data-runtime-popover], .dv-context-controls';
    const nodes = scope.matches?.(selector) ? [scope] : [];
    nodes.push(...scope.querySelectorAll?.(selector) || []);
    nodes.forEach(node => registerDetails(node));
  }

  document.addEventListener('pointerdown', event => {
    const path = pathFor(event);
    [...records].filter(isOpen).forEach(record => {
      if (!contains(record, path, event.target)) close(record);
    });
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const active = [...records].filter(isOpen).sort((a, b) => b.openedAt - a.openedAt)[0];
    if (!active) return;
    event.preventDefault();
    close(active, {returnFocus: true});
  });
  const reposition = () => [...records].filter(isOpen).forEach(position);
  global.addEventListener('resize', reposition, {passive: true});
  global.addEventListener('scroll', reposition, {capture: true, passive: true});

  root.overlay = {register, registerDetails, hydrate, open, close, closeAll, position, records};
  root.hydrate = root.hydrate || (scope => root.overlay.hydrate(scope));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => hydrate());
  else hydrate();
})(window);
