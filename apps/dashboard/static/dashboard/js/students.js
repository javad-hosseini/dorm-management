/* ===================================================================
   STUDENTS TAB — Robust real-world data rendering
=================================================================== */

const Students = (() => {
  function occLabel(o) {
    return { STUDENT: 'دانشجو', EMPLOYED: 'شاغل', OTHER: 'سایر' }[o] || o || 'سایر';
  }

  function populateDormFilter() {
    const select = document.getElementById('filter-dorm');
    if (!select || !DB.dorms) return;
    const currentVal = select.value;
    select.innerHTML = '<option value="">همه خوابگاه‌ها</option>' +
      DB.dorms.map(d => `<option value="${d}">${d}</option>`).join('');
    if (currentVal) select.value = currentVal;
  }

  function render(list = DB.residents) {
    populateDormFilter();
    const grid = document.getElementById('students-grid');
    if (!grid) return;

    if (!list || list.length === 0) {
      grid.innerHTML = `<div class="empty-state col-span-full">😶 موردی با این فیلترها پیدا نشد</div>`;
    } else {
      grid.innerHTML = list.map((r, i) => {
        const roomText = r.room ? `اتاق ${r.room.room_number}` : 'اتاق تعیین‌نشده';
        const rentText = r.room ? Utils.toToman(r.room.monthly_rent) : '-';
        const initial = (r.first_name || r.full_name || 'س')[0];
        const isLeft = r.status === 'LEFT';
        const statusClass = isLeft ? 'bg-slate-500 text-white' : (r.is_in_debt ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-white');
        const statusText = isLeft ? 'خارج شده' : (r.is_in_debt ? 'بدهکار' : 'تسویه');
        const cardClass = isLeft ? 'opacity-70' : (r.is_in_debt ? 'debt-card' : '');

        return `
          <div onclick="Modal.openResident(${r.id})" style="animation-delay:${Math.min(i,10)*30}ms"
               class="entity-card glass p-5 cursor-pointer ${cardClass}">
            <div class="flex justify-between items-start">
              <div class="flex gap-3">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-lg">${initial}</div>
                <div>
                  <p class="font-bold text-[15px]">${r.full_name || 'بدون نام'}</p>
                  <p class="text-[11px] text-muted">${r.national_code} • ${r.phone_number}</p>
                  <p class="text-[10px] mt-1 text-muted">🏢 ${r.dormitory || 'نامشخص'} - ${roomText} | ${occLabel(r.occupation)}</p>
                </div>
              </div>
              <span class="status-pill ${statusClass}">${statusText}</span>
            </div>
            <div class="grid grid-cols-3 gap-2 mt-4 text-[11px]">
              <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">ورود</p><p class="truncate">${r.entry_date || '-'}</p></div>
              <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">تسویه تا</p><p class="truncate">${r.settled_until || 'ثبت نشده'}</p></div>
              <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">این ماه</p><p>${r.has_paid_this_month ? '✅ پرداخت' : '❌ نپرداخته'}</p></div>
            </div>
            <div class="mt-3 flex gap-2 text-[10px] flex-wrap">
              <span class="glass px-2 py-1 rounded-full">اجاره: ${rentText}</span>
              <span class="glass px-2 py-1 rounded-full">روز پرداخت: ${r.monthly_payment_day || 1}ام</span>
            </div>
          </div>
        `;
      }).join('');
    }

    const activeEl = document.getElementById('kpi-active');
    const debtEl = document.getElementById('kpi-debt');
    const activeCount = DB.stats?.active_residents ?? DB.residents.filter(r => r.status === 'ACTIVE').length;
    const debtCount = DB.stats?.debt_residents ?? DB.residents.filter(r => r.is_in_debt && r.status === 'ACTIVE').length;

    if (activeEl) Utils.animateCounter(activeEl, activeCount);
    if (debtEl) Utils.animateCounter(debtEl, debtCount);
  }

  function filter() {
    const qEl = document.getElementById('search-student');
    const dormEl = document.getElementById('filter-dorm');
    const statusEl = document.getElementById('filter-status');
    const occEl = document.getElementById('filter-occupation');

    const q = qEl ? qEl.value.trim().toLowerCase() : '';
    const dorm = dormEl ? dormEl.value : '';
    const status = statusEl ? statusEl.value : '';
    const occ = occEl ? occEl.value : '';

    const filtered = (DB.residents || []).filter(r => {
      const roomStr = r.room ? String(r.room.room_number) : '';
      const fullName = (r.full_name || '').toLowerCase();
      const natCode = r.national_code || '';
      const phone = r.phone_number || '';

      const matchQ = !q ||
        fullName.includes(q) ||
        natCode.includes(q) ||
        phone.includes(q) ||
        roomStr.includes(q);

      const matchDorm = !dorm || r.dormitory === dorm;
      const matchOcc = !occ || r.occupation === occ;

      let matchStat = true;
      if (status === "debt") matchStat = r.is_in_debt && r.status === 'ACTIVE';
      else if (status === "paid") matchStat = !r.is_in_debt && r.status === 'ACTIVE';
      else if (status === "ACTIVE") matchStat = r.status === "ACTIVE";
      else if (status === "LEFT") matchStat = r.status === "LEFT";

      return matchQ && matchDorm && matchOcc && matchStat;
    });

    render(filtered);
  }

  return { render, filter, populateDormFilter };
})();
