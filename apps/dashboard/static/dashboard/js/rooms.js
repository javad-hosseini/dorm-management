/* ===================================================================
   ROOMS TAB — occupancy ring visualization & room management
=================================================================== */

const Rooms = (() => {
  function ringSvg(percent, colorVar) {
    const r = 24, c = 2 * Math.PI * r;
    const clampedPercent = Math.min(100, Math.max(0, percent));
    const offset = c - (clampedPercent / 100) * c;
    return `
      <div class="ring-wrap">
        <svg width="56" height="56" viewBox="0 0 56 56">
          <circle class="ring-bg" cx="28" cy="28" r="${r}" stroke-width="5"></circle>
          <circle class="ring-fill" cx="28" cy="28" r="${r}" stroke-width="5"
            stroke="${colorVar}" stroke-dasharray="${c}" stroke-dashoffset="${offset}"></circle>
        </svg>
        <span class="ring-label">${clampedPercent}%</span>
      </div>`;
  }

  function populateRoomDormFilter() {
    const select = document.getElementById('filter-room-dorm');
    if (!select || !DB.dorms) return;
    const currentVal = select.value;
    select.innerHTML = '<option value="">همه خوابگاه‌ها</option>' +
      DB.dorms.map(d => `<option value="${d}">${d}</option>`).join('');
    if (currentVal) select.value = currentVal;
  }

  function render() {
    populateRoomDormFilter();
    const dormEl = document.getElementById('filter-room-dorm');
    const statEl = document.getElementById('filter-room-status');
    const container = document.getElementById('rooms-grid');
    if (!container) return;

    const dorm = dormEl ? dormEl.value : '';
    const stat = statEl ? statEl.value : '';

    let list = (DB.rooms || []).map(room => {
      const occupants = (DB.residents || []).filter(r =>
        r.room && r.room.id === room.id && r.status === 'ACTIVE'
      );
      const current_occupants = occupants.length;
      const is_empty = current_occupants === 0;
      const is_full = current_occupants >= room.capacity;
      const is_half = !is_empty && !is_full;
      return { ...room, occupants, current_occupants, is_empty, is_full, is_half };
    });

    if (dorm) list = list.filter(r => r.dormitory === dorm);
    if (stat === "empty") list = list.filter(r => r.current_occupants < r.capacity);
    if (stat === "full") list = list.filter(r => r.is_full);
    if (stat === "half") list = list.filter(r => r.is_half);

    if (!list || list.length === 0) {
      container.innerHTML = `<div class="empty-state col-span-full">🛏 اتاقی با این فیلتر یافت نشد</div>`;
    } else {
      container.innerHTML = list.map((r, i) => {
        const sizeClass = r.capacity >= 6 ? "min-h-[190px]" : r.capacity >= 4 ? "min-h-[160px]" : "min-h-[130px]";
        const bg = r.is_empty ? "room-empty" : r.is_full ? "room-full" : "room-half";
        const percent = r.capacity > 0 ? Math.round((r.current_occupants / r.capacity) * 100) : 0;
        const ringColor = r.is_empty ? 'var(--text-3)' : r.is_full ? 'var(--brand-500)' : 'var(--warning-500)';
        const dormTag = typeof r.dormitory === 'string' && r.dormitory.trim() ? r.dormitory.split(' ').pop() : 'خوابگاه';
        const emptyBeds = Math.max(0, r.capacity - r.current_occupants);

        return `
        <div onclick="Modal.openRoom(${r.id})" style="grid-row: span ${r.capacity >= 6 ? 2 : 1};"
             class="entity-card ${bg} ${sizeClass} p-4 flex flex-col justify-between cursor-pointer">
          <div class="flex justify-between items-start">
            <div>
              <div class="flex items-center gap-2">
                <p class="font-extrabold text-[16px]">اتاق ${r.room_number}</p>
                <span class="text-[10px] px-2 py-1 rounded-full chip">${dormTag}</span>
              </div>
              <p class="text-[11px] mt-1 text-muted">ظرفیت: ${r.capacity} | پر: ${r.current_occupants} | خالی: ${emptyBeds}</p>
            </div>
            ${ringSvg(percent, ringColor)}
          </div>
          <div>
            <p class="text-[10px] font-bold mt-2">اجاره: ${Utils.toToman(r.monthly_rent)}</p>
            <div class="flex flex-wrap gap-1 mt-2">
              ${r.occupants.map(o => `<span class="text-[9px] chip px-2 py-1 rounded-full">${o.first_name || o.full_name || 'ساکن'}</span>`).join('') || '<span class="text-[9px] text-faint">بدون ساکن (خالی)</span>'}
            </div>
          </div>
        </div>`;

      }).join('');
    }

    const fullCount = DB.stats?.full_rooms ?? (DB.rooms || []).filter(r => {
      const c = (DB.residents || []).filter(x => x.room && x.room.id === r.id && x.status === 'ACTIVE').length;
      return c >= r.capacity;
    }).length;

    const emptyCount = DB.stats?.empty_rooms ?? (DB.rooms || []).filter(r => {
      const c = (DB.residents || []).filter(x => x.room && x.room.id === r.id && x.status === 'ACTIVE').length;
      return c < r.capacity;
    }).length;

    const kpiFull = document.getElementById('kpi-full');
    const kpiEmpty = document.getElementById('kpi-empty');
    if (kpiFull) Utils.animateCounter(kpiFull, fullCount);
    if (kpiEmpty) Utils.animateCounter(kpiEmpty, emptyCount);
  }

  return { render, populateRoomDormFilter };
})();
