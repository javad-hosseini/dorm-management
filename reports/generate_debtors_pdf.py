#!/usr/bin/env python3
"""
Debtors PDF Report Generator - Dormitory Management System
Generates an executive, high-aesthetic PDF report of all active overdue debtors.

Usage:
    .venv/bin/python reports/generate_debtors_pdf.py [--output <path>] [--date YYYY/MM/DD]
"""

import os
import sys
import argparse
import subprocess
import tempfile
from typing import Optional, List, Dict, Any

# Ensure Django environment is configured
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

import jdatetime
from apps.dormitory.models import Resident, Room, Dormitory, Transaction


def get_persian_weekday_name(date: jdatetime.date) -> str:
    weekdays = {
        0: 'شنبه', 1: 'یکشنبه', 2: 'دوشنبه', 3: 'سه‌شنبه',
        4: 'چهارشنبه', 5: 'پنج‌شنبه', 6: 'جمعه'
    }
    return weekdays.get(date.weekday(), '')


def fetch_debtors_data(target_date: Optional[jdatetime.date] = None, dormitory_id: Optional[int] = None) -> Dict[str, Any]:
    """Queries active residents and compiles detailed debt and payment statistics."""
    if target_date is None:
        target_date = jdatetime.date.today()

    residents_qs = Resident.objects.filter(status="ACTIVE", room__isnull=False).select_related("room", "dormitory")
    if dormitory_id:
        residents_qs = residents_qs.filter(dormitory_id=dormitory_id)

    total_capacity = sum(r.capacity for r in Room.objects.all())
    active_count = residents_qs.count()
    empty_beds = max(0, total_capacity - active_count)

    debtors: List[Dict[str, Any]] = []
    total_debt_tomans = 0

    for r in residents_qs:
        debt = r.total_debt_amount_tomans
        if debt > 0:
            total_debt_tomans += debt
            overdue_days = r.overdue_days
            last_tx = r.transactions.filter(transaction_type__in=["RENT", "DEPOSIT"]).order_by("-payment_date", "-id").first()
            
            settled_str = r.settled_until.strftime("%Y/%m/%d") if r.settled_until else (r.entry_date.strftime("%Y/%m/%d") if r.entry_date else "-")
            room_rate = int(r.room.monthly_rent / 10) if r.room and r.room.monthly_rent else 0
            
            last_tx_info = {
                "amount_tomans": int(last_tx.amount / 10) if last_tx else 0,
                "date_str": last_tx.payment_date.strftime("%Y/%m/%d") if (last_tx and last_tx.payment_date) else "-",
                "method_str": last_tx.get_payment_method_display() if (last_tx and hasattr(last_tx, "get_payment_method_display")) else (last_tx.payment_method if last_tx else "-"),
                "desc": last_tx.description if (last_tx and last_tx.description) else "",
            }

            debtors.append({
                "id": r.id,
                "name": r.full_name,
                "room_number": r.room.room_number if r.room else "-",
                "room_name": str(r.room.room_number) if r.room else "",
                "room_rate": room_rate,
                "settled_until_str": settled_str,
                "overdue_days": overdue_days,
                "debt_tomans": debt,
                "last_tx": last_tx_info,
            })

    # Sort primarily by overdue days descending, secondarily by debt amount descending
    debtors.sort(key=lambda x: (x["overdue_days"], x["debt_tomans"]), reverse=True)

    max_delay = debtors[0]["overdue_days"] if debtors else 0
    max_delay_room = debtors[0]["room_number"] if debtors else "-"
    max_debt = max((d["debt_tomans"] for d in debtors), default=0)

    dorm_name = "مجموعه خوابگاه‌ها"
    if dormitory_id:
        dorm = Dormitory.objects.filter(id=dormitory_id).first()
        if dorm:
            dorm_name = dorm.name

    return {
        "target_date": target_date,
        "target_date_str": target_date.strftime("%Y/%m/%d"),
        "weekday_name": get_persian_weekday_name(target_date),
        "dorm_name": dorm_name,
        "total_debt_tomans": total_debt_tomans,
        "debtors_count": len(debtors),
        "empty_beds": empty_beds,
        "max_delay": max_delay,
        "max_delay_room": max_delay_room,
        "max_debt": max_debt,
        "debtors": debtors,
    }


def render_html_report(data: Dict[str, Any]) -> str:
    """Generates the full styled HTML document for PDF rendering."""
    # Build Table Rows
    table_rows_html = []
    for idx, d in enumerate(data["debtors"], 1):
        # Classify delay badge
        days = d["overdue_days"]
        if days >= 15:
            delay_class = "delay-high"
        elif days >= 8:
            delay_class = "delay-med"
        else:
            delay_class = "delay-low"

        row = f"""
      <tr>
        <td>{idx}</td>
        <td class="resident-name">{d['name']}</td>
        <td><span class="room-badge">{d['room_number']}</span></td>
        <td>{d['settled_until_str']}</td>
        <td><span class="delay-pill {delay_class}">{days} روز تأخیر</span></td>
        <td class="amount-debt">{d['debt_tomans']:,}</td>
        <td>{d['last_tx']['amount_tomans']:,}</td>
        <td>{d['last_tx']['date_str']}</td>
      </tr>"""
        table_rows_html.append(row)

    # Build Detail Cards
    cards_html = []
    for idx, d in enumerate(data["debtors"], 1):
        days = d["overdue_days"]
        delay_color = "#e11d48" if days >= 15 else ("#d97706" if days >= 8 else "#0284c7")
        method_desc = d['last_tx']['method_str']
        if d['last_tx']['desc']:
            method_desc += f" - {d['last_tx']['desc']}"

        card = f"""
    <div class="debtor-card">
      <div class="card-top">
        <span class="card-title">{idx}. {d['name']}</span>
        <span class="room-badge">اتاق {d['room_number']}</span>
      </div>
      <div class="card-row"><span class="card-label">مبلغ بدهی تا امروز:</span><span class="card-value amount-debt">{d['debt_tomans']:,} تومان</span></div>
      <div class="card-row"><span class="card-label">موعد سررسید:</span><span class="card-value">{d['settled_until_str']} (<span style="color:{delay_color}; font-weight:700;">{days} روز تأخیر</span>)</span></div>
      <div class="card-row"><span class="card-label">نرخ اجاره اتاق:</span><span class="card-value">{d['room_rate']:,} تومان در ماه</span></div>
      <div class="card-row"><span class="card-label">آخرین واریزی:</span><span class="card-value">{d['last_tx']['amount_tomans']:,} تومان ({method_desc})</span></div>
      <div class="card-row"><span class="card-label">تاریخ آخرین پرداخت:</span><span class="card-value">{d['last_tx']['date_str']}</span></div>
    </div>"""
        cards_html.append(card)

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>گزارش تفصیلی بدهکاران خوابگاه - {data['target_date_str']}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&display=swap');

  @page {{
    size: A4 portrait;
    margin: 10mm 11mm 12mm 11mm;
    @bottom-center {{
      content: "صفحه " counter(page) " از " counter(pages);
      font-family: 'Vazirmatn', sans-serif;
      font-size: 8.5pt;
      color: #64748b;
    }}
  }}

  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}

  body {{
    font-family: 'Vazirmatn', 'Noto Sans Arabic', Tahoma, sans-serif;
    color: #1e293b;
    background-color: #ffffff;
    margin: 0;
    padding: 0;
    font-size: 10pt;
    line-height: 1.5;
  }}

  .header {{
    border-bottom: 2px solid #0f172a;
    padding-bottom: 12px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}

  .title-area h1 {{
    font-size: 18pt;
    font-weight: 800;
    color: #0f172a;
    margin: 0 0 4px 0;
  }}

  .title-area p {{
    font-size: 10pt;
    color: #475569;
    margin: 0;
  }}

  .meta-box {{
    text-align: left;
    font-size: 9pt;
    color: #334155;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 14px;
    min-width: 170px;
  }}

  .meta-box div {{
    margin-bottom: 3px;
  }}

  .meta-box div:last-child {{
    margin-bottom: 0;
  }}

  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 18px;
  }}

  .stat-card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: center;
  }}

  .stat-card.alert {{
    background: #fff1f2;
    border-color: #fecdd3;
  }}

  .stat-card.warning {{
    background: #fffbeb;
    border-color: #fde68a;
  }}

  .stat-label {{
    font-size: 8.5pt;
    color: #64748b;
    margin-bottom: 4px;
    font-weight: 500;
  }}

  .stat-card.alert .stat-label {{ color: #be123c; }}
  .stat-card.warning .stat-label {{ color: #b45309; }}

  .stat-value {{
    font-size: 13pt;
    font-weight: 800;
    color: #0f172a;
  }}

  .stat-card.alert .stat-value {{ color: #e11d48; }}
  .stat-card.warning .stat-value {{ color: #d97706; }}

  .section-title {{
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
    border-right: 4px solid #2563eb;
    padding-right: 8px;
    margin: 18px 0 10px 0;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin-bottom: 20px;
    page-break-inside: auto;
  }}

  tr {{
    page-break-inside: avoid;
    page-break-after: auto;
  }}

  th {{
    background: #1e293b;
    color: #ffffff;
    font-weight: 600;
    text-align: center;
    padding: 7px 5px;
    border: 1px solid #0f172a;
  }}

  td {{
    padding: 6px 6px;
    border: 1px solid #cbd5e1;
    text-align: center;
  }}

  tbody tr:nth-child(even) {{
    background-color: #f8fafc;
  }}

  tbody tr:hover {{
    background-color: #f1f5f9;
  }}

  .resident-name {{
    font-weight: 700;
    color: #0f172a;
    text-align: right;
  }}

  .room-badge {{
    display: inline-block;
    background: #e2e8f0;
    color: #334155;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 8pt;
  }}

  .delay-pill {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 12px;
    font-size: 7.5pt;
    font-weight: 700;
  }}

  .delay-high {{
    background: #ffe4e6;
    color: #e11d48;
    border: 1px solid #fecdd3;
  }}

  .delay-med {{
    background: #fef3c7;
    color: #d97706;
    border: 1px solid #fde68a;
  }}

  .delay-low {{
    background: #e0f2fe;
    color: #0284c7;
    border: 1px solid #bae6fd;
  }}

  .amount-debt {{
    font-weight: 800;
    color: #be123c;
  }}

  .total-row {{
    background: #0f172a !important;
    color: #ffffff;
    font-weight: 800;
    font-size: 9.5pt;
  }}

  .total-row td {{
    border-color: #0f172a;
    padding: 8px;
    color: #ffffff;
  }}

  .page-break {{
    page-break-before: always;
  }}

  .cards-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }}

  .debtor-card {{
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 10px;
    background: #ffffff;
    page-break-inside: avoid;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  }}

  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 4px;
    margin-bottom: 6px;
  }}

  .card-title {{
    font-size: 10pt;
    font-weight: 700;
    color: #0f172a;
  }}

  .card-row {{
    display: flex;
    justify-content: space-between;
    margin-bottom: 2.5px;
    font-size: 8pt;
  }}

  .card-label {{
    color: #64748b;
  }}

  .card-value {{
    font-weight: 600;
    color: #1e293b;
  }}

  .footer-note {{
    margin-top: 15px;
    padding: 10px;
    background: #f8fafc;
    border-right: 3px solid #64748b;
    font-size: 8pt;
    color: #475569;
    border-radius: 0 4px 4px 0;
  }}
</style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <div class="title-area">
      <h1>گزارش تفصیلی وضعیت بدهکاران معوق</h1>
      <p>{data['dorm_name']} • تاریخ تهیه: {data['weekday_name']} {data['target_date_str']}</p>
    </div>
    <div class="meta-box">
      <div><strong>سرپرست:</strong> جواد حسینی</div>
      <div><strong>کد ناظر:</strong> ۰۲۰۱۰۱۴۳۱۸</div>
      <div><strong>تخت خالی:</strong> {data['empty_beds']} تخت</div>
    </div>
  </div>

  <!-- STATS -->
  <div class="stats-grid">
    <div class="stat-card alert">
      <div class="stat-label">مجموع کل بدهی معوق</div>
      <div class="stat-value">{data['total_debt_tomans']:,} <span style="font-size: 8pt; font-weight: normal;">تومان</span></div>
    </div>
    <div class="stat-card warning">
      <div class="stat-label">تعداد کل بدهکاران</div>
      <div class="stat-value">{data['debtors_count']} <span style="font-size: 8pt; font-weight: normal;">نفر</span></div>
    </div>
    <div class="stat-card">
      <div class="stat-label">بیشترین روز تأخیر</div>
      <div class="stat-value">{data['max_delay']} <span style="font-size: 8pt; font-weight: normal;">روز (اتاق {data['max_delay_room']})</span></div>
    </div>
    <div class="stat-card">
      <div class="stat-label">بیشترین مبلغ بدهی</div>
      <div class="stat-value">{data['max_debt']:,} <span style="font-size: 8pt; font-weight: normal;">تومان</span></div>
    </div>
  </div>

  <!-- SECTION 1: COMPACT TABLE -->
  <div class="section-title">جدول جامع مدیریتی بدهکاران (به ترتیب اولویت روزهای دیرکرد)</div>
  <table>
    <thead>
      <tr>
        <th style="width: 5%;">ردیف</th>
        <th style="width: 20%; text-align: right; padding-right: 8px;">نام و نام خانوادگی</th>
        <th style="width: 8%;">اتاق</th>
        <th style="width: 12%;">موعد سررسید</th>
        <th style="width: 11%;">میزان تأخیر</th>
        <th style="width: 15%;">بدهی تا امروز (تومان)</th>
        <th style="width: 15%;">آخرین پرداختی (تومان)</th>
        <th style="width: 14%;">تاریخ آخرین واریز</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows_html)}
    </tbody>
    <tfoot>
      <tr class="total-row">
        <td colspan="5" style="text-align: right; padding-right: 14px;">مجموع کل بدهی معوق قطعی ({data['debtors_count']} نفر):</td>
        <td colspan="3" style="text-align: right; padding-right: 14px; font-size: 11pt;">{data['total_debt_tomans']:,} تومان</td>
      </tr>
    </tfoot>
  </table>

  <!-- PAGE BREAK FOR CARDS -->
  <div class="page-break"></div>

  <div class="section-title">شناسنامه و جزئیات تفصیلی بدهکاران</div>
  <div class="cards-grid">
    {''.join(cards_html)}
  </div>

  <div class="footer-note">
    <strong>توضیحات تکمیلی مدیریت:</strong><br>
    ۱. مبالغ بدهی بر مبنای نرخ مصوب اتاق و تعداد روزهای سپری‌شده پس از تاریخ آخرین تسویه (روز‌شمار تقویم جلالی) محاسبه شده است.<br>
    ۲. ساکنین با بیش از ۱۵ روز تأخیر در وضعیت اضطراری پیگیری قرار دارند.<br>
    ۳. این سند بر اساس اطلاعات پایگاه داده سامانه مدیریت خوابگاه در تاریخ {data['target_date_str']} تهیه گردیده است.
  </div>

</body>
</html>
"""
    return html_content


def find_chrome_binary() -> str:
    """Locates the Google Chrome or Chromium executable."""
    candidates = [
        "/opt/google/chrome/google-chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    # Fallback to which
    which_chrome = subprocess.run(["which", "google-chrome"], capture_output=True, text=True).stdout.strip()
    if which_chrome and os.path.isfile(which_chrome):
        return which_chrome

    raise RuntimeError("Google Chrome binary not found on the system. Cannot generate PDF.")


def generate_debtors_pdf(
    output_path: Optional[str] = None,
    target_date: Optional[jdatetime.date] = None,
    dormitory_id: Optional[int] = None
) -> str:
    """
    Main entry point: fetches data, renders HTML, and converts to PDF via Chrome Headless.
    Returns the absolute path to the generated PDF.
    """
    data = fetch_debtors_data(target_date=target_date, dormitory_id=dormitory_id)
    html_content = render_html_report(data)

    if output_path is None:
        filename = f"debtors_report_{data['target_date'].strftime('%Y_%m_%d')}.pdf"
        output_path = os.path.join(BASE_DIR, filename)

    output_path = os.path.abspath(output_path)
    chrome_bin = find_chrome_binary()

    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as f:
        f.write(html_content)
        temp_html_path = f.name

    try:
        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output_path}",
            temp_html_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    finally:
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)

    # Also update generic debtors_report.pdf at root if output is inside project
    default_root_copy = os.path.join(BASE_DIR, "debtors_report.pdf")
    if os.path.exists(output_path) and output_path != default_root_copy:
        try:
            import shutil
            shutil.copyfile(output_path, default_root_copy)
        except Exception:
            pass

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Executive Debtors PDF Report")
    parser.add_argument("--output", "-o", default=None, help="Output PDF file path (default: root/debtors_report_YYYY_MM_DD.pdf)")
    parser.add_argument("--date", "-d", default=None, help="Target date in Jalali YYYY/MM/DD format (default: today)")
    parser.add_argument("--dormitory", type=int, default=None, help="Dormitory ID (default: all dormitories)")

    args = parser.parse_args()

    target_d = None
    if args.date:
        parts = list(map(int, args.date.replace("-", "/").split("/")))
        target_d = jdatetime.date(parts[0], parts[1], parts[2])

    print("⏳ در حال استخراج اطلاعات بدهکاران و تولید گزارش PDF...")
    pdf_file = generate_debtors_pdf(output_path=args.output, target_date=target_d, dormitory_id=args.dormitory)
    print(f"✅ فایل PDF با موفقیت تولید و در مسیر زیر ذخیره شد:\n{pdf_file}")
