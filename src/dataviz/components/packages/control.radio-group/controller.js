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
      const existing = new Map(Array.from(group.children, button => [button.dataset.value, button]));
      let cursor = group.firstElementChild;
      options.forEach((option, index) => {
        const unavailable = Boolean(option.disabled);
        if (
          unavailable
          && option.dataset.preserveValue !== 'true'
          && control.dataset.showUnavailable !== 'true'
        ) return;
        const button = existing.get(option.value) || document.createElement('button');
        existing.delete(option.value);
        button.type = 'button';
        button.className = `dv-radio-group__option${option.selected ? ' is-selected' : ''}${unavailable ? ' is-unavailable' : ''}`;
        button.dataset.value = option.value;
        if (button.textContent !== option.textContent) button.textContent = option.textContent;
        button.setAttribute('role', 'radio');
        button.setAttribute('aria-checked', String(option.selected));
        button.tabIndex = option.selected || (!api.selectedOptions(input).length && index === 0) ? 0 : -1;
        button.disabled = input.disabled || unavailable;
        if (button !== cursor) group.insertBefore(button, cursor);
        cursor = button.nextElementSibling;
      });
      existing.forEach(button => button.remove());
    }

    // Resolve options at activation time: native candidates may have been
    // replaced by a snapshot while the button/focus remains in place.
    const targetOption = event => {
      const button = event.target.closest('.dv-radio-group__option');
      if (!button || button.disabled) return null;
      return api.options(input).find(option => option.value === button.dataset.value);
    };
    group.addEventListener('click', event => choose(targetOption(event)));
    group.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      const option = targetOption(event);
      if (!option) return;
      event.preventDefault();
      const enabled = api.options(input).filter(item => !item.disabled);
      const current = enabled.indexOf(option);
      const delta = ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1;
      choose(enabled[(current + delta + enabled.length) % enabled.length], {focus:true});
    });

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
