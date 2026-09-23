/* ===================================================================
   STUDENT PORTAL — page logic with real backend data
=================================================================== */

const Student = (() => {
  const MENUS = ['dashboard', 'profile', 'room', 'finance', 'pay', 'contract', 'maintenance'];

  function switchMenu(menu) {
    MENUS.forEach(m => {
      const sec = document.getElementById('sec-' + m);
      if (sec) sec.classList.add('hidden');
      const link = document.getElementById('m-' + m);
      if (link) link.classList.remove('active');
    });

    const sec = document.getElementById('sec-' + menu);
    if (sec) {
      sec.classList.remove('hidden');
      sec.classList.add('tab-section');
    }
    const link = document.getElementById('m-' + menu);
    if (link) link.classList.add('active');

    if (menu === 'room') renderRoommates();
    if (menu === 'finance') renderFinance();
    if (menu === 'dashboard') renderDashboard();
    if (menu === 'maintenance') renderMaintenance();
    window.lucide && lucide.createIcons();
  }

  function renderRoommates() {
    const grid = document.getElementById('roommates-grid');
    if (!grid) return;
    const list = StudentDB.roommates || [];

    grid.innerHTML = list.map((r, i) => {
      const initial = (r.first_name || r.full_name || 'س')[0];
      return `
        <div onclick="Student.openRoommate(${r.id})" style="animation-delay:${i * 40}ms"
             class="entity-card glass p-5 cursor-pointer ${r.me ? 'border-2 border-blue-400/50' : ''}">
          <div class="flex items-center gap-3">
            <div class="avatar-sm">${initial}</div>
            <div>
              <p class="font-bold text-sm">${r.full_name || 'بدون نام'}</p>
              <p class="text-[11px] text-muted">${r.me ? 'شما' : 'برای مشاهده اطلاعات کلیک کنید'}</p>
            </div>
          </div>
          <p class="text-[11px] mt-3 text-muted">تاریخ ورود: ${r.entry || '-'}</p>
          ${!r.me ? '<span class="text-[10px] text-blue-400 mt-2 inline-block">نمایش اطلاعات ←</span>' : ''}
        </div>
      `;
    }).join('') || '<p class="text-muted col-span-full py-4 text-center">هم‌اتاقی دیگری ثبت نشده است.</p>';
  }

  function renderDashboard() {
    const listEl = document.getElementById('dash-roommates');
    if (listEl) {
      const otherRoommates = (StudentDB.roommates || []).filter(r => !r.me);
      listEl.innerHTML = otherRoommates.map(r => `
        <div class="list-row glass flex justify-between items-center p-3 rounded-xl mb-2">
          <div><p class="font-bold text-[12px]">${r.full_name}</p><p class="text-[10px] text-muted">ورود: ${r.entry || '-'}</p></div>
          <button onclick="Student.openRoommate(${r.id})" class="btn btn-ghost text-[10px] px-3 py-1.5 rounded-full">شماره</button>
        </div>
      `).join('') || '<p class="text-xs text-muted py-2">هم‌اتاقی دیگری در این اتاق نیست.</p>';
    }

    if (StudentDB.monthlyHistory && StudentDB.monthlyHistory.labels && StudentDB.monthlyHistory.labels.length) {
      Charts.renderSimpleBar('payHistoryChart', StudentDB.monthlyHistory.labels, StudentDB.monthlyHistory.values, '#4A90E2');
    }
  }

  function renderFinance() {
    const t = StudentDB.transactions || [];
    const total = t.reduce((s, x) => s + (x.amount || 0), 0);
    const fTotal = document.getElementById('f-total');
    const fCount = document.getElementById('f-rent-count');
    const fList = document.getElementById('finance-list');

    if (fTotal) fTotal.innerText = Utils.toToman(total);
    if (fCount) fCount.innerText = t.filter(x => x.type === 'RENT').length;
    if (fList) {
      fList.innerHTML = t.map(x => `
        <div class="list-row glass flex flex-col md:flex-row justify-between gap-3 p-3 rounded-xl mb-2 animate-fadeInUp">
          <div>
            <p class="font-bold text-sm">${Utils.typeLabel(x.type)} - ${x.toman}
              <span class="text-[10px] glass px-2 py-1 rounded-full mr-2">${Utils.methodLabel(x.method)}</span>
            </p>
            <p class="text-[11px] text-muted mt-1">تاریخ: ${x.date} | مرجع: ${x.ref || 'ندارد'} | ${x.desc || 'بدون توضیح'}</p>
          </div>
          <span class="text-[10px] self-start md:self-center ${x.is_approved ? 'text-emerald-400' : 'text-amber-400'}">
            ${x.is_approved ? '✅ تایید شده' : '⏳ در انتظار تایید'}
          </span>
        </div>
      `).join('') || '<p class="text-muted text-center py-6">هنوز تراکنشی ثبت نشده است.</p>';
    }
  }

  function renderMaintenance() {
    const listEl = document.getElementById('maintenance-list');
    if (!listEl) return;
    const list = StudentDB.maintenance || [];
    listEl.innerHTML = list.map(m => `
      <div class="list-row glass flex justify-between items-center p-3 rounded-xl mb-2 animate-fadeInUp">
        <div><p class="font-bold text-sm">${m.title}</p><p class="text-[11px] text-muted">${m.date} - اتاق ${m.room}</p></div>
        <span class="status-pill glass text-xs">${m.status}</span>
      </div>
    `).join('') || '<p class="text-muted text-center py-6">درخواست تعمیراتی ثبت نشده است.</p>';
  }

  function openRoommate(id) {
    const r = (StudentDB.roommates || []).find(x => x.id === id);
    if (!r || r.me) return;

    const titleEl = document.getElementById('modal-title');
    const contentEl = document.getElementById('modal-content');
    const initial = (r.first_name || r.full_name || 'س')[0];
    const roomNum = StudentDB.me?.room?.room_number || '-';

    if (titleEl) titleEl.innerText = r.full_name;
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="text-center">
          <div class="avatar-lg mx-auto">${initial}</div>
          <p class="font-bold mt-3">${r.full_name}</p>
          <p class="text-[11px] text-muted">هم‌اتاقی در اتاق ${roomNum}</p>
        </div>
        <div class="mt-6 space-y-3 stagger">
          <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">نام کامل</span><b class="text-sm">${r.full_name}</b></div>
          <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">شماره تلفن</span><b class="text-sm">${r.phone || '-'}</b></div>
          <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">تاریخ ورود</span><b class="text-sm">${r.entry || '-'}</b></div>
          <div class="glass rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">کد ملی</span><b class="text-sm">${r.national || '-'}</b></div>
        </div>
      `;
    }
    Modal.open();
  }

  function openPayModal() {
    const titleEl = document.getElementById('modal-title');
    const contentEl = document.getElementById('modal-content');
    if (titleEl) titleEl.innerText = "پرداخت آنلاین اجاره";
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="text-center py-4">
          <p class="text-sm mb-4">مبلغ قابل پرداخت اجاره این ماه:</p>
          <p class="text-2xl font-bold text-emerald-400 mb-6">${Utils.toToman(StudentDB.me.room.monthly_rent || 0)}</p>
          <button onclick="Toast.show('اتصال به درگاه در نسخه بعدی فعال خواهد شد', 'info'); Modal.close();" class="btn btn-primary px-8 py-3 rounded-2xl font-bold text-sm w-full">انتقال به درگاه بانکی</button>
        </div>
      `;
    }
    Modal.open();
  }

  function openNewRequest() {
    const titleEl = document.getElementById('modal-title');
    const contentEl = document.getElementById('modal-content');
    if (titleEl) titleEl.innerText = "ثبت درخواست تعمیرات";
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="space-y-4">
          <div class="field"><label>عنوان مشکل</label><input id="req-title" placeholder="مثال: نشتی شیر آب، سوختن لامپ..."></div>
          <div class="field"><label>توضیحات تکمیلی</label><textarea id="req-desc" rows="3" class="w-full rounded-xl p-3 glass text-sm" placeholder="توضیح کوتاه..."></textarea></div>
          <button onclick="submitNewRequest()" class="btn btn-primary px-6 py-2.5 rounded-xl font-bold text-sm w-full">ارسال درخواست</button>
        </div>
      `;
    }
    Modal.open();
  }

  function submitNewRequest() {
    const title = document.getElementById('req-title')?.value;
    if (!title) { Toast.show('لطفاً عنوان مشکل را وارد کنید', 'warning'); return; }
    StudentDB.maintenance.unshift({
      id: Date.now(),
      title,
      date: 'امروز',
      room: StudentDB.me?.room?.room_number || '-',
      status: 'در حال بررسی'
    });
    Modal.close();
    renderMaintenance();
    Toast.show('درخواست با موفقیت ثبت شد', 'success');
  }

  async function boot() {
    Theme.init();
    Particles.init();
    Modal.bindGlobalHandlers();
    ScrollChrome.bind();

    await StudentDB.init();

    // Update profile topbar and details with real data
    const me = StudentDB.me;
    document.querySelectorAll('.student-name').forEach(el => el.innerText = me.full_name);
    document.querySelectorAll('.student-room').forEach(el => el.innerText = `اتاق ${me.room.room_number}`);
    document.querySelectorAll('.student-national').forEach(el => el.innerText = `کد ملی: ${me.national_code}`);

    renderDashboard();
    window.lucide && lucide.createIcons();

    window.switchMenu = switchMenu;
    window.openPayModal = openPayModal;
    window.openNewRequest = openNewRequest;
    window.submitNewRequest = submitNewRequest;
    window.closeModal = Modal.close;
  }

  return { boot, switchMenu, openRoommate, openPayModal, openNewRequest };
})();

document.addEventListener('DOMContentLoaded', Student.boot);
