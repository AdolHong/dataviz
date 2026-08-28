(function exposeDatePicker(global) {
  'use strict';
  const root = global.datavizComponents;
  const api = root?.controls;
  const dates = root?.calendarPrimitives;
  if (!api || !dates || root.createDatePicker) return;
  const {
    parseIso, iso, monthStart, addMonths, addDays, daysInMonth, mondayIndex,
    formatIsoEntry, createMonthSelector,
  } = dates;

  root.createDatePicker = function createDatePicker({control, input, mount}) {
    const minimum = control.dataset.minDate || '';
    const maximum = control.dataset.maxDate || '';
    const clearable = control.dataset.clearable === 'true' && control.dataset.required !== 'true';
    const locale = document.documentElement.lang || navigator.language || 'en';
    const today = iso(new Date());
    const dayFormatter = new Intl.DateTimeFormat(locale, {
      year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
    });
    const weekdayFormatter = new Intl.DateTimeFormat(locale, {
      weekday: 'short', timeZone: 'UTC',
    });
    const weekdays = Array.from({length: 7}, (_item, index) => weekdayFormatter.format(
      new Date(Date.UTC(2024, 0, 1 + index)),
    ));
    let selected = parseIso(input.value) ? input.value : '';
    let cursor = monthStart(parseIso(selected || today));

    input.type = 'text';
    input.inputMode = 'numeric';
    input.autocomplete = 'off';
    input.placeholder = input.placeholder || 'YYYY-MM-DD';
    input.classList.add('dv-date-picker__control');
    input.dataset.controlNative = 'visible';

    const shell = document.createElement('div');
    shell.className = 'dv-date-picker';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'dv-date-picker__trigger';
    trigger.dataset.controlTrigger = '';
    trigger.setAttribute('aria-label', 'Choose date');
    trigger.innerHTML = '<span class="dv-date-range__calendar-icon" aria-hidden="true"></span>';

    const panel = document.createElement('div');
    panel.className = 'dv-control-panel dv-date-range__panel dv-date-picker__panel';
    panel.dataset.controlPanel = '';
    panel.hidden = true;
    panel.tabIndex = -1;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Choose date');
    const calendarHost = document.createElement('div');
    calendarHost.className = 'dv-date-range__calendars dv-date-picker__calendars';
    const footer = document.createElement('footer');
    footer.className = 'dv-date-range__footer dv-date-picker__footer';
    const hint = document.createElement('small');
    hint.className = 'dv-date-range__hint';
    hint.setAttribute('aria-live', 'polite');
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'dv-date-range__clear';
    clear.textContent = control.dataset.clearLabel || 'Clear';
    clear.hidden = !clearable;
    footer.append(hint, clear);
    panel.append(calendarHost, footer);
    shell.append(input, trigger, panel);
    mount.replaceChildren(shell);

    const inBounds = value => Boolean(
      value && (!minimum || value >= minimum) && (!maximum || value <= maximum),
    );

    function setError(message = '') {
      input.setCustomValidity(message);
      input.setAttribute('aria-invalid', String(Boolean(message)));
      const output = control.querySelector('[data-control-error]');
      if (output) {
        output.textContent = message;
        output.hidden = !message;
      }
    }

    function validate(value, {allowEmpty = true} = {}) {
      const normalized = String(value || '').trim();
      if (!normalized) {
        if (allowEmpty && control.dataset.required !== 'true') return '';
        throw new Error('Use YYYY-MM-DD');
      }
      if (!parseIso(normalized)) throw new Error('Use a real YYYY-MM-DD date');
      if (!inBounds(normalized)) throw new Error('Date is outside the allowed range');
      return normalized;
    }

    function commit(value, {close = true} = {}) {
      try {
        selected = validate(value);
      } catch (error) {
        setError(error.message);
        return false;
      }
      setError('');
      input.value = selected;
      cursor = monthStart(parseIso(selected || today));
      input.dispatchEvent(new Event('input', {bubbles: true}));
      api.emitChange(input);
      renderCalendar();
      if (close) overlay.close({returnFocus: true});
      return true;
    }

    function focusDate(value) {
      requestAnimationFrame(() => panel.querySelector(`[data-date="${value}"]`)?.focus({preventScroll: true}));
    }

    function renderMonth(date) {
      const section = document.createElement('section');
      section.className = 'dv-date-range__month';
      const header = document.createElement('header');
      const previous = document.createElement('button');
      previous.type = 'button';
      previous.className = 'dv-date-range__nav';
      previous.setAttribute('aria-label', 'Previous month');
      previous.textContent = '‹';
      previous.addEventListener('click', () => {
        cursor = addMonths(cursor, -1);
        renderCalendar();
      });
      const period = createMonthSelector({
        date,
        locale,
        minimum,
        maximum,
        onChange: value => {
          cursor = value;
          renderCalendar();
        },
      });
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'dv-date-range__nav';
      next.setAttribute('aria-label', 'Next month');
      next.textContent = '›';
      next.addEventListener('click', () => {
        cursor = addMonths(cursor, 1);
        renderCalendar();
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
      for (let blank = 0; blank < mondayIndex(date); blank += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'dv-date-range__day-spacer';
        spacer.setAttribute('aria-hidden', 'true');
        grid.append(spacer);
      }
      for (let day = 1; day <= daysInMonth(date); day += 1) {
        const value = iso(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), day)));
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dv-date-range__day';
        button.dataset.date = value;
        button.textContent = String(day);
        button.setAttribute('role', 'gridcell');
        button.setAttribute('aria-label', dayFormatter.format(parseIso(value)));
        button.setAttribute('aria-selected', String(value === selected));
        button.disabled = !inBounds(value) || input.disabled;
        button.classList.toggle('is-today', value === today);
        button.classList.toggle('is-start', value === selected);
        button.classList.toggle('is-end', value === selected);
        button.addEventListener('click', () => commit(value));
        button.addEventListener('keydown', event => {
          const deltas = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
          if (!(event.key in deltas)) return;
          event.preventDefault();
          const target = addDays(parseIso(value), deltas[event.key]);
          const targetValue = iso(target);
          if (!inBounds(targetValue)) return;
          if (target < cursor || target >= addMonths(cursor, 1)) cursor = monthStart(target);
          renderCalendar();
          focusDate(targetValue);
        });
        grid.append(button);
      }
      section.append(header, grid);
      return section;
    }

    function renderCalendar() {
      calendarHost.replaceChildren(renderMonth(cursor));
      hint.textContent = '';
      clear.disabled = input.disabled || !selected;
      footer.hidden = !clearable;
      trigger.disabled = input.disabled;
      if (overlay.isOpen()) overlay.reposition();
    }

    const overlay = api.floating(shell, trigger, panel, {
      width: Number(control.dataset.overlayWidth || 340),
      focus: panel,
      ariaHaspopup: 'dialog',
      onOpen: () => {
        const current = parseIso(input.value) ? input.value : selected;
        selected = current || '';
        cursor = monthStart(parseIso(selected || today));
        renderCalendar();
        focusDate(selected || today);
      },
    });

    input.addEventListener('input', event => {
      if (!event.isComposing) formatIsoEntry(input);
      try {
        validate(input.value);
        setError('');
      } catch (error) {
        setError(error.message);
      }
    });
    input.addEventListener('change', () => {
      if (!commit(input.value, {close: false})) return;
      selected = input.value;
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        commit(input.value, {close: true});
      } else if (event.key === 'ArrowDown' && (event.altKey || event.metaKey)) {
        event.preventDefault();
        overlay.open();
      } else if (event.key === 'Escape') {
        input.value = selected;
        setError('');
        overlay.close();
      }
    });
    clear.addEventListener('click', () => commit(''));

    function sync() {
      if (document.activeElement !== input) {
        selected = parseIso(input.value) ? input.value : '';
        cursor = monthStart(parseIso(selected || today));
      }
      setError('');
      renderCalendar();
    }

    return {sync, overlay};
  };
})(window);
