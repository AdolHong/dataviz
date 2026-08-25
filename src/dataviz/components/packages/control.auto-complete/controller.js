(function exposeAutoComplete(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createAutoComplete) return;

  root.createAutoComplete = function createAutoComplete({control, input, mount}) {
    const picker = document.createElement('div');
    picker.className = 'dv-auto-complete';
    input.classList.add('dv-auto-complete__input');
    input.dataset.controlNative = 'visible';
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.autocomplete = 'off';
    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-auto-complete__panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    panel.setAttribute('role', 'listbox');
    const empty = document.createElement('div');
    empty.className = 'dv-choice-empty';
    empty.textContent = control.dataset.emptyText || 'No matching suggestions';
    let suggestions = [];
    try { suggestions = JSON.parse(control.dataset.suggestions || '[]'); } catch (_error) {}
    let filtered = [];
    let active = -1;
    picker.append(input, panel);
    mount.replaceChildren(picker);
    const overlay = api.floating(picker, input, panel, {
      width: Number(control.dataset.overlayWidth || 420),
      toggleOnTrigger: false,
      ariaHaspopup: 'listbox',
    });

    const commit = suggestion => {
      input.value = String(suggestion.value);
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      overlay.close({returnFocus: true});
    };
    const render = () => {
      const query = input.value.trim().toLocaleLowerCase();
      filtered = suggestions.filter(item => [item.label, item.value, ...(item.keywords || [])]
        .filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
      active = Math.min(active, filtered.length - 1);
      panel.replaceChildren();
      filtered.forEach((item, index) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = `dv-auto-complete__option${index === active ? ' is-active' : ''}`;
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', String(index === active));
        option.innerHTML = `<span>${api.escape(item.label || item.value)}</span>${item.description ? `<small>${api.escape(item.description)}</small>` : ''}`;
        option.addEventListener('mousedown', event => event.preventDefault());
        option.addEventListener('click', () => commit(item));
        panel.append(option);
      });
      empty.hidden = filtered.length > 0;
      if (!filtered.length) panel.append(empty);
      if (document.activeElement === input && !overlay.isOpen()) overlay.open();
      if (overlay.isOpen()) overlay.reposition();
    };
    input.addEventListener('focus', render);
    input.addEventListener('input', () => { active = -1; render(); });
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        active = Math.min(filtered.length - 1, active + 1);
        render();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        active = Math.max(0, active - 1);
        render();
      } else if (event.key === 'Enter' && active >= 0) {
        event.preventDefault();
        commit(filtered[active]);
      }
    });
    return {sync: () => { input.disabled ? overlay.close() : null; }};
  };
})(window);
