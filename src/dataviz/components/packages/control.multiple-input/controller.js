(function exposeMultipleInput(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createMultipleInput) return;

  root.createMultipleInput = function createMultipleInput({control, input, mount}) {
    const shell = document.createElement('div');
    shell.className = 'dv-multiple-input';
    const rows = document.createElement('div');
    rows.className = 'dv-multiple-input__rows';
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'dv-multiple-input__add';
    add.textContent = '+ Add value';
    shell.append(rows, add);
    mount.replaceChildren(shell);
    const valueType = control.dataset.valueType || 'text';
    const maxItems = Math.max(0, Number(control.dataset.maxItems || 0));
    let synchronizing = false;

    const parse = () => {
      if (!input.value) return [];
      try {
        const value = JSON.parse(input.value);
        return Array.isArray(value) ? value : [];
      } catch (_error) {
        return input.value.split(',').map(value => value.trim()).filter(Boolean);
      }
    };
    const typed = element => {
      if (element.value === '') return null;
      if (valueType === 'integer' || valueType === 'number') return Number(element.value);
      return element.value;
    };
    const publish = () => {
      if (synchronizing) return;
      const values = [...rows.querySelectorAll('[data-multiple-value]')]
        .map(typed).filter(value => value !== null);
      input.value = JSON.stringify(values);
      input.dispatchEvent(new Event('input', {bubbles:true}));
      api.emitChange(input);
      syncButtons();
    };
    const createValueInput = value => {
      const element = document.createElement('input');
      element.dataset.multipleValue = '';
      element.type = valueType === 'date' ? 'date'
        : ['integer', 'number'].includes(valueType) ? 'number' : 'text';
      element.value = value ?? '';
      element.disabled = input.disabled;
      element.required = input.required;
      if (valueType === 'integer') element.step = input.step || '1';
      else if (valueType === 'number') element.step = input.step || 'any';
      if (input.min) element.min = input.min;
      if (input.max) element.max = input.max;
      if (input.maxLength > 0) element.maxLength = input.maxLength;
      element.addEventListener('input', publish);
      return element;
    };
    const append = (value = '') => {
      const row = document.createElement('div');
      row.className = 'dv-multiple-input__row';
      const valueInput = createValueInput(value);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'dv-multiple-input__remove';
      remove.textContent = '×';
      remove.setAttribute('aria-label', 'Remove value');
      remove.disabled = input.disabled;
      remove.addEventListener('click', () => {
        row.remove();
        publish();
      });
      row.append(valueInput, remove);
      rows.append(row);
      return valueInput;
    };
    const syncButtons = () => {
      add.disabled = input.disabled || Boolean(maxItems && rows.children.length >= maxItems);
      rows.querySelectorAll('input, button').forEach(element => { element.disabled = input.disabled; });
    };
    const render = () => {
      synchronizing = true;
      const values = parse();
      rows.replaceChildren();
      values.forEach(append);
      synchronizing = false;
      syncButtons();
    };
    add.addEventListener('click', () => {
      if (add.disabled) return;
      append('').focus();
      syncButtons();
    });
    render();
    return {sync:render};
  };
})(window);
