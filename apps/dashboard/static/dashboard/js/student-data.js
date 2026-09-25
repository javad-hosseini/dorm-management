/* ===================================================================
   STUDENT DATA LAYER — Connected directly to Django Backend
=================================================================== */

const StudentDB = (() => {
  let me = {
    id: 0,
    full_name: "دانشجو",
    first_name: "دانشجو",
    last_name: "",
    national_code: "-",
    phone_number: "-",
    parent_phone_number: "-",
    occupation: "STUDENT",
    entry_date: "-",
    monthly_payment_day: 1,
    status: "ACTIVE",
    settled_until: "-",
    settled_until_display: "-",
    next_due_date: "-",
    next_due_date_display: "-",
    due_status_display: "-",
    days_until_due: 0,
    overdue_days: 0,
    room: { room_number: "-", dormitory: "-", capacity: 0, current_occupants: 0, monthly_rent: 0 },
    contract: { number: "-", start: "-", end: "-", deposit_toman: "-" }
  };

  let roommates = [];
  let transactions = [];
  let maintenance = [];
  let monthlyHistory = { labels: [], values: [] };
  let isLoaded = false;

  function parseData(payload) {
    if (!payload) return;
    if (payload.me) me = payload.me;
    roommates = payload.roommates || [];
    transactions = payload.transactions || [];
    maintenance = payload.maintenance || [];
    monthlyHistory = payload.monthlyHistory || { labels: [], values: [] };
    isLoaded = true;

    StudentDB.me = me;
    StudentDB.roommates = roommates;
    StudentDB.transactions = transactions;
    StudentDB.maintenance = maintenance;
    StudentDB.monthlyHistory = monthlyHistory;
  }

  async function init() {
    const scriptTag = document.getElementById('student-server-data');
    if (scriptTag && scriptTag.textContent.trim()) {
      try {
        const payload = JSON.parse(scriptTag.textContent);
        parseData(payload);
        return;
      } catch (err) {
        console.warn('Could not parse #student-server-data:', err);
      }
    }

    try {
      const res = await fetch('/dashboard/api/student-data/', {
        headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        const payload = await res.json();
        parseData(payload);
      }
    } catch (err) {
      console.error('Error fetching student data:', err);
    }
  }

  return {
    init,
    get isLoaded() { return isLoaded; },
    me,
    roommates,
    transactions,
    maintenance,
    monthlyHistory
  };
})();
