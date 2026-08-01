/* ===================================================================
   STUDENTS TAB
=================================================================== */

const Students = (() => {
  function render(list = DB.residents){
    const grid = document.getElementById('students-grid');
    grid.innerHTML = list.map((r,i) => `
      <div onclick="Modal.openResident(${r.id})" style="animation-delay:${Math.min(i,10)*30}ms"
           class="entity-card glass p-5 ${r.is_in_debt ? 'debt-card' : ''}">
        <div class="flex justify-between items-start">
          <div class="flex gap-3">
            <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-lg">${r.first_name[0]}</div>
            <div>
              <p class="font-bold text-[15px]">${r.full_name}</p>
              <p class="text-[11px] text-muted">${r.national_code} • ${r.phone_number}</p>
              <p class="text-[10px] mt-1 text-muted">🏠 ${r.dormitory} - اتاق ${r.room.room_number} | ${r.occupation}</p>
            </div>
          </div>
          <span class="status-pill ${r.is_in_debt ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-white'}">${r.is_in_debt ? 'بدهکار' : 'تسویه'}</span>
        </div>
        <div class="grid grid-cols-3 gap-2 mt-4 text-[11px]">
          <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">ورود</p><p>${r.entry_date}</p></div>
          <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">تسویه تا</p><p>${r.settled_until}</p></div>
          <div class="glass rounded-xl p-2"><p class="text-[9px] text-faint">این ماه</p><p>${r.has_paid_this_month ? '✅ پرداخت' : '❌ نپرداخته'}</p></div>
        </div>
        <div class="mt-3 flex gap-2 text-[10px]">
          <span class="glass px-2 py-1 rounded-full">اجاره: ${Utils.toToman(r.room.monthly_rent)}</span>
          <span class="glass px-2 py-1 rounded-full">روز پرداخت: ${r.monthly_payment_day}ام</span>
        </div>
      </div>
    `).join('') || `<div class="empty-state col-span-full">😶 هیچ دانشجویی با این فیلترها پیدا نشد</div>`;

    const activeEl = document.getElementById('kpi-active');
    const debtEl = document.getElementById('kpi-debt');
    Utils.animateCounter(activeEl, DB.residents.filter(r=>r.status==='ACTIVE').length);
    Utils.animateCounter(debtEl, DB.residents.filter(r=>r.is_in_debt).length);
  }

  function filter(){
    const q = document.getElementById('search-student').value.toLowerCase();
    const dorm = document.getElementById('filter-dorm').value;
    const status = document.getElementById('filter-status').value;
    const occ = document.getElementById('filter-occupation').value;
    const filtered = DB.residents.filter(r => {
      const matchQ = !q || r.full_name.toLowerCase().includes(q) || r.national_code.includes(q) || r.phone_number.includes(q) || (""+r.room.room_number).includes(q);
      const matchDorm = !dorm || r.dormitory===dorm;
      const matchOcc = !occ || r.occupation===occ;
      let matchStat = true;
      if (status==="debt") matchStat = r.is_in_debt;
      if (status==="paid") matchStat = !r.is_in_debt;
      if (status==="ACTIVE") matchStat = r.status==="ACTIVE";
      return matchQ && matchDorm && matchOcc && matchStat;
    });
    render(filtered);
  }

  return { render, filter };
})();
