(function exposeSelectControl(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  if (!api || root.createSelectControl) return;

  const enabledByMode = (mode, count, threshold) => (
    mode === 'always' || (mode !== 'never' && count >= threshold)
  );

  root.createSelectControl = function createSelectControl({control, input, mount}) {
    const rowHeight = Math.max(28, Number(control.dataset.itemHeight || 38));
    const viewportHeight = Math.max(rowHeight * 3, Number(control.dataset.viewportHeight || 304));
    const overscan = Math.max(2, Number(control.dataset.overscan || 5));
    const maxSelected = Number(control.dataset.maxSelected || 0);
    const allowEmpty = control.dataset.clearable === 'true';
    let filtered = [];
    let active = 0;
    let virtual = false;

    const picker = document.createElement('div');
    picker.className = 'dv-select';
    picker.dataset.controlPicker = '';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-choice-trigger';
    trigger.dataset.controlTrigger = '';
    trigger.innerHTML = '<span data-control-summary></span><i aria-hidden="true">⌄</i>';

    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-select-panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'dv-choice-search';
    search.dataset.controlSearch = '';
    search.placeholder = control.dataset.searchPlaceholder || 'Search options…';
    search.setAttribute('aria-label', search.placeholder);

    const viewport = document.createElement('div');
    viewport.className = 'dv-select-options';
    viewport.tabIndex = 0;
    viewport.setAttribute('role', 'listbox');
    viewport.setAttribute('aria-multiselectable', String(Boolean(input.multiple)));
    const spacer = document.createElement('div');
    spacer.className = 'dv-select-spacer';
    const rows = document.createElement('div');
    rows.className = 'dv-select-rows';
    spacer.append(rows);
    viewport.append(spacer);

    const empty = document.createElement('div');
    empty.className = 'dv-choice-empty';
    empty.textContent = control.dataset.emptyText || 'No matching options';
    empty.hidden = true;
    const footer = document.createElement('footer');
    const footerActions = document.createElement('span');
    footerActions.className = 'dv-select-footer__actions';
    const all = document.createElement('button');
    all.type = 'button';
    all.textContent = control.dataset.selectAllLabel || 'Select all';
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = control.dataset.clearLabel || 'Clear';
    const count = document.createElement('small');
    count.setAttribute('aria-live', 'polite');
    footerActions.append(all, clear);
    footer.append(footerActions, count);
    panel.append(search, viewport, empty, footer);
    picker.append(trigger, panel);
    mount.replaceChildren(picker);

    const overlay = api.floating(picker, trigger, panel, {
      width: Number(control.dataset.overlayWidth || 440),
      focus: search,
      onOpen: () => sync(),
    });

    const choose = index => {
      const option = filtered[index];
      if (!option || option.disabled || input.disabled) return;
      const selectedCount = api.selectedOptions(input).length;
      if (input.multiple && !option.selected && maxSelected && selectedCount >= maxSelected) return;
      if (input.multiple && option.selected && selectedCount === 1 && !allowEmpty) return;
      api.setOption(input, option, input.multiple ? !option.selected : true);
      api.markSelectionIntent(input, 'explicit');
      sync();
      api.emitChange(input);
      if (!input.multiple) overlay.close({returnFocus: true});
    };

    const rowFor = (option, index) => {
      const selectedCount = api.selectedOptions(input).length;
      const capped = Boolean(input.multiple && maxSelected && selectedCount >= maxSelected && !option.selected);
      const button = document.createElement('button');
      button.type = 'button';
      button.id = `${input.id || 'dv-select'}-option-${index}`;
      button.className = `dv-choice-option${option.selected ? ' is-selected' : ''}${option.dataset.unavailable === 'true' ? ' is-unavailable' : ''}${index === active ? ' is-active' : ''}`;
      button.setAttribute('role', 'option');
      button.setAttribute('aria-selected', String(option.selected));
      button.disabled = input.disabled || option.disabled || capped;
      const copy = document.createElement('span');
      copy.className = 'dv-select-option__copy';
      const label = document.createElement('strong');
      label.textContent = option.textContent;
      copy.append(label);
      const group = api.optionGroup(option);
      const detail = option.dataset.description;
      if (group || detail) {
        const meta = document.createElement('small');
        meta.textContent = [group, detail].filter(Boolean).join(' · ');
        copy.append(meta);
      }
      const mark = document.createElement('i');
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = option.selected ? '✓' : '';
      button.append(copy, mark);
      button.addEventListener('click', () => choose(index));
      return button;
    };

    function render() {
      const renderedOptions = filtered;
      if (virtual) {
        viewport.classList.add('is-virtual');
        viewport.style.height = `${viewportHeight}px`;
        spacer.style.height = `${renderedOptions.length * rowHeight}px`;
        const start = Math.max(0, Math.floor(viewport.scrollTop / rowHeight) - overscan);
        const end = Math.min(renderedOptions.length, Math.ceil((viewport.scrollTop + viewportHeight) / rowHeight) + overscan);
        rows.style.transform = `translateY(${start * rowHeight}px)`;
        rows.replaceChildren(...renderedOptions.slice(start, end).map((option, offset) => {
          const button = rowFor(option, start + offset);
          button.style.height = `${rowHeight}px`;
          return button;
        }));
      } else {
        viewport.classList.remove('is-virtual');
        viewport.style.height = '';
        spacer.style.height = '';
        rows.style.transform = '';
        const nodes = [];
        let previousGroup = null;
        renderedOptions.forEach((option, index) => {
          const group = api.optionGroup(option);
          if (group && group !== previousGroup) {
            const heading = document.createElement('div');
            heading.className = 'dv-select-group';
            heading.dataset.controlGroup = group;
            heading.setAttribute('role', 'presentation');
            heading.textContent = group;
            nodes.push(heading);
          }
          nodes.push(rowFor(option, index));
          previousGroup = group || null;
        });
        rows.replaceChildren(...nodes);
      }
      viewport.setAttribute('aria-activedescendant', renderedOptions[active] ? `${input.id || 'dv-select'}-option-${active}` : '');
      empty.hidden = renderedOptions.length > 0;
      viewport.hidden = renderedOptions.length === 0;
      const selectedCount = api.selectedOptions(input).length;
      const availableCount = api.availableOptions(input).length;
      const limit = maxSelected ? ` · max ${maxSelected}` : '';
      const matching = filtered.length === availableCount ? '' : `${filtered.length} matching · `;
      count.textContent = `${matching}${selectedCount} selected · ${availableCount} available${limit}`;
      clear.hidden = !allowEmpty;
      clear.disabled = input.disabled || selectedCount === 0;
      all.hidden = !input.multiple;
      const candidates = filtered.filter(option => !option.disabled);
      const allCandidatesSelected = candidates.length > 0 && candidates.every(option => option.selected);
      const required = candidates.filter(option => !option.selected).length;
      const remaining = maxSelected ? Math.max(0, maxSelected - selectedCount) : Number.POSITIVE_INFINITY;
      all.textContent = allCandidatesSelected
        ? control.dataset.invertLabel || 'Invert'
        : control.dataset.selectAllLabel || 'Select all';
      all.dataset.action = allCandidatesSelected ? 'invert' : 'select-all';
      const invertedSelectedCount = selectedCount
        + candidates.filter(option => !option.selected).length
        - candidates.filter(option => option.selected).length;
      all.disabled = input.disabled
        || candidates.length === 0
        || (!allCandidatesSelected && required > remaining)
        || (allCandidatesSelected && !allowEmpty && invertedSelectedCount === 0);
      all.title = !allCandidatesSelected && required > remaining
        ? `Selection limit is ${maxSelected}; narrow the search or clear values first.`
        : '';
      api.renderSummary(trigger, input, control, control.dataset.placeholder || 'Choose…');
      trigger.disabled = input.disabled;
    }

    function sync() {
      const allOptions = api.options(input);
      const searchEnabled = enabledByMode(
        control.dataset.searchMode || 'auto',
        allOptions.length,
        Math.max(0, Number(control.dataset.searchThreshold || 9)),
      );
      virtual = enabledByMode(
        control.dataset.virtualMode || 'auto',
        allOptions.length,
        Math.max(1, Number(control.dataset.virtualThreshold || 200)),
      );
      search.hidden = !searchEnabled;
      if (!searchEnabled) search.value = '';
      const query = search.value.trim().toLocaleLowerCase();
      filtered = allOptions.filter(option => {
        if (
          option.disabled
          && option.dataset.preserveValue !== 'true'
          && control.dataset.showUnavailable !== 'true'
        ) return false;
        if (control.dataset.hideSelected === 'true' && option.selected) return false;
        return !query || api.optionSearchText(option).includes(query);
      });
      active = Math.min(active, Math.max(0, filtered.length - 1));
      render();
      if (overlay.isOpen()) overlay.reposition();
    }

    search.addEventListener('input', () => {
      viewport.scrollTop = 0;
      active = 0;
      sync();
    });
    search.addEventListener('keydown', event => {
      if (event.key !== 'ArrowDown' || !filtered.length) return;
      event.preventDefault();
      viewport.focus();
    });
    viewport.addEventListener('scroll', () => { if (virtual) render(); }, {passive: true});
    viewport.addEventListener('keydown', event => {
      if (!filtered.length) return;
      if (event.key === 'ArrowDown') active = Math.min(filtered.length - 1, active + 1);
      else if (event.key === 'ArrowUp') active = Math.max(0, active - 1);
      else if (event.key === 'Home') active = 0;
      else if (event.key === 'End') active = filtered.length - 1;
      else if (['Enter', ' '].includes(event.key)) { event.preventDefault(); choose(active); return; }
      else return;
      event.preventDefault();
      const top = active * rowHeight;
      if (top < viewport.scrollTop) viewport.scrollTop = top;
      else if (top + rowHeight > viewport.scrollTop + viewport.clientHeight) viewport.scrollTop = top + rowHeight - viewport.clientHeight;
      render();
    });
    all.addEventListener('click', () => {
      if (!input.multiple || input.disabled) return;
      const candidates = filtered.filter(option => !option.disabled);
      const allCandidatesSelected = candidates.length > 0 && candidates.every(option => option.selected);
      const selectedOutsideCandidates = api.selectedOptions(input).filter(
        option => !candidates.includes(option)
      ).length;
      if (allCandidatesSelected && !allowEmpty && selectedOutsideCandidates === 0) return;
      candidates.forEach(option => { option.selected = !allCandidatesSelected; });
      api.markSelectionIntent(input, allCandidatesSelected ? 'explicit' : 'all_available');
      sync();
      api.emitChange(input);
    });
    clear.addEventListener('click', () => {
      if (input.disabled || !allowEmpty) return;
      api.clearOptions(input);
      api.markSelectionIntent(input, 'explicit');
      sync();
      api.emitChange(input);
      if (!input.multiple) overlay.close({returnFocus: true});
    });

    return {
      sync,
      overlay,
      metrics: () => ({total: api.options(input).length, matching: filtered.length, rendered: rows.childElementCount, virtual}),
    };
  };
})(window);
