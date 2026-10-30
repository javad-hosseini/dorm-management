# Dormitory Management System - Agent Operating Guidelines

This document provides system-wide operational rules, business domain knowledge, and standard protocols for AI assistants working in this repository.

---

## 🏢 System Overview & Environment

- **Framework:** Django 5.2 (Python 3.11/3.14)
- **Database:** SQLite (`db.sqlite3` with atomic backups in `db-backups/`)
- **Active Virtual Environment:** `.venv/bin/python`
  > **Crucial:** Always execute management commands using `.venv/bin/python manage.py ...` (the system-level python lacks installed dependencies like `decouple`).
- **Calendar & Timezone:** Jalali Solar Hijri (`jdatetime`, `django_jalali`), Timezone: `Asia/Tehran`.
- **Default Supervisor:** جواد حسینی (ID: `1`, National Code: `0201014318`).
- **Default Dormitory:** خوابگاه نوید (ID: `1`).

---

## 🧾 Receipt Intake & Transaction Processing Protocol

When the user provides transaction receipts (photos of POS slips, card-to-card screenshots, or text descriptions) and asks to add them to the system, **follow this protocol strictly**:

### 1. Understanding Inputs
- **User Text:** Usually includes the resident's name, room number, amount in Tomans, and settlement conditions (e.g., "تا اول آبان تسویه شد").
- **Receipt Image:** Contains POS details:
  - `مبلغ:` Amount in Rials (convert to Tomans = Rials / 10).
  - `زمان-تاریخ:` Jalali date and time (e.g. `۱۴۰۵/۰۷/۲۱ - ۱۷:۵۵:۴۰`).
  - `پیگیری - مرجع:` Tracking & reference code (e.g. `094909118430` / `118430`).
  - Handwritten notes: Often contains the resident's last name and room number.
  - Bank / Card: Last 4 digits of card and terminal number.

### 2. Transaction Types
- **`RENT` (Default):** Monthly rent payment. Auto-computes period start/end, formats `period_name`, and updates `resident.settled_until`.
- **`DEPOSIT`:** Security deposit. Updates `resident.has_deposit = True`.
- **Split Transactions (Rent + Deposit):** When a single receipt/swipe combines rent and deposit (e.g. 5,800,000 Tomans = 2M deposit + 3.8M rent), record **two separate transactions** sharing the identical receipt metadata (date, time, tracking, card, supervisor): one as `DEPOSIT` and the other as `RENT`.

### 3. Dedicated CLI Tool: `record_receipt` & `ReceiptProcessor`
To ensure data integrity, atomicity, and high performance, use the optimized Django management command or Python service (`apps.dormitory.services.receipt_processor`):

```bash
# Single Transaction:
.venv/bin/python manage.py record_receipt \
  --resident "<name or id or national_code>" \
  --room "<room_number>" \
  --amount-tomans <amount_in_tomans> \
  --type <RENT|DEPOSIT> \
  --method CARD \
  --date "<jalali_datetime e.g. 1405/07/21 17:55:40>" \
  --ref "<reference_and_tracking_numbers>" \
  [--settled-until "<target_settlement_date e.g. 1405-08-01>"] \
  [--desc "<optional_notes>"]

# Split Transaction (Rent + Deposit in ONE atomic step):
.venv/bin/python manage.py record_receipt \
  --resident "<name or id or national_code>" \
  --room "<room_number>" \
  --deposit-tomans <deposit_amount> \
  --rent-tomans <rent_amount> \
  --date "<jalali_datetime>" \
  --ref "<reference_and_tracking_numbers>" \
  [--settled-until "<target_settlement_date>"]
```

#### Key Capabilities of `record_receipt`:
- Resolves resident with fuzzy token matching, room priority, and space/half-space normalization (e.g. handles typos like 'امیدرضا جعفری' for 'امیر رضا جعفری' in room 109).
- Supports native split transactions in a single execution.
- Automatically links to Supervisor ID `1` (جواد حسینی) and Dormitory ID `1`.
- Accurately advances Jalali months and computes prorated days.
- Respects explicit `--settled-until` overrides when specified by the user.
- Supports `--dry-run` to test before committing.
- Supports `--json-output` if machine-readable feedback is desired.

For full technical specifications, see [RECEIPT_PROCESSING_PROTOCOL.md](file:///home/javad/projects/websites/Dormitory%20Management%20System/dormitory-management/RECEIPT_PROCESSING_PROTOCOL.md).

---

## 📋 Response Standard

After recording each transaction:
1. Provide a clean GitHub-style Markdown table summarizing the created transaction (`#ID`, resident link, room, amounts in both Tomans and Rials, type, method, period, tracking info, supervisor, and new settlement date).
2. Prompt the user for the next receipt.

