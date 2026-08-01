/* ===================================================================
   FINANCE TAB
=================================================================== */

const Finance = (() => {
  function getFiltered(){
    const from = document.getElementById('finance-from').value;
    const to = document.getElementById('finance-to').value;
    const type = document.getElementById('finance-type').value;
    const method = document.getElementById('finance-method').value;
    return DB.transactions.filter(t => {
      if (from && t.payment_date < from) return false;
      if (to && t.payment_date > to) return false;
      if (type && t.transaction_type !== type) return false;
      if (method && t.payment_method !== method) return false;
      return true;
    });
  }

  function render(){
    const filtered = getFiltered();
    const total = filtered.reduce((s,t)=>s+t.amount,0);
    const rentTotal = filtered.filter(t=>t.transaction_type==='RENT').reduce((s,t)=>s+t.amount,0);
    const depositTotal = filtered.filter(t=>t.transaction_type==='DEPOSIT').reduce((s,t)=>s+t.amount,0);
    const pending = filtered.filter(t=>!t.is_approved).length;

    document.getElementById('fin-total').innerText = Utils.toToman(total);
    document.getElementById('fin-rent').innerText = Utils.toToman(rentTotal);
    document.getElementById('fin-deposit').innerText = Utils.toToman(depositTotal);
    document.getElementById('fin-pending').innerText = pending + " تراکنش";
    document.getElementById('fin-avg').innerText = filtered.length ? Utils.toToman(total/filtered.length) : "0";

    const months = {};
    filtered.forEach(t => { const m = t.payment_date.slice(0,7); months[m] = (months[m]||0) + t.amount; });
    const sortedMonths = Object.keys(months).sort();
    Charts.renderMonthly(sortedMonths, months);

    const methods = {};
    filtered.forEach(t => { methods[t.payment_method] = (methods[t.payment_method]||0) + t.amount; });
    Charts.renderMethods(Object.keys(methods).map(Utils.methodLabel), Object.values(methods).map(v=>v/10));

    document.getElementById('finance-recent').innerHTML = filtered.slice(0,15).map(t => `
      <div class="glass rounded-xl p-2.5 flex justify-between text-[11px] animate-fadeInUp">
        <div><p class="font-bold">${t.resident.full_name} - ${Utils.toToman(t.amount)}</p><p class="text-[10px] text-muted">${t.payment_date} | ${Utils.methodLabel(t.payment_method)}</p></div>
        <span class="text-[9px] px-2 py-1 rounded-full ${t.transaction_type==='RENT' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'}">${Utils.typeLabel(t.transaction_type)}</span>
      </div>
    `).join('');

    const currentMonthIncome = DB.transactions.filter(t => {
      const d = new Date(t.payment_date); const now = new Date();
      return d.getMonth()===now.getMonth() && d.getFullYear()===now.getFullYear();
    }).reduce((s,t)=>s+t.amount,0);
    document.getElementById('kpi-income').innerText = Utils.toToman(currentMonthIncome);

    // sparkline: last 8 months trend regardless of filters
    const trendMonths = {};
    DB.transactions.forEach(t => { const m = t.payment_date.slice(0,7); trendMonths[m] = (trendMonths[m]||0) + t.amount; });
    const trendVals = Object.keys(trendMonths).sort().slice(-8).map(m=>trendMonths[m]);
    Charts.drawSparkline('spark-income', trendVals.length ? trendVals : [0], '#22c55e');
  }

  function apply(){ render(); Toast.show('فیلترهای مالی اعمال شد', 'success'); }

  return { render, apply, getFiltered };
})();
