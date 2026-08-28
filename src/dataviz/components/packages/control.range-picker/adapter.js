/* One trigger and one floating calendar own the complete range interaction. */
(function registerRangePicker(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  const dates = root?.calendarPrimitives;
  if (!api || !dates) return;
  const {
    parseIso, iso, monthStart, addMonths, addDays, daysInMonth, mondayIndex,
    formatIsoEntry, createMonthSelector,
  } = dates;

  api.register('range-picker', ({control, input, mount}) => {
    const required = control.dataset.required === 'true';
    const clearable = control.dataset.clearable === 'true' && !required;
    const allowEmptyStart = control.dataset.allowEmptyStart === 'true';
    const allowEmptyEnd = control.dataset.allowEmptyEnd === 'true';
    const allowOpen = allowEmptyStart || allowEmptyEnd;
    const minimum = control.dataset.minDate || '';
    const maximum = control.dataset.maxDate || '';
    const startLabel = control.dataset.startLabel || 'Start';
    const endLabel = control.dataset.endLabel || 'End';
    const locale = document.documentElement.lang || navigator.language || 'en';
    const today = iso(new Date());
    const dayFormatter = new Intl.DateTimeFormat(locale, {year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC'});
    const weekdayFormatter = new Intl.DateTimeFormat(locale, {weekday: 'short', timeZone: 'UTC'});
    const weekdays = Array.from({length: 7}, (_item, index) => weekdayFormatter.format(
      new Date(Date.UTC(2024, 0, 1 + index))
    ));

    let committedStart = '';
    let committedEnd = '';
    let draftStart = '';
    let draftEnd = '';
    let hoverDate = '';
    let phase = 'start';
    let cursor = monthStart(parseIso(today));

    const picker = document.createElement('div');
    picker.className = 'dv-date-range';
    picker.dataset.controlPicker = '';

    const field = document.createElement('div');
    field.className = 'dv-date-range__field';
    const startEditor = document.createElement('input');
    startEditor.type = 'text';
    startEditor.inputMode = 'numeric';
    startEditor.autocomplete = 'off';
    startEditor.className = 'dv-date-range__endpoint';
    startEditor.placeholder = startLabel;
    startEditor.setAttribute('aria-label', startLabel);
    const separator = document.createElement('span');
    separator.className = 'dv-date-range__separator';
    separator.textContent = '→';
    separator.setAttribute('aria-hidden', 'true');
    const endEditor = document.createElement('input');
    endEditor.type = 'text';
    endEditor.inputMode = 'numeric';
    endEditor.autocomplete = 'off';
    endEditor.className = 'dv-date-range__endpoint';
    endEditor.placeholder = endLabel;
    endEditor.setAttribute('aria-label', endLabel);
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-date-range__trigger';
    trigger.dataset.controlTrigger = '';
    trigger.setAttribute('aria-label', `${startLabel} – ${endLabel}`);
    trigger.innerHTML = '<span class="dv-date-range__calendar-icon" aria-hidden="true"></span>';
    field.append(startEditor, separator, endEditor, trigger);

    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-date-range__panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    panel.tabIndex = -1;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', `${startLabel} – ${endLabel}`);

    const presetHost = document.createElement('div');
    presetHost.className = 'dv-date-range__presets';
    let presetValues = [];
    try { presetValues = JSON.parse(control.dataset.presets || '[]'); } catch (_error) {}

    const calendarHost = document.createElement('div');
    calendarHost.className = 'dv-date-range__calendars';

    const footer = document.createElement('footer');
    footer.className = 'dv-date-range__footer';
    const hint = document.createElement('small');
    hint.className = 'dv-date-range__hint';
    hint.setAttribute('aria-live', 'polite');
    const actions = document.createElement('div');
    actions.className = 'dv-date-range__actions';
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'dv-date-range__clear';
    clear.textContent = control.dataset.clearLabel || 'Clear';
    const apply = document.createElement('button');
    apply.type = 'button';
    apply.className = 'dv-date-range__apply';
    apply.textContent = 'Apply';
    actions.append(clear, apply);
    footer.append(hint, actions);
    panel.append(presetHost, calendarHost, footer);
    picker.append(field, panel);
    mount.replaceChildren(picker);

    const readValue = () => {
      const [start = '', end = ''] = String(input.value || '').split(',', 2);
      return [parseIso(start) ? start : '', parseIso(end) ? end : ''];
    };
    const inBounds = value => Boolean(value && (!minimum || value >= minimum) && (!maximum || value <= maximum));
    const visibleRange = () => {
      const end = draftEnd || (phase === 'end' ? hoverDate : '');
      if (!draftStart || !end) return ['', ''];
      return draftStart <= end ? [draftStart, end] : [end, draftStart];
    };

    function renderSummary() {
      if (document.activeElement !== startEditor) startEditor.value = committedStart;
      if (document.activeElement !== endEditor) endEditor.value = committedEnd;
      startEditor.disabled = input.disabled;
      endEditor.disabled = input.disabled;
      trigger.disabled = input.disabled;
    }

    function setEditorError(message = '', editor = null) {
      input.setCustomValidity(message);
      [startEditor, endEditor].forEach(item => {
        item.setAttribute('aria-invalid', String(Boolean(message && (!editor || editor === item))));
      });
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = message;
        output.hidden = !message;
      }
    }

    function editorValue(editor, label, allowEmpty) {
      const value = editor.value.trim();
      if (!value) {
        if (allowEmpty) return '';
        throw new Error(`${label} must use YYYY-MM-DD`);
      }
      if (!parseIso(value)) throw new Error(`${label} must use a real YYYY-MM-DD date`);
      if (!inBounds(value)) throw new Error(`${label} is outside the allowed date range`);
      return value;
    }

    function commit(start, end, {close = true} = {}) {
      let nextStart = start || '';
      let nextEnd = end || '';
      if (nextStart && nextEnd && nextStart > nextEnd) [nextStart, nextEnd] = [nextEnd, nextStart];
      if (!nextStart && nextEnd && !allowEmptyStart) return false;
      if (nextStart && !nextEnd && !allowEmptyEnd) return false;
      if (nextStart && !inBounds(nextStart)) return false;
      if (nextEnd && !inBounds(nextEnd)) return false;
      setEditorError('');
      committedStart = nextStart;
      committedEnd = nextEnd;
      draftStart = nextStart;
      draftEnd = nextEnd;
      phase = nextStart && !nextEnd ? 'end' : 'start';
      input.value = nextStart || nextEnd ? `${nextStart},${nextEnd}` : '';
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      renderSummary();
      renderCalendars();
      if (close) overlay.close({returnFocus: true});
      return true;
    }

    function commitEditors({close = false} = {}) {
      try {
        const start = editorValue(startEditor, startLabel, allowEmptyStart || clearable);
        const end = editorValue(endEditor, endLabel, allowEmptyEnd || clearable);
        if (!start && !end && clearable) return commit('', '', {close});
        if (start && end && start > end) throw new Error(`${startLabel} cannot be after ${endLabel}`);
        return commit(start, end, {close});
      } catch (error) {
        const editor = /start/i.test(error.message) ? startEditor
          : /end/i.test(error.message) ? endEditor : null;
        setEditorError(error.message, editor);
        return false;
      }
    }

    function choose(value) {
      if (!inBounds(value)) return;
      if (phase === 'start' || (draftStart && draftEnd)) {
        draftStart = value;
        draftEnd = '';
        hoverDate = '';
        phase = 'end';
        renderCalendars();
        return;
      }
      if (!draftStart) {
        draftStart = value;
        phase = 'end';
        renderCalendars();
        return;
      }
      draftEnd = value;
      commit(draftStart, draftEnd);
    }

    function focusDate(value) {
      requestAnimationFrame(() => panel.querySelector(`[data-date="${value}"]`)?.focus({preventScroll: true}));
    }

    function calendar(date, index) {
      const section = document.createElement('section');
      section.className = 'dv-date-range__month';
      const header = document.createElement('header');
      const previous = document.createElement('button');
      previous.type = 'button';
      previous.className = 'dv-date-range__nav';
      previous.setAttribute('aria-label', 'Previous month');
      previous.textContent = '‹';
      previous.hidden = index !== 0;
      previous.addEventListener('click', () => {
        cursor = addMonths(cursor, -1);
        renderCalendars();
      });
      const period = createMonthSelector({
        date,
        locale,
        minimum,
        maximum,
        onChange: value => {
          cursor = addMonths(value, -index);
          renderCalendars();
        },
      });
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'dv-date-range__nav';
      next.setAttribute('aria-label', 'Next month');
      next.textContent = '›';
      next.hidden = index !== 1;
      next.addEventListener('click', () => {
        cursor = addMonths(cursor, 1);
        renderCalendars();
      });
      header.append(previous, period, next);

      const grid = document.createElement('div');
      grid.className = 'dv-date-range__grid';
      grid.setAttribute('role', 'grid');
      weekdays.forEach(label => {
        const cell = document.createElement('span');
        cell.className = 'dv-date-range__weekday';
        cell.textContent = label;
        cell.setAttribute('role', 'columnheader');
        grid.append(cell);
      });
      const offset = mondayIndex(date);
      for (let blank = 0; blank < offset; blank += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'dv-date-range__day-spacer';
        spacer.setAttribute('aria-hidden', 'true');
        grid.append(spacer);
      }
      const [rangeStart, rangeEnd] = visibleRange();
      for (let day = 1; day <= daysInMonth(date); day += 1) {
        const value = iso(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), day)));
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dv-date-range__day';
        button.dataset.date = value;
        button.textContent = String(day);
        button.setAttribute('role', 'gridcell');
        button.setAttribute('aria-label', dayFormatter.format(parseIso(value)));
        button.setAttribute('aria-selected', String(value === draftStart || value === draftEnd));
        button.disabled = !inBounds(value) || input.disabled;
        button.classList.toggle('is-today', value === today);
        button.classList.toggle('is-start', value === draftStart);
        button.classList.toggle('is-end', value === draftEnd);
        button.classList.toggle('is-in-range', Boolean(rangeStart && value > rangeStart && value < rangeEnd));
        button.addEventListener('mouseenter', () => {
          if (phase !== 'end' || !draftStart || hoverDate === value) return;
          hoverDate = value;
          renderCalendars();
        });
        button.addEventListener('click', () => choose(value));
        button.addEventListener('keydown', event => {
          const deltas = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
          if (!(event.key in deltas)) return;
          event.preventDefault();
          const target = addDays(parseIso(value), deltas[event.key]);
          const targetValue = iso(target);
          if (!inBounds(targetValue)) return;
          if (target < cursor) cursor = monthStart(target);
          else if (target >= addMonths(cursor, 2)) cursor = addMonths(monthStart(target), -1);
          renderCalendars();
          focusDate(targetValue);
        });
        grid.append(button);
      }
      section.append(header, grid);
      return section;
    }

    function renderCalendars() {
      calendarHost.replaceChildren(calendar(cursor, 0), calendar(addMonths(cursor, 1), 1));
      const [rangeStart, rangeEnd] = visibleRange();
      hint.textContent = phase === 'end' && draftStart && !draftEnd
        ? `Choose an end date after ${draftStart}`
        : '';
      clear.hidden = !clearable;
      clear.disabled = input.disabled || (!committedStart && !committedEnd);
      apply.hidden = !allowOpen;
      apply.disabled = input.disabled || (!draftStart && !draftEnd);
      footer.hidden = clear.hidden && apply.hidden;
      panel.dataset.rangePhase = phase;
      if (overlay.isOpen()) overlay.reposition();
    }

    presetValues.forEach(preset => {
      if (!preset?.label || !parseIso(preset.start) || !parseIso(preset.end)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = preset.label;
      button.addEventListener('click', () => commit(preset.start, preset.end));
      presetHost.append(button);
    });
    presetHost.hidden = presetHost.childElementCount === 0;

    const overlay = api.floating(picker, trigger, panel, {
      width: Number(control.dataset.overlayWidth || 680),
      focus: panel,
      ariaHaspopup: 'dialog',
      onOpen: () => {
        [committedStart, committedEnd] = readValue();
        draftStart = committedStart;
        draftEnd = committedEnd;
        hoverDate = '';
        phase = 'start';
        cursor = monthStart(parseIso(committedStart || today));
        renderSummary();
        renderCalendars();
        focusDate(draftStart || today);
      },
      onClose: () => {
        draftStart = committedStart;
        draftEnd = committedEnd;
        hoverDate = '';
        phase = 'start';
      },
    });

    clear.addEventListener('click', () => {
      if (!clearable || input.disabled) return;
      commit('', '');
    });
    apply.addEventListener('click', () => commit(draftStart, draftEnd));
    [startEditor, endEditor].forEach(editor => {
      editor.addEventListener('input', event => {
        if (!event.isComposing) formatIsoEntry(editor);
        const value = editor.value.trim();
        if (!value || parseIso(value)) setEditorError('');
        else setEditorError('Use YYYY-MM-DD', editor);
      });
      editor.addEventListener('change', () => commitEditors());
      editor.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          commitEditors({close: true});
        } else if (event.key === 'Escape') {
          editor.value = editor === startEditor ? committedStart : committedEnd;
          setEditorError('');
          overlay.close();
        }
      });
    });

    function sync() {
      [committedStart, committedEnd] = readValue();
      if (!overlay.isOpen()) {
        draftStart = committedStart;
        draftEnd = committedEnd;
        phase = 'start';
        cursor = monthStart(parseIso(committedStart || today));
      }
      renderSummary();
      renderCalendars();
    }

    return {sync, overlay};
  });
})(window);
