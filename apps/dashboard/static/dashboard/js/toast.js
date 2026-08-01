/* ===================================================================
   TOAST — success/warning/error/info notifications
=================================================================== */

const Toast = (() => {
  const ICONS = { success:'✅', warning:'⚠️', danger:'⛔', info:'ℹ️' };

  function show(message, type='info', duration=3200){
    const root = document.getElementById('toast-root');
    if (!root) return;
    const el = document.createElement('div');
    el.className = `toast glass toast-${type}`;
    el.innerHTML = `<span>${ICONS[type]||''}</span><span>${message}</span>`;
    root.appendChild(el);
    setTimeout(() => {
      el.classList.add('leaving');
      el.addEventListener('animationend', () => el.remove(), { once:true });
    }, duration);
  }

  return { show };
})();
