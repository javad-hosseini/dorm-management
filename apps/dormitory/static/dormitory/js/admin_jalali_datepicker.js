/**
 * Admin Persian (Jalali) Datepicker
 * Designed for Django Jazzmin Admin & Bootstrap 4 Tabs.
 * 100% Vanilla JS, zero dependencies, tab-friendly, high z-index.
 */

(function () {
    'use strict';

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

        function toAsciiDigits(str) {
            if (!str) return '';
            return String(str).replace(/[۰-۹]/g, d => String(PERSIAN_DIGITS.indexOf(d)));
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
            const day = date.getDay(); // Sunday=0 ... Saturday=6
            return (day + 1) % 7;     // Saturday=0 ... Friday=6
        }

        function getToday() {
            const now = new Date();
            return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
        }

        function getYesterday() {
            const now = new Date();
            now.setDate(now.getDate() - 1);
            return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
        }

        function formatString(jy, jm, jd) {
            const m = String(jm).padStart(2, '0');
            const d = String(jd).padStart(2, '0');
            // Strict hyphen format required by django_jalali: YYYY-MM-DD
            return `${jy}-${m}-${d}`;
        }

        function parseString(str) {
            if (!str) return null;
            const cleanStr = toAsciiDigits(str.trim());
            const parts = cleanStr.split(/[\/\-]/);
            if (parts.length === 3) {
                const y = parseInt(parts[0], 10);
                const m = parseInt(parts[1], 10);
                const d = parseInt(parts[2], 10);
                if (!isNaN(y) && !isNaN(m) && !isNaN(d) && y > 1300 && y < 1500 && m >= 1 && m <= 12 && d >= 1 && d <= 31) {
                    return { year: y, month: m, day: d };
                }
            }
            return null;
        }

        return {
            MONTH_NAMES,
            toPersianDigits,
            toAsciiDigits,
            getDaysInMonth,
            getJalaliDayOfWeek,
            getToday,
            getYesterday,
            formatString,
            parseString
        };
    })();

    function isTimeInput(input) {
        if (!input || !input.tagName) return false;
        if (input.classList && (
            input.classList.contains('vTimeField') ||
            input.classList.contains('vjTimeField') ||
            input.classList.contains('admin-clock-input')
        )) {
            return true;
        }
        const name = (input.name || '').toLowerCase();
        const id = (input.id || '').toLowerCase();
        if (name.includes('time') || id.includes('time')) return true;
        if (name.endsWith('_1') || id.endsWith('_1')) return true;
        if (input.closest && (input.closest('.time') || input.closest('p.time') || input.closest('.admin-clock-wrap'))) {
            return true;
        }
        return false;
    }

    class AdminPersianDatePicker {
        constructor(inputEl, options = {}) {
            if (!inputEl || isTimeInput(inputEl)) return null;
            if (inputEl._adminPdp) return inputEl._adminPdp;
            this.input = inputEl;
            this.options = Object.assign({
                minYear: 1380,
                maxYear: 1420,
                autoClose: true
            }, options);

            this.today = PersianDate.getToday();
            this.yesterday = PersianDate.getYesterday();
            this.selected = PersianDate.parseString(this.input.value);

            const initial = this.selected || this.today;
            this.viewYear = initial.year;
            this.viewMonth = initial.month;

            this.isOpen = false;
            this.popup = null;

            this.initDOM();
            inputEl._adminPdp = this;
        }

        initDOM() {
            // Remove Django's gregorian shortcuts if attached next to input
            const nextSib = this.input.nextElementSibling;
            if (nextSib && (nextSib.classList.contains('datetimeshortcuts') || nextSib.classList.contains('ui-datepicker-trigger'))) {
                nextSib.remove();
            }

            // Wrap input in styled container if not already wrapped
            let wrapper = this.input.parentElement;
            if (!wrapper || !wrapper.classList.contains('admin-pdp-wrap')) {
                wrapper = document.createElement('div');
                wrapper.className = 'admin-pdp-wrap';
                this.input.parentNode.insertBefore(wrapper, this.input);
                wrapper.appendChild(this.input);

                // Add 📅 trigger button
                const trigger = document.createElement('button');
                trigger.type = 'button';
                trigger.className = 'admin-pdp-trigger';
                trigger.innerHTML = '📅';
                trigger.title = 'انتخاب تاریخ شمسی';
                trigger.setAttribute('tabindex', '-1');
                wrapper.appendChild(trigger);

                trigger.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggle();
                });
            }

            this.input.classList.add('admin-pdp-input');
            this.input.setAttribute('autocomplete', 'off');
            this.input.setAttribute('placeholder', '۱۴۰۳-۰۷-۰۱');

            this.input.addEventListener('click', (e) => {
                e.stopPropagation();
                this.open();
            });

            this.input.addEventListener('focus', () => {
                this.open();
            });

            this.input.addEventListener('change', () => {
                const parsed = PersianDate.parseString(this.input.value);
                if (parsed) {
                    this.selected = parsed;
                    this.viewYear = parsed.year;
                    this.viewMonth = parsed.month;
                }
            });
        }

        buildPopup() {
            if (this.popup) return;

            this.popup = document.createElement('div');
            this.popup.className = 'admin-pdp-popup';
            document.body.appendChild(this.popup);

            // Prevent clicks inside popup from closing it
            this.popup.addEventListener('click', (e) => {
                e.stopPropagation();
            });

            this.boundOnOutsideClick = (e) => {
                if (!this.isOpen) return;
                const wrapper = this.input.closest('.admin-pdp-wrap');
                if (wrapper && wrapper.contains(e.target)) return;
                if (this.popup && this.popup.contains(e.target)) return;
                this.close();
            };

            this.boundOnKeyDown = (e) => {
                if (e.key === 'Escape' && this.isOpen) {
                    this.close();
                }
            };
        }

        positionPopup() {
            if (!this.popup) return;
            const rect = this.input.getBoundingClientRect();
            const scrollY = window.pageYOffset || document.documentElement.scrollTop;
            const scrollX = window.pageXOffset || document.documentElement.scrollLeft;

            const popupWidth = 320;
            let top = rect.bottom + scrollY + 4;
            // Align RTL: align right edges
            let left = rect.right + scrollX - popupWidth;

            // Viewport boundary checks
            if (left < 10) {
                left = 10;
            }
            if (left + popupWidth > window.innerWidth - 10) {
                left = window.innerWidth - popupWidth - 10;
            }

            this.popup.style.top = `${top}px`;
            this.popup.style.left = `${left}px`;
        }

        open() {
            // Close other open datepickers
            document.querySelectorAll('.admin-pdp-popup').forEach(p => {
                p.style.display = 'none';
            });

            this.buildPopup();
            this.selected = PersianDate.parseString(this.input.value);
            if (this.selected) {
                this.viewYear = this.selected.year;
                this.viewMonth = this.selected.month;
            } else {
                this.viewYear = this.today.year;
                this.viewMonth = this.today.month;
            }

            this.render();
            this.popup.style.display = 'block';
            this.positionPopup();
            this.isOpen = true;

            document.addEventListener('click', this.boundOnOutsideClick);
            document.addEventListener('keydown', this.boundOnKeyDown);
        }

        close() {
            if (this.popup) {
                this.popup.style.display = 'none';
            }
            this.isOpen = false;
            document.removeEventListener('click', this.boundOnOutsideClick);
            document.removeEventListener('keydown', this.boundOnKeyDown);
        }

        toggle() {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        }

        render() {
            if (!this.popup) return;

            const daysInMonth = PersianDate.getDaysInMonth(this.viewYear, this.viewMonth);
            const startDayOfWeek = PersianDate.getJalaliDayOfWeek(this.viewYear, this.viewMonth, 1);

            const monthOptions = PersianDate.MONTH_NAMES.map((name, idx) => {
                const mNum = idx + 1;
                return `<option value="${mNum}" ${mNum === this.viewMonth ? 'selected' : ''}>${name}</option>`;
            }).join('');

            let yearOptions = '';
            for (let y = this.options.minYear; y <= this.options.maxYear; y++) {
                yearOptions += `<option value="${y}" ${y === this.viewYear ? 'selected' : ''}>${PersianDate.toPersianDigits(y)}</option>`;
            }

            // Weekdays
            const weekdays = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
            const weekdayHeaders = weekdays.map((w, idx) => {
                const isFriday = idx === 6;
                return `<div class="admin-pdp-weekday ${isFriday ? 'admin-pdp-friday' : ''}">${w}</div>`;
            }).join('');

            // Days grid
            let dayCells = '';
            for (let i = 0; i < startDayOfWeek; i++) {
                dayCells += '<div class="admin-pdp-day admin-pdp-empty"></div>';
            }

            for (let d = 1; d <= daysInMonth; d++) {
                const isToday = (this.viewYear === this.today.year && this.viewMonth === this.today.month && d === this.today.day);
                const isSelected = this.selected && (this.viewYear === this.selected.year && this.viewMonth === this.selected.month && d === this.selected.day);
                const dayOfWeek = (startDayOfWeek + d - 1) % 7;
                const isFriday = (dayOfWeek === 6);

                const classes = ['admin-pdp-day'];
                if (isToday) classes.push('admin-pdp-today');
                if (isSelected) classes.push('admin-pdp-selected');
                if (isFriday) classes.push('admin-pdp-friday');

                dayCells += `<div class="${classes.join(' ')}" data-day="${d}">${PersianDate.toPersianDigits(d)}</div>`;
            }

            this.popup.innerHTML = `
                <div class="admin-pdp-header">
                    <button type="button" class="admin-pdp-nav-btn admin-pdp-next" title="ماه بعد">‹</button>
                    <div class="admin-pdp-selectors">
                        <select class="admin-pdp-select admin-pdp-month-select">${monthOptions}</select>
                        <select class="admin-pdp-select admin-pdp-year-select">${yearOptions}</select>
                    </div>
                    <button type="button" class="admin-pdp-nav-btn admin-pdp-prev" title="ماه قبل">›</button>
                </div>
                <div class="admin-pdp-weekdays">${weekdayHeaders}</div>
                <div class="admin-pdp-days">${dayCells}</div>
                <div class="admin-pdp-footer">
                    <button type="button" class="admin-pdp-btn admin-pdp-btn-yesterday" title="ثبت تاریخ دیروز">دیروز</button>
                    <button type="button" class="admin-pdp-btn admin-pdp-btn-today" title="ثبت تاریخ امروز">امروز</button>
                    <button type="button" class="admin-pdp-btn admin-pdp-btn-clear" title="پاک کردن فیلد">پاک کردن</button>
                    <button type="button" class="admin-pdp-btn admin-pdp-btn-close" title="بستن تقویم">بستن</button>
                </div>
            `;

            // Event Listeners
            this.popup.querySelector('.admin-pdp-prev').addEventListener('click', () => {
                if (this.viewMonth === 1) {
                    this.viewMonth = 12;
                    this.viewYear--;
                } else {
                    this.viewMonth--;
                }
                this.render();
            });

            this.popup.querySelector('.admin-pdp-next').addEventListener('click', () => {
                if (this.viewMonth === 12) {
                    this.viewMonth = 1;
                    this.viewYear++;
                } else {
                    this.viewMonth++;
                }
                this.render();
            });

            this.popup.querySelector('.admin-pdp-month-select').addEventListener('change', (e) => {
                this.viewMonth = parseInt(e.target.value, 10);
                this.render();
            });

            this.popup.querySelector('.admin-pdp-year-select').addEventListener('change', (e) => {
                this.viewYear = parseInt(e.target.value, 10);
                this.render();
            });

            // Days
            this.popup.querySelectorAll('.admin-pdp-day[data-day]').forEach(cell => {
                cell.addEventListener('click', () => {
                    const day = parseInt(cell.getAttribute('data-day'), 10);
                    this.selectDate(this.viewYear, this.viewMonth, day);
                });
            });

            // Quick buttons
            this.popup.querySelector('.admin-pdp-btn-yesterday').addEventListener('click', () => {
                const yest = PersianDate.getYesterday();
                this.selectDate(yest.year, yest.month, yest.day);
            });

            this.popup.querySelector('.admin-pdp-btn-today').addEventListener('click', () => {
                const tod = PersianDate.getToday();
                this.selectDate(tod.year, tod.month, tod.day);
            });

            this.popup.querySelector('.admin-pdp-btn-clear').addEventListener('click', () => {
                this.input.value = '';
                this.selected = null;
                this.input.dispatchEvent(new Event('change', { bubbles: true }));
                this.input.dispatchEvent(new Event('input', { bubbles: true }));
                this.close();
            });

            this.popup.querySelector('.admin-pdp-btn-close').addEventListener('click', () => {
                this.close();
            });
        }

        selectDate(year, month, day) {
            const formatted = PersianDate.formatString(year, month, day);
            this.selected = { year, month, day };
            this.input.value = formatted;

            this.input.dispatchEvent(new Event('change', { bubbles: true }));
            this.input.dispatchEvent(new Event('input', { bubbles: true }));

            if (this.options.autoClose) {
                this.close();
            } else {
                this.render();
            }
        }
    }

    /* ===================================================================
       ADMIN TIME PICKER (انتخاب‌گر ساعت و زمان پنل مدیریت)
       =================================================================== */
    class AdminTimePicker {
        constructor(inputEl, options = {}) {
            if (!inputEl || inputEl._adminClock) return inputEl ? inputEl._adminClock : null;
            this.input = inputEl;
            this.options = Object.assign({
                autoClose: false
            }, options);

            const parsed = this.parseTime(this.input.value);
            if (parsed) {
                this.currentHour = parsed.hour;
                this.currentMinute = parsed.minute;
                this.currentSecond = parsed.second;
                this.selected = { ...parsed };
            } else {
                const now = new Date();
                this.currentHour = now.getHours();
                this.currentMinute = now.getMinutes();
                this.currentSecond = now.getSeconds();
                this.selected = null;
            }

            this.isOpen = false;
            this.popup = null;

            this.initDOM();
            inputEl._adminClock = this;
        }

        parseTime(val) {
            if (!val || typeof val !== 'string') return null;
            const ascii = PersianDate.toAsciiDigits(val.trim());
            const parts = ascii.split(':').map(p => parseInt(p, 10));
            if (parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
                const hour = Math.max(0, Math.min(23, parts[0]));
                const minute = Math.max(0, Math.min(59, parts[1]));
                const second = parts.length >= 3 && !isNaN(parts[2]) ? Math.max(0, Math.min(59, parts[2])) : 0;
                return { hour, minute, second };
            }
            return null;
        }

        formatTime(h, m, s) {
            const pad = n => String(n).padStart(2, '0');
            return `${pad(h)}:${pad(m)}:${pad(s)}`;
        }

        initDOM() {
            // Remove Django default shortcuts next to input
            const nextSib = this.input.nextElementSibling;
            if (nextSib && (nextSib.classList.contains('datetimeshortcuts') || nextSib.classList.contains('timezonewarning'))) {
                nextSib.remove();
            }

            // Remove any erroneously attached Persian Datepicker artifacts
            if (this.input._adminPdp) {
                this.input._adminPdp = null;
            }

            let wrapper = this.input.parentElement;
            if (wrapper && wrapper.classList.contains('admin-pdp-wrap')) {
                wrapper.classList.remove('admin-pdp-wrap');
                wrapper.classList.add('admin-clock-wrap');
                const oldTrigger = wrapper.querySelector('.admin-pdp-trigger');
                if (oldTrigger) oldTrigger.remove();
            } else if (!wrapper || !wrapper.classList.contains('admin-clock-wrap')) {
                wrapper = document.createElement('div');
                wrapper.className = 'admin-clock-wrap';
                this.input.parentNode.insertBefore(wrapper, this.input);
                wrapper.appendChild(this.input);
            }

            // Ensure 🕒 trigger button exists
            let trigger = wrapper.querySelector('.admin-clock-trigger');
            if (!trigger) {
                trigger = document.createElement('button');
                trigger.type = 'button';
                trigger.className = 'admin-clock-trigger';
                trigger.innerHTML = '🕒';
                trigger.title = 'انتخاب زمان و ساعت';
                trigger.setAttribute('tabindex', '-1');
                wrapper.appendChild(trigger);
            }

            trigger.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggle();
            };

            this.input.classList.remove('admin-pdp-input');
            this.input.classList.add('admin-clock-input');
            this.input.setAttribute('autocomplete', 'off');
            this.input.setAttribute('placeholder', '۱۲:۳۰:۰۰');

            this.input.onclick = (e) => {
                e.stopPropagation();
                this.open();
            };

            this.input.onfocus = () => {
                this.open();
            };

            this.input.onchange = () => {
                const parsed = this.parseTime(this.input.value);
                if (parsed) {
                    this.currentHour = parsed.hour;
                    this.currentMinute = parsed.minute;
                    this.currentSecond = parsed.second;
                    this.selected = { ...parsed };
                    if (this.isOpen) this.render();
                }
            };
        }

        open() {
            if (this.isOpen) return;
            // Close any open popups
            document.querySelectorAll('.admin-pdp-popup, .admin-clock-popup').forEach(p => p.remove());

            // Refresh current time values from input if available
            const parsed = this.parseTime(this.input.value);
            if (parsed) {
                this.currentHour = parsed.hour;
                this.currentMinute = parsed.minute;
                this.currentSecond = parsed.second;
                this.selected = { ...parsed };
            } else if (!this.selected) {
                const now = new Date();
                this.currentHour = now.getHours();
                this.currentMinute = now.getMinutes();
                this.currentSecond = now.getSeconds();
            }

            this.buildPopup();
            document.body.appendChild(this.popup);
            this.positionPopup();
            this.isOpen = true;

            this._onDocClick = (e) => {
                if (this.popup && !this.popup.contains(e.target) && !this.input.contains(e.target) && !e.target.closest('.admin-clock-trigger')) {
                    this.close();
                }
            };
            this._onKeydown = (e) => {
                if (e.key === 'Escape') this.close();
            };
            this._onScroll = () => {
                if (this.isOpen) this.positionPopup();
            };

            setTimeout(() => {
                document.addEventListener('click', this._onDocClick);
                document.addEventListener('keydown', this._onKeydown);
                window.addEventListener('scroll', this._onScroll, true);
                window.addEventListener('resize', this._onScroll);
            }, 10);
        }

        close() {
            if (!this.isOpen) return;
            if (this.popup) {
                this.popup.remove();
                this.popup = null;
            }
            this.isOpen = false;
            document.removeEventListener('click', this._onDocClick);
            document.removeEventListener('keydown', this._onKeydown);
            window.removeEventListener('scroll', this._onScroll, true);
            window.removeEventListener('resize', this._onScroll);
        }

        toggle() {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        }

        positionPopup() {
            if (!this.popup) return;
            const rect = this.input.getBoundingClientRect();
            const popupRect = this.popup.getBoundingClientRect();
            const viewportH = window.innerHeight;
            const viewportW = window.innerWidth;

            let top = rect.bottom + 6;
            let left = rect.right - popupRect.width;

            // If not enough room below, show above
            if (top + popupRect.height > viewportH && rect.top > popupRect.height + 6) {
                top = rect.top - popupRect.height - 6;
            }

            if (left < 10) left = 10;
            if (left + popupRect.width > viewportW - 10) {
                left = viewportW - popupRect.width - 10;
            }

            this.popup.style.top = `${top}px`;
            this.popup.style.left = `${left}px`;
        }

        buildPopup() {
            this.popup = document.createElement('div');
            this.popup.className = 'admin-clock-popup';
            this.popup.setAttribute('role', 'dialog');
            this.popup.setAttribute('aria-label', 'انتخاب ساعت');

            this.render();
        }

        render() {
            if (!this.popup) return;

            const pad = n => String(n).padStart(2, '0');
            const hStr = pad(this.currentHour);
            const mStr = pad(this.currentMinute);
            const sStr = pad(this.currentSecond);

            const presets = [
                { label: '۰۸:۰۰', h: 8, m: 0 },
                { label: '۱۲:۰۰', h: 12, m: 0 },
                { label: '۱۴:۰۰', h: 14, m: 0 },
                { label: '۱۶:۰۰', h: 16, m: 0 },
                { label: '۱۸:۰۰', h: 18, m: 0 },
                { label: '۲۰:۰۰', h: 20, m: 0 },
                { label: '۲۲:۰۰', h: 22, m: 0 },
                { label: '۲۳:۵۹', h: 23, m: 59 }
            ];

            const minSteps = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];

            let html = `
                <div class="admin-clock-header">
                    <div class="admin-clock-title">
                        <span>🕒</span>
                        <span>انتخاب ساعت و زمان</span>
                    </div>
                    <button type="button" class="admin-clock-close-btn" title="بستن">✕</button>
                </div>

                <div class="admin-clock-display-card">
                    <div class="admin-clock-time-val">
                        <span id="clk-h">${hStr}</span>
                        <span class="clock-colon">:</span>
                        <span id="clk-m">${mStr}</span>
                        <span class="clock-colon">:</span>
                        <span id="clk-s">${sStr}</span>
                    </div>
                    <div class="admin-clock-labels">
                        <span>ساعت</span>
                        <span>دقیقه</span>
                        <span>ثانیه</span>
                    </div>
                </div>

                <div class="admin-clock-quick-bar">
                    <button type="button" class="admin-clock-btn-now">⚡ الان (هم‌اکنون)</button>
                    <div class="admin-clock-presets">
                        ${presets.map(p => `
                            <button type="button" class="admin-clock-preset-btn" data-h="${p.h}" data-m="${p.m}">${p.label}</button>
                        `).join('')}
                    </div>
                </div>

                <div class="admin-clock-grid-container">
                    <div class="admin-clock-col">
                        <div class="admin-clock-col-title">ساعت (۰-۲۳)</div>
                        <div class="admin-clock-hours-grid">
                            ${Array.from({ length: 24 }, (_, i) => `
                                <button type="button" class="admin-clock-item clk-hour-btn ${i === this.currentHour ? 'active' : ''}" data-val="${i}">
                                    ${pad(i)}
                                </button>
                            `).join('')}
                        </div>
                    </div>

                    <div class="admin-clock-col">
                        <div class="admin-clock-col-title">دقیقه</div>
                        <div class="admin-clock-minutes-grid">
                            ${minSteps.map(m => `
                                <button type="button" class="admin-clock-item clk-min-btn ${m === this.currentMinute ? 'active' : ''}" data-val="${m}">
                                    ${pad(m)}
                                </button>
                            `).join('')}
                        </div>
                        <div class="admin-clock-minute-stepper">
                            <button type="button" class="admin-clock-step-btn" data-step="-1">−۱ د</button>
                            <span class="admin-clock-step-val">${mStr}</span>
                            <button type="button" class="admin-clock-step-btn" data-step="1">+۱ د</button>
                        </div>
                    </div>
                </div>

                <div class="admin-clock-footer">
                    <button type="button" class="admin-clock-btn admin-clock-btn-confirm">ثبت و تایید ساعت</button>
                    <button type="button" class="admin-clock-btn admin-clock-btn-clear">پاک کردن</button>
                </div>
            `;

            this.popup.innerHTML = html;
            this.bindPopupEvents();
        }

        bindPopupEvents() {
            // Close
            const closeBtn = this.popup.querySelector('.admin-clock-close-btn');
            if (closeBtn) closeBtn.onclick = () => this.close();

            // Now button
            const nowBtn = this.popup.querySelector('.admin-clock-btn-now');
            if (nowBtn) {
                nowBtn.onclick = () => {
                    const now = new Date();
                    this.setTime(now.getHours(), now.getMinutes(), now.getSeconds(), true);
                };
            }

            // Presets
            this.popup.querySelectorAll('.admin-clock-preset-btn').forEach(btn => {
                btn.onclick = () => {
                    const h = parseInt(btn.dataset.h, 10);
                    const m = parseInt(btn.dataset.m, 10);
                    this.setTime(h, m, 0, false);
                };
            });

            // Hour buttons
            this.popup.querySelectorAll('.clk-hour-btn').forEach(btn => {
                btn.onclick = () => {
                    const h = parseInt(btn.dataset.val, 10);
                    this.setTime(h, this.currentMinute, this.currentSecond, false);
                };
            });

            // Minute buttons
            this.popup.querySelectorAll('.clk-min-btn').forEach(btn => {
                btn.onclick = () => {
                    const m = parseInt(btn.dataset.val, 10);
                    this.setTime(this.currentHour, m, this.currentSecond, false);
                };
            });

            // Minute stepper
            this.popup.querySelectorAll('.admin-clock-step-btn').forEach(btn => {
                btn.onclick = () => {
                    const delta = parseInt(btn.dataset.step, 10);
                    let newM = (this.currentMinute + delta + 60) % 60;
                    this.setTime(this.currentHour, newM, this.currentSecond, false);
                };
            });

            // Confirm
            const confirmBtn = this.popup.querySelector('.admin-clock-btn-confirm');
            if (confirmBtn) {
                confirmBtn.onclick = () => {
                    this.commitValue();
                    this.close();
                };
            }

            // Clear
            const clearBtn = this.popup.querySelector('.admin-clock-btn-clear');
            if (clearBtn) {
                clearBtn.onclick = () => {
                    this.input.value = '';
                    this.selected = null;
                    this.input.dispatchEvent(new Event('change', { bubbles: true }));
                    this.input.dispatchEvent(new Event('input', { bubbles: true }));
                    this.close();
                };
            }
        }

        setTime(h, m, s, commitImmediately = false) {
            this.currentHour = h;
            this.currentMinute = m;
            this.currentSecond = s;
            this.commitValue();
            if (commitImmediately && this.options.autoClose) {
                this.close();
            } else {
                this.render();
            }
        }

        commitValue() {
            const formatted = this.formatTime(this.currentHour, this.currentMinute, this.currentSecond);
            this.input.value = formatted;
            this.selected = {
                hour: this.currentHour,
                minute: this.currentMinute,
                second: this.currentSecond
            };
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
            this.input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    // Auto-binding function for all date fields in admin
    function bindAllAdminDatepickers() {
        const dateInputSelectors = [
            'input.vjDateField',
            'input.vDateField',
            '#id_entry_date',
            '#id_exit_date',
            '#id_settled_until',
            '#id_date',
            '#id_payment_date',
            '#id_payment_date_0',
            'input[name*="date"]'
        ];

        const inputs = document.querySelectorAll(dateInputSelectors.join(', '));
        inputs.forEach(input => {
            // Strictly ignore time fields, hidden fields, or anything marked as time
            if (input.type === 'hidden' || isTimeInput(input)) {
                return;
            }
            if (!input._adminPdp) {
                new AdminPersianDatePicker(input);
            }
        });
    }

    // Auto-binding function for all time fields in admin
    function bindAllAdminTimepickers() {
        const timeInputSelectors = [
            'input.vTimeField',
            'input.vjTimeField',
            '#id_payment_date_1',
            'input[name="payment_date_1"]',
            'input[name$="_1"]',
            'p.time input',
            '.field-payment_date p.time input',
            'input[name*="time"]',
            'input.admin-clock-input'
        ];

        const inputs = document.querySelectorAll(timeInputSelectors.join(', '));
        inputs.forEach(input => {
            if (input.type === 'hidden') return;
            if (!isTimeInput(input)) return;

            // If it had a pdp attached mistakenly, clean it up
            if (input._adminPdp) {
                input._adminPdp = null;
                const wrap = input.closest('.admin-pdp-wrap');
                if (wrap) {
                    const trigger = wrap.querySelector('.admin-pdp-trigger');
                    if (trigger) trigger.remove();
                    wrap.classList.remove('admin-pdp-wrap');
                }
            }

            if (!input._adminClock) {
                new AdminTimePicker(input);
            }
        });
    }

    // Auto-select default dormitory ('خوابگاه نوید' or first available option) if empty
    function autoSelectDefaultDormitory() {
        const dormSelects = document.querySelectorAll('select[name="dormitory"], select[name$="-dormitory"], #id_dormitory');
        dormSelects.forEach(select => {
            if (!select.value && select.options && select.options.length > 1) {
                let targetOption = null;
                for (let i = 0; i < select.options.length; i++) {
                    if (select.options[i].text && select.options[i].text.includes('نوید')) {
                        targetOption = select.options[i];
                        break;
                    }
                }
                if (!targetOption) {
                    for (let i = 0; i < select.options.length; i++) {
                        if (select.options[i].value) {
                            targetOption = select.options[i];
                            break;
                        }
                    }
                }
                if (targetOption) {
                    select.value = targetOption.value;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });
    }

    function initAllAdminEnhancements() {
        bindAllAdminDatepickers();
        bindAllAdminTimepickers();
        autoSelectDefaultDormitory();
    }

    // Initialize on DOM load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAllAdminEnhancements);
    } else {
        initAllAdminEnhancements();
    }

    // Watch for Jazzmin Bootstrap 4 tab transitions (including #جزئیات-رسید-و-پیگیری-tab)
    if (typeof window.jQuery !== 'undefined') {
        window.jQuery(document).on('shown.bs.tab', 'a[data-toggle="tab"]', function () {
            initAllAdminEnhancements();
        });
    }

    window.addEventListener('hashchange', function () {
        setTimeout(initAllAdminEnhancements, 50);
    });

    // Also watch for DOM changes (such as inline rows or modal dialogs added in admin)
    const observer = new MutationObserver(function () {
        initAllAdminEnhancements();
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener('DOMContentLoaded', function () {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    }

    // Expose globally
    window.AdminPersianDatePicker = AdminPersianDatePicker;
    window.AdminTimePicker = AdminTimePicker;
    window.bindAllAdminDatepickers = bindAllAdminDatepickers;
    window.bindAllAdminTimepickers = bindAllAdminTimepickers;
    window.isTimeInput = isTimeInput;

})();
