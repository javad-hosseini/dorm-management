/* ===================================================================
   DATA LAYER — Connected directly to Django Backend
   Reads bootstrap JSON from DOM if present, or fetches from API.
=================================================================== */

const DB = (() => {
  let dorms = [];
  let rooms = [];
  let residents = [];
  let transactions = [];
  let stats = {};
  let isLoaded = false;

  function parseData(payload) {
    if (!payload) return;
    dorms = payload.dorms || [];
    rooms = payload.rooms || [];
    residents = payload.residents || [];
    transactions = payload.transactions || [];
    stats = payload.stats || {};
    isLoaded = true;

    // Update public properties on DB object
    DB.dorms = dorms;
    DB.rooms = rooms;
    DB.residents = residents;
    DB.transactions = transactions;
    DB.stats = stats;
  }

  async function init() {
    // 1. Try reading pre-rendered JSON script from DOM (instant load)
    const scriptTag = document.getElementById('server-data');
    if (scriptTag && scriptTag.textContent.trim()) {
      try {
        const payload = JSON.parse(scriptTag.textContent);
        parseData(payload);
        return;
      } catch (err) {
        console.warn('Could not parse #server-data JSON:', err);
      }
    }

    // 2. Otherwise fetch from API
    await refresh();
  }

  async function refresh() {
    try {
      const res = await fetch('/dashboard/api/admin-data/', {
        headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        const payload = await res.json();
        parseData(payload);
      } else {
        console.error('API error loading dashboard data:', res.status);
      }
    } catch (err) {
      console.error('Network error loading dashboard data:', err);
    }
  }

  return {
    init,
    refresh,
    get isLoaded() { return isLoaded; },
    dorms,
    rooms,
    residents,
    transactions,
    stats,
  };
})();
