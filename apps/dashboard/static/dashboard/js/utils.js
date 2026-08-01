/* ===================================================================
   UTILS — formatting, debounce, animated counters
=================================================================== */

const Utils = (() => {
  function toToman(rial){ return (rial/10).toLocaleString('fa-IR') + " تومان"; }
  function methodLabel(m){ return {CASH:"نقدی 💵", CARD:"کارتخوان 💳", BANK_TRANSFER:"کارت به کارت 🏦", ONLINE_GATEWAY:"درگاه آنلاین 🌐"}[m] || m; }
  function typeLabel(t){ return t==="RENT" ? "اجاره" : "ودیعه"; }

  function debounce(fn, wait=250){
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
  }

  /** Animate a number from 0 -> target inside el.textContent, formatted with a callback. */
  function animateCounter(el, target, { duration=900, format=(n)=>Math.round(n).toLocaleString('fa-IR') } = {}){
    if (prefersReducedMotion()) { el.textContent = format(target); return; }
    const start = performance.now();
    const from = 0;
    function tick(now){
      const p = Math.min(1, (now-start)/duration);
      const eased = 1 - Math.pow(1-p, 3);
      el.textContent = format(from + (target-from)*eased);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function prefersReducedMotion(){
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  return { toToman, methodLabel, typeLabel, debounce, animateCounter, prefersReducedMotion };
})();
