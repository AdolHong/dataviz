(function exposeCheckboxGroup(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createCheckboxGroup) return;

  root.createCheckboxGroup = function createCheckboxGroup({control, input, mount}) {
    const group = document.createElement('div');
    group.className = 'dv-checkbox-group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', input.getAttribute('aria-label') || 'Choose values');

    const maxSelected = Number(control.dataset.maxSelected || 0);
    const allowEmpty = control.dataset.clearable === 'true';
    const optionsHost = document.createElement('div');
    optionsHost.className = 'dv-checkbox-group__options';
    group.append(optionsHost);

    function sync() {
      const options = api.options(input);
      const selected = api.selectedOptions(input);

      // A host snapshot can arrive between pointerdown/up or keydown/up.
      // Keep unchanged targets attached so syncing cannot swallow activation
      // or drop keyboard focus. Native option nodes may themselves be new.
      const existing = new Map(Array.from(optionsHost.children, button => [button.dataset.value, button]));
      let cursor = optionsHost.firstElementChild;
      options.forEach(option => {
        const unavailable = Boolean(option.disabled);
        if (
          unavailable
          && option.dataset.preserveValue !== 'true'
          && control.dataset.showUnavailable !== 'true'
        ) return;
        const capped = Boolean(maxSelected && selected.length >= maxSelected && !option.selected);
        let button = existing.get(option.value);
        if (!button) {
          button = document.createElement('button');
          button.type = 'button';
          const mark = document.createElement('i');
          mark.setAttribute('aria-hidden', 'true');
          button.append(mark, document.createElement('span'));
        }
        existing.delete(option.value);
        button.className = `dv-checkbox-option${option.selected ? ' is-selected' : ''}${unavailable ? ' is-unavailable' : ''}`;
        button.dataset.value = option.value;
        button.setAttribute('aria-pressed', String(option.selected));
        button.disabled = input.disabled || unavailable || capped;
        const [mark, label] = button.children;
        const markText = option.selected ? '✓' : '';
        if (mark.textContent !== markText) mark.textContent = markText;
        if (label.textContent !== option.textContent) label.textContent = option.textContent;
        if (button !== cursor) optionsHost.insertBefore(button, cursor);
        cursor = button.nextElementSibling;
      });
      existing.forEach(button => button.remove());
    }

    optionsHost.addEventListener('click', event => {
      const button = event.target.closest('.dv-checkbox-option');
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const option = api.options(input).find(item => item.value === button.dataset.value);
      if (!option) return;
      const selected = api.selectedOptions(input);
      if (option.selected && selected.length === 1 && !allowEmpty) return;
      option.selected = !option.selected;
      api.markSelectionIntent(input, 'explicit');
      // Publish the canonical native-control state before refreshing the
      // visual buttons. This avoids stale detached-button closures during
      // consecutive clicks, notably in Firefox.
      api.emitChange(input);
      sync();
    });

    mount.replaceChildren(group);
    return {sync};
  };
})(window);
