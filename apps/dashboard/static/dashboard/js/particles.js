/* ===================================================================
   PARTICLES — cheap ambient floating dots (pure CSS transforms)
=================================================================== */

const Particles = (() => {
  function init(count=18){
    if (Utils.prefersReducedMotion()) return;
    const root = document.getElementById('particles');
    if (!root) return;
    for (let i=0; i<count; i++){
      const p = document.createElement('span');
      p.className = 'particle';
      const size = 3 + Math.random()*6;
      p.style.width = p.style.height = size+'px';
      p.style.left = Math.random()*100+'vw';
      p.style.setProperty('--drift', (Math.random()*40-20)+'vw');
      p.style.animationDuration = (14 + Math.random()*16)+'s';
      p.style.animationDelay = (Math.random()*-20)+'s';
      root.appendChild(p);
    }
  }
  return { init };
})();
