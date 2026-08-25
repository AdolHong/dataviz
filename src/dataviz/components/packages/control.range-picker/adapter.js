/* One trigger and one floating calendar own the complete range interaction. */
(function registerRangePicker(global) {
  'use strict';
  const api = global.datavizComponents?.controls;
  if (!api) return;

  const DAY_MS = 86_400_000;
  const parseIso = value => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''));
    if (!match) return null;
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const iso = date => [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-');
  const monthStart = date => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
  const addMonths = (date, amount) => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + amount, 1));
  const addDays = (date, amount) => new Date(date.getTime() + amount * DAY_MS);
  const daysInMonth = date => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  const mondayIndex = date => (date.getUTCDay() + 6) % 7;

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
    const monthFormatter = new Intl.DateTimeFormat(locale, {year: 'numeric', month: 'long', timeZone: 'UTC'});
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

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-date-range__trigger';
    trigger.dataset.controlTrigger = '';
    trigger.innerHTML = `
      <span class="dv-date-range__value">
        <span data-range-start></span><i aria-hidden="true">→</i><span data-range-end></span>
      </span>
      <span class="dv-date-range__calendar-icon" aria-hidden="true"></span>`;

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
    picker.append(trigger, panel);
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
      const start = trigger.querySelector('[data-range-start]');
      const end = trigger.querySelector('[data-range-end]');
      start.textContent = committedStart || startLabel;
      end.textContent = committedEnd || endLabel;
      start.classList.toggle('is-placeholder', !committedStart);
      end.classList.toggle('is-placeholder', !committedEnd);
      trigger.classList.toggle('has-value', Boolean(committedStart || committedEnd));
      trigger.disabled = input.disabled;
    }

    function commit(start, end, {close = true} = {}) {
      let nextStart = start || '';
      let nextEnd = end || '';
      if (nextStart && nextEnd && nextStart > nextEnd) [nextStart, nextEnd] = [nextEnd, nextStart];
      if (!nextStart && nextEnd && !allowEmptyStart) return;
      if (nextStart && !nextEnd && !allowEmptyEnd) return;
      if (nextStart && !inBounds(nextStart)) return;
      if (nextEnd && !inBounds(nextEnd)) return;
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
      const heading = document.createElement('strong');
      heading.textContent = monthFormatter.format(date);
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
      header.append(previous, heading, next);

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
      if (phase === 'end' && draftStart && !draftEnd) {
        hint.textContent = `Choose an end date after ${draftStart}`;
      } else if (rangeStart && rangeEnd) {
        hint.textContent = `${rangeStart} → ${rangeEnd}`;
      } else {
        hint.textContent = 'Choose a start date';
      }
      clear.hidden = !clearable;
      clear.disabled = input.disabled || (!committedStart && !committedEnd);
      apply.hidden = !allowOpen;
      apply.disabled = input.disabled || (!draftStart && !draftEnd);
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
