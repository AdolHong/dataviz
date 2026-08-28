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
          api.markSelectionIntent(input, 'explicit');
          sync();
          api.emitChange(input);
        });
        optionsHost.append(button);
      });
    }

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
