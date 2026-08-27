(function registerCascader(global) {
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api) return;
  api.register('cascader', ({control, input, mount}) => {
    let levels = [];
    try { levels = JSON.parse(control.dataset.cascaderLevels || '[]'); } catch (_error) {}
    const separator = control.dataset.pathSeparator || ' / ';
    const allowEmpty = control.dataset.clearable === 'true';
    let activePath = [];
    const picker = document.createElement('div');
    picker.className = 'dv-cascader';
    picker.dataset.controlPicker = '';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-choice-trigger';
    trigger.dataset.controlTrigger = '';
    trigger.innerHTML = '<span data-control-summary></span><i aria-hidden="true">⌄</i>';
    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-cascader-panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'dv-choice-search';
    search.placeholder = control.dataset.searchPlaceholder || 'Search paths…';
    search.setAttribute('aria-label', search.placeholder);
    const columns = document.createElement('div');
    columns.className = 'dv-cascader-columns';
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
    panel.append(search, columns, empty, footer);
    picker.append(trigger, panel);
    mount.replaceChildren(picker);
    const overlay = api.floating(picker, trigger, panel, {
      width: Number(control.dataset.overlayWidth || Math.min(720, 220 * Math.max(2, levels.length))),
      focus: search,
      onOpen: () => render(true),
    });
    const pathSource = () => {
      const supplied = typeof root.controlPathOptions === 'function'
        ? root.controlPathOptions({control, input, levels}) || []
        : Array.from(input.options).map(option => {
          try { return JSON.parse(option.value); } catch (_error) { return null; }
        }).filter(Boolean);
      const unique = new Map();
      supplied.forEach(path => {
        if (!Array.isArray(path) || path.length !== levels.length || path.some(value => value == null)) return;
        unique.set(JSON.stringify(path), path);
      });
      return [...unique.values()];
    };
    const selected = () => new Set(api.selectedOptions(input).map(option => option.value));
    const rebuildNative = paths => {
      const selectionKey = control.closest('[data-selection-key]')?.dataset.selectionKey;
      const computeKey = control.closest('[data-compute-key]')?.dataset.computeKey;
      const key = selectionKey || computeKey;
      const stored = selectionKey
        ? global.dataviz?.selection?.value?.(selectionKey)
        : global.dataviz?.compute_parameters?.[key];
      const storedPaths = input.multiple
        ? (Array.isArray(stored) ? stored : [])
        : (Array.isArray(stored) && stored.length ? [stored] : []);
      const previous = input.options.length
        ? new Set(api.selectedOptions(input).map(option => option.value))
        : new Set(storedPaths.map(JSON.stringify));
      const nodes = paths.map(path => {
        const option = document.createElement('option');
        option.value = JSON.stringify(path);
        option.textContent = path.join(separator);
        option.selected = previous.has(option.value);
        return option;
      });
      if (selectionKey && global.dataviz?.selection?.reconcileOptionDomain) {
        global.dataviz.selection.reconcileOptionDomain(input, nodes, {
          selectedValues:[...previous],
          required:control.dataset.required === 'true',
        });
      } else input.replaceChildren(...nodes);
    };
    const choose = path => {
      const value = JSON.stringify(path);
      const option = api.options(input).find(item => item.value === value);
      if (!option) return;
      if (input.multiple && option.selected && selected().size === 1 && !allowEmpty) return;
      if (selectionKeyFor(input)) api.markSelectionIntent(input, 'explicit');
      api.setOption(input, option, input.multiple ? !option.selected : true);
      render(false);
      api.emitChange(input);
      if (!input.multiple) overlay.close({returnFocus: true});
    };
    const toggleDescendants = paths => {
      const selectedValues = selected();
      const values = paths.map(JSON.stringify);
      const shouldSelect = values.some(value => !selectedValues.has(value));
      const selectedOutside = [...selectedValues].filter(value => !values.includes(value)).length;
      if (!shouldSelect && !allowEmpty && selectedOutside === 0) return;
      if (selectionKeyFor(input)) api.markSelectionIntent(input, 'explicit');
      api.options(input).forEach(option => {
        if (values.includes(option.value)) option.selected = shouldSelect;
      });
      render(false);
      api.emitChange(input);
    };
    const branchState = paths => {
      const selectedValues = selected();
      const values = paths.map(JSON.stringify);
      const count = values.filter(value => selectedValues.has(value)).length;
      return {checked: values.length > 0 && count === values.length, mixed: count > 0 && count < values.length};
    };
    const buttonFor = (path, depth, leaf, selectedValues, allPaths) => {
      const isSelected = selectedValues.has(JSON.stringify(path));
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `dv-cascader-option${isSelected ? ' is-selected' : ''}`;
      button.setAttribute('role', leaf ? 'option' : 'treeitem');
      if (leaf) button.setAttribute('aria-selected', String(isSelected));
      button.innerHTML = `<span>${api.escape(leaf ? path.join(separator) : path[depth])}</span><i aria-hidden="true">${leaf ? (isSelected ? '✓' : '') : '›'}</i>`;
      button.addEventListener('click', () => {
        if (leaf) choose(path);
        else {
          activePath = path.slice(0, depth + 1);
          render(false);
        }
      });
      if (leaf || control.dataset.selectionStrategy !== 'cascade' || !input.multiple) return button;
      const prefix = path.slice(0, depth + 1);
      const descendants = allPaths.filter(candidate => prefix.every((value, index) => String(candidate[index]) === String(value)));
      const state = branchState(descendants);
      const row = document.createElement('div');
      row.className = 'dv-cascader-branch';
      if (state.checked) row.classList.add('is-selected');
      if (state.mixed) row.classList.add('is-mixed');
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'dv-cascader-branch__check';
      toggle.setAttribute('role', 'checkbox');
      toggle.setAttribute('aria-checked', state.mixed ? 'mixed' : String(state.checked));
      toggle.setAttribute('aria-label', `${state.checked ? 'Clear' : 'Select'} ${path[depth]} descendants`);
      toggle.addEventListener('click', () => toggleDescendants(descendants));
      row.append(toggle, button);
      return row;
    };
    function render(rebuild = true) {
      const paths = pathSource();
      if (rebuild) rebuildNative(paths);
      const selectedValues = selected();
      if (!activePath.length && selectedValues.size) activePath = JSON.parse([...selectedValues][0]);
      const normalized = [];
      for (let depth = 0; depth < levels.length; depth += 1) {
        const candidates = paths.filter(path => normalized.every((value, index) => String(path[index]) === String(value)));
        const values = [...new Set(candidates.map(path => String(path[depth])))];
        const current = activePath[depth] == null ? null : String(activePath[depth]);
        if (current != null && values.includes(current)) normalized.push(activePath[depth]);
        else if (values.length === 1) normalized.push(candidates[0][depth]);
        else break;
      }
      activePath = normalized;
      const query = search.value.trim().toLocaleLowerCase();
      columns.replaceChildren();
      let rendered = 0;
      if (query) {
        const results = document.createElement('div');
        results.className = 'dv-cascader-results';
        paths.filter(path => path.join(separator).toLocaleLowerCase().includes(query)).forEach(path => {
          results.append(buttonFor(path, levels.length - 1, true, selectedValues, paths));
          rendered += 1;
        });
        columns.append(results);
      } else {
        for (let depth = 0; depth < levels.length; depth += 1) {
          if (depth > 0 && activePath.length < depth) break;
          const prefix = activePath.slice(0, depth);
          const candidates = paths.filter(path => prefix.every((value, index) => String(path[index]) === String(value)));
          const values = [...new Map(candidates.map(path => [String(path[depth]), path])).values()];
          if (!values.length) break;
          const column = document.createElement('div');
          column.className = 'dv-cascader-column';
          column.dataset.level = levels[depth]?.label || levels[depth]?.field || String(depth + 1);
          column.setAttribute('role', depth === levels.length - 1 ? 'listbox' : 'tree');
          values.forEach(path => {
            const leaf = depth === levels.length - 1;
            const button = buttonFor(path, depth, leaf, selectedValues, paths);
            const activeButton = button.matches('.dv-cascader-option') ? button : button.querySelector('.dv-cascader-option');
            if (!leaf && String(activePath[depth]) === String(path[depth])) activeButton?.classList.add('is-active');
            column.append(button);
            rendered += 1;
          });
          columns.append(column);
        }
      }
      empty.hidden = rendered > 0;
      api.renderSummary(
        trigger,
        input,
        control,
        control.dataset.placeholder || 'All paths',
        api.hierarchySummaryLabels(paths, selectedValues, control.dataset.showCheckedStrategy || 'child', separator),
      );
      count.textContent = `${paths.length} available`;
      clear.hidden = !allowEmpty;
      clear.disabled = input.disabled || selectedValues.size === 0;
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
    return input?.closest('[data-selection-key]')?.dataset.selectionKey || null;
  }
})(window);
