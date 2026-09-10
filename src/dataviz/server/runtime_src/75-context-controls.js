// One active scope path. Moving a panel never commits a Control.
const datavizContextControlKeys = new Set();
// Keep already-opened keys authorized for in-flight commits while the panel
// closes or changes scope. This set dies with the frame, not the UI host.
const datavizHostControlKeys = new Set();
let datavizContextOwner = null;
let datavizContextFollowsPopover = false;
let datavizContextSequence = 0;
const datavizContextTemplates = new WeakMap();
document.querySelectorAll('.dv-context-controls__panel, .dv-runtime-control > .dv-runtime-popover').forEach(panel => {
  datavizContextTemplates.set(panel, panel.cloneNode(true));
});
let datavizContextPanel = null;
const datavizContextEmbedded = () => window.parent !== window;
const datavizContextPath = owner => {
  if (owner.dataset.controlOrigin === 'dashboard') return [];
  const section = owner.closest('.dv-section');
  const parent = owner.dataset.controlOrigin === 'view'
    ? section?.querySelector(':scope > header .dv-context-controls')
      || document.querySelector(`[data-editor-owner="${CSS.escape(`section:${owner.dataset.controlParentSection}`)}"]`) : null;
  return [...new Set([parent, owner].filter(Boolean))];
};
const datavizContextTitle = owner => {
  const scope = owner.dataset.controlOrigin === 'view' ? 'View' : 'Section';
  const container = owner.closest(scope === 'View' ? '.dv-view' : '.dv-section');
  const name = container?.querySelector('header h2, header h3, .dv-view-title')?.textContent?.trim();
  return `${scope} · ${name || owner.dataset.controlOwnerTitle || owner.dataset.editorOwner.split(':').slice(1).join(':')}`;
};
const datavizCloseContextControls = ({notify = true, focus = true} = {}) => {
  const opener = datavizContextOwner?.querySelector(':scope > summary');
  if (!datavizContextFollowsPopover) opener?.setAttribute('aria-expanded', 'false');
  datavizContextOwner = null;
  datavizContextControlKeys.clear();
  datavizContextPanel?.querySelectorAll('*').forEach(node => {
    const overlay = node._datavizOverlayRecord?.api;
    overlay?.close({returnFocus:false});
    overlay?.destroy();
  });
  datavizContextPanel?.remove();
  datavizContextPanel = null;
  document.body.classList.remove('dv-context-sidebar-open');
  document.querySelector('.dv-canvas')?.removeAttribute('inert');
  document.querySelector('.dv-runtime-header')?.removeAttribute('inert');
  if (notify && datavizContextEmbedded()) datavizPostToParent({type:'dataviz:context-controls', groups:[]});
  if (focus && opener?.isConnected) opener.focus({preventScroll:true});
  window.dispatchEvent(new Event('resize'));
};
const datavizOpenContextControls = (owner, {focus = true, follow = false} = {}) => {
  if (datavizContextOwner === owner && !follow) { datavizCloseContextControls(); return; }
  if (datavizContextOwner === owner && datavizContextPanel) return;
  datavizCloseContextControls({notify:false, focus:false});
  if (!follow) window.datavizComponents?.overlay.closeAll({group:'popover'});
  datavizContextOwner = owner;
  datavizContextSequence += 1;
  datavizContextFollowsPopover = follow;
  if (!follow) owner.querySelector(':scope > summary')?.setAttribute('aria-expanded', 'true');
  const path = datavizContextPath(owner);
  const groups = path.map(item => ({
    id:item.dataset.editorOwner,
    title:datavizContextTitle(item),
    keys:[...item.querySelectorAll('[data-control-state-input]')].map(input => input.dataset.controlStateInput),
  }));
  groups.forEach(group => group.keys.forEach(key => { datavizContextControlKeys.add(key); datavizHostControlKeys.add(key); }));
  if (datavizContextEmbedded()) {
    datavizPostToParent({type:'dataviz:context-controls', groups, focus, follow, context_id:datavizContextSequence, snapshot:datavizControlOperationalSnapshot()});
    return;
  }
  setDatavizRuntimeQueryOpen(false);
  const sidebar = document.createElement('aside');
  sidebar.className = 'dv-context-sidebar';
  sidebar.setAttribute('aria-label', 'Controls');
  sidebar.innerHTML = '<header><h2>Controls</h2><button type="button" aria-label="Close controls">×</button></header><div class="dv-context-sidebar__body"></div>';
  sidebar.querySelector('button').onclick = () => datavizCloseContextControls();
  const dashboard = document.querySelector('.dv-runtime-control[data-control-origin="dashboard"]');
  const entries = [...(dashboard ? [{owner:dashboard, title:'Dashboard', selector:'.dv-runtime-popover'}] : []),
    ...path.map(item => ({owner:item, title:datavizContextTitle(item), selector:'.dv-context-controls__panel'}))];
  for (const entry of entries) {
    const original = entry.owner.querySelector(entry.selector);
    if (!original) continue;
    const panel = (datavizContextTemplates.get(original) || original).cloneNode(true);
    // Mirrored labels and ARIA references must target this host, not the
    // original popover's inputs in the same document.
    const ids = new Map();
    [panel, ...panel.querySelectorAll('[id]')].forEach(node => {
      if (!node.id) return;
      const id = `${node.id}-context-${datavizContextSequence}`;
      ids.set(node.id, id);
      node.id = id;
    });
    panel.querySelectorAll('[for], [aria-labelledby], [aria-describedby], [aria-controls], [list]').forEach(node => {
      for (const attr of ['for', 'aria-labelledby', 'aria-describedby', 'aria-controls', 'list']) {
        if (node.hasAttribute(attr)) node.setAttribute(attr, node.getAttribute(attr).split(/\s+/).map(id => ids.get(id) || id).join(' '));
      }
    });
    if (!follow) entry.owner.open = false;
    panel.removeAttribute('popover');
    const group = document.createElement('section');
    const heading = document.createElement('h3');
    const scope = entry.owner.dataset.controlOrigin === 'dashboard' ? 'Dashboard'
      : entry.owner.dataset.controlOrigin === 'view' ? 'View' : 'Section';
    const scopeLabel = document.createElement('span');
    scopeLabel.className = 'control-group-scope';
    scopeLabel.dataset.scope = scope.toLowerCase();
    scopeLabel.textContent = scope;
    heading.append(scopeLabel);
    if (scope !== 'Dashboard') {
      const title = document.createElement('span');
      title.textContent = entry.title.replace(`${scope} · `, '');
      heading.append(title);
    }
    heading.tabIndex = -1;
    group.append(heading, panel);
    sidebar.querySelector('.dv-context-sidebar__body').append(group);
  }
  document.body.append(sidebar);
  window.datavizComponents?.hydrate(sidebar);
  sidebar.querySelectorAll('[data-control-state-input]').forEach(input => {
    input.addEventListener('input', scheduleDatavizControl);
    input.addEventListener('change', scheduleDatavizControl);
  });
  sidebar.querySelectorAll('[data-control-apply]').forEach(button => {
    button.addEventListener('click', () => window.dataviz.applyControls({apply:true, keys:JSON.parse(button.dataset.controlKeys || '[]')}).catch(console.error));
  });
  refreshControlOptionDomains({canonicalKeys:new Set(Object.keys(datavizControlStateSnapshot()))});
  setControlInputs(datavizControlStateSnapshot());
  datavizContextPanel = sidebar;
  document.body.classList.add('dv-context-sidebar-open');
  const syncLayout = () => {
    if (!datavizContextPanel) return;
    const modal = matchMedia('(max-width: 1279px)').matches;
    sidebar.setAttribute('role', modal ? 'dialog' : 'complementary');
    if (modal) sidebar.setAttribute('aria-modal', 'true'); else sidebar.removeAttribute('aria-modal');
    for (const selector of ['.dv-canvas', '.dv-runtime-header']) {
      const node = document.querySelector(selector);
      if (node) node.inert = modal;
    }
  };
  syncLayout();
  sidebar._syncLayout = syncLayout;
  const heading = sidebar.querySelector('section:last-child h3');
  if (!follow && (focus || matchMedia('(max-width:1279px)').matches)) heading?.focus({preventScroll:true});
  heading?.scrollIntoView({block:'nearest'});
  window.dispatchEvent(new Event('resize'));
};
document.addEventListener('click', event => {
  const dashboard = event.target.closest?.('.dv-runtime-control[data-control-origin="dashboard"] > summary');
  if (dashboard && datavizContextOwner) {
    event.preventDefault();
    event.stopImmediatePropagation();
    datavizCloseContextControls();
    return;
  }
  const summary = event.target.closest?.('.dv-context-controls > summary');
  if (!summary) return;
  const owner = summary.parentElement;
  if (owner.dataset.controlsPlacement !== 'sidebar') {
    if (datavizContextEmbedded() || datavizContextPanel || datavizRuntimeQueryToggle?.getAttribute('aria-expanded') === 'true') {
      datavizOpenContextControls(owner, {focus:false, follow:true});
    }
    return;
  }
  event.preventDefault();
  event.stopImmediatePropagation();
  datavizOpenContextControls(owner, {focus:event.detail === 0});
}, true);
window.addEventListener('message', event => {
  if (event.source !== window.parent || event.origin !== location.origin) return;
  if (event.data?.type === 'dataviz:context-controls-close'
      && (event.data.context_id == null || event.data.context_id === datavizContextSequence)) {
    datavizCloseContextControls({notify:false, focus:event.data.focus !== false});
  }
});
window.addEventListener('resize', () => datavizContextPanel?._syncLayout());
new MutationObserver(() => {
  if (datavizContextOwner && !datavizContextOwner.isConnected) datavizCloseContextControls({focus:false});
}).observe(document.documentElement, {childList:true, subtree:true});
document.addEventListener('keydown', event => {
  if (!datavizContextPanel || event.defaultPrevented || document.querySelector(':popover-open, dialog[open]')) return;
  if (event.key === 'Escape') { event.preventDefault(); datavizCloseContextControls(); }
  if (event.key === 'Tab' && datavizContextPanel.getAttribute('aria-modal') === 'true') {
    const nodes = [...datavizContextPanel.querySelectorAll('button,input,select,textarea,[tabindex="0"]')]
      .filter(node => !node.disabled && node.getClientRects().length);
    if (event.shiftKey && (document.activeElement === nodes[0] || document.activeElement.tagName === 'H3')) { event.preventDefault(); nodes.at(-1)?.focus(); }
    else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0]?.focus(); }
  }
});
