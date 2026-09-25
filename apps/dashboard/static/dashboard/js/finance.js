/* ===================================================================
   FINANCE TAB — Real data charts, calculations, and filters
=================================================================== */

const Finance = (() => {
  let pickersInitialized = false;

  function initPickers() {
    if (pickersInitialized) return;
    if (typeof PersianDatePicker !== 'undefined') {
      const fromEl = document.getElementById('finance-from');
      const toEl = document.getElementById('finance-to');
      if (fromEl) {
        new PersianDatePicker(fromEl, {
          onSelect: () => render()
        });
      }
      if (toEl) {
        new PersianDatePicker(toEl, {
          onSelect: () => render()
        });
      }
      pickersInitialized = true;
    }
  }

  function getFiltered() {
    const fromEl = document.getElementById('finance-from');
    const toEl = document.getElementById('finance-to');
    const typeEl = document.getElementById('finance-type');
    const methodEl = document.getElementById('finance-method');

    const from = fromEl ? fromEl.value.trim().replace(/-/g, '/') : '';
    const to = toEl ? toEl.value.trim().replace(/-/g, '/') : '';
    const type = typeEl ? typeEl.value : '';
    const method = methodEl ? methodEl.value : '';

    return (DB.transactions || []).filter(t => {
      const pDate = (t.payment_date || '').replace(/-/g, '/');
      const pDateDay = pDate.slice(0, 10);
      if (from && pDateDay < from) return false;
      if (to && pDateDay > to) return false;
      if (type && t.transaction_type !== type) return false;
      if (method && t.payment_method !== method) return false;
      return true;
    });
  }

  function render() {
    initPickers();
    const filtered = getFiltered();
    const total = filtered.reduce((s, t) => s + (t.amount || 0), 0);
    const rentTotal = filtered.filter(t => t.transaction_type === 'RENT').reduce((s, t) => s + (t.amount || 0), 0);
    const depositTotal = filtered.filter(t => t.transaction_type === 'DEPOSIT').reduce((s, t) => s + (t.amount || 0), 0);
    const pending = filtered.filter(t => !t.is_approved).length;

    const elTotal = document.getElementById('fin-total');
    const elRent = document.getElementById('fin-rent');
    const elDeposit = document.getElementById('fin-deposit');
    const elPending = document.getElementById('fin-pending');
    const elAvg = document.getElementById('fin-avg');

    if (elTotal) elTotal.innerText = Utils.toToman(total);
    if (elRent) elRent.innerText = Utils.toToman(rentTotal);
    if (elDeposit) elDeposit.innerText = Utils.toToman(depositTotal);
    if (elPending) elPending.innerText = pending + " تراکنش";
    if (elAvg) elAvg.innerText = filtered.length ? Utils.toToman(Math.round(total / filtered.length)) : "0 تومان";

    // 1. Monthly income breakdown
    const months = {};
    (DB.transactions || []).forEach(t => {
      if (t.payment_date) {
        const m = t.payment_date.slice(0, 7); // e.g. "1405/05"
        months[m] = (months[m] || 0) + (t.amount || 0);
      }
    });
    const sortedMonths = Object.keys(months).sort();
    if (sortedMonths.length > 0) {
      Charts.renderMonthly(sortedMonths, months);
    }

    // 2. Payment methods chart
    const methods = {};
    filtered.forEach(t => {
      if (t.payment_method) {
        methods[t.payment_method] = (methods[t.payment_method] || 0) + (t.amount || 0);
      }
    });
    const methodKeys = Object.keys(methods);
    if (methodKeys.length > 0) {
      Charts.renderMethods(
        methodKeys.map(Utils.methodLabel),
        methodKeys.map(k => Math.round(methods[k] / 10))
      );
    }

    // 3. Recent transactions list
    const recentContainer = document.getElementById('finance-recent');
    if (recentContainer) {
      if (filtered.length === 0) {
        recentContainer.innerHTML = '<p class="text-xs text-muted text-center py-4">تراکنشی یافت نشد</p>';
      } else {
        recentContainer.innerHTML = filtered.slice(0, 20).map(t => {
          const resName = t.resident ? t.resident.full_name : 'ساکن نامشخص';
          const typeBadge = t.transaction_type === 'RENT'
            ? 'bg-emerald-500/20 text-emerald-400'
            : 'bg-blue-500/20 text-blue-400';
          const approvalBadge = !t.is_approved
            ? '<span class="bg-amber-500 text-white text-[9px] px-2 py-0.5 rounded-full mr-1">نیاز تایید</span>'
            : '';

          return `
            <div class="surface-subtle rounded-xl p-2.5 flex justify-between text-[11px]">
              <div>

                <p class="font-bold">${resName} - ${Utils.toToman(t.amount)} ${approvalBadge}</p>
                <p class="text-[10px] text-muted">${t.payment_date} | ${Utils.methodLabel(t.payment_method)}</p>
              </div>
              <span class="text-[9px] px-2 py-1 rounded-full ${typeBadge} h-fit">${Utils.typeLabel(t.transaction_type)}</span>
            </div>
          `;
        }).join('');
      }
    }

    // 4. Current month income KPI
    const currentMonthIncome = DB.stats?.current_month_income ?? 0;
    const kpiIncome = document.getElementById('kpi-income');
    if (kpiIncome) kpiIncome.innerText = Utils.toToman(currentMonthIncome);

    // 5. Income sparkline trend
    const trendVals = sortedMonths.slice(-8).map(m => Math.round(months[m] / 10));
    Charts.drawSparkline('spark-income', trendVals.length ? trendVals : [0], '#22c55e');
  }

  function apply() {
    render();
    Toast.show('فیلترهای مالی اعمال شد', 'success');
  }

  return { render, apply, getFiltered };
})();
