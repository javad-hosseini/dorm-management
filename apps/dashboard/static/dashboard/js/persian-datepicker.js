/**
 * Modern Vanilla Persian (Shamsi) Datepicker
 * Designed for Dormitory Management Dashboard
 * 100% Dependency-free, glassmorphic styling, RTL native.
 */

const PersianDate = (() => {
  const J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
  const G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

  const MONTH_NAMES = [
    'فروردین', 'اردیبهشت', 'خرداد',
    'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر',
    'دی', 'بهمن', 'اسفند'
  ];

  const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

  function toPersianDigits(n) {
    return String(n).replace(/[0-9]/g, d => PERSIAN_DIGITS[+d]);
  }

  function isLeapJalali(jy) {
    return [1, 5, 9, 13, 17, 22, 26, 30].includes(jy % 33);
  }

  function getDaysInMonth(jy, jm) {
    if (jm >= 1 && jm <= 6) return 31;
    if (jm >= 7 && jm <= 11) return 30;
    if (jm === 12) return isLeapJalali(jy) ? 30 : 29;
    return 30;
  }

  function gregorianToJalali(gy, gm, gd) {
    const gyOff = gy - 1600;
    const gmOff = gm - 1;
    let jDayNo = 365 * gyOff + Math.floor((gyOff + 3) / 4) - Math.floor((gyOff + 99) / 100)
      + Math.floor((gyOff + 399) / 400) + gd - 1 - 79;

    for (let i = 0; i < gmOff; i++) {
      jDayNo += G_DAYS_IN_MONTH[i];
    }
    if (gmOff > 1 && ((gy % 4 === 0 && gy % 100 !== 0) || (gy % 400 === 0))) {
      jDayNo++;
    }

    const jNp = Math.floor(jDayNo / 12053);
    jDayNo %= 12053;
    let jy = 979 + 33 * jNp + 4 * Math.floor(jDayNo / 1461);
    jDayNo %= 1461;

    if (jDayNo >= 366) {
      jDayNo--;
      jy += Math.floor(jDayNo / 365);
      jDayNo %= 365;
    }

    let i = 0;
    for (i = 0; i < 11; i++) {
      if (jDayNo < J_DAYS_IN_MONTH[i]) break;
      jDayNo -= J_DAYS_IN_MONTH[i];
    }

    return {
      year: jy,
      month: i + 1,
      day: jDayNo + 1
    };
  }

  function jalaliToGregorian(jy, jm, jd) {
    const jyOff = jy - 979;
    let gDayNo = 365 * jyOff + Math.floor(jyOff / 33) * 8 + Math.floor((jyOff % 33 + 3) / 4) + jd - 1 + 79;
    for (let i = 0; i < jm - 1; i++) {
      gDayNo += J_DAYS_IN_MONTH[i];
    }

    let gy = 1600 + 400 * Math.floor(gDayNo / 146097);
    gDayNo %= 146097;

    let leap = 1;
    if (gDayNo >= 36525) {
      gDayNo--;
      gy += 100 * Math.floor(gDayNo / 36524);
      gDayNo %= 36524;
      if (gDayNo >= 365) {
        gDayNo++;
      } else {
        leap = 0;
      }
    }

    gy += 4 * Math.floor(gDayNo / 1461);
    gDayNo %= 1461;

    if (gDayNo >= 366) {
      leap = 0;
      gDayNo--;
      gy += Math.floor(gDayNo / 365);
      gDayNo %= 365;
    }

    let i = 0;
    while (gDayNo >= G_DAYS_IN_MONTH[i] + (i === 1 && leap ? 1 : 0)) {
      gDayNo -= G_DAYS_IN_MONTH[i] + (i === 1 && leap ? 1 : 0);
      i++;
    }

    return {
      year: gy,
      month: i + 1,
      day: gDayNo + 1
    };
  }

  // Returns 0 for Saturday (شنبه) to 6 for Friday (جمعه)
  function getJalaliDayOfWeek(jy, jm, jd) {
    const g = jalaliToGregorian(jy, jm, jd);
    const date = new Date(g.year, g.month - 1, g.day);
    const day = date.getDay(); // Sunday=0, Monday=1, ..., Saturday=6
    return (day + 1) % 7; // Saturday=0, Sunday=1, ..., Friday=6
  }

  function getToday() {
    const now = new Date();
    return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }

  function formatString(jy, jm, jd) {
    const m = String(jm).padStart(2, '0');
    const d = String(jd).padStart(2, '0');
    return `${jy}/${m}/${d}`;
  }

  function parseString(str) {
    if (!str) return null;
    const parts = str.trim().split(/[\/\-]/);
    if (parts.length === 3) {
      const y = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10);
      const d = parseInt(parts[2], 10);
      if (!isNaN(y) && !isNaN(m) && !isNaN(d)) {
        return { year: y, month: m, day: d };
      }
    }
    return null;
  }

  return {
    MONTH_NAMES,
    toPersianDigits,
    isLeapJalali,
    getDaysInMonth,
    gregorianToJalali,
    jalaliToGregorian,
    getJalaliDayOfWeek,
    getToday,
    formatString,
    parseString
  };
})();


class PersianDatePicker {
  constructor(inputElement, options = {}) {
    this.input = typeof inputElement === 'string' ? document.querySelector(inputElement) : inputElement;
    if (!this.input) return;

    this.options = Object.assign({
      onSelect: null,
      minYear: 1395,
      maxYear: 1415,
      autoClose: true
    }, options);

    this.today = PersianDate.getToday();
    const existingVal = PersianDate.parseString(this.input.value);
    this.selected = existingVal || null;
    this.viewYear = this.selected ? this.selected.year : this.today.year;
    this.viewMonth = this.selected ? this.selected.month : this.today.month;

    this.isOpen = false;
    this.popup = null;
    this.input._pdp = this;

    this.init();
  }

  init() {
    this.input._pdp = this;
    this.input.setAttribute('autocomplete', 'off');
    this.input.classList.add('persian-datepicker-input');

    // Create container popup
    this.createPopup();

    // Event listeners
    this.input.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });

    this.input.addEventListener('focus', (e) => {
      e.stopPropagation();
      if (!this.isOpen) this.open();
    });

    document.addEventListener('click', (e) => {
      if (this.isOpen && this.popup && !this.popup.contains(e.target) && e.target !== this.input) {
        this.close();
      }
    });

    window.addEventListener('resize', () => {
      if (this.isOpen) this.position();
    });

    window.addEventListener('scroll', () => {
      if (this.isOpen) this.position();
    }, true);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    });
  }

  createPopup() {
    this.popup = document.createElement('div');
    this.popup.className = 'persian-datepicker-popup';
    this.popup.style.display = 'none';
    this.popup.style.position = 'fixed';
    this.popup.style.zIndex = '99999';
    document.body.appendChild(this.popup);

    this.popup.addEventListener('click', (e) => e.stopPropagation());
  }

  position() {
    if (!this.popup || !this.input) return;
    const rect = this.input.getBoundingClientRect();
    const popupWidth = 310;
    const popupHeight = 360;

    let top = rect.bottom + 6;
    let left = rect.right - popupWidth;

    // Check bottom boundary
    if (top + popupHeight > window.innerHeight && rect.top - popupHeight > 0) {
      top = rect.top - popupHeight - 6;
    }

    // Check left boundary
    if (left < 10) {
      left = 10;
    }
    if (left + popupWidth > window.innerWidth - 10) {
      left = window.innerWidth - popupWidth - 10;
    }

    this.popup.style.position = 'fixed';
    this.popup.style.top = `${Math.round(top)}px`;
    this.popup.style.left = `${Math.round(left)}px`;
  }

  open() {
    const parsed = PersianDate.parseString(this.input.value);
    if (parsed) {
      this.selected = parsed;
      this.viewYear = parsed.year;
      this.viewMonth = parsed.month;
    }

    this.render();
    this.popup.style.display = 'block';
    this.position();
    this.isOpen = true;
  }

  close() {
    if (this.popup) {
      this.popup.style.display = 'none';
    }
    this.isOpen = false;
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  render() {
    const { viewYear, viewMonth } = this;
    const daysInMonth = PersianDate.getDaysInMonth(viewYear, viewMonth);
    const startDayOfWeek = PersianDate.getJalaliDayOfWeek(viewYear, viewMonth, 1);

    const monthOptions = PersianDate.MONTH_NAMES.map((name, idx) => {
      const mNum = idx + 1;
      return `<option value="${mNum}" ${mNum === viewMonth ? 'selected' : ''}>${name}</option>`;
    }).join('');

    let yearOptions = '';
    for (let y = this.options.minYear; y <= this.options.maxYear; y++) {
      yearOptions += `<option value="${y}" ${y === viewYear ? 'selected' : ''}>${PersianDate.toPersianDigits(y)}</option>`;
    }

    // Weekday headers: ش ی د س چ پ ج
    const weekdays = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
    const weekdayHeaders = weekdays.map((w, idx) => {
      const isFriday = idx === 6;
      return `<div class="pdp-weekday ${isFriday ? 'pdp-friday' : ''}">${w}</div>`;
    }).join('');

    // Day cells
    let dayCells = '';
    for (let i = 0; i < startDayOfWeek; i++) {
      dayCells += '<div class="pdp-day pdp-empty"></div>';
    }

    for (let d = 1; d <= daysInMonth; d++) {
      const isToday = (viewYear === this.today.year && viewMonth === this.today.month && d === this.today.day);
      const isSelected = this.selected && (viewYear === this.selected.year && viewMonth === this.selected.month && d === this.selected.day);
      const dayOfWeek = (startDayOfWeek + d - 1) % 7;
      const isFriday = dayOfWeek === 6;

      const classes = ['pdp-day'];
      if (isToday) classes.push('pdp-today');
      if (isSelected) classes.push('pdp-selected');
      if (isFriday) classes.push('pdp-friday');

      dayCells += `<div class="${classes.join(' ')}" data-day="${d}">${PersianDate.toPersianDigits(d)}</div>`;
    }

    this.popup.innerHTML = `
      <div class="pdp-header">
        <button type="button" class="pdp-nav-btn pdp-next" title="ماه بعد">‹</button>
        <div class="pdp-selectors">
          <select class="pdp-select pdp-month-select">${monthOptions}</select>
          <select class="pdp-select pdp-year-select">${yearOptions}</select>
        </div>
        <button type="button" class="pdp-nav-btn pdp-prev" title="ماه قبل">›</button>
      </div>
      <div class="pdp-weekdays">${weekdayHeaders}</div>
      <div class="pdp-days">${dayCells}</div>
      <div class="pdp-footer">
        <button type="button" class="pdp-action-btn pdp-today-btn">امروز</button>
        <button type="button" class="pdp-action-btn pdp-clear-btn">پاک کردن</button>
        <button type="button" class="pdp-action-btn pdp-close-btn">بستن</button>
      </div>
    `;

    // Attach internal popup event handlers
    const prevBtn = this.popup.querySelector('.pdp-prev');
    const nextBtn = this.popup.querySelector('.pdp-next');
    const monthSelect = this.popup.querySelector('.pdp-month-select');
    const yearSelect = this.popup.querySelector('.pdp-year-select');

    prevBtn.addEventListener('click', () => {
      if (this.viewMonth === 1) {
        this.viewMonth = 12;
        this.viewYear--;
      } else {
        this.viewMonth--;
      }
      this.render();
    });

    nextBtn.addEventListener('click', () => {
      if (this.viewMonth === 12) {
        this.viewMonth = 1;
        this.viewYear++;
      } else {
        this.viewMonth++;
      }
      this.render();
    });

    monthSelect.addEventListener('change', (e) => {
      this.viewMonth = parseInt(e.target.value, 10);
      this.render();
    });

    yearSelect.addEventListener('change', (e) => {
      this.viewYear = parseInt(e.target.value, 10);
      this.render();
    });

    // Day selection
    this.popup.querySelectorAll('.pdp-day[data-day]').forEach(cell => {
      cell.addEventListener('click', () => {
        const day = parseInt(cell.getAttribute('data-day'), 10);
        this.selectDate(this.viewYear, this.viewMonth, day);
      });
    });

    // Footer actions
    this.popup.querySelector('.pdp-today-btn').addEventListener('click', () => {
      this.selectDate(this.today.year, this.today.month, this.today.day);
    });

    this.popup.querySelector('.pdp-clear-btn').addEventListener('click', () => {
      this.input.value = '';
      this.selected = null;
      this.input.dispatchEvent(new Event('change', { bubbles: true }));
      this.input.dispatchEvent(new Event('input', { bubbles: true }));
      if (typeof this.options.onSelect === 'function') {
        this.options.onSelect('');
      }
      this.close();
    });

    this.popup.querySelector('.pdp-close-btn').addEventListener('click', () => {
      this.close();
    });
  }

  selectDate(year, month, day) {
    const formatted = PersianDate.formatString(year, month, day);
    this.selected = { year, month, day };
    this.input.value = formatted;

    // Trigger standard input/change events
    this.input.dispatchEvent(new Event('change', { bubbles: true }));
    this.input.dispatchEvent(new Event('input', { bubbles: true }));

    if (typeof this.options.onSelect === 'function') {
      this.options.onSelect(formatted);
    }

    if (this.options.autoClose) {
      this.close();
    } else {
      this.render();
    }
  }
}

// Global initialization helper
window.PersianDatePicker = PersianDatePicker;
window.initPersianDatePicker = (selector, options) => {
  const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
  if (el) {
    if (el._pdp) return el._pdp;
    return new PersianDatePicker(el, options);
  }
  return null;
};

// Auto-bind finance date inputs
function autoBindPersianDatepickers() {
  ['#finance-from', '#finance-to'].forEach(sel => {
    const el = document.querySelector(sel);
    if (el && !el._pdp) {
      new PersianDatePicker(el, {
        onSelect: () => {
          if (typeof Finance !== 'undefined' && typeof Finance.render === 'function') {
            Finance.render();
          }
        }
      });
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoBindPersianDatepickers);
} else {
  autoBindPersianDatepickers();
}
