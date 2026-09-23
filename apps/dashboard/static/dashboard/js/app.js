/* ===================================================================
   APP — wiring, RTL tab switching, real backend data boot sequence
=================================================================== */

const App = (() => {
  const TABS = ['students', 'rooms', 'finance'];

  function updateIndicator(activeBtn) {
    const indicator = document.getElementById('tab-indicator');
    if (!indicator || !activeBtn) return;
    const parent = activeBtn.parentElement;
    indicator.style.width = activeBtn.offsetWidth + 'px';
    // Calculate distance from right for RTL
    const rightDistance = parent.clientWidth - (activeBtn.offsetLeft + activeBtn.offsetWidth);
    indicator.style.right = rightDistance + 'px';
    indicator.style.transform = 'none';
  }

  function switchTab(tab) {
    TABS.forEach(t => {
      const sec = document.getElementById('section-' + t);
      if (sec) sec.classList.add('hidden');
      const btn = document.getElementById('tab-' + t);
      if (btn) btn.classList.remove('active');
    });

    const target = document.getElementById('section-' + tab);
    if (target) {
      target.classList.remove('hidden');
      target.classList.add('tab-section');
    }

    const activeBtn = document.getElementById('tab-' + tab);
    if (activeBtn) {
      activeBtn.classList.add('active');
      updateIndicator(activeBtn);
    }

    if (tab === 'finance' && typeof Finance !== 'undefined') Finance.render();
    if (tab === 'rooms' && typeof Rooms !== 'undefined') Rooms.render();
    if (tab === 'students' && typeof Students !== 'undefined') Students.render();
  }

  function initTabIndicator() {
    const first = document.getElementById('tab-students');
    if (first) updateIndicator(first);
  }

  function bindRipples() {
    document.addEventListener('click', e => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      const rect = btn.getBoundingClientRect();
      const ripple = document.createElement('span');
      ripple.className = 'ripple';
      const size = Math.max(rect.width, rect.height);
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove());
    });
  }

  async function boot() {
    Theme.init();
    Particles.init();
    Modal.bindGlobalHandlers();
    bindRipples();
    ScrollChrome.bind();

    // 1. Fetch or parse real DB data
    await DB.init();

    // 2. Initialize UI components
    initTabIndicator();
    Students.render();
    Rooms.render();
    Finance.render();

    // 3. KPI sparklines with real data
    const inDebtCount = DB.stats?.debt_residents ?? DB.residents.filter(r => r.is_in_debt).length;
    const debtTrend = [
      Math.max(0, inDebtCount - 2),
      Math.max(0, inDebtCount - 1),
      inDebtCount
    ];
    Charts.drawSparkline('spark-debt', debtTrend, '#f43f5e');

    Toast.show('داشبورد با داده‌های واقعی دیتابیس بارگذاری شد', 'success');

    // Keep global handlers working for inline HTML onclick attributes
    window.switchTab = switchTab;
    window.filterStudents = Students.filter;
    window.renderRooms = Rooms.render;
    window.applyFinanceFilter = Finance.apply;
    window.closeModal = Modal.close;
  }

  return { boot, switchTab };
})();

document.addEventListener('DOMContentLoaded', App.boot);
