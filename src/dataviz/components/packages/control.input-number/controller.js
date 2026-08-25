(function exposeInputNumber(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createInputNumber) return;

  root.createInputNumber = function createInputNumber({control, input, mount}) {
    const shell = document.createElement('div');
    shell.className = 'dv-input-number';
    const prefix = document.createElement('span');
    prefix.className = 'dv-input-number__affix';
    prefix.textContent = control.dataset.prefix || '';
    prefix.hidden = !prefix.textContent;
    input.classList.add('dv-input-number__control');
    input.dataset.controlNative = 'visible';
    const suffix = document.createElement('span');
    suffix.className = 'dv-input-number__affix';
    suffix.textContent = control.dataset.suffix || '';
    suffix.hidden = !suffix.textContent;
    const steps = document.createElement('span');
    steps.className = 'dv-input-number__steps';
    const up = document.createElement('button');
    const down = document.createElement('button');
    up.type = down.type = 'button';
    up.className = down.className = 'dv-input-number__step';
    up.textContent = '＋';
    down.textContent = '−';
    up.setAttribute('aria-label', 'Increase value');
    down.setAttribute('aria-label', 'Decrease value');
    steps.append(up, down);
    steps.hidden = control.dataset.numberControls === 'false';
    const step = direction => {
      if (input.disabled) return;
      direction > 0 ? input.stepUp() : input.stepDown();
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
    };
    up.addEventListener('click', () => step(1));
    down.addEventListener('click', () => step(-1));
    shell.append(prefix, input, suffix, steps);
    mount.replaceChildren(shell);
    return {sync: () => { up.disabled = down.disabled = input.disabled; }};
  };
})(window);
