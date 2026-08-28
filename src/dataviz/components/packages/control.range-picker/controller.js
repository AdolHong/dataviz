/* Shared, dependency-free ISO calendar primitives for both date controls. */
(function exposeCalendarPrimitives(global) {
  'use strict';
  const root = global.datavizComponents = global.datavizComponents || {};
  if (root.calendarPrimitives) return;

  const DAY_MS = 86_400_000;
  const parseIso = value => {
    const normalized = String(value || '').trim();
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
    if (!match) return null;
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== normalized
      ? null
      : date;
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
  const formatIsoEntry = input => {
    const raw = String(input?.value || '');
    if (!input || !/^[\d\s./-]*$/.test(raw)) return raw;
    const caret = input.selectionStart ?? raw.length;
    const digitsBeforeCaret = raw.slice(0, caret).replace(/\D/g, '').length;
    const digits = raw.replace(/\D/g, '').slice(0, 8);
    const value = digits.length <= 4
      ? digits
      : digits.length <= 6
      ? `${digits.slice(0, 4)}-${digits.slice(4)}`
      : `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
    if (value !== raw) {
      input.value = value;
      const nextCaret = Math.min(
        value.length,
        digitsBeforeCaret
          + (digitsBeforeCaret > 4 ? 1 : 0)
          + (digitsBeforeCaret > 6 ? 1 : 0),
      );
      input.setSelectionRange?.(nextCaret, nextCaret);
    }
    return value;
  };

  const createMonthSelector = ({date, locale, minimum = '', maximum = '', onChange}) => {
    const period = document.createElement('span');
    period.className = 'dv-date-range__period';
    const year = date.getUTCFullYear();
    const month = date.getUTCMonth();
    const minimumDate = parseIso(minimum);
    const maximumDate = parseIso(maximum);
    const minimumYear = minimumDate ? minimumDate.getUTCFullYear() : year - 100;
    const maximumYear = maximumDate ? maximumDate.getUTCFullYear() : year + 100;
    const yearSelect = document.createElement('select');
    yearSelect.className = 'dv-date-range__year-select';
    yearSelect.setAttribute('aria-label', 'Choose year');
    for (let value = minimumYear; value <= maximumYear; value += 1) {
      const option = document.createElement('option');
      option.value = String(value);
      option.textContent = String(value);
      option.selected = value === year;
      yearSelect.append(option);
    }
    const monthSelect = document.createElement('select');
    monthSelect.className = 'dv-date-range__month-select';
    monthSelect.setAttribute('aria-label', 'Choose month');
    const monthFormatter = new Intl.DateTimeFormat(locale, {month: 'long', timeZone: 'UTC'});
    for (let value = 0; value < 12; value += 1) {
      const option = document.createElement('option');
      option.value = String(value);
      option.textContent = monthFormatter.format(new Date(Date.UTC(2024, value, 1)));
      option.selected = value === month;
      monthSelect.append(option);
    }
    const choose = () => {
      let next = new Date(Date.UTC(Number(yearSelect.value), Number(monthSelect.value), 1));
      const minimumMonth = minimumDate ? monthStart(minimumDate) : null;
      const maximumMonth = maximumDate ? monthStart(maximumDate) : null;
      if (minimumMonth && next < minimumMonth) next = minimumMonth;
      if (maximumMonth && next > maximumMonth) next = maximumMonth;
      onChange(next);
    };
    yearSelect.addEventListener('change', choose);
    monthSelect.addEventListener('change', choose);
    if (String(locale).toLowerCase().startsWith('zh')) period.append(yearSelect, monthSelect);
    else period.append(monthSelect, yearSelect);
    return period;
  };

  root.calendarPrimitives = {
    parseIso, iso, monthStart, addMonths, addDays, daysInMonth, mondayIndex,
    formatIsoEntry, createMonthSelector,
  };
})(window);
