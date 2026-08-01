/* ===================================================================
   ROOMS TAB — occupancy ring visualization
=================================================================== */

const Rooms = (() => {
  function ringSvg(percent, colorVar){
    const r = 24, c = 2*Math.PI*r;
    const offset = c - (percent/100)*c;
    return `
      <div class="ring-wrap">
        <svg width="56" height="56" viewBox="0 0 56 56">
          <circle class="ring-bg" cx="28" cy="28" r="${r}" stroke-width="5"></circle>
          <circle class="ring-fill" cx="28" cy="28" r="${r}" stroke-width="5"
            stroke="${colorVar}" stroke-dasharray="${c}" stroke-dashoffset="${offset}"></circle>
        </svg>
        <span class="ring-label">${percent}%</span>
      </div>`;
  }

  function render(){
    const dorm = document.getElementById('filter-room-dorm').value;
    const stat = document.getElementById('filter-room-status').value;
    const container = document.getElementById('rooms-grid');

    let list = DB.rooms.map(room => {
      const occupants = DB.residents.filter(r => r.room.id === room.id);
      room.current_occupants = occupants.length;
      const is_empty = occupants.length === 0;
      const is_full = occupants.length >= room.capacity;
      const is_half = !is_empty && !is_full;
      return { ...room, occupants, is_empty, is_full, is_half };
    });
    if (dorm) list = list.filter(r => r.dormitory === dorm);
    if (stat==="empty") list = list.filter(r => r.is_empty);
    if (stat==="full") list = list.filter(r => r.is_full);
    if (stat==="half") list = list.filter(r => r.is_half);

    container.innerHTML = list.map((r,i) => {
      const sizeClass = r.capacity>=6 ? "min-h-[190px]" : r.capacity>=4 ? "min-h-[160px]" : "min-h-[130px]";
      const bg = r.is_empty ? "room-empty" : r.is_full ? "room-full" : "room-half";
      const percent = Math.round((r.current_occupants/r.capacity)*100);
      const ringColor = r.is_empty ? 'var(--text-3)' : r.is_full ? 'var(--brand-500)' : 'var(--warning-500)';
      return `
      <div onclick="Modal.openRoom(${r.id})" style="grid-row: span ${r.capacity>=6?2:1}; animation-delay:${Math.min(i,10)*25}ms"
           class="entity-card glass ${bg} ${sizeClass} p-4 flex flex-col justify-between">
        <div class="flex justify-between items-start">
          <div>
            <div class="flex items-center gap-2">
              <p class="font-extrabold text-[16px]">اتاق ${r.room_number}</p>
              <span class="text-[10px] px-2 py-1 rounded-full glass">${r.dormitory.split(' ').pop()}</span>
            </div>
            <p class="text-[11px] mt-1 text-muted">ظرفیت: ${r.capacity} | پر: ${r.current_occupants} | خالی: ${r.capacity - r.current_occupants}</p>
          </div>
          ${ringSvg(percent, ringColor)}
        </div>
        <div>
          <p class="text-[10px] font-bold mt-2">اجاره: ${Utils.toToman(r.monthly_rent)}</p>
          <div class="flex flex-wrap gap-1 mt-2">${r.occupants.map(o=>`<span class="text-[9px] glass px-2 py-1 rounded-full">${o.first_name}</span>`).join('') || '<span class="text-[9px] text-faint">بدون ساکن</span>'}</div>
        </div>
      </div>`;
    }).join('') || `<div class="empty-state col-span-full">🛏 اتاقی با این فیلتر یافت نشد</div>`;

    Utils.animateCounter(document.getElementById('kpi-full'), DB.rooms.filter(r=>{
      const c = DB.residents.filter(x=>x.room.id===r.id).length; return c>=r.capacity;
    }).length);
    Utils.animateCounter(document.getElementById('kpi-empty'), DB.rooms.filter(r=>
      DB.residents.filter(x=>x.room.id===r.id).length===0
    ).length);
  }

  return { render };
})();
