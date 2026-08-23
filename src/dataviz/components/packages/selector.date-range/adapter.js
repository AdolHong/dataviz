(function registerDateRange(global) {
  const api = global.datavizComponents?.selectors;
  if (!api) return;
  api.register('date-range', ({selector, input, mount}) => {
    const group = document.createElement('div');
    group.className = 'dv-date-range';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', input.getAttribute('aria-label') || 'Date range');
    const make = (part, labelText) => {
      const label = document.createElement('label');
      label.className = 'dv-date-range__field';
      const span = document.createElement('span');
      span.textContent = labelText;
      const control = document.createElement('input');
      control.type = 'date';
      control.dataset.rangePart = part;
      if (selector.dataset.min) control.min = selector.dataset.min;
      if (selector.dataset.max) control.max = selector.dataset.max;
      label.append(span, control);
      return {label, control};
    };
    const start = make('start', selector.dataset.startLabel || 'Start');
    const end = make('end', selector.dataset.endLabel || 'End');
    const presets = document.createElement('div');
    presets.className = 'dv-date-range__presets';
    let presetValues = [];
    try { presetValues = JSON.parse(selector.dataset.presets || '[]'); } catch (_error) {}
    presetValues.forEach(preset => {
      if (!preset?.label || !preset?.start || !preset?.end) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = preset.label;
      button.addEventListener('click', () => {
        start.control.value = preset.start;
        end.control.value = preset.end;
        commit();
      });
      presets.append(button);
    });
    const actions = document.createElement('div');
    actions.className = 'dv-date-range__actions';
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = selector.dataset.clearLabel || 'Clear';
    clear.addEventListener('click', () => {
      start.control.value = '';
      end.control.value = '';
      commit();
    });
    const status = document.createElement('small');
    status.setAttribute('aria-live', 'polite');
    actions.append(clear, status);
    if (presets.childElementCount) group.append(presets);
    group.append(start.label, end.label, actions);
    mount.replaceChildren(group);
    function commit() {
      const allowOpen = selector.dataset.allowOpenRange === 'true';
      if (!allowOpen && start.control.value && !end.control.value) end.control.value = start.control.value;
      if (!allowOpen && end.control.value && !start.control.value) start.control.value = end.control.value;
      if (start.control.value) end.control.min = start.control.value;
      const invalidOrder = Boolean(start.control.value && end.control.value && start.control.value > end.control.value);
      if (invalidOrder) end.control.value = start.control.value;
      input.value = start.control.value || end.control.value
        ? [start.control.value, end.control.value].join(',')
        : '';
      status.textContent = start.control.value || end.control.value
        ? `${start.control.value || '…'} → ${end.control.value || '…'}`
        : 'All dates';
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      sync();
    }
    function sync() {
      const value = String(input.value || '').split(',', 2);
      start.control.value = value[0] || '';
      end.control.value = value[1] || '';
      start.control.disabled = input.disabled;
      end.control.disabled = input.disabled;
      clear.disabled = input.disabled || (!start.control.value && !end.control.value);
      presets.querySelectorAll('button').forEach(button => { button.disabled = input.disabled; });
      end.control.min = start.control.value || selector.dataset.min || '';
      status.textContent = start.control.value || end.control.value
        ? `${start.control.value || '…'} → ${end.control.value || '…'}`
        : 'All dates';
    }
    start.control.addEventListener('change', commit);
    end.control.addEventListener('change', commit);
    return {sync};
  });
})(window);
