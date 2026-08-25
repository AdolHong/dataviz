(function exposeInput(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createInput) return;

  root.createInput = function createInput({control, input, mount}) {
    const shell = document.createElement('div');
    shell.className = 'dv-input';
    const prefix = document.createElement('span');
    prefix.className = 'dv-input__prefix';
    prefix.textContent = control.dataset.prefix || '';
    prefix.hidden = !prefix.textContent;
    const suffix = document.createElement('span');
    suffix.className = 'dv-input__suffix';
    suffix.textContent = control.dataset.suffix || '';
    suffix.hidden = !suffix.textContent;
    input.classList.add('dv-input__control');
    input.dataset.controlNative = 'visible';
    if (input.tagName === 'TEXTAREA') {
      input.rows = Math.max(1, Number(control.dataset.minRows || 2));
      input.style.setProperty('--dv-input-max-rows', String(Math.max(input.rows, Number(control.dataset.maxRows || 6))));
    }
    shell.append(prefix, input, suffix);
    const count = document.createElement('small');
    count.className = 'dv-input__count';
    count.setAttribute('aria-live', 'polite');
    count.hidden = control.dataset.showCount !== 'true';
    mount.replaceChildren(shell, count);
    const sync = () => {
      const maximum = Number(input.maxLength || 0);
      count.textContent = maximum > 0 ? `${input.value.length} / ${maximum}` : String(input.value.length);
      count.hidden = control.dataset.showCount !== 'true';
    };
    input.addEventListener('input', sync);
    return {sync};
  };
})(window);
