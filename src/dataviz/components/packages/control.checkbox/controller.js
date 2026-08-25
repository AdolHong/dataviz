(function exposeCheckbox(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createCheckbox) return;
  root.createCheckbox = function createCheckbox({input, mount}) {
    const host = document.createElement('label');
    host.className = 'dv-checkbox';
    input.dataset.controlNative = 'visible';
    input.classList.add('dv-checkbox__native');
    const mark = document.createElement('span');
    mark.className = 'dv-checkbox__mark';
    mark.setAttribute('aria-hidden', 'true');
    host.append(input, mark);
    mount.replaceChildren(host);
    const sync = () => host.classList.toggle('is-checked', input.checked);
    input.addEventListener('change', sync);
    return {sync};
  };
})(window);
