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
    const optionsHost = document.createElement('div');
    optionsHost.className = 'dv-checkbox-group__options';
    group.append(optionsHost);

    function sync() {
      const options = api.options(input);
      const selected = api.selectedOptions(input);

      optionsHost.replaceChildren();
      options.forEach(option => {
        const unavailable = Boolean(option.disabled);
        if (
          unavailable
          && option.dataset.preserveValue !== 'true'
          && control.dataset.showUnavailable !== 'true'
        ) return;
        const capped = Boolean(maxSelected && selected.length >= maxSelected && !option.selected);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `dv-checkbox-option${option.selected ? ' is-selected' : ''}${unavailable ? ' is-unavailable' : ''}`;
        button.dataset.value = option.value;
        button.setAttribute('aria-pressed', String(option.selected));
        button.disabled = input.disabled || unavailable || capped;
        const mark = document.createElement('i');
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = option.selected ? '✓' : '';
        const label = document.createElement('span');
        label.textContent = option.textContent;
        button.append(mark, label);
        optionsHost.append(button);
      });
    }

    optionsHost.addEventListener('click', event => {
      const button = event.target.closest('.dv-checkbox-option');
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const option = api.options(input).find(item => item.value === button.dataset.value);
      if (!option) return;
      const selected = api.selectedOptions(input);
      if (option.selected && selected.length === 1 && !allowEmpty) return;
      option.selected = !option.selected;
      api.markSelectionIntent(input, 'explicit');
      // Publish the canonical native-control state before refreshing the
      // visual buttons. This avoids stale detached-button closures during
      // consecutive clicks, notably in Firefox.
      api.emitChange(input);
      sync();
    });

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
