/* ===================================================================
   MODAL — resident/room detail panels with null guards
=================================================================== */

const Modal = (() => {
  let touchStartY = null;

  function open() {
    const backdrop = document.getElementById('modal');
    if (!backdrop) return;
    document.body.style.overflow = 'hidden';
    backdrop.classList.remove('hidden');
    requestAnimationFrame(() => backdrop.classList.add('show'));
  }

  function close() {
    const backdrop = document.getElementById('modal');
    if (!backdrop) return;
    backdrop.classList.remove('show');
    document.body.style.overflow = '';
    setTimeout(() => backdrop.classList.add('hidden'), 320);
  }

  function openResident(id) {
    const r = (DB.residents || []).find(x => x.id === id);
    if (!r) {
      Toast.show('اطلاعات ساکن یافت نشد', 'danger');
      return;
    }

    const trans = (DB.transactions || []).filter(t => t.resident && t.resident.id === id);
    const roomText = r.room ? `اتاق ${r.room.room_number}` : 'اتاق تعیین‌نشده';
    const titleEl = document.getElementById('modal-title');
    const contentEl = document.getElementById('modal-content');

    const idTitle = r.is_foreign ? (r.national_code ? `پاسپورت: ${r.national_code}` : 'اتباع (بدون مدرک)') : (r.national_code || 'بدون کد ملی');
    if (titleEl) titleEl.innerText = `${r.full_name || 'بدون نام'} - ${idTitle} | ${roomText}`;
    if (contentEl) {
      const missingAlert = r.has_incomplete_profile
        ? `<div class="mb-4 p-3 rounded-2xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
             <span class="text-base">⚠️</span>
             <span><strong>پرونده ناقص (کسری مدارک):</strong> این ساکن فاقد ${(r.missing_profile_fields || []).join(' و ')} است. لطفاً جهت تکمیل اطلاعات پیگیری نمایید.</span>
           </div>`
        : '';

      const idLabel = r.is_foreign ? 'شماره پاسپورت / فراگیر (اتباع)' : 'کد ملی';
      const natCodeHtml = r.national_code
        ? (r.is_foreign ? `${r.national_code} <span class="text-[10px] bg-sky-500/20 text-sky-400 px-1.5 py-0.5 rounded">اتباع</span>` : r.national_code)
        : '<span class="text-amber-400 font-medium">⚠️ ثبت‌نشده</span>';

      const fatherNameHtml = r.father_name
        ? r.father_name
        : '<span class="text-amber-400 font-medium">⚠️ ثبت‌نشده</span>';

      const parentPhoneHtml = r.parent_phone_number
        ? r.parent_phone_number
        : '<span class="text-amber-400 font-medium">⚠️ ثبت‌نشده</span>';

      contentEl.innerHTML = `
        ${missingAlert}
        <div class="flex flex-wrap justify-between items-center gap-2 mb-4 p-3 rounded-2xl glass border border-blue-500/20">
          <div class="text-xs text-muted flex items-center gap-2">
            <span>🏢 خوابگاه: <strong>${r.dormitory || '-'}</strong></span>
            <span>•</span>
            <span>${roomText}</span>
          </div>
          <div class="flex gap-2">
            <button type="button" onclick="Students.copyProfile(${r.id}, this)" class="btn glass text-xs px-3 py-1.5 rounded-xl hover:bg-blue-600 transition flex items-center gap-1.5 text-blue-300 hover:text-white font-medium" title="کپی مشخصات کامل در کلیپ‌بورد">
              <span>📋</span>
              <span>کپی مشخصات ساکن</span>
            </button>
            <button type="button" onclick="Students.downloadSingleTxt(${r.id})" class="btn glass text-xs px-3 py-1.5 rounded-xl hover:bg-slate-700 transition flex items-center gap-1.5 text-slate-300 font-medium" title="دانلود فایل متنی">
              <span>📥</span>
              <span>دانلود فایل متنی</span>
            </button>
          </div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4 stagger">
          <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">نام پدر</p><p class="font-bold text-sm">${fatherNameHtml}</p></div>
          <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">${idLabel}</p><p class="font-bold">${natCodeHtml}</p></div>
          <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">موبایل / والدین</p><p class="font-bold text-sm">${r.phone_number || '-'} / ${parentPhoneHtml}</p></div>
          <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">اجاره‌نامه / مدارک</p><p class="font-bold text-sm ${r.has_lease ? 'text-emerald-400' : 'text-rose-400'}">${r.has_lease ? '✅ اجاره‌نامه' : '⚠️ بدون اجاره'} • <span class="${r.has_id_card_image ? 'text-sky-400' : 'text-amber-400'}">${r.has_id_card_image ? '📷 ' + r.id_images_count + ' عکس' : 'بدون عکس'}</span></p></div>
          <div class="glass rounded-2xl p-4"><p class="text-[11px] text-muted">ودیعه</p><p class="font-bold text-sm ${r.has_deposit ? 'text-emerald-400' : 'text-slate-400'}">${r.has_deposit ? '✅ ودیعه دارد' : '❌ فاقد ودیعه'}</p></div>
        </div>

        <!-- بلوک وضعیت تسویه حساب و سررسید موعد اجاره -->
        ${(() => {
          const pp = r.period_payment || {};
          const isPartial = Boolean(r.is_partial_payment || pp.is_partial);
          const isOverdue = Boolean(r.is_in_debt) && !isPartial;
          const overdue = r.overdue_days || 0;
          const isWarning = isOverdue && overdue <= 7;
          const isCritical = isOverdue && overdue > 7;

          let containerClass, headerColor, pillClass, pillText, dueDateColor;

          if (isPartial) {
            containerClass = 'border-amber-500/35 bg-amber-500/10';
            headerColor = 'text-amber-300';
            pillClass = 'bg-amber-500 text-slate-950 font-bold';
            pillText = `🟡 پرداخت مرحله‌ای (${Utils.toToman((pp.remaining_tomans || 0) * 10)} مانده)`;
            dueDateColor = 'text-amber-300';
          } else if (isCritical) {
            containerClass = 'border-rose-500/30 bg-rose-500/10';
            headerColor = 'text-rose-300';
            pillClass = 'bg-rose-500 text-white font-bold';
            pillText = `🔴 ${overdue} روز تاخیر در پرداخت (بدهکار)`;
            dueDateColor = 'text-rose-400';
          } else if (isWarning) {
            containerClass = 'border-amber-500/30 bg-amber-500/10';
            headerColor = 'text-amber-300';
            pillClass = 'bg-amber-500 text-slate-900 font-bold';
            pillText = overdue === 0 ? '🟡 سررسید امروز (مهلت پرداخت)' : `🟡 ${overdue} روز تاخیر (هشدار مهلت یک هفته)`;
            dueDateColor = 'text-amber-400';
          } else {
            containerClass = 'border-emerald-500/30 bg-emerald-500/5';
            headerColor = 'text-emerald-300';
            pillClass = 'bg-emerald-500 text-white font-bold';
            pillText = '🟢 تسویه به روز';
            dueDateColor = 'text-emerald-400';
          }

          const settleCoverLabel = isPartial
            ? 'پوشش علی‌الحساب تا این تاریخ'
            : (r.settled_until ? 'پوشش کامل تا این تاریخ' : 'حساب بدون پرداخت');

          const dueBoxTitle = isPartial ? 'وضعیت پرداخت دوره' : 'مهلت تا موعد / تاخیر';
          const dueBoxValue = isPartial
            ? `<span class="text-amber-300">مرحله اول (${pp.progress_percent || 0}٪)</span>`
            : (isCritical ? `${overdue} روز تاخیر (بیش از یک هفته)` : (isWarning ? (overdue === 0 ? 'امروز سررسید است' : `${overdue} روز تاخیر (تا ۱ هفته)`) : `${r.days_until_due || 0} روز تا سررسید`));

          const debtBoxValue = isPartial
            ? `<span class="text-amber-300 font-bold">${Utils.toToman((pp.remaining_tomans || 0) * 10)} مانده</span>`
            : (r.is_in_debt ? Utils.toToman(r.total_debt_tomans * 10) + ' بدهی' : (r.room ? Utils.toToman(r.room.monthly_rent) : '-'));

          const debtBoxSub = isPartial
            ? `پرداختی: ${Utils.toToman((pp.paid_tomans || 0) * 10)} از ${Utils.toToman((pp.total_rent_tomans || 0) * 10)}`
            : `روز پرداخت: ${r.monthly_payment_day || 1}ام هر ماه`;

          return `
            <div class="mb-5 p-4 rounded-2xl glass border ${containerClass}">
              <div class="flex flex-wrap items-center justify-between gap-2 mb-3 pb-2 border-b border-white/10">
                <h5 class="text-xs font-bold flex items-center gap-1.5 ${headerColor}">
                  <span>🗓️</span>
                  <span>وضعیت تسویه حساب و سررسید موعد پرداخت اجاره</span>
                </h5>
                <span class="status-pill text-[11px] ${pillClass}">
                  ${pillText}
                </span>
              </div>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-right">
                <div class="p-3 rounded-xl bg-white/5 border border-white/5">
                  <p class="text-[10px] text-muted">تسویه تا تاریخ</p>
                  <p class="font-bold text-sm text-blue-300 mt-1">${r.settled_until || 'فاقد پرداخت'}</p>
                  <p class="text-[10px] text-muted mt-0.5">${settleCoverLabel}</p>
                </div>
                <div class="p-3 rounded-xl bg-white/5 border border-white/5">
                  <p class="text-[10px] text-muted">تاریخ سررسید موعد بعدی</p>
                  <p class="font-bold text-sm ${dueDateColor} mt-1">${r.next_due_date_display || r.settled_until || '-'}</p>
                  <p class="text-[10px] text-muted mt-0.5">موعد پرداخت بعدی</p>
                </div>
                <div class="p-3 rounded-xl bg-white/5 border border-white/5">
                  <p class="text-[10px] text-muted">${dueBoxTitle}</p>
                  <p class="font-bold text-sm mt-1 ${isPartial ? 'text-amber-300' : (isCritical ? 'text-rose-400' : (isWarning ? 'text-amber-400' : 'text-emerald-400'))}">
                    ${dueBoxValue}
                  </p>
                  <p class="text-[10px] text-muted mt-0.5">${isPartial ? (pp.period_name || 'دوره جاری') : (r.is_in_debt && r.unpaid_months ? r.unpaid_months : 'بدون تاخیر')}</p>
                </div>
                <div class="p-3 rounded-xl bg-white/5 border border-white/5">
                  <p class="text-[10px] text-muted">${isPartial ? 'مانده این دوره / نرخ' : 'مبلغ بدهی / نرخ ماهانه'}</p>
                  <p class="font-bold text-sm mt-1">${debtBoxValue}</p>
                  <p class="text-[10px] text-muted mt-0.5">${debtBoxSub}</p>
                </div>
              </div>

              ${isPartial ? `
                <div class="mt-3.5 p-3.5 rounded-xl bg-slate-900/60 border border-amber-500/30 text-xs">
                  <div class="flex flex-wrap items-center justify-between gap-2 mb-2 pb-1.5 border-b border-white/10">
                    <span class="font-bold text-amber-300 flex items-center gap-1.5">
                      <span>💳</span>
                      <span>وضعیت پرداخت دوره (${pp.period_name || 'دوره جاری'}):</span>
                    </span>
                    <span class="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold text-[11px]">
                      ${pp.progress_percent || 0}٪ پرداخت شده
                    </span>
                  </div>
                  <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-center my-3">
                    <div class="p-2.5 rounded-xl bg-white/5 border border-white/5">
                      <p class="text-[10px] text-muted">اجاره مصوب دوره</p>
                      <p class="font-bold text-sm mt-1 text-slate-200">${Utils.toToman((pp.total_rent_tomans || 0) * 10)}</p>
                    </div>
                    <div class="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                      <p class="text-[10px] text-emerald-400 font-semibold">پرداخت‌شده (مرحله اول)</p>
                      <p class="font-bold text-sm mt-1 text-emerald-300">✅ ${Utils.toToman((pp.paid_tomans || 0) * 10)}</p>
                    </div>
                    <div class="p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30">
                      <p class="text-[10px] text-amber-400 font-semibold">مانده بدهی (مرحله دوم)</p>
                      <p class="font-bold text-sm mt-1 text-amber-300">⏳ ${Utils.toToman((pp.remaining_tomans || 0) * 10)}</p>
                    </div>
                  </div>
                  <!-- نوار پیشرفت درصد پرداخت -->
                  <div class="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden mb-2.5 shadow-inner">
                    <div class="bg-gradient-to-r from-emerald-500 to-amber-400 h-2.5 rounded-full transition-all duration-500" style="width: ${pp.progress_percent || 0}%"></div>
                  </div>
                  <div class="flex flex-wrap items-center justify-between gap-2 mt-2 pt-2 border-t border-white/5">
                    <p class="text-[11px] text-amber-200/90 leading-relaxed">
                      ⚠️ این ساکن بخشی از اجاره این دوره را پرداخت نموده و مبلغ <strong class="text-white">${Utils.toToman((pp.remaining_tomans || 0) * 10)}</strong> از اجاره مصوب باقی مانده است.
                    </p>
                    <a href="/admin/dormitory/transaction/add/?resident=${r.id}&amount_tomans=${((pp.remaining_tomans || 0) / 1000000).toFixed(3)}" target="_blank"
                       class="px-3 py-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-amber-400 hover:from-amber-400 hover:to-amber-300 text-slate-950 font-bold text-[11px] transition whitespace-nowrap shadow flex items-center gap-1.5">
                      <span>➕</span>
                      <span>ثبت تسویه مرحله دوم (${Utils.toToman((pp.remaining_tomans || 0) * 10)})</span>
                    </a>
                  </div>
                </div>
              ` : ''}

              ${(r.is_in_debt && r.unpaid_periods && r.unpaid_periods.length > 0) ? `
                <div class="mt-3 pt-3 border-t border-white/10 text-xs">
                  <span class="text-muted block mb-1.5 font-medium">ریز دوره‌های معوقه و نرخ مصوب هر دوره:</span>
                  <div class="flex flex-wrap gap-2">
                    ${r.unpaid_periods.map(p => `
                      <span class="px-2.5 py-1 rounded-lg ${p.overdue_days > 7 ? 'bg-rose-500/10 border border-rose-500/20 text-rose-300' : 'bg-amber-500/10 border border-amber-500/20 text-amber-300'} text-[11px] flex items-center gap-1.5">
                        <strong>${p.name}:</strong> ${Utils.toToman(p.amount_tomans * 10)} (${p.overdue_days} روز تاخیر ${p.overdue_days <= 7 ? '🟡 مهلت' : '🔴 معوق'})
                      </span>
                    `).join('')}
                  </div>
                </div>
              ` : ''}
            </div>
          `;
        })()}

        <div class="mb-5 p-4 rounded-2xl glass border border-slate-700/40">
          <div class="flex justify-between items-center mb-2.5">
            <h5 class="text-xs font-bold flex items-center gap-1.5 text-slate-200">
              <span>📷</span>
              <span>تصاویر مدارک شناسایی (${r.id_images_count || 0} از ۳ تصویر)</span>
            </h5>
            <span class="text-[11px] ${r.has_id_card_image ? 'text-emerald-400' : 'text-amber-400 font-semibold'}">
              ${r.has_id_card_image ? '✅ مدرک شناسایی ثبت شده' : '⚠️ فاقد تصویر مدرک شناسایی (کسری مدارک)'}
            </span>
          </div>
          ${(() => {
            const images = [
              { url: r.id_card_image_url, label: 'تصویر ۱ (روی مدرک / کارت ملی)' },
              { url: r.id_card_image_2_url, label: 'تصویر ۲ (پشت کارت / صفحه پاسپورت)' },
              { url: r.id_card_image_3_url, label: 'تصویر ۳ (مدرک تکمیلی)' }
            ].filter(img => Boolean(img.url));

            if (images.length === 0) {
              return `
                <div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center justify-between gap-2">
                  <span>⚠️ هیچ تصویری از کارت ملی یا مدرک شناسایی آپلود نشده است.</span>
                  <a href="/admin/dormitory/resident/${r.id}/change/#id_card_image" target="_blank" class="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 text-[11px] transition">
                    ثبت یا عکسبرداری مدرک ↗
                  </a>
                </div>
              `;
            }

            return `
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                ${images.map(img => `
                  <a href="${img.url}" target="_blank" rel="noopener noreferrer" class="group relative block rounded-xl overflow-hidden border border-white/10 bg-slate-900/60 hover:border-blue-500/50 transition">
                    <div class="aspect-[4/3] w-full overflow-hidden bg-black/40 flex items-center justify-center">
                      <img src="${img.url}" alt="${img.label}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
                    </div>
                    <div class="p-2 bg-slate-800/80 text-[11px] text-slate-300 flex justify-between items-center">
                      <span class="truncate">${img.label}</span>
                      <span class="text-blue-400 group-hover:text-blue-300">↗ بزرگ‌نمایی</span>
                    </div>
                  </a>
                `).join('')}
              </div>
            `;
          })()}
        </div>

        <div class="flex justify-between items-center mb-3">
          <h4 class="font-bold">💳 تراکنش‌های مالی (${trans.length})</h4>
          <span class="text-[11px] text-muted">خوابگاه: ${r.dormitory || '-'}</span>
        </div>
        <div class="space-y-2 max-h-[50vh] overflow-auto scroll-thin pr-1 stagger">
          ${trans.map(t => {
            const hasDiscount = Boolean(t.has_discount || (t.discount_amount && t.discount_amount > 0) || (t.discount_in_tomans && t.discount_in_tomans > 0));
            const discountTomans = t.discount_in_tomans || (t.discount_amount ? t.discount_amount / 10 : 0);
            const paidTomans = t.amount_toman ?? (t.amount ? t.amount / 10 : 0);
            const effectiveTomans = t.total_effective_amount_toman || (paidTomans + discountTomans);

            return `
            <div class="glass rounded-2xl p-4 flex flex-col md:flex-row justify-between gap-3 ${hasDiscount ? 'border-amber-500/30 bg-amber-500/[0.04]' : ''}">
              <div class="flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <p class="font-bold text-sm text-white">
                    ${Utils.typeLabel(t.transaction_type)} - ${Utils.toToman(t.amount)}
                  </p>
                  <span class="text-[11px] glass px-2 py-0.5 rounded-full mr-1">${Utils.methodLabel(t.payment_method)}</span>
                  ${hasDiscount ? `
                    <span class="bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold px-2 py-0.5 rounded-full inline-flex items-center gap-1 shadow-sm">
                      <span>🏷️</span>
                      <span>${Utils.toToman(discountTomans * 10)} تخفیف/کسورات</span>
                    </span>
                  ` : ''}
                  ${!t.is_approved ? '<span class="bg-amber-500 text-white text-[9px] px-2 py-0.5 rounded-full">نیاز تایید</span>' : ''}
                </div>
                <p class="text-[11px] text-muted mt-1.5 flex flex-wrap items-center gap-x-2">
                  <span>تاریخ: ${t.payment_date || '-'}</span>
                  <span>|</span>
                  <span>${t.reference_number ? 'شماره پیگیری: ' + t.reference_number : 'بدون پیگیری'}</span>
                  ${t.period_name ? `<span>|</span><span class="text-slate-300 font-medium">دوره: ${t.period_name}</span>` : ''}
                </p>
                <p class="text-[11px] text-faint mt-0.5">${t.description || 'بدون توضیح'}</p>

                ${hasDiscount ? `
                  <div class="mt-2.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                    <div class="flex items-start sm:items-center gap-1.5 text-amber-300">
                      <span class="text-base shrink-0">🏷️</span>
                      <div>
                        <strong class="text-amber-200">علت کسورات / تخفیف:</strong>
                        <span class="text-amber-100 font-medium mr-1">${t.discount_reason || 'کسر مصوب مدیریت'}</span>
                      </div>
                    </div>
                    <div class="text-[11px] text-slate-300 bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-white/5 flex items-center gap-2 shrink-0">
                      <span>کسورات: <strong class="text-amber-300">${Utils.toToman(discountTomans * 10)}</strong></span>
                      <span class="text-white/30">•</span>
                      <span>پوشش کل موثر: <strong class="text-emerald-400">${Utils.toToman(effectiveTomans * 10)}</strong></span>
                    </div>
                  </div>
                ` : ''}
              </div>
              <div class="text-left md:text-right shrink-0">
                <p class="text-[10px] font-medium ${t.is_approved ? 'text-emerald-400' : 'text-amber-400'}">
                  ${t.is_approved ? '✅ تایید شده' : '⏳ در انتظار تایید'}
                </p>
              </div>
            </div>
            `;
          }).join('') || '<p class="text-center text-muted py-6">تراکنشی برای این ساکن ثبت نشده است.</p>'}
        </div>
      `;
    }
    open();
  }

  function openRoom(id) {
    const room = (DB.rooms || []).find(r => r.id === id);
    if (!room) {
      Toast.show('اطلاعات اتاق یافت نشد', 'danger');
      return;
    }

    const occupants = (DB.residents || []).filter(r => r.room && r.room.id === id && r.status === 'ACTIVE');
    const titleEl = document.getElementById('modal-title');
    const contentEl = document.getElementById('modal-content');
    const emptyBeds = Math.max(0, room.capacity - occupants.length);

    if (titleEl) titleEl.innerText = `اتاق ${room.room_number} - ${room.dormitory} - ظرفیت ${room.capacity}`;
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="grid md:grid-cols-4 gap-3 mb-6 stagger">
          <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">ظرفیت کل</p><p class="font-bold text-xl">${room.capacity}</p></div>
          <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">تخت پر</p><p class="font-bold text-xl">${occupants.length}</p></div>
          <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">تخت خالی</p><p class="font-bold text-xl text-emerald-500">${emptyBeds}</p></div>
          <div class="glass rounded-2xl p-4 text-center"><p class="text-[11px] text-muted">اجاره ماهانه</p><p class="font-bold text-sm">${Utils.toToman(room.monthly_rent)}</p></div>
        </div>
        <h4 class="font-bold mb-3">ساکنین فعلی اتاق (کلیک برای جزئیات و تراکنش‌ها)</h4>
        <div class="grid md:grid-cols-2 gap-3 stagger">
          ${occupants.map(o => `
            <div onclick="Modal.openResident(${o.id})" class="glass rounded-2xl p-4 cursor-pointer hover:bg-white/5 transition flex justify-between items-center">
              <div>
                <p class="font-bold">${o.full_name}</p>
                <p class="text-[11px] text-muted">${o.national_code} | ${o.phone_number}</p>
                <p class="text-[10px] mt-1">${o.is_in_debt ? (o.overdue_days > 7 ? '🔴 بدهکار (بیش از ۱ هفته)' : '🟡 هشدار تاخیر (تا ۱ هفته)') : '🟢 تسویه'} | ورود: ${o.entry_date || '-'}</p>
              </div>
              <span class="text-blue-400 text-[11px]">مشاهده پرونده ←</span>
            </div>
          `).join('') || '<p class="text-muted py-6 col-span-full text-center">این اتاق در حال حاضر کاملاً خالی است.</p>'}
        </div>
      `;
    }
    open();
  }

  function bindGlobalHandlers() {
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('modal');
        if (modal && !modal.classList.contains('hidden')) close();
      }
    });

    const panel = document.getElementById('modal-panel');
    if (panel) {
      panel.addEventListener('touchstart', e => { touchStartY = e.touches[0].clientY; }, { passive: true });
      panel.addEventListener('touchmove', e => {
        if (touchStartY === null) return;
        const dy = e.touches[0].clientY - touchStartY;
        if (dy > 0) panel.style.transform = `translateY(${dy}px)`;
      }, { passive: true });
      panel.addEventListener('touchend', e => {
        const dy = (e.changedTouches[0].clientY - (touchStartY || 0));
        panel.style.transform = '';
        if (dy > 120) close();
        touchStartY = null;
      });
    }
  }

  return { open, close, openResident, openRoom, bindGlobalHandlers };
})();
