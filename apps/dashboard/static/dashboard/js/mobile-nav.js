/* ===================================================================
   MOBILE NAV — hamburger drawer (reuses the same open/close motion
   language as Modal, but drives a side-drawer instead of a centered
   panel). Generic: works on any page that includes a #drawer + #hamburger-btn.
=================================================================== */

const MobileNav = (() => {
  let startX = null;

  function open(){
    document.getElementById('drawer-backdrop').classList.add('show');
    document.getElementById('hamburger-btn').classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function close(){
    document.getElementById('drawer-backdrop').classList.remove('show');
    document.getElementById('hamburger-btn').classList.remove('open');
    document.body.style.overflow = '';
  }
  function toggle(){
    document.getElementById('drawer-backdrop').classList.contains('show') ? close() : open();
  }

  function bind(){
    const btn = document.getElementById('hamburger-btn');
    const backdrop = document.getElementById('drawer-backdrop');
    if (!btn || !backdrop) return;

    btn.addEventListener('click', toggle);
    backdrop.addEventListener('click', e => { if (e.target === backdrop) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });

    const panel = document.getElementById('drawer-panel');
    panel.addEventListener('touchstart', e => { startX = e.touches[0].clientX; }, { passive:true });
    panel.addEventListener('touchmove', e => {
      if (startX === null) return;
      const dx = e.touches[0].clientX - startX;
      if (dx > 0) panel.style.transform = `translateX(${dx}px)`;
    }, { passive:true });
    panel.addEventListener('touchend', e => {
      const dx = e.changedTouches[0].clientX - (startX||0);
      panel.style.transform = '';
      if (dx > 90) close();
      startX = null;
    });

    // close drawer automatically whenever a nav link inside it is used
    panel.querySelectorAll('[data-menu]').forEach(el => el.addEventListener('click', close));
  }

  return { open, close, toggle, bind };
})();
