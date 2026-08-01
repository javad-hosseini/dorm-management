/* ===================================================================
   SCROLL CHROME — top progress bar + back-to-top FAB.
   Shared by the Admin Dashboard and the Student Portal.
=================================================================== */

const ScrollChrome = (() => {
  function bind(){
    const bar = document.getElementById('scroll-progress');
    const fab = document.getElementById('fab-top');
    if (!bar || !fab) return;
    window.addEventListener('scroll', () => {
      const h = document.documentElement;
      const pct = (h.scrollTop / (h.scrollHeight - h.clientHeight || 1)) * 100;
      bar.style.width = pct + '%';
      fab.classList.toggle('show', h.scrollTop > 400);
    }, { passive:true });
    fab.addEventListener('click', () => window.scrollTo({ top:0, behavior:'smooth' }));
  }
  return { bind };
})();
