/* ===================================================================
   JALALI DATEPICKER
   Converts Gregorian <-> Jalali (no external deps) and renders a
   glass-styled calendar popover. Keeps the underlying <input> value
   as an ISO Gregorian date (YYYY-MM-DD) so existing filtering logic
   (e.g. finance.js comparing t.payment_date strings) needs zero changes —
   only the *display* is Jalali.

   Usage: put data-jalali-picker on a hidden/plain <input id="X"> that
   should hold the ISO value, and JalaliDatepicker.attach('X') will
   inject a visible Jalali text field right before it.
=================================================================== */

const JalaliDatepicker = (() => {
  const MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
  const WEEKDAYS = ['ش','ی','د','س','چ','پ','ج'];

  // --- Gregorian -> Jalali ---
  function toJalali(gy, gm, gd){
    const g_d_m = [0,31,59,90,120,151,181,212,243,273,304,334];
    let jy = (gy <= 1600) ? 0 : 979;
    gy -= (gy <= 1600) ? 621 : 1600;
    const gy2 = (gm > 2) ? (gy + 1) : gy;
    let days = (365*gy) + Math.floor((gy2+3)/4) - Math.floor((gy2+99)/100) + Math.floor((gy2+399)/400) - 80 + gd + g_d_m[gm-1];
    jy += 33*Math.floor(days/12053); days %= 12053;
    jy += 4*Math.floor(days/1461); days %= 1461;
    jy += Math.floor((days-1)/365); if (days > 365) days = (days-1)%365;
    const jm = (days < 186) ? 1+Math.floor(days/31) : 7+Math.floor((days-186)/30);
    const jd = 1 + ((days < 186) ? (days%31) : ((days-186)%30));
    return [jy, jm, jd];
  }

  // --- Jalali -> Gregorian ---
  function toGregorian(jy, jm, jd){
    jy += 1595;
    let days = -355668 + (365*jy) + (Math.floor(jy/33)*8) + Math.floor(((jy%33)+3)/4) + jd + ((jm<7) ? (jm-1)*31 : ((jm-7)*30)+186);
    let gy = 400*Math.floor(days/146097); days %= 146097;
    if (days > 36524){ gy += 100*Math.floor(--days/36524); days %= 36524; if (days >= 365) days++; }
    gy += 4*Math.floor(days/1461); days %= 1461;
    if (days > 365){ gy += Math.floor((days-1)/365); days = (days-1)%365; }
    let gd = days + 1;
    const sal_a = [0,31,(gy%4===0 && (gy%100!==0 || gy%400===0))?29:28,31,30,31,30,31,31,30,31,30,31];
    let gm = 0;
    for (gm=1; gm<=12 && gd > sal_a[gm]; gm++) gd -= sal_a[gm];
    return [gy, gm, gd];
  }

  function pad(n){ return String(n).padStart(2,'0'); }
  function isoFromJalali(jy,jm,jd){ const [gy,gm,gd] = toGregorian(jy,jm,jd); return `${gy}-${pad(gm)}-${pad(gd)}`; }
  function jalaliFromIso(iso){
    const [gy,gm,gd] = iso.split('-').map(Number);
    return toJalali(gy,gm,gd);
  }

  let activePopover = null;

  function closePopover(){
    if (activePopover){ activePopover.remove(); activePopover = null; }
  }

  function renderCalendar(displayInput, hiddenInput, jy, jm){
    closePopover();
    const daysInMonth = jm <= 6 ? 31 : (jm <= 11 ? 30 : 29);
    const firstDayIso = isoFromJalali(jy, jm, 1);
    const firstWeekday = (new Date(firstDayIso).getDay() + 1) % 7; // shift so Saturday=0

    const pop = document.createElement('div');
    pop.className = 'glass-strong jalali-pop animate-popIn';
    pop.innerHTML = `
      <div class="jalali-pop-head">
        <button type="button" data-nav="prev" class="icon-btn" style="width:2rem;height:2rem">›</button>
        <span class="font-bold text-sm">${MONTHS[jm-1]} ${jy}</span>
        <button type="button" data-nav="next" class="icon-btn" style="width:2rem;height:2rem">‹</button>
      </div>
      <div class="jalali-pop-grid jalali-pop-weekdays">${WEEKDAYS.map(w=>`<span>${w}</span>`).join('')}</div>
      <div class="jalali-pop-grid">
        ${Array(firstWeekday).fill('<span></span>').join('')}
        ${Array.from({length:daysInMonth}, (_,i)=>i+1).map(d => `<button type="button" class="jalali-day" data-d="${d}">${d.toLocaleString('fa-IR')}</button>`).join('')}
      </div>
      <button type="button" class="jalali-today btn btn-ghost text-[11px] py-2 rounded-xl w-full mt-2">امروز</button>
    `;
    document.body.appendChild(pop);
    activePopover = pop;

    const rect = displayInput.getBoundingClientRect();
    pop.style.position = 'absolute';
    pop.style.top = (window.scrollY + rect.bottom + 8) + 'px';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    pop.style.zIndex = 75;

    pop.querySelector('[data-nav="prev"]').onclick = () => {
      let ny=jy, nm=jm+1; if (nm>12){ nm=1; ny++; } renderCalendar(displayInput, hiddenInput, ny, nm);
    };
    pop.querySelector('[data-nav="next"]').onclick = () => {
      let ny=jy, nm=jm-1; if (nm<1){ nm=12; ny--; } renderCalendar(displayInput, hiddenInput, ny, nm);
    };
    pop.querySelectorAll('.jalali-day').forEach(btn => {
      btn.onclick = () => {
        const d = parseInt(btn.dataset.d, 10);
        hiddenInput.value = isoFromJalali(jy, jm, d);
        displayInput.value = `${jy}/${pad(jm)}/${pad(d)}`;
        hiddenInput.dispatchEvent(new Event('change'));
        closePopover();
      };
    });
    pop.querySelector('.jalali-today').onclick = () => {
      const now = new Date();
      const [ty,tm,td] = toJalali(now.getFullYear(), now.getMonth()+1, now.getDate());
      hiddenInput.value = isoFromJalali(ty,tm,td);
      displayInput.value = `${ty}/${pad(tm)}/${pad(td)}`;
      hiddenInput.dispatchEvent(new Event('change'));
      closePopover();
    };

    setTimeout(() => {
      document.addEventListener('click', function onDoc(e){
        if (!pop.contains(e.target) && e.target !== displayInput){ closePopover(); document.removeEventListener('click', onDoc); }
      });
    }, 0);
  }

  function attach(hiddenInputId){
    const hidden = document.getElementById(hiddenInputId);
    if (!hidden) return;
    hidden.type = 'hidden';

    const display = document.createElement('input');
    display.type = 'text';
    display.readOnly = true;
    display.placeholder = '۱۴۰۳/۰۱/۰۱';
    display.className = hidden.dataset.displayClass || '';
    display.id = hiddenInputId + '-jalali';
    hidden.parentNode.insertBefore(display, hidden);

    if (hidden.value){
      const [jy,jm,jd] = jalaliFromIso(hidden.value);
      display.value = `${jy}/${pad(jm)}/${pad(jd)}`;
    }

    display.addEventListener('click', () => {
      const base = hidden.value ? jalaliFromIso(hidden.value) : (() => {
        const now = new Date(); return toJalali(now.getFullYear(), now.getMonth()+1, now.getDate());
      })();
      renderCalendar(display, hidden, base[0], base[1]);
    });
  }

  return { attach, toJalali, toGregorian, isoFromJalali, jalaliFromIso };
})();
