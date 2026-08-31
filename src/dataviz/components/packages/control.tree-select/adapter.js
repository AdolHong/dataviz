(function registerTreeSelect(global) {
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api) return;
  api.register('tree-select', ({control, input, mount}) => {
    let levels = [];
    try { levels = JSON.parse(control.dataset.cascaderLevels || '[]'); } catch (_error) {}
    const separator = control.dataset.pathSeparator || ' / ';
    const allowEmpty = control.dataset.clearable === 'true';
    const expanded = new Set();
    let initializedExpansion = false;
    const picker = document.createElement('div');
    picker.className = 'dv-tree-select';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-choice-trigger';
    trigger.dataset.controlTrigger = '';
    trigger.innerHTML = '<span data-control-summary></span><i aria-hidden="true">⌄</i>';
    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-tree-panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'dv-choice-search';
    search.placeholder = control.dataset.searchPlaceholder || 'Search paths…';
    search.setAttribute('aria-label', search.placeholder);
    const list = document.createElement('div');
    list.className = 'dv-tree-list';
    list.setAttribute('role', 'tree');
    list.setAttribute('aria-multiselectable', String(Boolean(input.multiple)));
    const empty = document.createElement('div');
    empty.className = 'dv-choice-empty';
    empty.textContent = control.dataset.emptyText || 'No matching paths';
    empty.hidden = true;
    const footer = document.createElement('footer');
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = control.dataset.clearLabel || 'Clear selection';
    const count = document.createElement('small');
    footer.append(clear, count);
    panel.append(search, list, empty, footer);
    picker.append(trigger, panel);
    mount.replaceChildren(picker);
    const overlay = api.floating(picker, trigger, panel, {width: 440, focus: search, onOpen: () => render(true)});
    const paths = () => {
      const values = root.controlPathOptions?.({control, input, levels}) || [];
      return [...new Map(values.filter(path => Array.isArray(path) && path.length === levels.length).map(path => [JSON.stringify(path), path])).values()];
    };
    const rebuildNative = values => {
      const key = control.closest('[data-control-key]')?.dataset.controlKey;
      const stored = global.dataviz?.control?.value?.(key);
      const storedPaths = input.multiple
        ? (Array.isArray(stored) ? stored : [])
        : (Array.isArray(stored) && stored.length ? [stored] : []);
      const previous = input.options.length
        ? new Set(api.selectedOptions(input).map(option => option.value))
        : new Set(storedPaths.map(JSON.stringify));
      const nodes = values.map(path => {
        const option = document.createElement('option');
        option.value = JSON.stringify(path);
        option.textContent = path.join(separator);
        option.selected = previous.has(option.value);
        return option;
      });
      if (key && global.dataviz?.control?.reconcileOptionDomain) {
        global.dataviz.control.reconcileOptionDomain(input, nodes, {
          selectedValues:[...previous],
          required:control.dataset.required === 'true',
        });
      } else input.replaceChildren(...nodes);
    };
    const toggleLeaf = path => {
      const option = api.options(input).find(item => item.value === JSON.stringify(path));
      if (!option) return;
      if (input.multiple && option.selected && api.selectedOptions(input).length === 1 && !allowEmpty) return;
      if (selectionKeyFor(input)) api.markSelectionIntent(input, 'explicit');
      api.setOption(input, option, input.multiple ? !option.selected : true);
      render(false);
      api.emitChange(input);
      if (!input.multiple) overlay.close({returnFocus: true});
    };
    const toggleDescendants = (descendants, selected) => {
      const values = descendants.map(JSON.stringify);
      const shouldSelect = values.some(value => !selected.has(value));
      const selectedOutside = [...selected].filter(value => !values.includes(value)).length;
      if (!shouldSelect && !allowEmpty && selectedOutside === 0) return;
      if (selectionKeyFor(input)) api.markSelectionIntent(input, 'explicit');
      api.options(input).forEach(option => {
        if (values.includes(option.value)) option.selected = shouldSelect;
      });
      render(false);
      api.emitChange(input);
    };
    function render(rebuild = true) {
      const values = paths();
      if (rebuild) rebuildNative(values);
      if (!initializedExpansion) {
        const depth = Math.min(
          Math.max(0, Number(control.dataset.defaultExpandDepth || 0)),
          Math.max(0, levels.length - 1),
        );
        values.forEach(path => {
          for (let index = 1; index <= depth; index += 1) {
            expanded.add(JSON.stringify(path.slice(0, index)));
          }
        });
        initializedExpansion = true;
      }
      const selected = new Set(api.selectedOptions(input).map(option => option.value));
      const query = search.value.trim().toLocaleLowerCase();
      list.replaceChildren();
      let rendered = 0;
      if (query) {
        values.filter(path => path.join(separator).toLocaleLowerCase().includes(query)).forEach(path => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = `dv-tree-option dv-tree-option--result${selected.has(JSON.stringify(path)) ? ' is-selected' : ''}`;
          button.setAttribute('role', 'treeitem');
          button.setAttribute('aria-selected', String(selected.has(JSON.stringify(path))));
          button.innerHTML = `<span>${api.escape(path.join(separator))}</span><i aria-hidden="true">✓</i>`;
          button.addEventListener('click', () => toggleLeaf(path));
          list.append(button);
          rendered += 1;
        });
      } else {
        const walk = (prefix, depth) => {
          const candidates = values.filter(path => prefix.every((value, index) => String(path[index]) === String(value)));
          const children = [...new Map(candidates.map(path => [String(path[depth]), path])).values()];
          children.forEach(path => {
            const nodePath = path.slice(0, depth + 1);
            const key = JSON.stringify(nodePath);
            const leaf = depth === levels.length - 1;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `dv-tree-option${leaf && selected.has(JSON.stringify(path)) ? ' is-selected' : ''}`;
            button.style.setProperty('--dv-tree-depth', depth);
            button.setAttribute('role', 'treeitem');
            button.setAttribute('aria-level', String(depth + 1));
            if (leaf) button.setAttribute('aria-selected', String(selected.has(JSON.stringify(path))));
            else button.setAttribute('aria-expanded', String(expanded.has(key)));
            button.innerHTML = `<span><b aria-hidden="true">${leaf ? '·' : (expanded.has(key) ? '−' : '+')}</b>${api.escape(path[depth])}</span><i aria-hidden="true">${leaf && selected.has(JSON.stringify(path)) ? '✓' : ''}</i>`;
            button.addEventListener('click', () => {
              if (leaf) toggleLeaf(path);
              else {
                expanded.has(key) ? expanded.delete(key) : expanded.add(key);
                render(false);
              }
            });
            let renderedNode = button;
            if (!leaf && control.dataset.selectionStrategy === 'cascade' && input.multiple) {
              const descendants = candidates.filter(candidate => nodePath.every((value, index) => String(candidate[index]) === String(value)));
              const descendantValues = descendants.map(JSON.stringify);
              const selectedCount = descendantValues.filter(value => selected.has(value)).length;
              const checked = descendantValues.length > 0 && selectedCount === descendantValues.length;
              const mixed = selectedCount > 0 && selectedCount < descendantValues.length;
              const row = document.createElement('div');
              row.className = `dv-tree-branch${checked ? ' is-selected' : ''}${mixed ? ' is-mixed' : ''}`;
              const check = document.createElement('button');
              check.type = 'button';
              check.className = 'dv-tree-branch__check';
              check.setAttribute('role', 'checkbox');
              check.setAttribute('aria-checked', mixed ? 'mixed' : String(checked));
              check.setAttribute('aria-label', `${checked ? 'Clear' : 'Select'} ${path[depth]} descendants`);
              check.addEventListener('click', () => toggleDescendants(descendants, selected));
              row.append(check, button);
              renderedNode = row;
            }
            list.append(renderedNode);
            rendered += 1;
            if (!leaf && expanded.has(key)) walk(nodePath, depth + 1);
          });
        };
        walk([], 0);
      }
      empty.hidden = rendered > 0;
      api.renderSummary(
        trigger,
        input,
        control,
        control.dataset.placeholder || 'All paths',
        api.hierarchySummaryLabels(values, selected, control.dataset.showCheckedStrategy || 'child', separator),
      );
      count.textContent = `${values.length} available`;
      clear.hidden = !allowEmpty;
      clear.disabled = input.disabled || selected.size === 0;
      trigger.disabled = input.disabled;
      if (overlay.isOpen()) overlay.reposition();
    }
    search.addEventListener('input', () => render(false));
    clear.addEventListener('click', () => {
      if (!allowEmpty || input.disabled) return;
      if (selectionKeyFor(input)) api.markSelectionIntent(input, 'explicit');
      api.clearOptions(input);
      render(false);
      api.emitChange(input);
    });
    api.keyboardList(panel, button => button.click());
    return {sync: () => render(true), overlay};
  });
  function selectionKeyFor(input) {
    return input?.closest('[data-control-key]')?.dataset.controlKey || null;
  }
})(window);
