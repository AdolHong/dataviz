(function exposeCheckboxGroup(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createCheckboxGroup) return;

  root.createCheckboxGroup = function createCheckboxGroup({control, input, mount}) {
    const group = document.createElement('div');
    group.className = 'dv-checkbox-group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', input.getAttribute('aria-label') || 'Choose values');

    const maxSelected = Number(control.dataset.maxSelected || 0);
    const allowEmpty = control.dataset.clearable === 'true';
    const selectAllLabel = control.dataset.selectAllLabel || 'Select all';
    const invertLabel = control.dataset.invertLabel || 'Invert';
    const bulkActions = control.dataset.bulkActions !== 'false';

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
    group.append(toolbar, optionsHost);
    toolbar.hidden = !bulkActions;

    function sync() {
      const options = api.options(input);
      const available = api.availableOptions(input);
      const selected = api.selectedOptions(input);
      const allSelected = available.length > 0 && selected.length === available.length;
      const canSelectAll = !maxSelected || maxSelected >= available.length;

      all.textContent = allSelected ? invertLabel : selectAllLabel;
      all.dataset.action = allSelected ? 'invert' : 'select-all';
      all.disabled = input.disabled
        || available.length === 0
        || (!allSelected && !canSelectAll)
        || (allSelected && !allowEmpty);
      all.title = !allSelected && !canSelectAll
        ? `Selection limit is ${maxSelected}; select values individually.`
        : '';
      count.textContent = `${selected.length} / ${available.length}`;
      count.setAttribute('aria-label', `${selected.length} of ${available.length} selected`);

      optionsHost.replaceChildren();
      options.forEach(option => {
        const unavailable = Boolean(option.disabled);
        if (unavailable && control.dataset.showUnavailable !== 'true') return;
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
          if (option.selected && selected.length === 1 && !allowEmpty) return;
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
      if (allSelected && !allowEmpty) return;
      available.forEach(option => { option.selected = !allSelected; });
      sync();
      api.emitChange(input);
    });

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
