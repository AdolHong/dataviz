(function exposeSegmentedSelector(global) {
  const root = global.datavizComponents;
  const api = root?.selectors;
  if (!api || root.createSegmentedSelector) return;
  root.createSegmentedSelector = function createSegmentedSelector({selector, input, mount}) {
    const control = document.createElement('div');
    control.className = `dv-segmented dv-segmented--${selector.dataset.variant || 'default'}`;
    control.setAttribute('role', 'radiogroup');
    control.setAttribute('aria-label', input.getAttribute('aria-label') || 'Choose one');
    const emptyMeansAll = selector.dataset.emptyMeansAll === 'true';
    const required = selector.dataset.required === 'true';
    const all = document.createElement('button');
    all.type = 'button';
    all.className = 'dv-segmented__option dv-segmented__option--all';
    all.textContent = selector.dataset.allLabel || 'All';
    all.setAttribute('role', 'radio');
    const clear = () => api.clearOptions(input);
    all.addEventListener('click', () => {
      if (input.disabled || required) return;
      clear();
      sync();
      api.emitChange(input);
    });
    control.append(all);

    function sync() {
      const options = api.options(input);
      const selected = api.selectedOptions(input)[0];
      all.hidden = required && !emptyMeansAll;
      all.disabled = input.disabled || required;
      all.classList.toggle('is-selected', !selected);
      all.setAttribute('aria-checked', String(!selected));
      control.querySelectorAll('[data-value]').forEach(node => node.remove());
      options.forEach(option => {
        const unavailable = Boolean(option.disabled);
        if (unavailable && selector.dataset.showUnavailable !== 'true') return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `dv-segmented__option${option.selected && !unavailable ? ' is-selected' : ''}`;
        button.dataset.value = option.value;
        button.textContent = option.textContent;
        button.setAttribute('role', 'radio');
        button.setAttribute('aria-checked', String(option.selected && !unavailable));
        button.disabled = input.disabled || unavailable;
        button.addEventListener('click', () => {
          if (button.disabled) return;
          api.setOption(input, option, true);
          sync();
          api.emitChange(input);
        });
        control.append(button);
      });
    }
    mount.replaceChildren(control);
    return {sync};
  };
})(window);
