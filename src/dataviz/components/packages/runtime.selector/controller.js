(function installDatavizSelectorRuntime(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.selectors) return;
  const factories = new Map();
  const escape = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  const nativeOptions = input => Array.from(input?.options || []);
  const options = input => nativeOptions(input).filter(option => option.dataset.emptyOption !== 'true');
  const selectedOptions = input => options(input).filter(option => option.selected && !option.disabled);
  const availableOptions = input => options(input).filter(option => !option.disabled);
  const emitChange = input => input.dispatchEvent(new Event('change', {bubbles: true}));
  const setOption = (input, option, selected) => {
    if (!input.multiple && selected) nativeOptions(input).forEach(item => { item.selected = item === option; });
    else option.selected = selected;
  };
  const clearOptions = input => {
    const empty = nativeOptions(input).find(option => option.dataset.emptyOption === 'true');
    nativeOptions(input).forEach(option => { option.selected = option === empty; });
    if (!empty && !input.multiple) input.selectedIndex = -1;
  };
  const summary = (input, placeholder = 'Choose…') => {
    const available = availableOptions(input);
    const selected = selectedOptions(input);
    if (!input.multiple) return selected[0]?.textContent || placeholder;
    if (available.length && selected.length === available.length) return `All (${available.length})`;
    return selected.length ? `${selected.length} selected` : placeholder;
  };
  const optionGroup = option => option.dataset.group || (
    option.parentElement?.tagName === 'OPTGROUP' ? option.parentElement.label : ''
  );
  const optionSearchText = option => [
    option.textContent,
    option.value,
    optionGroup(option),
    option.dataset.description,
    option.dataset.keywords,
  ].filter(Boolean).join(' ').toLocaleLowerCase();
  const renderSummary = (trigger, input, selector, placeholder = 'Choose…', summaryLabels = null) => {
    const host = trigger.querySelector('[data-selector-summary]');
    if (!host) return;
    const available = availableOptions(input);
    const selected = selectedOptions(input);
    const emptyMeansAll = selector.dataset.emptyMeansAll === 'true';
    const maxVisible = Math.max(0, Number(selector.dataset.maxVisibleTags || 2));
    host.replaceChildren();
    if (!input.multiple) {
      host.textContent = selected[0]?.textContent || (emptyMeansAll ? selector.dataset.allLabel || 'All' : placeholder);
      return;
    }
    if (emptyMeansAll && (!selected.length || (available.length && selected.length === available.length))) {
      const label = document.createElement('span');
      label.className = 'dv-choice-summary__all';
      label.textContent = available.length ? `${selector.dataset.allLabel || 'All'} (${available.length})` : selector.dataset.allLabel || 'All';
      host.append(label);
      return;
    }
    if (!selected.length) {
      host.textContent = placeholder;
      return;
    }
    const labels = Array.isArray(summaryLabels) ? summaryLabels : selected.map(option => option.textContent);
    labels.slice(0, maxVisible).forEach(value => {
      const tag = document.createElement('span');
      tag.className = 'dv-choice-summary__tag';
      tag.textContent = value;
      host.append(tag);
    });
    const hidden = labels.length - maxVisible;
    if (hidden > 0) {
      const rest = document.createElement('span');
      rest.className = 'dv-choice-summary__rest';
      rest.textContent = `+${hidden}`;
      host.append(rest);
    }
  };
  const hierarchySummaryLabels = (paths, selectedValues, strategy = 'child', separator = ' / ') => {
    const selected = selectedValues instanceof Set ? selectedValues : new Set(selectedValues || []);
    const leaves = paths.filter(path => selected.has(JSON.stringify(path)));
    if (strategy === 'child') return leaves.map(path => path.join(separator));
    const descendants = prefix => paths.filter(path => prefix.every((value, index) => String(path[index]) === String(value)));
    const fullySelected = prefix => {
      const values = descendants(prefix);
      return values.length > 0 && values.every(path => selected.has(JSON.stringify(path)));
    };
    const labels = [];
    const walk = (prefix, depth) => {
      const children = [...new Map(descendants(prefix).map(path => [String(path[depth]), path[depth]])).values()];
      children.forEach(value => {
        const node = [...prefix, value];
        const leaf = depth >= (paths[0]?.length || 0) - 1;
        if (strategy === 'parent' && fullySelected(node)) labels.push(node.join(separator));
        else if (leaf) {
          if (selected.has(JSON.stringify(node))) labels.push(node.join(separator));
        } else walk(node, depth + 1);
      });
    };
    walk([], 0);
    if (strategy === 'all') {
      const inferred = [];
      paths.forEach(path => {
        for (let depth = 1; depth < path.length; depth += 1) {
          const prefix = path.slice(0, depth);
          const label = prefix.join(separator);
          if (fullySelected(prefix) && !inferred.includes(label)) inferred.push(label);
        }
      });
      return [...inferred, ...leaves.map(path => path.join(separator))];
    }
    return labels;
  };
  const focusableOptions = panel => Array.from(panel.querySelectorAll(
    '[role="option"]:not([hidden]):not(:disabled), [role="treeitem"]:not([hidden]):not(:disabled)'
  ));
  function keyboardList(panel, choose) {
    panel.addEventListener('keydown', event => {
      const items = focusableOptions(panel);
      if (!items.length) return;
      const current = items.indexOf(document.activeElement);
      let next = current;
      if (event.key === 'ArrowDown') next = Math.min(items.length - 1, current + 1);
      else if (event.key === 'ArrowUp') next = Math.max(0, current - 1);
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = items.length - 1;
      else if (['Enter', ' '].includes(event.key) && current >= 0) {
        event.preventDefault();
        choose?.(items[current]);
        return;
      } else return;
      event.preventDefault();
      items[next < 0 ? 0 : next].focus();
    });
  }
  function floating(owner, trigger, panel, options = {}) {
    return root.overlay.register({
      owner,
      trigger,
      panel,
      group: 'selector',
      floating: true,
      width: options.width || 420,
      align: options.align || 'start',
      focus: options.focus || null,
      ariaHaspopup: options.ariaHaspopup || 'listbox',
      onOpen: options.onOpen,
      onClose: options.onClose,
    }).api;
  }
  function register(template, factory) {
    if (factories.has(template)) throw new Error(`Selector adapter already registered: ${template}`);
    factories.set(template, factory);
  }
  function hydrate(scope = document) {
    const nodes = [];
    if (scope.matches?.('.dv-selector')) nodes.push(scope);
    nodes.push(...scope.querySelectorAll?.('.dv-selector') || []);
    nodes.forEach(selector => {
      if (selector.dataset.selectorHydrated === 'true') return;
      const template = selector.dataset.selectorTemplate;
      const factory = factories.get(template);
      if (!factory) return;
      const input = selector.querySelector('[data-selection-input], select, input');
      const mount = selector.querySelector('[data-selector-mount]');
      if (!input || !mount) return;
      const instance = factory({selector, input, mount, api});
      selector.dataset.selectorHydrated = 'true';
      selector._datavizSelector = instance || {};
      input._syncChoiceControl = () => selector._datavizSelector?.sync?.();
      selector._syncSelector = input._syncChoiceControl;
      input._syncChoiceControl();
    });
  }
  function sync(scope = document) {
    const nodes = scope.matches?.('.dv-selector') ? [scope] : Array.from(scope.querySelectorAll?.('.dv-selector') || []);
    nodes.forEach(selector => selector._syncSelector?.());
  }
  const api = {
    register,
    hydrate,
    sync,
    escape,
    options,
    selectedOptions,
    availableOptions,
    emitChange,
    setOption,
    clearOptions,
    summary,
    optionGroup,
    optionSearchText,
    renderSummary,
    hierarchySummaryLabels,
    floating,
    keyboardList,
  };
  root.selectors = api;
  const previousHydrate = root.hydrate;
  root.hydrate = scope => {
    previousHydrate?.(scope || document);
    hydrate(scope || document);
  };
})(window);
