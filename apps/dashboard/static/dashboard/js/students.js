/* ===================================================================
   STUDENTS TAB — Robust real-world data rendering, export & copy
=================================================================== */

const Students = (() => {
  let currentFiltered = [];
  let exportSelectedIds = new Set();

  function occLabel(o) {
    return { STUDENT: 'دانشجو', EMPLOYED: 'شاغل', OTHER: 'سایر' }[o] || o || 'سایر';
  }

  function toEngDigits(str) {
    if (!str) return '';
    const p2e = {'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9','٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'};
    return String(str).replace(/[۰-۹٠-٩]/g, d => p2e[d] || d);
  }

  function populateDormFilter() {
    const select = document.getElementById('filter-dorm');
    if (!select || !DB.dorms) return;
    const currentVal = select.value;
    select.innerHTML = '<option value="">همه خوابگاه‌ها</option>' +
      DB.dorms.map(d => `<option value="${d}">${d}</option>`).join('');
    if (currentVal) select.value = currentVal;
  }

  function populateRoomSelectFilter() {
    const select = document.getElementById('filter-room-select');
    if (!select || !DB.rooms) return;
    const currentVal = select.value;

    const dormEl = document.getElementById('filter-dorm');
    const selectedDorm = dormEl ? dormEl.value : '';

    let rooms = [...(DB.rooms || [])];
    if (selectedDorm) {
      rooms = rooms.filter(r => r.dormitory === selectedDorm);
    }

    rooms.sort((a, b) => (a.room_number || 0) - (b.room_number || 0));

    let html = '<option value="">همه اتاق‌ها</option>';
    rooms.forEach(rm => {
      const dormTag = (!selectedDorm && rm.dormitory) ? ` (${rm.dormitory})` : '';
      html += `<option value="${rm.room_number}">اتاق ${rm.room_number}${dormTag}</option>`;
    });

    select.innerHTML = html;
    if (currentVal && rooms.some(r => String(r.room_number) === String(currentVal))) {
      select.value = currentVal;
    }
  }

  // --- Profile Text Formatter (Strictly Non-Financial / No Transaction History) ---
  function formatResidentText(r) {
    if (!r) return '';
    const roomText = r.room ? `اتاق ${r.room.room_number}` : 'تعیین‌نشده';
    const rentText = r.room && r.room.monthly_rent ? `${Utils.toToman(r.room.monthly_rent)}` : 'نامشخص';
    const dormName = r.dormitory || 'نامشخص';
    const natCode = r.national_code || '⚠️ ثبت‌نشده';
    const parentPhone = r.parent_phone_number || '⚠️ ثبت‌نشده';
    const occ = occLabel(r.occupation);
    const statusText = r.status === 'ACTIVE' ? 'فعال' : (r.status === 'LEFT' ? 'خارج شده' : r.status);
    const settledText = r.settled_until || 'ثبت نشده';
    const entryText = r.entry_date || 'نامشخص';

    const idLabel = r.is_foreign ? '🛂 شماره پاسپورت/فراگیر (اتباع)' : '🆔 کد ملی';
    const idVal = r.national_code ? (r.is_foreign ? `${r.national_code} (اتباع)` : r.national_code) : '⚠️ ثبت‌نشده';

    return [
      `👤 نام و نام خانوادگی: ${r.full_name || 'بدون نام'}`,
      `👨 نام پدر: ${r.father_name || '⚠️ ثبت‌نشده'}`,
      `${idLabel}: ${idVal}`,
      `📱 شماره تماس: ${r.phone_number || '-'}`,
      `👨‍👩‍👦 شماره والدین: ${parentPhone}`,
      `💼 وضعیت شغلی: ${occ}`,
      `🏢 خوابگاه: ${dormName}`,
      `🚪 شماره اتاق: ${roomText} (اجاره: ${rentText})`,
      `📄 اجاره‌نامه: ${r.has_lease ? '✅ دارد' : '⚠️ ندارد (کسری مدرک)'}`,
      `💰 ودیعه: ${r.has_deposit ? '✅ دارد' : '❌ ندارد'}`,
      `📅 تاریخ ورود: ${entryText}`,
      `📌 وضعیت اقامت: ${statusText}`,
      `⌛ تسویه تا تاریخ: ${r.settled_until_display || settledText}`,
      `🗓️ سررسید موعد بعدی: ${r.next_due_date_display || settledText} (${r.due_status_display || (r.is_in_debt ? 'بدهکار' : 'تسویه')})`,
    ].join('\n');
  }

  // --- Reliable Cross-Browser Clipboard Helper ---
  function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      ta.style.top = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        const successful = document.execCommand('copy');
        document.body.removeChild(ta);
        if (successful) resolve();
        else reject(new Error('execCommand failed'));
      } catch (err) {
        document.body.removeChild(ta);
        reject(err);
      }
    });
  }

  function render(list = DB.residents) {
    populateDormFilter();
    populateRoomSelectFilter();
    currentFiltered = list || [];
    const grid = document.getElementById('students-grid');
    const countEl = document.getElementById('students-count');
    if (countEl) countEl.innerText = currentFiltered.length;

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
        const natCodeDisplay = r.national_code
          ? (r.is_foreign ? `${r.national_code} <span class="text-[9px] bg-sky-500/20 text-sky-400 px-1.5 py-0.5 rounded">اتباع</span>` : r.national_code)
          : (r.is_foreign ? '<span class="text-amber-400 font-medium">⚠️ بدون پاسپورت</span>' : '<span class="text-amber-400 font-medium">⚠️ بدون کدملی</span>');
        const missingBadge = r.has_incomplete_profile
          ? `<div class="mt-2.5 px-2.5 py-1 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[10px] flex items-center gap-1.5 font-medium">
               <span>⚠️ کسری مدارک:</span>
               <span>${(r.missing_profile_fields || []).join(' و ')}</span>
             </div>`
          : '';

        return `
          <div onclick="Modal.openResident(${r.id})"
               class="entity-card p-5 cursor-pointer ${cardClass}">
            <div class="flex justify-between items-start">
              <div class="flex gap-3">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-md">${initial}</div>
                <div>
                  <p class="font-bold text-[15px]">${r.full_name || 'بدون نام'}${r.father_name ? ` <span class="text-[11px] text-muted font-normal">(فرزند ${r.father_name})</span>` : ''}</p>
                  <p class="text-[11px] text-muted">${natCodeDisplay} • ${r.phone_number}</p>
                  <p class="text-[10px] mt-1 text-muted">🏢 ${r.dormitory || 'نامشخص'} - ${roomText} | ${occLabel(r.occupation)}</p>
                </div>
              </div>
              <span class="status-pill ${statusClass}">${statusText}</span>
            </div>
            ${missingBadge}
            <div class="grid grid-cols-3 gap-2 mt-4 text-[11px]">
              <div class="card-cell rounded-xl p-2"><p class="text-[9px] text-faint">تاریخ ورود</p><p class="truncate">${r.entry_date || '-'}</p></div>
              <div class="card-cell rounded-xl p-2"><p class="text-[9px] text-faint">تسویه تا تاریخ</p><p class="truncate font-bold ${r.settled_until ? 'text-blue-400' : 'text-amber-400'}">${r.settled_until || 'فاقد پرداخت'}</p></div>
              <div class="card-cell rounded-xl p-2"><p class="text-[9px] text-faint">موعد سررسید</p><p class="truncate font-bold ${
                r.is_in_debt
                  ? (r.overdue_days > 7 ? 'text-rose-400' : 'text-amber-400')
                  : 'text-emerald-400'
              }">${r.next_due_date_display || r.settled_until || '-'}</p></div>
            </div>
            <!-- وضعیت سررسید و مهلت پرداخت به صورت برجسته -->
            <div class="mt-2.5 p-2 rounded-xl text-[11px] flex items-center justify-between gap-2 ${
              isLeft ? 'bg-slate-500/10 border border-slate-500/20 text-slate-300' :
              (r.is_in_debt
                ? (r.overdue_days > 7
                    ? 'bg-rose-500/10 border border-rose-500/25 text-rose-300'
                    : 'bg-amber-500/10 border border-amber-500/25 text-amber-300')
                : 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-300')
            }">
              <div class="flex items-center gap-1.5 truncate">
                <span>${isLeft ? '⚪' : (r.is_in_debt ? (r.overdue_days > 7 ? '🔴' : '🟡') : '🟢')}</span>
                <span class="font-medium truncate">${
                  isLeft ? 'خارج شده' : (
                    r.due_status_display || (
                      r.is_in_debt
                        ? (r.overdue_days > 7 ? `${r.overdue_days} روز تاخیر (بدهکار)` : `${r.overdue_days} روز تاخیر (هشدار)`)
                        : 'تسویه به روز'
                    )
                  )
                }</span>
              </div>
              <span class="text-[10px] font-semibold whitespace-nowrap">
                ${isLeft ? 'خارج شده' : (r.is_in_debt ? (Utils.toToman(r.total_debt_tomans * 10) + ' بدهی') : 'تسویه')}
              </span>
            </div>
            <div class="mt-3 flex justify-between items-center text-[10px]">
              <div class="flex gap-2 flex-wrap">
                <span class="chip px-2 py-1 rounded-full">اجاره: ${rentText}</span>
                <span class="chip px-2 py-1 rounded-full">روز پرداخت: ${r.monthly_payment_day || 1}ام</span>
              </div>
              <button onclick="event.stopPropagation(); Students.copyProfile(${r.id}, this)"
                      class="btn-copy-card px-2.5 py-1 rounded-lg glass text-[10px] text-blue-400 hover:text-white hover:bg-blue-600 transition flex items-center gap-1 font-medium"
                      title="کپی مشخصات این ساکن">
                <span>📋</span>
                <span>کپی</span>
              </button>
            </div>
          </div>
        `;

      }).join('');
    }

    const activeEl = document.getElementById('kpi-active');
    const debtEl = document.getElementById('kpi-debt');
    const incompleteEl = document.getElementById('kpi-incomplete');
    const activeCount = DB.stats?.active_residents ?? DB.residents.filter(r => r.status === 'ACTIVE').length;
    const debtCount = DB.stats?.debt_residents ?? DB.residents.filter(r => r.is_in_debt && r.status === 'ACTIVE').length;
    const incompleteCount = DB.stats?.incomplete_residents ?? DB.residents.filter(r => r.has_incomplete_profile && r.status === 'ACTIVE').length;

    if (activeEl) Utils.animateCounter(activeEl, activeCount);
    if (debtEl) Utils.animateCounter(debtEl, debtCount);
    if (incompleteEl) Utils.animateCounter(incompleteEl, incompleteCount);
  }

  let filterTimer = null;
  function debouncedFilter() {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(runFilter, 60);
  }

  function runFilter() {
    const qEl = document.getElementById('search-student');
    const dormEl = document.getElementById('filter-dorm');
    const roomSelectEl = document.getElementById('filter-room-select');
    const statusEl = document.getElementById('filter-status');
    const occEl = document.getElementById('filter-occupation');

    const rawQ = qEl ? qEl.value.trim() : '';
    const qNorm = toEngDigits(rawQ).toLowerCase();
    const qDigits = qNorm.replace(/\D/g, '');
    const dorm = dormEl ? dormEl.value : '';
    const selectedRoom = roomSelectEl ? roomSelectEl.value : '';
    const status = statusEl ? statusEl.value : '';
    const occ = occEl ? occEl.value : '';

    const filtered = (DB.residents || []).filter(r => {
      const roomNumStr = r.room ? String(r.room.room_number) : '';
      const fullName = (r.full_name || '').toLowerCase();
      const father = (r.father_name || '').toLowerCase();
      const natCode = toEngDigits(r.national_code || '');
      const phone = toEngDigits(r.phone_number || '');

      const matchQ = !rawQ ||
        fullName.includes(rawQ.toLowerCase()) ||
        father.includes(rawQ.toLowerCase()) ||
        natCode.includes(qNorm) ||
        phone.includes(qNorm) ||
        roomNumStr.includes(qNorm) ||
        (qDigits && roomNumStr.includes(qDigits)) ||
        (`اتاق ${roomNumStr}`).toLowerCase().includes(rawQ.toLowerCase()) ||
        (`اتاق${roomNumStr}`).toLowerCase().includes(rawQ.toLowerCase());

      const matchDorm = !dorm || r.dormitory === dorm;
      const matchRoom = !selectedRoom || roomNumStr === String(selectedRoom);
      const matchOcc = !occ || r.occupation === occ;

      let matchStat = true;
      if (status === "debt") matchStat = r.is_in_debt && r.status === 'ACTIVE';
      else if (status === "debt_warning") matchStat = r.is_in_debt && r.overdue_days <= 7 && r.status === 'ACTIVE';
      else if (status === "debt_critical") matchStat = r.is_in_debt && r.overdue_days > 7 && r.status === 'ACTIVE';
      else if (status === "paid") matchStat = !r.is_in_debt && r.status === 'ACTIVE';
      else if (status === "incomplete") matchStat = r.has_incomplete_profile && r.status === 'ACTIVE';
      else if (status === "ACTIVE") matchStat = r.status === "ACTIVE";
      else if (status === "LEFT") matchStat = r.status === "LEFT";

      return matchQ && matchDorm && matchRoom && matchOcc && matchStat;
    });

    render(filtered);
  }


  // --- Single Resident Copy ---
  function copyProfile(id, btn) {
    const r = (DB.residents || []).find(x => x.id === id);
    if (!r) {
      Toast.show('ساکن یافت نشد', 'danger');
      return;
    }
    const text = formatResidentText(r);
    copyTextToClipboard(text).then(() => {
      Toast.show(`مشخصات ${r.full_name || ''} در کلیپ‌بورد کپی شد`, 'success');
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✅</span><span>کپی شد!</span>';
        btn.classList.add('bg-emerald-500', 'text-white');
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.classList.remove('bg-emerald-500', 'text-white');
        }, 2000);
      }
    }).catch(() => {
      Toast.show('خطا در کپی کلیپ‌بورد', 'danger');
    });
  }

  // --- Single Resident Download .txt ---
  function downloadSingleTxt(id) {
    const r = (DB.residents || []).find(x => x.id === id);
    if (!r) return;
    const text = formatResidentText(r);
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `profile_${r.full_name || r.id}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    Toast.show('فایل متنی مشخصات دانلود شد', 'success');
  }

  // --- Copy All Visible / Filtered Residents ---
  function copyFilteredProfiles() {
    const list = currentFiltered.length ? currentFiltered : (DB.residents || []);
    if (!list.length) {
      Toast.show('ساکنی برای کپی وجود ندارد', 'warning');
      return;
    }
    const sep = '\n' + ('═'.repeat(45)) + '\n\n';
    const text = `📋 فهرست مشخصات ساکنین (${list.length} نفر)\n` +
      ('═'.repeat(45)) + '\n\n' +
      list.map((r, i) => `ردیف ${i + 1}:\n` + formatResidentText(r)).join(sep);

    copyTextToClipboard(text).then(() => {
      Toast.show(`مشخصات ${list.length} نفر در کلیپ‌بورد کپی شد`, 'success');
    }).catch(() => {
      Toast.show('خطا در کپی کلیپ‌بورد', 'danger');
    });
  }

  // --- Download Filtered Residents as CSV (with UTF-8 BOM for Persian Excel) ---
  function downloadFilteredCsv() {
    const list = currentFiltered.length ? currentFiltered : (DB.residents || []);
    if (!list.length) {
      Toast.show('ساکنی برای خروجی اکسل وجود ندارد', 'warning');
      return;
    }

    const headers = [
      'ردیف', 'نام و نام خانوادگی', 'کد ملی', 'شماره تماس', 'شماره والدین',
      'شغل', 'خوابگاه', 'شماره اتاق', 'اجاره ماهانه (تومان)', 'اجاره‌نامه', 'ودیعه', 'تاریخ ورود',
      'موعد پرداخت', 'وضعیت اقامت', 'تسویه تا تاریخ', 'تاریخ سررسید موعد', 'وضعیت سررسید'
    ];

    const rows = list.map((r, i) => {
      const roomNum = r.room ? r.room.room_number : 'تعیین‌نشده';
      const rent = r.room && r.room.monthly_rent ? (r.room.monthly_rent / 10).toLocaleString('en-US') : '0';
      const dorm = r.dormitory || '-';
      const occ = occLabel(r.occupation);
      const stat = r.status === 'ACTIVE' ? 'فعال' : (r.status === 'LEFT' ? 'خارج شده' : r.status);
      const leaseStat = r.has_lease ? 'دارد' : 'ندارد';
      const depStat = r.has_deposit ? 'دارد' : 'ندارد';
      const settledUntil = r.settled_until || 'ثبت نشده';
      const dueDate = r.next_due_date_display || settledUntil;
      const dueStatus = r.due_status_display || (r.is_in_debt ? 'بدهکار' : 'تسویه');
      return [
        i + 1,
        `"${(r.full_name || '').replace(/"/g, '""')}"`,
        `"${r.national_code || 'ثبت‌نشده'}"`,
        `"${r.phone_number || ''}"`,
        `"${r.parent_phone_number || 'ثبت‌نشده'}"`,
        `"${occ}"`,
        `"${dorm}"`,
        `"${roomNum}"`,
        `"${rent}"`,
        `"${leaseStat}"`,
        `"${depStat}"`,
        `"${r.entry_date || ''}"`,
        `"${r.monthly_payment_day || 1}ام هر ماه"`,
        `"${stat}"`,
        `"${settledUntil}"`,
        `"${dueDate}"`,
        `"${dueStatus}"`
      ].join(',');
    });

    const csvContent = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `residents_export_${list.length}_persons.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    Toast.show(`فایل اکسل (${list.length} نفر) دانلود شد`, 'success');
  }

  // --- Export Modal Management ---
  function openExportModal() {
    const modal = document.getElementById('export-modal');
    if (!modal) return;
    modal.classList.remove('hidden');

    // Default selection: select all currently filtered residents
    const initialList = currentFiltered.length ? currentFiltered : (DB.residents || []);
    exportSelectedIds = new Set(initialList.map(r => r.id));

    renderExportList();
    updateExportPreview();
  }

  function closeExportModal() {
    const modal = document.getElementById('export-modal');
    if (modal) modal.classList.add('hidden');
  }

  function renderExportList() {
    const container = document.getElementById('export-residents-list');
    if (!container) return;

    const qInput = document.getElementById('export-search');
    const q = qInput ? qInput.value.trim().toLowerCase() : '';

    const list = (DB.residents || []).filter(r => {
      if (!q) return true;
      const fn = (r.full_name || '').toLowerCase();
      const nc = r.national_code || '';
      const rm = r.room ? String(r.room.room_number) : '';
      return fn.includes(q) || nc.includes(q) || rm.includes(q);
    });

    if (!list.length) {
      container.innerHTML = '<div class="text-center text-muted py-6">موردی یافت نشد</div>';
      return;
    }

    container.innerHTML = list.map(r => {
      const isChecked = exportSelectedIds.has(r.id);
      const roomNum = r.room ? `اتاق ${r.room.room_number}` : 'بی‌اتاق';
      return `
        <label class="flex items-center justify-between p-2 rounded-xl glass hover:bg-white/5 cursor-pointer transition">
          <div class="flex items-center gap-2">
            <input type="checkbox" onchange="Students.toggleExportResident(${r.id})" ${isChecked ? 'checked' : ''} class="rounded accent-blue-500">
            <div>
              <p class="font-bold text-[11px]">${r.full_name || 'بدون نام'}</p>
              <p class="text-[9px] text-muted">${r.national_code || 'فاقد کدملی'} • ${r.phone_number || '-'}</p>
            </div>
          </div>
          <span class="text-[10px] text-muted">${roomNum}</span>
        </label>
      `;
    }).join('');

    const countEl = document.getElementById('export-selected-count');
    if (countEl) countEl.innerText = exportSelectedIds.size;
  }

  function filterExportList() {
    renderExportList();
  }

  function selectAllExport(select) {
    if (select) {
      exportSelectedIds = new Set((DB.residents || []).map(r => r.id));
    } else {
      exportSelectedIds.clear();
    }
    renderExportList();
    updateExportPreview();
  }

  function toggleExportResident(id) {
    if (exportSelectedIds.has(id)) {
      exportSelectedIds.delete(id);
    } else {
      exportSelectedIds.add(id);
    }
    const countEl = document.getElementById('export-selected-count');
    if (countEl) countEl.innerText = exportSelectedIds.size;
    updateExportPreview();
  }

  function updateExportPreview() {
    const previewTa = document.getElementById('export-preview-text');
    const linesEl = document.getElementById('export-preview-lines');
    if (!previewTa) return;

    const selected = (DB.residents || []).filter(r => exportSelectedIds.has(r.id));
    if (!selected.length) {
      previewTa.value = 'هیچ ساکنی برای خروجی انتخاب نشده است. لطفاً حداقل یک نفر را انتخاب کنید.';
      if (linesEl) linesEl.innerText = '۰ سطر';
      return;
    }

    const sep = '\n' + ('═'.repeat(45)) + '\n\n';
    const text = `📋 فهرست مشخصات ساکنین (${selected.length} نفر)\n` +
      ('═'.repeat(45)) + '\n\n' +
      selected.map((r, i) => `ردیف ${i + 1}:\n` + formatResidentText(r)).join(sep);

    previewTa.value = text;
    if (linesEl) {
      const lineCount = text.split('\n').length;
      linesEl.innerText = `${lineCount} سطر (${selected.length} نفر)`;
    }
  }

  function copyExportModalText() {
    const previewTa = document.getElementById('export-preview-text');
    if (!previewTa || !exportSelectedIds.size) {
      Toast.show('ساکنی انتخاب نشده است', 'warning');
      return;
    }
    const btn = document.getElementById('btn-export-copy');
    copyTextToClipboard(previewTa.value).then(() => {
      Toast.show(`مشخصات ${exportSelectedIds.size} ساکن در کلیپ‌بورد کپی شد`, 'success');
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✅</span><span>کپی شد!</span>';
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
      }
    }).catch(() => {
      Toast.show('خطا در دسترسی به کلیپ‌بورد', 'danger');
    });
  }

  function downloadExportModalTxt() {
    const previewTa = document.getElementById('export-preview-text');
    if (!previewTa || !exportSelectedIds.size) {
      Toast.show('ساکنی انتخاب نشده است', 'warning');
      return;
    }
    const blob = new Blob([previewTa.value], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `residents_export_${exportSelectedIds.size}_persons.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    Toast.show('فایل متنی دانلود شد', 'success');
  }

  function downloadExportModalCsv() {
    const selected = (DB.residents || []).filter(r => exportSelectedIds.has(r.id));
    if (!selected.length) {
      Toast.show('ساکنی انتخاب نشده است', 'warning');
      return;
    }

    const headers = [
      'ردیف', 'نام و نام خانوادگی', 'کد ملی', 'شماره تماس', 'شماره والدین',
      'شغل', 'خوابگاه', 'شماره اتاق', 'اجاره ماهانه (تومان)', 'اجاره‌نامه', 'ودیعه', 'تاریخ ورود',
      'موعد پرداخت', 'وضعیت اقامت', 'تسویه تا تاریخ', 'تاریخ سررسید موعد', 'وضعیت سررسید'
    ];

    const rows = selected.map((r, i) => {
      const roomNum = r.room ? r.room.room_number : 'تعیین‌نشده';
      const rent = r.room && r.room.monthly_rent ? (r.room.monthly_rent / 10).toLocaleString('en-US') : '0';
      const dorm = r.dormitory || '-';
      const occ = occLabel(r.occupation);
      const stat = r.status === 'ACTIVE' ? 'فعال' : (r.status === 'LEFT' ? 'خارج شده' : r.status);
      const leaseStat = r.has_lease ? 'دارد' : 'ندارد';
      const depStat = r.has_deposit ? 'دارد' : 'ندارد';
      const settledUntil = r.settled_until || 'ثبت نشده';
      const dueDate = r.next_due_date_display || settledUntil;
      const dueStatus = r.due_status_display || (r.is_in_debt ? 'بدهکار' : 'تسویه');
      return [
        i + 1,
        `"${(r.full_name || '').replace(/"/g, '""')}"`,
        `"${r.national_code || 'ثبت‌نشده'}"`,
        `"${r.phone_number || ''}"`,
        `"${r.parent_phone_number || 'ثبت‌نشده'}"`,
        `"${occ}"`,
        `"${dorm}"`,
        `"${roomNum}"`,
        `"${rent}"`,
        `"${leaseStat}"`,
        `"${depStat}"`,
        `"${r.entry_date || ''}"`,
        `"${r.monthly_payment_day || 1}ام هر ماه"`,
        `"${stat}"`,
        `"${settledUntil}"`,
        `"${dueDate}"`,
        `"${dueStatus}"`
      ].join(',');
    });

    const csvContent = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `residents_export_${selected.length}_persons.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    Toast.show(`فایل اکسل (${selected.length} نفر) دانلود شد`, 'success');
  }

  return {
    render,
    filter: debouncedFilter,
    populateDormFilter,
    populateRoomSelectFilter,
    formatResidentText,
    copyProfile,
    downloadSingleTxt,
    copyFilteredProfiles,
    downloadFilteredCsv,
    openExportModal,
    closeExportModal,
    filterExportList,
    selectAllExport,
    toggleExportResident,
    copyExportModalText,
    downloadExportModalTxt,
    downloadExportModalCsv,
  };
})();
