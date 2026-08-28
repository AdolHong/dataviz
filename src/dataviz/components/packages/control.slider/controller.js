(function exposeSlider(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createSlider) return;
  root.createSlider = function createSlider({control, input, mount}) {
    if (control.dataset.controlType === 'range_input') {
      const shell = document.createElement('div');
      shell.className = 'dv-slider dv-slider--range';
      const minimum = Number(input.min || 0);
      const maximum = Number(input.max || 100);
      const step = input.step || (control.dataset.valueType === 'integer' ? '1' : 'any');
      const parse = () => {
        const [start, end] = String(input.value || '').split(',', 2).map(Number);
        return [Number.isFinite(start) ? start : minimum, Number.isFinite(end) ? end : maximum];
      };
      const start = document.createElement('input');
      const end = document.createElement('input');
      const startNumber = document.createElement('input');
      const endNumber = document.createElement('input');
      [start, end].forEach(element => {
        element.type = 'range';
        element.className = 'dv-slider__track';
        element.min = String(minimum);
        element.max = String(maximum);
        element.step = step;
      });
      [startNumber, endNumber].forEach(element => {
        element.type = 'number';
        element.className = 'dv-slider__input';
        element.min = String(minimum);
        element.max = String(maximum);
        element.step = step;
        element.hidden = control.dataset.showInput !== 'true';
      });
      const values = document.createElement('output');
      values.className = 'dv-slider__value';
      const publish = (source, edge) => {
        let left = Number(edge === 'start' ? source.value : start.value);
        let right = Number(edge === 'end' ? source.value : end.value);
        if (left > right) edge === 'start' ? right = left : left = right;
        input.value = `${left},${right}`;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        api.emitChange(input);
        sync();
      };
      start.addEventListener('input', () => publish(start, 'start'));
      end.addEventListener('input', () => publish(end, 'end'));
      startNumber.addEventListener('input', () => publish(startNumber, 'start'));
      endNumber.addEventListener('input', () => publish(endNumber, 'end'));
      shell.append(start, end, values, startNumber, endNumber);
      mount.replaceChildren(shell);
      const sync = () => {
        const [left, right] = parse();
        start.value = startNumber.value = String(left);
        end.value = endNumber.value = String(right);
        values.textContent = `${left} – ${right}`;
        values.hidden = control.dataset.tooltip === 'never';
        [start, end, startNumber, endNumber].forEach(element => { element.disabled = input.disabled; });
      };
      sync();
      return {sync};
    }
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
