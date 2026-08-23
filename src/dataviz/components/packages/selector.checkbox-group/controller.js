(function exposeCheckboxGroup(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.selectors;
  if (!api || root.createCheckboxGroup) return;

  root.createCheckboxGroup = function createCheckboxGroup({selector, input, mount}) {
    const control = document.createElement('div');
    control.className = `dv-checkbox-group dv-checkbox-group--${selector.dataset.variant || 'default'}`;
    control.setAttribute('role', 'group');
    control.setAttribute('aria-label', input.getAttribute('aria-label') || 'Choose values');

    const maxSelected = Number(selector.dataset.maxSelected || 0);
    const selectAllLabel = selector.dataset.selectAllLabel || 'Select all';
    const invertLabel = selector.dataset.invertLabel || 'Invert';

    const toolbar = document.createElement('div');
    toolbar.className = 'dv-checkbox-group__toolbar';
    const all = document.createElement('button');
    all.type = 'button';
    all.className = 'dv-checkbox-group__action';
    const count = document.createElement('span');
    count.className = 'dv-checkbox-group__count';
    count.setAttribute('aria-live', 'polite');
    toolbar.append(all, count);

    const optionsHost = document.createElement('div');
    optionsHost.className = 'dv-checkbox-group__options';
    control.append(toolbar, optionsHost);

    function sync() {
      const options = api.options(input);
      const available = api.availableOptions(input);
      const selected = api.selectedOptions(input);
      const allSelected = available.length > 0 && selected.length === available.length;
      const canSelectAll = !maxSelected || maxSelected >= available.length;

      all.textContent = allSelected ? invertLabel : selectAllLabel;
      all.dataset.action = allSelected ? 'invert' : 'select-all';
      all.disabled = input.disabled || available.length === 0 || (!allSelected && !canSelectAll);
      all.title = !allSelected && !canSelectAll
        ? `Selection limit is ${maxSelected}; select values individually.`
        : '';
      count.textContent = `${selected.length} / ${available.length}`;
      count.setAttribute('aria-label', `${selected.length} of ${available.length} selected`);

      optionsHost.replaceChildren();
      options.forEach(option => {
        const unavailable = Boolean(option.disabled);
        if (unavailable && selector.dataset.showUnavailable !== 'true') return;
        const capped = Boolean(maxSelected && selected.length >= maxSelected && !option.selected);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `dv-checkbox-option${option.selected && !unavailable ? ' is-selected' : ''}`;
        button.dataset.value = option.value;
        button.setAttribute('aria-pressed', String(option.selected && !unavailable));
        button.disabled = input.disabled || unavailable || capped;
        const mark = document.createElement('i');
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = option.selected ? '✓' : '';
        const label = document.createElement('span');
        label.textContent = option.textContent;
        button.append(mark, label);
        button.addEventListener('click', () => {
          if (button.disabled) return;
          option.selected = !option.selected;
          sync();
          api.emitChange(input);
        });
        optionsHost.append(button);
      });
    }

    all.addEventListener('click', () => {
      if (all.disabled) return;
      const available = api.availableOptions(input);
      const allSelected = available.length > 0 && available.every(option => option.selected);
      available.forEach(option => { option.selected = !allSelected; });
      sync();
      api.emitChange(input);
    });

    mount.replaceChildren(control);
    return {sync};
  };
})(window);
