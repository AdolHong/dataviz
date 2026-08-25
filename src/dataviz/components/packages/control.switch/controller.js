(function exposeSwitch(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createSwitch) return;
  root.createSwitch = function createSwitch({control, input, mount}) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dv-switch';
    button.setAttribute('role', 'switch');
    const label = document.createElement('span');
    label.className = 'dv-switch__label';
    const thumb = document.createElement('span');
    thumb.className = 'dv-switch__thumb';
    button.append(label, thumb);
    const sync = () => {
      button.setAttribute('aria-checked', String(input.checked));
      button.classList.toggle('is-checked', input.checked);
      button.disabled = input.disabled;
      label.textContent = input.checked
        ? (control.dataset.checkedLabel || '')
        : (control.dataset.uncheckedLabel || '');
      label.hidden = !label.textContent;
    };
    button.addEventListener('click', () => {
      if (input.disabled) return;
      input.checked = !input.checked;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      sync();
    });
    input.dataset.controlNative = 'hidden';
    mount.replaceChildren(button);
    return {sync};
  };
})(window);
