/* ===================================================================
   DATA LAYER
   Mock data shaped like the real Django models (Dormitory, Room,
   Resident, Transaction). Swap the bodies of these functions for
   real `fetch('/api/...')` calls when wiring up the backend — the
   rest of the app only depends on the shapes returned here.
=================================================================== */

const DB = (() => {
  const dorms = ["خوابگاه پسرانه 1", "خوابگاه پسرانه 2"];

  const rooms = [];
  let roomIdCounter = 1;
  dorms.forEach(dorm => {
    for (let i = 1; i <= 12; i++) {
      const cap = [2,3,4,4,6,2,3,4,2,6,4,3][i-1];
      const rentRial = [25000000,30000000,35000000,40000000][Math.floor(Math.random()*4)];
      rooms.push({ id: roomIdCounter++, dormitory: dorm, room_number: 100+i, capacity: cap, monthly_rent: rentRial, current_occupants: 0 });
    }
  });

  const firstNames = ["علی","محمد","رضا","حسین","جواد","امیر","سجاد","مهدی","پارسا","آرمان","کیان","نیما","سینا","فرهاد","بهزاد"];
  const lastNames = ["حسینی","رضایی","محمدی","احمدی","کریمی","موسوی","جعفری","صادقی","اکبری","نوری"];
  const occupations = ["STUDENT","EMPLOYED","OTHER"];

  const residents = [];
  for (let i = 0; i < 38; i++) {
    const room = rooms[Math.floor(Math.random()*rooms.length)];
    if (room.current_occupants >= room.capacity) continue;
    room.current_occupants++;
    const fn = firstNames[Math.floor(Math.random()*firstNames.length)];
    const ln = lastNames[Math.floor(Math.random()*lastNames.length)];
    const entry = new Date(2024, Math.floor(Math.random()*12), Math.floor(Math.random()*28)+1);
    const settled = new Date();
    settled.setDate(settled.getDate() - (Math.random() > 0.3 ? -10 : 40));
    residents.push({
      id: i+1,
      first_name: fn, last_name: ln, full_name: fn+" "+ln,
      national_code: "00"+(10000000+Math.floor(Math.random()*80000000)),
      phone_number: "0912"+Math.floor(1000000+Math.random()*8000000),
      parent_phone_number: "0912"+Math.floor(1000000+Math.random()*8000000),
      room, dormitory: room.dormitory,
      entry_date: entry.toISOString().split('T')[0],
      settled_until: settled.toISOString().split('T')[0],
      status: "ACTIVE",
      occupation: occupations[Math.floor(Math.random()*3)],
      monthly_payment_day: Math.floor(Math.random()*28)+1,
      is_in_debt: settled < new Date(),
      has_paid_this_month: Math.random() > 0.25
    });
  }

  const paymentMethods = ["CASH","CARD","BANK_TRANSFER","ONLINE_GATEWAY"];
  const transactions = [];
  residents.forEach(r => {
    const count = 2 + Math.floor(Math.random()*4);
    for (let j = 0; j < count; j++) {
      const method = paymentMethods[Math.floor(Math.random()*paymentMethods.length)];
      const type = j===0 && Math.random()>0.7 ? "DEPOSIT" : "RENT";
      const amount = type==="DEPOSIT" ? 600000000 : r.room.monthly_rent;
      const date = new Date();
      date.setMonth(date.getMonth() - Math.floor(Math.random()*6));
      date.setDate(Math.floor(Math.random()*28)+1);
      transactions.push({
        id: transactions.length+1,
        resident: r, dormitory: r.dormitory,
        amount, amount_toman: amount/10,
        transaction_type: type, payment_method: method,
        payment_date: date.toISOString().split('T')[0],
        reference_number: method!=="CASH" ? "IR"+Math.floor(1000000000+Math.random()*9000000000) : "",
        description: method==="CARD" ? "پرداخت با کارتخوان پذیرش" : method==="CASH" ? "دریافت نقدی" : "",
        is_approved: (method==="CASH"||method==="CARD") ? Math.random()>0.2 : true,
        applicable_rent: r.room.monthly_rent
      });
    }
  });

  return { dorms, rooms, residents, transactions };
})();
