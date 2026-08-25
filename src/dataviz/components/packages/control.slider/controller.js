(function exposeSlider(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createSlider) return;
  root.createSlider = function createSlider({control, input, mount}) {
    const shell = document.createElement('div');
    shell.className = 'dv-slider';
    input.classList.add('dv-slider__track');
    input.dataset.controlNative = 'visible';
    const value = document.createElement('output');
    value.className = 'dv-slider__value';
    const number = document.createElement('input');
    number.type = 'number';
    number.className = 'dv-slider__input';
    number.min = input.min;
    number.max = input.max;
    number.step = input.step;
    number.hidden = control.dataset.showInput !== 'true';
    const marks = document.createElement('div');
    marks.className = 'dv-slider__marks';
    let markValues = [];
    try { markValues = JSON.parse(control.dataset.marks || '[]'); } catch (_error) {}
    markValues.forEach(mark => {
      const label = document.createElement('span');
      const minimum = Number(input.min || 0);
      const maximum = Number(input.max || 100);
      label.style.left = `${maximum === minimum ? 0 : ((Number(mark.value) - minimum) / (maximum - minimum)) * 100}%`;
      label.textContent = mark.label;
      marks.append(label);
    });
    const sync = () => {
      value.value = input.value;
      value.textContent = input.value;
      value.hidden = control.dataset.tooltip === 'never';
      number.value = input.value;
      number.disabled = input.disabled;
    };
    input.addEventListener('input', sync);
    number.addEventListener('input', () => {
      input.value = number.value;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      sync();
    });
    shell.append(input, value, marks, number);
    mount.replaceChildren(shell);
    return {sync};
  };
})(window);
