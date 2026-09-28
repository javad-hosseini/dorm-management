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
        <div onclick="Student.openRoommate(${r.id})"
             class="entity-card p-5 cursor-pointer ${r.me ? 'border-2 border-blue-400/50' : ''}">
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
        <div class="list-row surface-subtle flex justify-between items-center p-3 rounded-xl mb-2">
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
      fList.innerHTML = t.map(x => {
        const hasDiscount = Boolean(x.has_discount || (x.discount_in_tomans && x.discount_in_tomans > 0));
        const discountTomans = x.discount_in_tomans || (x.discount_amount ? x.discount_amount / 10 : 0);
        return `
        <div class="list-row surface-subtle flex flex-col md:flex-row justify-between gap-3 p-3 rounded-xl mb-2 ${hasDiscount ? 'border border-amber-500/30' : ''}">
          <div class="flex-1">
            <div class="flex flex-wrap items-center gap-1.5">
              <p class="font-bold text-sm">${Utils.typeLabel(x.type)} - ${x.toman}</p>
              <span class="text-[10px] chip px-2 py-1 rounded-full mr-2">${Utils.methodLabel(x.method)}</span>
              ${hasDiscount ? `
                <span class="bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[9px] font-bold px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                  <span>🏷️</span>
                  <span>${Utils.toToman(discountTomans * 10)} کسر/تخفیف</span>
                </span>
              ` : ''}
            </div>
            <p class="text-[11px] text-muted mt-1">
              تاریخ: ${x.date} | مرجع: ${x.ref || 'ندارد'} | ${x.desc || 'بدون توضیح'}
              ${x.period_name ? ` | دوره: ${x.period_name}` : ''}
            </p>
            ${hasDiscount ? `
              <div class="mt-2 p-2 rounded-lg bg-amber-500/10 text-amber-300 text-[11px] flex flex-wrap items-center justify-between gap-2 border border-amber-500/20">
                <span>🏷️ <strong>علت کسورات / تخفیف:</strong> ${x.discount_reason || 'کسر مصوب مدیریت'} (${Utils.toToman(discountTomans * 10)})</span>
                <span class="text-slate-300">پوشش کل: <strong class="text-emerald-400">${Utils.toToman((x.total_effective_amount_toman || 0) * 10)}</strong></span>
              </div>
            ` : ''}
          </div>
          <span class="text-[10px] self-start md:self-center shrink-0 ${x.is_approved ? 'text-emerald-400' : 'text-amber-400'}">
            ${x.is_approved ? '✅ تایید شده' : '⏳ در انتظار تایید'}
          </span>
        </div>
      `;
      }).join('') || '<p class="text-muted text-center py-6">هنوز تراکنشی ثبت نشده است.</p>';
    }
  }

  function renderMaintenance() {
    const listEl = document.getElementById('maintenance-list');
    if (!listEl) return;
    const list = StudentDB.maintenance || [];
    listEl.innerHTML = list.map(m => `
      <div class="list-row surface-subtle flex justify-between items-center p-3 rounded-xl mb-2">
        <div><p class="font-bold text-sm">${m.title}</p><p class="text-[11px] text-muted">${m.date} - اتاق ${m.room}</p></div>
        <span class="status-pill chip text-xs">${m.status}</span>
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
        <div class="mt-6 space-y-3">
          <div class="surface-subtle rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">نام کامل</span><b class="text-sm">${r.full_name}</b></div>
          <div class="surface-subtle rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">شماره تلفن</span><b class="text-sm">${r.phone || '-'}</b></div>
          <div class="surface-subtle rounded-2xl p-4 flex justify-between"><span class="text-[11px] text-muted">تاریخ ورود</span><b class="text-sm">${r.entry || '-'}</b></div>
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

  function updateStudentUI() {
    const me = StudentDB.me;
    if (!me) return;

    const initial = (me.first_name || me.full_name || 'د')[0];
    const roomNum = me.room ? me.room.room_number : '-';
    const dormName = me.room ? me.room.dormitory : '-';
    const rentToman = me.room && me.room.monthly_rent ? Utils.toToman(me.room.monthly_rent) : 'نامشخص';
    const settledUntil = me.settled_until_display || me.settled_until || 'ثبت نشده';
    const dueDate = me.next_due_date_display || me.settled_until || '-';
    const dueStatus = me.due_status_display || (me.is_in_debt ? 'بدهکار' : 'تسویه به روز');
    const pp = me.period_payment || {};
    const isPartial = Boolean(me.is_partial_payment || pp.is_partial);
    const isInDebt = Boolean(me.is_in_debt) && !isPartial;
    const overdueDays = me.overdue_days || 0;
    const daysUntilDue = me.days_until_due || 0;
    const isWarning = isInDebt && overdueDays <= 7;
    const isCritical = isInDebt && overdueDays > 7;

    // Sidebar & Profile Header
    const avatarEl = document.getElementById('student-avatar');
    if (avatarEl) avatarEl.innerText = initial;

    const nameEl = document.getElementById('student-name');
    if (nameEl) nameEl.innerText = me.full_name || 'بدون نام';

    const dashNameEl = document.getElementById('dash-name');
    if (dashNameEl) dashNameEl.innerText = me.first_name || me.full_name || 'دانشجو';

    const codeEl = document.getElementById('student-code');
    if (codeEl) codeEl.innerText = `کد ملی: ${me.national_code || 'ثبت‌نشده'}`;

    const roomDormEl = document.getElementById('student-room-dorm');
    if (roomDormEl) roomDormEl.innerText = `اتاق ${roomNum} - ${dormName}`;

    const debtBadgeEl = document.getElementById('debt-badge');
    if (debtBadgeEl) {
      if (isPartial) {
        debtBadgeEl.innerText = `🟡 پرداخت مرحله‌ای (${toToman((pp.remaining_tomans || 0) * 10)} مانده)`;
        debtBadgeEl.className = 'text-[10px] bg-amber-500 text-slate-900 px-3 py-1 rounded-full font-bold shadow-sm';
      } else if (isCritical) {
        debtBadgeEl.innerText = `🔴 ${overdueDays} روز تاخیر (بدهکار)`;
        debtBadgeEl.className = 'text-[10px] bg-rose-500 text-white px-3 py-1 rounded-full font-bold shadow-sm';
      } else if (isWarning) {
        debtBadgeEl.innerText = overdueDays === 0 ? '🟡 سررسید امروز (مهلت پرداخت)' : `🟡 ${overdueDays} روز تاخیر (هشدار مهلت)`;
        debtBadgeEl.className = 'text-[10px] bg-amber-500 text-slate-900 px-3 py-1 rounded-full font-bold shadow-sm';
      } else {
        debtBadgeEl.innerText = '🟢 تسویه به روز';
        debtBadgeEl.className = 'text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-3 py-1 rounded-full font-bold';
      }
    }

    // Quick Finance widget (sidebar)
    const qSettled = document.getElementById('quick-settled');
    if (qSettled) qSettled.innerText = me.settled_until || 'فاقد پرداخت';

    const qDue = document.getElementById('quick-due');
    if (qDue) {
      qDue.innerText = dueDate;
      qDue.className = `font-bold ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400')}`;
    }

    const qDueStatus = document.getElementById('quick-due-status');
    if (qDueStatus) {
      if (isPartial) {
        qDueStatus.innerText = `🟡 ${toToman((pp.remaining_tomans || 0) * 10)} مانده`;
        qDueStatus.className = 'text-amber-300 font-bold';
      } else if (isCritical) {
        qDueStatus.innerText = `🔴 ${overdueDays} روز تاخیر`;
        qDueStatus.className = 'text-rose-400 font-bold';
      } else if (isWarning) {
        qDueStatus.innerText = overdueDays === 0 ? '🟡 سررسید امروز' : `🟡 ${overdueDays} روز تاخیر`;
        qDueStatus.className = 'text-amber-400 font-bold';
      } else {
        qDueStatus.innerText = daysUntilDue === 0 ? '🟢 سررسید امروز' : `🟢 ${daysUntilDue} روز مانده`;
        qDueStatus.className = 'text-emerald-400 font-bold';
      }
    }

    const qRent = document.getElementById('quick-rent');
    if (qRent) qRent.innerText = rentToman;

    // Dashboard Banner
    const dueBanner = document.getElementById('dash-due-banner');
    const dueIcon = document.getElementById('dash-due-icon');
    const dueTitle = document.getElementById('dash-due-title');
    const dueDesc = document.getElementById('dash-due-desc');

    if (dueTitle) {
      if (isPartial) {
        dueTitle.innerText = `🟡 پرداخت مرحله اول انجام شده (مانده این دوره: ${toToman((pp.remaining_tomans || 0) * 10)})`;
        dueTitle.className = 'font-bold text-sm md:text-base text-amber-300 mt-0.5';
      } else if (isCritical) {
        dueTitle.innerText = `🔴 دارای ${overdueDays} روز تاخیر در پرداخت اجاره (بیش از یک هفته)`;
        dueTitle.className = 'font-bold text-sm md:text-base text-rose-400 mt-0.5';
      } else if (isWarning) {
        dueTitle.innerText = overdueDays === 0
          ? '⚠️ سررسید موعد پرداخت اجاره فرا رسیده است (امروز)'
          : `⚠️ هشدار مهلت پرداخت: دارای ${overdueDays} روز تاخیر (کمتر از یک هفته)`;
        dueTitle.className = 'font-bold text-sm md:text-base text-amber-400 mt-0.5';
      } else {
        dueTitle.innerText = daysUntilDue === 0 ? '🟡 موعد پرداخت اجاره امروز است' : `🟢 وضعیت حساب تسویه است (${daysUntilDue} روز تا سررسید بعدی)`;
        dueTitle.className = 'font-bold text-sm md:text-base text-emerald-400 mt-0.5';
      }
    }

    if (dueDesc) {
      if (isPartial) {
        dueDesc.innerText = `دوره: ${pp.period_name || 'جاری'} • پرداخت‌شده: ${toToman((pp.paid_tomans || 0) * 10)} • مانده بدهی: ${toToman((pp.remaining_tomans || 0) * 10)} (پوشش علی‌الحساب تا: ${settledUntil})`;
      } else {
        dueDesc.innerText = `تسویه تا تاریخ: ${settledUntil} • تاریخ سررسید موعد بعدی: ${dueDate} • روز پرداخت: ${me.monthly_payment_day || 1}ام هر ماه`;
      }
    }

    if (dueBanner) {
      if (isPartial) {
        dueBanner.className = 'mt-4 p-4 rounded-2xl glass border border-amber-500/35 bg-amber-500/10 flex flex-col md:flex-row justify-between items-start md:items-center gap-3';
      } else if (isCritical) {
        dueBanner.className = 'mt-4 p-4 rounded-2xl glass border border-rose-500/30 bg-rose-500/10 flex flex-col md:flex-row justify-between items-start md:items-center gap-3';
      } else if (isWarning) {
        dueBanner.className = 'mt-4 p-4 rounded-2xl glass border border-amber-500/30 bg-amber-500/10 flex flex-col md:flex-row justify-between items-start md:items-center gap-3';
      } else {
        dueBanner.className = 'mt-4 p-4 rounded-2xl glass border border-emerald-500/30 bg-emerald-500/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-3';
      }
    }

    if (dueIcon) {
      if (isPartial) {
        dueIcon.innerHTML = '💳';
        dueIcon.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-amber-500/20 text-amber-400';
      } else if (isCritical) {
        dueIcon.innerHTML = '🚨';
        dueIcon.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-rose-500/20 text-rose-400';
      } else if (isWarning) {
        dueIcon.innerHTML = '⚠️';
        dueIcon.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-amber-500/20 text-amber-400';
      } else {
        dueIcon.innerHTML = '🗓️';
        dueIcon.className = 'w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-emerald-500/20 text-emerald-400';
      }
    }

    // Dashboard Stat Tiles
    const dashRoomNum = document.getElementById('dash-room-num');
    if (dashRoomNum) dashRoomNum.innerText = roomNum;

    const dashDormCap = document.getElementById('dash-dorm-capacity');
    if (dashDormCap) dashDormCap.innerText = `${dormName} - ظرفیت ${me.room?.capacity || 0}`;

    const dashPaymentTile = document.getElementById('dash-payment-tile');
    if (dashPaymentTile) {
      dashPaymentTile.className = `stat-tile glass border ${isCritical ? 'border-rose-500/30' : (isWarning ? 'border-amber-500/30' : 'border-emerald-500/25')}`;
    }

    const dashDueTile = document.getElementById('dash-due-tile');
    if (dashDueTile) {
      dashDueTile.className = `stat-tile glass border ${isCritical ? 'border-rose-500/30' : (isWarning ? 'border-amber-500/30' : 'border-amber-500/25')}`;
    }

    const dashPayStatus = document.getElementById('dash-pay-status');
    if (dashPayStatus) {
      dashPayStatus.innerText = me.settled_until || 'تسویه نشده';
      dashPayStatus.className = `font-bold text-lg ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-blue-400')}`;
    }

    const dashSettledInfo = document.getElementById('dash-settled-info');
    if (dashSettledInfo) {
      dashSettledInfo.innerText = isCritical
        ? `بدهکار (${me.unpaid_months || 'معوقه بیش از ۱ هفته'})`
        : (isWarning ? `مهلت پرداخت (${me.unpaid_months || 'تا ۱ هفته'})` : 'پوشش کامل تا تاریخ فوق');
    }

    const dashDueDate = document.getElementById('dash-due-date');
    if (dashDueDate) {
      dashDueDate.innerText = dueDate;
      dashDueDate.className = `font-bold text-lg ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400')}`;
    }

    const dashDueCountdown = document.getElementById('dash-due-countdown');
    if (dashDueCountdown) {
      if (isCritical) {
        dashDueCountdown.innerText = `🔴 ${overdueDays} روز گذشته از موعد (بیش از یک هفته)`;
      } else if (isWarning) {
        dashDueCountdown.innerText = overdueDays === 0 ? '🟡 امروز روز سررسید است' : `🟡 ${overdueDays} روز گذشته از موعد (مهلت یک هفته)`;
      } else {
        dashDueCountdown.innerText = `🟢 ${daysUntilDue} روز مانده به سررسید`;
      }
    }

    const dashContractStatus = document.getElementById('dash-contract-status');
    if (dashContractStatus) {
      dashContractStatus.innerText = me.has_lease ? 'قرارداد رسمی' : 'فاقد اجاره‌نامه';
      dashContractStatus.className = `font-bold text-base ${me.has_lease ? 'text-emerald-400' : 'text-amber-400'}`;
    }

    const dashContractLease = document.getElementById('dash-contract-lease');
    if (dashContractLease) {
      dashContractLease.innerText = `ودیعه: ${me.has_deposit ? '✅ پرداخت شده' : '❌ فاقد ودیعه'}`;
    }

    // Profile Tab elements
    const profName = document.getElementById('prof-name');
    if (profName) profName.innerText = me.full_name || '-';

    const profNat = document.getElementById('prof-natcode');
    if (profNat) profNat.innerText = me.national_code || 'ثبت‌نشده';

    const profPhone = document.getElementById('prof-phone');
    if (profPhone) profPhone.innerText = me.phone_number || '-';

    const profParent = document.getElementById('prof-parent-phone');
    if (profParent) profParent.innerText = me.parent_phone_number || 'ثبت‌نشده';

    const profOcc = document.getElementById('prof-occupation');
    if (profOcc) profOcc.innerText = { STUDENT: 'دانشجو', EMPLOYED: 'شاغل', OTHER: 'سایر' }[me.occupation] || me.occupation || 'دانشجو';

    const profEntry = document.getElementById('prof-entry');
    if (profEntry) profEntry.innerText = me.entry_date || '-';

    const profPayDay = document.getElementById('prof-pay-day');
    if (profPayDay) profPayDay.innerText = `${me.monthly_payment_day || 1}ام هر ماه`;

    const profSettled = document.getElementById('prof-settled');
    if (profSettled) profSettled.innerText = settledUntil;

    const profDueDate = document.getElementById('prof-due-date');
    if (profDueDate) {
      profDueDate.innerText = dueDate;
      profDueDate.className = `font-bold mt-1 ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400')}`;
    }

    const profDueStatus = document.getElementById('prof-due-status');
    if (profDueStatus) {
      profDueStatus.innerText = dueStatus;
      profDueStatus.className = `font-bold mt-1 ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400')}`;
    }

    // Pay Tab elements
    const payRoomDesc = document.getElementById('pay-room-desc');
    if (payRoomDesc) payRoomDesc.innerText = `اتاق ${roomNum} - ${dormName}`;

    const paySettled = document.getElementById('pay-settled-until');
    if (paySettled) paySettled.innerText = settledUntil;

    const payDue = document.getElementById('pay-due-date');
    if (payDue) {
      payDue.innerText = dueDate;
      payDue.className = `font-bold ${isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400')}`;
    }

    const payDueStatus = document.getElementById('pay-due-status');
    if (payDueStatus) {
      payDueStatus.innerText = dueStatus;
      payDueStatus.className = isCritical ? 'text-rose-400 font-bold' : (isWarning ? 'text-amber-400 font-bold' : 'text-emerald-400 font-bold');
    }

    const payAmount = document.getElementById('pay-amount-toman');
    if (payAmount) {
      if (isPartial) {
        payAmount.innerText = `${toToman((pp.remaining_tomans || 0) * 10)} (مانده جهت تسویه دوره)`;
      } else {
        payAmount.innerText = rentToman;
      }
    }

    // Contract Tab elements
    const cNum = document.getElementById('contract-number');
    if (cNum) cNum.innerText = me.contract?.number || `#RES${me.id}`;

    const cStart = document.getElementById('contract-start');
    if (cStart) cStart.innerText = me.contract?.start || me.entry_date || '-';

    const cEnd = document.getElementById('contract-end');
    if (cEnd) cEnd.innerText = me.contract?.end || 'تمدید خودکار سالانه';

    const cLease = document.getElementById('contract-lease');
    if (cLease) {
      cLease.innerText = me.has_lease ? '✅ منعقد شده و معتبر' : '⚠️ فاقد اجاره‌نامه رسمی (کسری مدرک)';
      cLease.className = me.has_lease ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold';
    }

    const cDeposit = document.getElementById('contract-deposit');
    if (cDeposit) {
      cDeposit.innerText = me.has_deposit ? '✅ دریافت و ثبت شده' : '❌ پرداخت نشده';
      cDeposit.className = me.has_deposit ? 'text-emerald-400 font-bold' : 'text-slate-400 font-bold';
    }

    const cSettled = document.getElementById('contract-settled');
    if (cSettled) cSettled.innerText = settledUntil;

    const cDue = document.getElementById('contract-due');
    if (cDue) cDue.innerText = dueDate;

    const cRoom = document.getElementById('contract-room');
    if (cRoom) cRoom.innerText = `${dormName} - اتاق ${roomNum}`;

    document.querySelectorAll('.student-name').forEach(el => el.innerText = me.full_name);
    document.querySelectorAll('.student-room').forEach(el => el.innerText = `اتاق ${roomNum}`);
    document.querySelectorAll('.student-national').forEach(el => el.innerText = `کد ملی: ${me.national_code}`);
  }

  async function boot() {
    Theme.init();
    Particles.init();
    Modal.bindGlobalHandlers();
    ScrollChrome.bind();

    await StudentDB.init();

    updateStudentUI();
    renderDashboard();
    window.lucide && lucide.createIcons();

    window.switchMenu = switchMenu;
    window.openPayModal = openPayModal;
    window.openNewRequest = openNewRequest;
    window.submitNewRequest = submitNewRequest;
    window.closeModal = Modal.close;
  }

  return { boot, switchMenu, openRoommate, openPayModal, openNewRequest, updateStudentUI };
})();

document.addEventListener('DOMContentLoaded', Student.boot);
