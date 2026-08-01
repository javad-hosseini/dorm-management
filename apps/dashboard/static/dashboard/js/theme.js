/* ===================================================================
   THEME — dark / light / auto (system), persisted in localStorage
=================================================================== */

const Theme = (() => {
  const KEY = 'dorm-dashboard-theme';

  function apply(mode){
    const root = document.documentElement;
    const resolved = mode === 'auto'
      ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
      : mode;
    root.setAttribute('data-theme', resolved);
    document.querySelectorAll('.theme-toggle button').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    localStorage.setItem(KEY, mode);
    Charts.refreshThemeColors && Charts.refreshThemeColors();
  }

  function init(){
    const saved = localStorage.getItem(KEY) || 'dark';
    apply(saved);
    document.querySelectorAll('.theme-toggle button').forEach(b => {
      b.addEventListener('click', () => apply(b.dataset.mode));
    });
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
      if ((localStorage.getItem(KEY)||'dark') === 'auto') apply('auto');
    });
  }

  return { init, apply };
})();
