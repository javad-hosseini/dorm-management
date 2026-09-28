/* ===================================================================
   FINANCE DASHBOARD — Interactive charts, filters, and real-time updates
=================================================================== */

const FinanceApp = (() => {
  let state = {
    data: null,
    transactions: [],
    filteredTransactions: [],
    barChart: null,
    donutChart: null
  };

  function toToman(amount) {
    if (typeof amount !== 'number') amount = Number(amount) || 0;
    return amount.toLocaleString('fa-IR') + ' تومان';
  }

  function toPersianDigits(n) {
    if (n === null || n === undefined) return '';
    return String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
  }

  function init() {
    const rawEl = document.getElementById('finance-server-data');
    if (rawEl && rawEl.textContent) {
      try {
        state.data = JSON.parse(rawEl.textContent);
        state.transactions = state.data.recent_transactions || [];
        state.filteredTransactions = [...state.transactions];
      } catch (e) {
        console.error('Error parsing finance server data:', e);
      }
    }

    if (!state.data) return;

    renderKPIs();
    render7DayChart();
    render7DayCards();
    renderDistributionChart();
    renderTopDebtors();
    renderTransactionsTable();
    bindEvents();
  }

  function renderKPIs() {
    const today = state.data.today_stats || {};
    const debt = state.data.debt_stats || {};
    const month = state.data.month_stats || {};

    // 1. Today
    const elToday = document.getElementById('kpi-today-val');
    if (elToday) elToday.textContent = toToman(today.total_tomans || 0);

    const elTodayCount = document.getElementById('kpi-today-count');
    if (elTodayCount) elTodayCount.textContent = toPersianDigits(today.count || 0) + ' تراکنش';

    const elTodayDiff = document.getElementById('kpi-today-diff');
    if (elTodayDiff) {
      const diff = today.diff_vs_yesterday_percent || 0;
      const isPositive = diff >= 0;
      elTodayDiff.className = `text-[11px] font-bold px-2 py-0.5 rounded-lg flex items-center gap-1 ${
        isPositive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'
      }`;
      elTodayDiff.innerHTML = `<span>${isPositive ? '▲ +' : '▼ '}${toPersianDigits(Math.abs(diff))}%</span> <span class="text-white/60 font-normal">نسبت به دیروز</span>`;
    }

    const elTodayCard = document.getElementById('kpi-today-card');
    if (elTodayCard) elTodayCard.textContent = toToman(today.card_tomans || 0);
    const elTodayTransfer = document.getElementById('kpi-today-transfer');
    if (elTodayTransfer) elTodayTransfer.textContent = toToman(today.transfer_tomans || 0);
    const elTodayCash = document.getElementById('kpi-today-cash');
    if (elTodayCash) elTodayCash.textContent = toToman(today.cash_tomans || 0);

    // 2. Month-to-Date
    const elMonthVal = document.getElementById('kpi-month-val');
    if (elMonthVal) elMonthVal.textContent = toToman(month.month_total_tomans || 0);
    const elMonthName = document.getElementById('kpi-month-name');
    if (elMonthName) elMonthName.textContent = month.month_name || 'ماه جاری';
    const elMonthRent = document.getElementById('kpi-month-rent');
    if (elMonthRent) elMonthRent.textContent = toToman(month.month_rent_tomans || 0);
    const elMonthDeposit = document.getElementById('kpi-month-deposit');
    if (elMonthDeposit) elMonthDeposit.textContent = toToman(month.month_deposit_tomans || 0);

    // 3. Debts (Both numbers as requested)
    const elDebtNow = document.getElementById('kpi-debt-now-val');
    if (elDebtNow) elDebtNow.textContent = toToman(debt.overdue_debt_tomans || 0);

    const elDebtNext = document.getElementById('kpi-debt-next-val');
    if (elDebtNext) elDebtNext.textContent = toToman(debt.projected_debt_until_next_month_tomans || 0);

    const elDebtNextDate = document.getElementById('kpi-debt-next-date');
    if (elDebtNextDate) elDebtNextDate.textContent = toPersianDigits(debt.first_of_next_month_str || 'اول ماه بعد');

    const elDebtCount = document.getElementById('kpi-debt-count');
    if (elDebtCount) elDebtCount.textContent = toPersianDigits(debt.indebted_residents_count || 0) + ' ساکن بدهکار';

    // 4. Rent vs Deposit ratio bar
    const totalMonth = (month.month_rent_tomans || 0) + (month.month_deposit_tomans || 0);
    const rentPct = totalMonth > 0 ? Math.round((month.month_rent_tomans / totalMonth) * 100) : 100;
    const depPct = 100 - rentPct;
    const elBarRent = document.getElementById('bar-rent');
    if (elBarRent) elBarRent.style.width = rentPct + '%';
    const elBarDep = document.getElementById('bar-deposit');
    if (elBarDep) elBarDep.style.width = depPct + '%';
    const elRentPct = document.getElementById('pct-rent');
    if (elRentPct) elRentPct.textContent = toPersianDigits(rentPct) + '%';
    const elDepPct = document.getElementById('pct-deposit');
    if (elDepPct) elDepPct.textContent = toPersianDigits(depPct) + '%';
  }

  function render7DayChart() {
    const ctx = document.getElementById('chart-7days');
    if (!ctx) return;

    const list = state.data.seven_days_breakdown || [];
    const labels = list.map(d => `${d.day_name} (${toPersianDigits(d.short_date)})`);
    const cardData = list.map(d => d.card_tomans);
    const transferData = list.map(d => d.transfer_tomans);
    const cashData = list.map(d => d.cash_tomans);
    const onlineData = list.map(d => d.online_tomans);

    if (state.barChart) {
      state.barChart.destroy();
    }

    state.barChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'کارتخوان (POS)',
            data: cardData,
            backgroundColor: 'rgba(6, 182, 212, 0.85)',
            borderColor: '#06b6d4',
            borderWidth: 1.5,
            borderRadius: 6,
            stack: 'Stack 0'
          },
          {
            label: 'کارت به کارت',
            data: transferData,
            backgroundColor: 'rgba(139, 92, 246, 0.85)',
            borderColor: '#8b5cf6',
            borderWidth: 1.5,
            borderRadius: 6,
            stack: 'Stack 0'
          },
          {
            label: 'نقدی',
            data: cashData,
            backgroundColor: 'rgba(16, 185, 129, 0.85)',
            borderColor: '#10b981',
            borderWidth: 1.5,
            borderRadius: 6,
            stack: 'Stack 0'
          },
          {
            label: 'درگاه آنلاین',
            data: onlineData,
            backgroundColor: 'rgba(245, 158, 11, 0.85)',
            borderColor: '#f59e0b',
            borderWidth: 1.5,
            borderRadius: 6,
            stack: 'Stack 0'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 12 },
              usePointStyle: true,
              pointStyle: 'circle',
              padding: 18
            }
          },
          tooltip: {
            rtl: true,
            titleFont: { family: 'Vazirmatn' },
            bodyFont: { family: 'Vazirmatn' },
            callbacks: {
              label: function(context) {
                const val = context.parsed.y || 0;
                return `${context.dataset.label}: ${val.toLocaleString('fa-IR')} تومان`;
              },
              footer: function(tooltipItems) {
                let sum = 0;
                tooltipItems.forEach(item => { sum += item.parsed.y; });
                return `جمع کل روز: ${sum.toLocaleString('fa-IR')} تومان`;
              }
            }
          }
        },
        scales: {
          x: {
            stacked: true,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 11 }
            }
          },
          y: {
            stacked: true,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 11 },
              callback: function(value) {
                if (value >= 1000000) return (value / 1000000).toLocaleString('fa-IR') + ' م.ت';
                return value.toLocaleString('fa-IR');
              }
            }
          }
        }
      }
    });
  }

  function render7DayCards() {
    const container = document.getElementById('daily-cards-container');
    if (!container) return;

    const list = state.data.seven_days_breakdown || [];
    container.innerHTML = '';

    list.forEach((day, index) => {
      const isToday = index === list.length - 1;
      const card = document.createElement('div');
      card.className = `glass rounded-2xl p-3.5 flex flex-col justify-between transition-all hover:border-cyan-400/40 ${
        isToday ? 'border-cyan-500/50 bg-cyan-500/10 shadow-lg shadow-cyan-500/10' : ''
      }`;

      card.innerHTML = `
        <div class="flex justify-between items-center mb-2 pb-2 border-b border-white/10">
          <div class="flex items-center gap-1.5">
            <span class="font-bold text-xs ${isToday ? 'text-cyan-300' : 'text-white'}">${day.day_name}</span>
            ${isToday ? '<span class="px-1.5 py-0.5 rounded text-[9px] bg-cyan-500/30 text-cyan-200 font-bold">امروز</span>' : ''}
          </div>
          <span class="text-[11px] text-muted">${toPersianDigits(day.date_str)}</span>
        </div>
        <div class="mb-3">
          <div class="text-[10px] text-muted">مجموع واریزی</div>
          <div class="text-sm font-extrabold text-emerald-400">${toToman(day.total_tomans)}</div>
        </div>
        <div class="space-y-1.5 text-[10px] bg-black/20 rounded-xl p-2 border border-white/5">
          <div class="flex justify-between text-cyan-300">
            <span>کارتخوان:</span>
            <span class="font-medium">${toPersianDigits(day.card_tomans ? day.card_tomans.toLocaleString() : '۰')}</span>
          </div>
          <div class="flex justify-between text-indigo-300">
            <span>کارت به کارت:</span>
            <span class="font-medium">${toPersianDigits(day.transfer_tomans ? day.transfer_tomans.toLocaleString() : '۰')}</span>
          </div>
          <div class="flex justify-between text-emerald-300">
            <span>نقدی:</span>
            <span class="font-medium">${toPersianDigits(day.cash_tomans ? day.cash_tomans.toLocaleString() : '۰')}</span>
          </div>
          <div class="flex justify-between text-muted pt-1 border-t border-white/5">
            <span>تعداد تراکنش:</span>
            <span class="font-bold text-white">${toPersianDigits(day.count)}</span>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  function renderDistributionChart() {
    const ctx = document.getElementById('chart-distribution');
    if (!ctx) return;

    const month = state.data.month_stats || {};
    const values = [
      month.method_card_tomans || 0,
      month.method_transfer_tomans || 0,
      month.method_cash_tomans || 0,
      month.method_online_tomans || 0
    ];

    if (state.donutChart) {
      state.donutChart.destroy();
    }

    state.donutChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['کارتخوان 💳', 'کارت به کارت 🏦', 'نقدی 💵', 'درگاه آنلاین 🌐'],
        datasets: [{
          data: values,
          backgroundColor: [
            '#06b6d4',
            '#8b5cf6',
            '#10b981',
            '#f59e0b'
          ],
          borderColor: 'rgba(15, 23, 42, 0.9)',
          borderWidth: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 11 },
              padding: 12
            }
          },
          tooltip: {
            rtl: true,
            titleFont: { family: 'Vazirmatn' },
            bodyFont: { family: 'Vazirmatn' },
            callbacks: {
              label: function(context) {
                const val = context.parsed || 0;
                return `${context.label}: ${val.toLocaleString('fa-IR')} تومان`;
              }
            }
          }
        },
        cutout: '68%'
      }
    });
  }

  function renderTopDebtors() {
    const container = document.getElementById('top-debtors-list');
    if (!container) return;

    const list = state.data.top_debtors || [];
    container.innerHTML = '';

    if (list.length === 0) {
      container.innerHTML = '<div class="text-center py-8 text-muted text-xs">هیچ بدهی معوقی ثبت نشده است 🎉</div>';
      return;
    }

    list.forEach(item => {
      const el = document.createElement('div');
      el.className = 'flex items-center justify-between p-3 rounded-xl bg-white/5 hover:bg-white/10 transition border border-white/5';
      el.innerHTML = `
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl bg-rose-500/20 text-rose-300 flex items-center justify-center font-bold text-xs">
            ${item.room_number ? 'اتاق ' + toPersianDigits(item.room_number) : '⚠️'}
          </div>
          <div>
            <div class="font-bold text-xs text-white">${item.name}</div>
            <div class="text-[11px] text-muted">${item.dormitory} • ${item.unpaid_months}</div>
          </div>
        </div>
        <div class="text-left">
          <div class="font-extrabold text-xs text-rose-400">${toToman(item.debt_tomans)}</div>
          <div class="text-[10px] text-amber-400 font-medium">${toPersianDigits(item.overdue_days)} روز تاخیر</div>
        </div>
      `;
      container.appendChild(el);
    });
  }

  function renderTransactionsTable() {
    const tbody = document.getElementById('tx-table-body');
    const countEl = document.getElementById('tx-count-display');
    if (!tbody) return;

    tbody.innerHTML = '';
    const list = state.filteredTransactions;

    if (countEl) {
      countEl.textContent = `نمایش ${toPersianDigits(list.length)} از ${toPersianDigits(state.transactions.length)} تراکنش`;
    }

    if (list.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center py-12 text-muted text-xs">
            تراکنشی منطبق با جستجو و فیلترهای جاری یافت نشد.
          </td>
        </tr>
      `;
      return;
    }

    list.forEach((tx, idx) => {
      const tr = document.createElement('tr');
      tr.className = 'border-b border-white/5 hover:bg-white/[0.03] transition text-xs';

      const isRent = tx.type === 'RENT';
      const badgeType = isRent
        ? '<span class="px-2 py-0.5 rounded-lg bg-blue-500/20 text-blue-300 text-[10px] font-bold">اجاره</span>'
        : '<span class="px-2 py-0.5 rounded-lg bg-purple-500/20 text-purple-300 text-[10px] font-bold">ودیعه</span>';

      tr.innerHTML = `
        <td class="py-3 px-3 text-muted text-[11px]">
          ${toPersianDigits(tx.date_str)} <span class="text-white/40">| ${toPersianDigits(tx.time_str)}</span>
        </td>
        <td class="py-3 px-3 font-medium text-white">
          ${tx.resident_name}
        </td>
        <td class="py-3 px-3 text-muted">
          اتاق ${toPersianDigits(tx.room_number)} <span class="text-white/30 text-[10px]">(${tx.dormitory})</span>
        </td>
        <td class="py-3 px-3">${badgeType}</td>
        <td class="py-3 px-3 text-muted text-[11px]">${tx.period_name || '-'}</td>
        <td class="py-3 px-3">
          <span class="text-muted text-[11px] font-medium">${tx.method_display}</span>
        </td>
        <td class="py-3 px-3 font-mono text-[11px] text-muted">${tx.reference_number || '-'}</td>
        <td class="py-3 px-3 font-bold text-emerald-400 text-left">
          ${toToman(tx.amount_tomans)}
          ${tx.has_discount ? `
            <span class="block text-[10px] text-amber-300 font-normal mt-0.5" title="${tx.discount_reason || ''}">
              🏷️ ${toToman(tx.discount_in_tomans)} تخفیف
            </span>
          ` : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  function filterTransactions() {
    const q = (document.getElementById('search-tx')?.value || '').trim().toLowerCase();
    const typeFilter = document.getElementById('filter-type')?.value || '';
    const methodFilter = document.getElementById('filter-method')?.value || '';

    state.filteredTransactions = state.transactions.filter(tx => {
      if (typeFilter && tx.type !== typeFilter) return false;
      if (methodFilter && tx.method !== methodFilter) return false;
      if (q) {
        const matchName = (tx.resident_name || '').toLowerCase().includes(q);
        const matchRoom = String(tx.room_number || '').includes(q);
        const matchRef = (tx.reference_number || '').toLowerCase().includes(q);
        const matchPeriod = (tx.period_name || '').toLowerCase().includes(q);
        if (!matchName && !matchRoom && !matchRef && !matchPeriod) return false;
      }
      return true;
    });

    renderTransactionsTable();
  }

  async function refreshData() {
    const btn = document.getElementById('btn-refresh-finance');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('animate-spin');
    }

    try {
      const res = await fetch('/dashboard/api/finance-data/');
      if (!res.ok) throw new Error('Network error');
      const data = await res.json();
      state.data = data;
      state.transactions = data.recent_transactions || [];
      state.filteredTransactions = [...state.transactions];

      renderKPIs();
      render7DayChart();
      render7DayCards();
      renderDistributionChart();
      renderTopDebtors();
      renderTransactionsTable();

      if (typeof Toast !== 'undefined') {
        Toast.show('داده‌های مالی با موفقیت به‌روزرسانی شدند', 'success', 3500);
      }
    } catch (e) {
      console.error('Failed to refresh finance data:', e);
      if (typeof Toast !== 'undefined') {
        Toast.show('خطا در به‌روزرسانی داده‌ها', 'danger', 4000);
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('animate-spin');
      }
    }
  }

  function bindEvents() {
    const searchInput = document.getElementById('search-tx');
    if (searchInput) searchInput.addEventListener('input', filterTransactions);

    const filterType = document.getElementById('filter-type');
    if (filterType) filterType.addEventListener('change', filterTransactions);

    const filterMethod = document.getElementById('filter-method');
    if (filterMethod) filterMethod.addEventListener('change', filterTransactions);

    const refreshBtn = document.getElementById('btn-refresh-finance');
    if (refreshBtn) refreshBtn.addEventListener('click', refreshData);
  }

  return { init, filterTransactions, refreshData };
})();

// Boot on DOM loaded
document.addEventListener('DOMContentLoaded', () => {
  FinanceApp.init();
});
