/* ===================================================================
   STUDENT DATA LAYER
   Mock data shaped like the real models. Swap function bodies for
   `fetch('/api/students/me/...')` calls once the backend is wired —
   student.js only depends on these shapes.
=================================================================== */

const StudentDB = (() => {
  const me = {
    id: 3, first_name: "جواد", last_name: "حسینی", full_name: "جواد حسینی",
    national_code: "0012345678", phone_number: "09121234567", parent_phone_number: "09129876543",
    occupation: "STUDENT", entry_date: "1403/06/01", monthly_payment_day: 5,
    status: "ACTIVE", is_in_debt: false, settled_until: "1403/08/15",
    room: { room_number: 302, dormitory: "خوابگاه پسرانه 1", capacity: 4, current_occupants: 3, monthly_rent: 35000000 },
    contract: { number: "RES302", start: "1403/06/01", end: "1404/06/01", deposit_toman: "60,000,000 تومان" }
  };

  const roommates = [
    { id:1, first_name:"علی", last_name:"رضایی", full_name:"علی رضایی", phone:"09121230001", entry:"1403/05/10", national:"0011111111" },
    { id:2, first_name:"محمد", last_name:"احمدی", full_name:"محمد احمدی", phone:"09121230002", entry:"1403/06/01", national:"0022222222" },
    { id:3, first_name:"جواد", last_name:"حسینی", full_name:"جواد حسینی (شما)", phone:"09121234567", entry:"1403/06/01", national:"0012345678", me:true },
  ];

  const transactions = [
    { type:"RENT", amount:35000000, toman:"3,500,000 تومان", method:"ONLINE_GATEWAY", date:"1403/07/05", ref:"IR123456789", desc:"پرداخت آنلاین مهر" },
    { type:"RENT", amount:35000000, toman:"3,500,000 تومان", method:"BANK_TRANSFER", date:"1403/06/05", ref:"603799123456", desc:"کارت به کارت" },
    { type:"DEPOSIT", amount:600000000, toman:"60,000,000 تومان", method:"CARD", date:"1403/06/01", ref:"", desc:"ودیعه اولیه" },
    { type:"RENT", amount:35000000, toman:"3,500,000 تومان", method:"CASH", date:"1403/08/05", ref:"", desc:"پرداخت نقدی" },
  ];

  const maintenance = [
    { id:1, title:"خرابی کولر گازی", date:"1403/07/20", room:302, status:"در حال بررسی" },
    { id:2, title:"تعویض لامپ", date:"1403/06/15", room:302, status:"انجام شد" },
  ];

  const monthlyHistory = { labels:['تیر','مرداد','شهریور','مهر','آبان','آذر'], values:[3500000,3500000,60000000,3500000,3500000,0] };

  return { me, roommates, transactions, maintenance, monthlyHistory };
})();
