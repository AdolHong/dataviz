(function exposeDatePicker(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createDatePicker) return;
  root.createDatePicker = function createDatePicker({control, input, mount}) {
    const shell = document.createElement('div');
    shell.className = 'dv-date-picker';
    input.classList.add('dv-date-picker__control');
    input.dataset.controlNative = 'visible';
    const calendar = document.createElement('button');
    calendar.type = 'button';
    calendar.className = 'dv-date-picker__calendar';
    calendar.setAttribute('aria-label', 'Open calendar');
    calendar.textContent = '▦';
    calendar.addEventListener('click', () => {
      if (input.disabled) return;
      if (typeof input.showPicker === 'function') input.showPicker();
      else input.focus();
    });
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'dv-date-picker__clear';
    clear.textContent = control.dataset.clearLabel || 'Clear';
    clear.addEventListener('click', () => {
      if (input.disabled || control.dataset.clearable !== 'true') return;
      input.value = '';
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      sync();
    });
    shell.append(input, clear, calendar);
    mount.replaceChildren(shell);
    const sync = () => {
      calendar.disabled = input.disabled;
      clear.hidden = control.dataset.clearable !== 'true' || !input.value;
      clear.disabled = input.disabled;
    };
    input.addEventListener('input', sync);
    return {sync};
  };
})(window);
