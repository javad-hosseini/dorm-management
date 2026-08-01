/* ===================================================================
   APP — wiring, tab switching, scroll chrome, boot sequence
=================================================================== */

const App = (() => {
  const TABS = ['students','rooms','finance'];

  function switchTab(tab){
    TABS.forEach(t => {
      document.getElementById('section-'+t).classList.add('hidden');
    });
    const target = document.getElementById('section-'+tab);
    target.classList.remove('hidden');
    target.classList.add('tab-section');

    const indicator = document.getElementById('tab-indicator');
    const activeBtn = document.getElementById('tab-'+tab);
    TABS.forEach(t => document.getElementById('tab-'+t).classList.remove('active'));
    activeBtn.classList.add('active');
    indicator.style.width = activeBtn.offsetWidth + 'px';
    indicator.style.transform = `translateX(${activeBtn.offsetLeft * -1}px)`;
    indicator.style.right = activeBtn.offsetLeft + 'px';

    if (tab === 'finance') Finance.render();
  }

  function initTabIndicator(){
    const first = document.getElementById('tab-students');
    const indicator = document.getElementById('tab-indicator');
    indicator.style.width = first.offsetWidth + 'px';
    indicator.style.right = first.offsetLeft + 'px';
  }

  function bindRipples(){
    document.addEventListener('click', e => {
      const btn = e.target.closest('.btn');
      if (!btn) return;
      const rect = btn.getBoundingClientRect();
      const ripple = document.createElement('span');
      ripple.className = 'ripple';
      const size = Math.max(rect.width, rect.height);
      ripple.style.width = ripple.style.height = size+'px';
      ripple.style.left = (e.clientX - rect.left - size/2)+'px';
      ripple.style.top = (e.clientY - rect.top - size/2)+'px';
      btn.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove());
    });
  }

  function boot(){
    Theme.init();
    Particles.init();
    Modal.bindGlobalHandlers();
    bindRipples();
    ScrollChrome.bind();
    initTabIndicator();

    Students.render();
    Rooms.render();
    Finance.render();

    // KPI sparklines (ambient, always visible in header)
    const debtTrend = [4,6,5,7,6,8,DB.residents.filter(r=>r.is_in_debt).length];
    Charts.drawSparkline('spark-debt', debtTrend, '#f43f5e');

    Toast.show('داشبورد با موفقیت بارگذاری شد', 'success');

    window.switchTab = switchTab; // keep inline onclick="" handlers working
    window.filterStudents = Students.filter;
    window.renderRooms = Rooms.render;
    window.applyFinanceFilter = Finance.apply;
    window.closeModal = Modal.close;
  }

  return { boot, switchTab };
})();

document.addEventListener('DOMContentLoaded', App.boot);
