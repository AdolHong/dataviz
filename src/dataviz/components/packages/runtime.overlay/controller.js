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

  function popoverOpen(panel) {
    if (!panel?.matches) return false;
    try { return panel.matches(':popover-open'); }
    catch (_) { return false; }
  }

  function showInTopLayer(record) {
    const panel = record.panel;
    if (!record.floating || typeof panel?.showPopover !== 'function') return false;
    try {
      if (!popoverOpen(panel)) panel.showPopover();
      record.topLayer = true;
      return true;
    } catch (_) {
      record.topLayer = false;
      return false;
    }
  }

  function hideFromTopLayer(record) {
    if (!record.topLayer || typeof record.panel?.hidePopover !== 'function') return;
    try {
      if (popoverOpen(record.panel)) record.panel.hidePopover();
    } catch (_) { /* The owning element may already have left the document. */ }
  }

  function viewportBounds() {
    const visual = global.visualViewport;
    const widths = [
      document.documentElement.clientWidth,
      global.innerWidth,
      visual?.width,
    ].map(Number).filter(value => Number.isFinite(value) && value > 0);
    const heights = [
      document.documentElement.clientHeight,
      global.innerHeight,
      visual?.height,
    ].map(Number).filter(value => Number.isFinite(value) && value > 0);
    const left = Number(visual?.offsetLeft || 0);
    const top = Number(visual?.offsetTop || 0);
    const width = Math.min(...widths);
    const height = Math.min(...heights);
    return {left, top, right:left + width, bottom:top + height, width, height};
  }

  function position(record) {
    if (!record.floating || !record.panel || record.panel.hidden) return;
    const gutter = Number(record.gutter || 12);
    const gap = Number(record.gap || 6);
    const viewport = viewportBounds();
    const triggerRect = record.trigger.getBoundingClientRect();
    const preferredWidth = Number(record.width || record.panel.dataset.overlayWidth || 420);
    const width = Math.max(1, Math.min(preferredWidth, viewport.width - gutter * 2));
    record.panel.style.position = 'fixed';
    // Overlay geometry and stacking are runtime guarantees, not theme concerns.
    // Keep floating panels above later sibling controls in every browser.
    record.panel.style.zIndex = String(
      record.zIndex || record.panel.dataset.overlayZIndex || 1000,
    );
    record.panel.style.width = `${width}px`;
    // Measure against the viewport first, then constrain the panel to the side
    // of the trigger where it will be placed. Clamping an almost viewport-high
    // panel after measuring it used to move the panel over its own Header
    // triggers, making adjacent controls impossible to click.
    record.panel.style.maxHeight = `${Math.max(1, viewport.height - gutter * 2)}px`;
    record.panel.style.right = 'auto';
    record.panel.style.bottom = 'auto';
    record.panel.style.margin = '0';
    record.panel.style.left = '0px';
    record.panel.style.top = '0px';
    // ``scrollHeight`` excludes borders while positioning uses the border-box
    // rectangle. Firefox exposes that difference here; clamping with the
    // rendered box prevents a nominal 12px gutter from becoming 10px.
    const desiredHeight = Math.min(
      record.panel.getBoundingClientRect().height,
      viewport.height - gutter * 2,
    );
    const roomBelow = Math.max(
      1,
      viewport.bottom - triggerRect.bottom - gutter - gap,
    );
    const roomAbove = Math.max(
      1,
      triggerRect.top - viewport.top - gutter - gap,
    );
    const above = desiredHeight > roomBelow && roomAbove > roomBelow;
    const availableHeight = above ? roomAbove : roomBelow;
    record.panel.style.maxHeight = `${availableHeight}px`;
    const height = Math.min(
      record.panel.getBoundingClientRect().height,
      availableHeight,
    );
    const align = record.align || 'end';
    const rawLeft = align === 'start' ? triggerRect.left : triggerRect.right - width;
    const left = Math.max(
      viewport.left + gutter,
      Math.min(rawLeft, viewport.right - width - gutter),
    );
    const rawTop = above ? triggerRect.top - height - gap : triggerRect.bottom + gap;
    // Height is already constrained to the selected side, so no bottom clamp
    // may move the panel across the trigger that owns it.
    const top = Math.max(viewport.top + gutter, rawTop);
    record.panel.style.left = `${left}px`;
    record.panel.style.top = `${top}px`;
    if (!record.topLayer) {
      // A filter, transform or containment property on an ancestor changes the
      // containing block of a fixed descendant.  Runtime geometry is expressed
      // in viewport coordinates, so compensate for that offset in browsers
      // without the Popover top layer.  Two passes also settle nested offsets.
      for (let pass = 0; pass < 2; pass += 1) {
        const actual = record.panel.getBoundingClientRect();
        const deltaLeft = left - actual.left;
        const deltaTop = top - actual.top;
        if (Math.abs(deltaLeft) < 0.5 && Math.abs(deltaTop) < 0.5) break;
        record.panel.style.left = `${parseFloat(record.panel.style.left) + deltaLeft}px`;
        record.panel.style.top = `${parseFloat(record.panel.style.top) + deltaTop}px`;
      }
    }
    record.panel.dataset.overlayPlacement = above ? 'top' : 'bottom';
  }

  function isOpen(record) {
    return record.kind === 'details'
      ? Boolean(
        record.owner.open
        || record.owner.classList.contains('is-overlay-open')
        || popoverOpen(record.panel),
      )
      : !record.panel.hidden;
  }

  function close(record, options = {}) {
    if (!isOpen(record)) return;
    record.silent = true;
    hideFromTopLayer(record);
    if (record.kind === 'details') {
      if (record.owner.open) {
        record.expectedToggleState = false;
        record.owner.open = false;
      }
    } else record.panel.hidden = true;
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
    if (record.kind === 'details') {
      if (!record.owner.open) {
        record.expectedToggleState = true;
        record.owner.open = true;
      }
    } else record.panel.hidden = false;
    showInTopLayer(record);
    record.silent = false;
    record.openedAt = ++sequence;
    record.trigger?.setAttribute('aria-expanded', 'true');
    record.owner?.classList.add('is-overlay-open');
    position(record);
    record.onOpen?.();
    const focusTarget = options.focus || record.focus;
    if (focusTarget) requestAnimationFrame(() => focusTarget.focus({preventScroll: true}));
  }

  function refresh(record, options = {}) {
    if (!isOpen(record)) return false;
    const focused = options.preserveFocus && record.panel?.contains?.(document.activeElement)
      ? document.activeElement
      : null;
    const selection = focused && typeof focused.selectionStart === 'number'
      ? {start:focused.selectionStart, end:focused.selectionEnd}
      : null;

    // Reattach an already-open Popover after its asynchronously supplied
    // children change. Chromium can otherwise keep the previous nested
    // top-layer surface until the user closes and reopens the picker.
    if (record.topLayer) {
      hideFromTopLayer(record);
      showInTopLayer(record);
    }
    position(record);
    if (focused?.isConnected) {
      focused.focus({preventScroll: true});
      if (selection && typeof focused.setSelectionRange === 'function') {
        focused.setSelectionRange(selection.start, selection.end);
      }
    }
    return true;
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
      topLayer: false,
      expectedToggleState: null,
    };
    if (record.floating && typeof record.panel?.showPopover === 'function') {
      record.panel.setAttribute('popover', 'manual');
      record.panel.dataset.dvOverlayTopLayer = '';
    }
    owner._datavizOverlayRecord = record;
    records.add(record);
    if (record.trigger && record.panel) {
      if (!record.panel.id) record.panel.id = `dv-overlay-${Math.random().toString(36).slice(2, 10)}`;
      record.trigger.setAttribute('aria-controls', record.panel.id);
      record.trigger.setAttribute('aria-haspopup', options.ariaHaspopup || 'dialog');
      record.trigger.setAttribute('aria-expanded', String(isOpen(record)));
    }
    if (record.kind === 'details') {
      // Native <details> reveals its contents before the asynchronous `toggle`
      // event.  Floating panels would therefore flash at their unpositioned CSS
      // coordinates for one frame.  Own summary activation synchronously while
      // retaining the toggle listener for external `details.open = ...` calls.
      record.trigger?.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        isOpen(record) ? close(record) : open(record);
      });
      owner.addEventListener('toggle', () => {
        if (record.expectedToggleState === owner.open) {
          record.expectedToggleState = null;
          return;
        }
        record.expectedToggleState = null;
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
      refresh: value => refresh(record, value),
      reposition: () => position(record),
      isOpen: () => isOpen(record),
      destroy: () => records.delete(record),
    };
    // Browsers may restore native <details open> state before this controller
    // hydrates (notably when reopening a portable report or traversing history).
    // Adopt that state through the same open path so group exclusivity,
    // top-layer ownership and viewport positioning are established immediately.
    // Without this normalization, two restored Header trays can remain open and
    // occupy the same floating coordinates even though later clicks are exclusive.
    if (isOpen(record)) open(record);
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
