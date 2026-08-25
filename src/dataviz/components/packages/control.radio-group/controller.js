(function exposeRadioGroup(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createRadioGroup) return;

  root.createRadioGroup = function createRadioGroup({control, input, mount}) {
    const group = document.createElement('div');
    const optionType = control.dataset.optionType || 'default';
    const buttonStyle = control.dataset.buttonStyle || 'outline';
    group.className = `dv-radio-group dv-radio-group--${optionType} dv-radio-group--${buttonStyle}`;
    group.setAttribute('role', 'radiogroup');
    group.setAttribute('aria-label', input.getAttribute('aria-label') || 'Choose one option');

    const choose = (option, {focus = false} = {}) => {
      if (!option || option.disabled || input.disabled) return;
      api.setOption(input, option, true);
      sync();
      if (focus) group.querySelector(`[data-value="${CSS.escape(option.value)}"]`)?.focus();
      api.emitChange(input);
    };

    function sync() {
      const options = api.options(input);
      group.replaceChildren();
      options.forEach((option, index) => {
        const unavailable = Boolean(option.disabled);
        if (unavailable && control.dataset.showUnavailable !== 'true') return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `dv-radio-group__option${option.selected && !unavailable ? ' is-selected' : ''}`;
        button.dataset.value = option.value;
        button.textContent = option.textContent;
        button.setAttribute('role', 'radio');
        button.setAttribute('aria-checked', String(option.selected && !unavailable));
        button.tabIndex = option.selected || (!api.selectedOptions(input).length && index === 0) ? 0 : -1;
        button.disabled = input.disabled || unavailable;
        button.addEventListener('click', () => choose(option));
        button.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
          event.preventDefault();
          const enabled = options.filter(item => !item.disabled);
          const current = enabled.indexOf(option);
          const delta = ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1;
          choose(enabled[(current + delta + enabled.length) % enabled.length], {focus: true});
        });
        group.append(button);
      });
    }

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
