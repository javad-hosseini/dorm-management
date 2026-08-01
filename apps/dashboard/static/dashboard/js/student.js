/* ===================================================================
   STUDENT PORTAL — page logic
   Reuses Modal.open()/Modal.close() from modal.js (the generic panel
   machinery), Toast, Charts and Utils from the admin dashboard as-is.
=================================================================== */

const Student = (() => {
  const MENUS = ['dashboard','profile','room','finance','pay','contract','maintenance'];

  function switchMenu(menu){
    MENUS.forEach(m => {
      document.getElementById('sec-'+m).classList.add('hidden');
      document.getElementById('m-'+m).classList.remove('active');
    });
    const sec = document.getElementById('sec-'+menu);
    sec.classList.remove('hidden');
    sec.classList.add('tab-section');
    document.getElementById('m-'+menu).classList.add('active');

    if (menu === 'room') renderRoommates();
    if (menu === 'finance') renderFinance();
    if (menu === 'dashboard') renderDashboard();
    if (menu === 'maintenance') renderMaintenance();
    window.lucide && lucide.createIcons();
  }

  function renderRoommates(){
    document.getElementById('roommates-grid').innerHTML = StudentDB.roommates.map((r,i) => `
      <div onclick="Student.openRoommate(${r.id})" style="animation-delay:${i*40}ms"
           class="entity-card glass p-5 ${r.me ? 'border-2 border-blue-400/50' : ''}">
        <div class="flex items-center gap-3">
          <div class="avatar-sm">${r.first_name[0]}</div>
          <div><p class="font-bold text-sm">${r.full_name}</p><p class="text-[11px] text-muted">${r.me ? 'شما' : 'برای مشاهده اطلاعات کلیک کنید'}</p></div>
        </div>
        <p class="text-[11px] mt-3 text-muted">تاریخ ورود: ${r.entry}</p>
        ${!r.me ? '<span class="text-[10px] text-blue-400 mt-2 inline-block">نمایش اطلاعات ←</span>' : ''}
      </div>
    `).join('');
  }

  function renderDashboard(){
    document.getElementById('dash-roommates').innerHTML = StudentDB.roommates.filter(r=>!r.me).map(r => `
      <div class="list-row glass flex justify-between items-center">
        <div><p class="font-bold text-[12px]">${r.full_name}</p><p class="text-[10px] text-muted">${r.entry}</p></div>
        <button onclick="Student.openRoommate(${r.id})" class="btn btn-ghost text-[10px] px-3 py-1.5 rounded-full">شماره</button>
      </div>
    `).join('');
    Charts.renderSimpleBar('payHistoryChart', StudentDB.monthlyHistory.labels, StudentDB.monthlyHistory.values, '#4A90E2');
  }

  function renderFinance(){
    const t = StudentDB.transactions;
    const total = t.reduce((s,x)=>s+x.amount,0);
    document.getElementById('f-total').innerText = Utils.toToman(total);
    document.getElementById('f-rent-count').innerText = t.filter(x=>x.type==='RENT').length;
    document.getElementById('finance-list').innerHTML = t.map(x => `
      <div class="list-row glass flex flex-col md:flex-row justify-between gap-3 animate-fadeInUp">
        <div>
          <p class="font-bold text-sm">${Utils.typeLabel(x.type)} - ${x.toman}
            <span class="text-[10px] glass px-2 py-1 rounded-full mr-2">${Utils.methodLabel(x.method)}</span>
          </p>
          <p class="text-[11px] text-muted mt-1">تاریخ: ${x.date} | مرجع: ${x.ref || 'ندارد'} | ${x.desc}</p>
        </div>
      </div>
    `).join('');
  }

  function renderMaintenance(){
    document.getElementById('maintenance-list').innerHTML = StudentDB.maintenance.map(m => `
      <div class="list-row glass flex justify-between items-center animate-fadeInUp">
        <div><p class="font-bold text-sm">${m.title}</p><p class="text-[11px] text-muted">${m.date} - اتاق ${m.room}</p></div>
        <span class="status-pill glass">${m.status}</span>
      </div>
    `).join('');
  }

  function openRoommate(id){
    const r = StudentDB.roommates.find(x => x.id === id);
    if (r.me) return;
    document.getElementById('modal-title').innerText = r.full_name;
    document.getElementById('modal-content').innerHTML = `
      <div class="text-center">
        <div class="avatar-lg">${r.first_name[0]}</div>
        <p class="font-bold mt-3">${r.full_name}</p>
        <p class="text-[11px] text-muted">هم‌اتاقی اتاق ${StudentDB.me.room.room_number}</p>
      </div>
      <div class="mt-6 space-y-3 stagger">
        <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">نام کامل</span><b class="text-sm">${r.full_name}</b></div>
        <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">شماره تلفن</span><b class="text-sm">${r.phone}</b></div>
        <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">تاریخ ورود</span><b class="text-sm">${r.entry}</b></div>
        <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">کد ملی</span><b class="text-sm">${r.national}</b></div>
      </div>
    `;
    Modal.open();
  }

  function openPayModal(){
    document.getElementById('modal-title').innerText = "پرداخت آنلاین";
    document.getElementById('modal-content').innerHTML = `
      <p class="text-sm">در حال انتقال به درگاه پرداخت...</p>
      <p class="text-[11px] mt-3 text-muted">مبلغ: ${Utils.toToman(StudentDB.me.room.monthly_rent)}</p>
      <div class="mt-6 glass rounded-2xl p-4 text-[11px] border border-emerald-500/25">پس از تایید درگاه، رسید پرداخت به‌صورت خودکار در تاریخچه مالی شما ثبت می‌شود.</div>
      <button class="btn btn-primary w-full py-3 rounded-xl mt-5" onclick="Toast.show('این بخش هنوز به درگاه واقعی وصل نشده','info')">رفتن به درگاه (نمونه)</button>
    `;
    Modal.open();
  }

  function openNewRequest(){
    document.getElementById('modal-title').innerText = "ثبت درخواست جدید";
    document.getElementById('modal-content').innerHTML = `
      <div class="field mb-3"><input placeholder="عنوان خرابی..."></div>
      <div class="field"><textarea placeholder="توضیحات..." class="w-full" style="background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:1rem;padding:.85rem 1rem;color:var(--text-0);height:6rem"></textarea></div>
      <button class="btn btn-primary w-full py-3 rounded-xl mt-4" onclick="Toast.show('درخواست شما ثبت شد','success'); Modal.close();">ثبت درخواست</button>
    `;
    Modal.open();
  }

  return { switchMenu, openRoommate, openPayModal, openNewRequest };
})();

document.addEventListener('DOMContentLoaded', () => {
  Theme.init();
  Particles.init();
  Modal.bindGlobalHandlers();
  MobileNav.bind();
  ScrollChrome.bind();
  Student.switchMenu('dashboard');
  window.lucide && lucide.createIcons();
  Toast.show('خوش آمدید', 'success');

  window.switchMenu = Student.switchMenu;
  window.openRoommate = Student.openRoommate;
  window.openPayModal = Student.openPayModal;
  window.openNewRequest = Student.openNewRequest;
  window.closeModal = Modal.close;
});
