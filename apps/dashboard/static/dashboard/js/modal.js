/* ===================================================================
   MODAL — resident/room detail panels
   Premium open/close: backdrop fade + panel spring scale, ESC key,
   click-outside, and a drag-down-to-close gesture on touch devices.
=================================================================== */

const Modal = (() => {
  let touchStartY = null;

  function open(){
    const backdrop = document.getElementById('modal');
    document.body.style.overflow = 'hidden'; // scroll lock
    backdrop.classList.remove('hidden');
    // next frame so the transition actually runs
    requestAnimationFrame(() => backdrop.classList.add('show'));
  }

  function close(){
    const backdrop = document.getElementById('modal');
    backdrop.classList.remove('show');
    document.body.style.overflow = '';
    setTimeout(() => backdrop.classList.add('hidden'), 320);
  }

  function openResident(id){
    const r = DB.residents.find(x => x.id === id);
    const trans = DB.transactions.filter(t => t.resident.id === id).sort((a,b)=>new Date(b.payment_date)-new Date(a.payment_date));
    document.getElementById('modal-title').innerText = `${r.full_name} - ${r.national_code} | اتاق ${r.room.room_number}`;
    document.getElementById('modal-content').innerHTML = `
      <div class="grid md:grid-cols-3 gap-4 mb-6 stagger">
        <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">کد ملی</p><p class="font-bold">${r.national_code}</p></div>
        <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">موبایل / والدین</p><p class="font-bold text-sm">${r.phone_number} / ${r.parent_phone_number}</p></div>
        <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">وضعیت بدهی</p><p class="font-bold ${r.is_in_debt?'text-rose-500':'text-emerald-500'}">${r.is_in_debt ? 'بدهکار - تسویه تا '+r.settled_until : 'تسویه کامل'}</p></div>
      </div>
      <h4 class="font-bold mb-3">💳 تراکنش‌ها (${trans.length})</h4>
      <div class="space-y-2 max-h-[50vh] overflow-auto scroll-thin pr-1 stagger">
        ${trans.map(t => `
          <div class="glass rounded-2xl p-4 flex flex-col md:flex-row justify-between gap-3">
            <div>
              <p class="font-bold text-sm">${Utils.typeLabel(t.transaction_type)} - ${Utils.toToman(t.amount)}
                <span class="text-[11px] glass px-2 py-1 rounded-full mr-2">${Utils.methodLabel(t.payment_method)}</span>
                ${!t.is_approved ? '<span class="bg-amber-500 text-white text-[9px] px-2 py-1 rounded-full">نیاز تایید</span>' : ''}
              </p>
              <p class="text-[11px] text-muted mt-1">تاریخ: ${t.payment_date} | ${t.reference_number ? 'شماره مرجع: '+t.reference_number : 'بدون مرجع'} | اجاره زمان تراکنش: ${Utils.toToman(t.applicable_rent)}</p>
              <p class="text-[11px] text-faint">${t.description || 'بدون توضیح'}</p>
            </div>
            <div class="text-left"><p class="text-[10px] text-muted">خوابگاه: ${t.dormitory}</p><p class="text-[10px] ${t.is_approved?'text-emerald-500':'text-amber-500'}">${t.is_approved ? '✅ تایید شده' : '⏳ در انتظار تایید'}</p></div>
          </div>
        `).join('') || '<p class="text-center text-muted">تراکنشی ندارد</p>'}
      </div>
    `;
    open();
  }

  function openRoom(id){
    const room = DB.rooms.find(r => r.id === id);
    const occupants = DB.residents.filter(r => r.room.id === id);
    document.getElementById('modal-title').innerText = `اتاق ${room.room_number} - ${room.dormitory} - ظرفیت ${room.capacity}`;
    document.getElementById('modal-content').innerHTML = `
      <div class="grid md:grid-cols-4 gap-3 mb-6 stagger">
        <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">ظرفیت</p><p class="font-bold text-xl">${room.capacity}</p></div>
        <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">فعلی</p><p class="font-bold text-xl">${occupants.length}</p></div>
        <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">خالی</p><p class="font-bold text-xl">${room.capacity - occupants.length}</p></div>
        <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">اجاره ماهانه</p><p class="font-bold text-sm">${Utils.toToman(room.monthly_rent)}</p></div>
      </div>
      <h4 class="font-bold mb-3">ساکنین فعلی - کلیک روی اسم برای دیدن تراکنش‌ها</h4>
      <div class="grid md:grid-cols-2 gap-3 stagger">
        ${occupants.map(o => `
          <div onclick="Modal.openResident(${o.id})" class="glass rounded-2xl p-4 cursor-pointer hover:bg-white/5 transition flex justify-between">
            <div><p class="font-bold">${o.full_name}</p><p class="text-[11px] text-muted">${o.national_code} | ${o.phone_number}</p><p class="text-[10px] mt-1">${o.is_in_debt ? '🔴 بدهکار' : '🟢 تسویه'} | ورود: ${o.entry_date}</p></div>
            <span class="text-blue-400 text-[11px]">تراکنش‌ها →</span>
          </div>
        `).join('') || '<p class="text-muted">اتاق خالی است</p>'}
      </div>
    `;
    open();
  }

  function bindGlobalHandlers(){
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !document.getElementById('modal').classList.contains('hidden')) close();
    });

    const panel = document.getElementById('modal-panel');
    panel.addEventListener('touchstart', e => { touchStartY = e.touches[0].clientY; }, { passive:true });
    panel.addEventListener('touchmove', e => {
      if (touchStartY === null) return;
      const dy = e.touches[0].clientY - touchStartY;
      if (dy > 0) panel.style.transform = `translateY(${dy}px)`;
    }, { passive:true });
    panel.addEventListener('touchend', e => {
      const dy = (e.changedTouches[0].clientY - (touchStartY||0));
      panel.style.transform = '';
      if (dy > 120) close();
      touchStartY = null;
    });
  }

  return { open, close, openResident, openRoom, bindGlobalHandlers };
})();
