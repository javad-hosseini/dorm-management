# Dormitory Management System - Agent Operating Guidelines

This document is the **single authoritative protocol** for all AI agents working in this repository. It covers system environment, receipt intake, batch processing, response standards, and special-case handling.

---

## 🏢 System Overview & Environment

- **Framework:** Django 5.2 (Python 3.11/3.14)
- **Database:** SQLite (`db.sqlite3` with atomic backups in `db-backups/`)
- **Active Virtual Environment:** `.venv/bin/python`
  > **Crucial:** Always execute management commands using `.venv/bin/python manage.py ...` (the system-level python lacks installed dependencies like `decouple`).
- **Calendar & Timezone:** Jalali Solar Hijri (`jdatetime`, `django_jalali`), Timezone: `Asia/Tehran`.
- **Default Supervisor:** جواد حسینی (ID: `1`, National Code: `0201014318`).
- **Default Dormitory:** خوابگاه نوید (ID: `1`).
- **Currency:** All user-facing amounts are in **Tomans**. Database stores **Rials** (`Rials = Tomans × 10`). POS receipts always print in **Rials** — divide by 10 to get Tomans.

---

## 🧾 Receipt Intake & Transaction Processing Protocol

When the user provides transaction receipts (photos of POS slips, card-to-card screenshots, or text descriptions) and asks to add them to the system, **follow this protocol strictly**:

### 1. Understanding Inputs

- **User Text:** Usually includes the resident's name, room number, amount in Tomans, and settlement conditions (e.g., "تا اول آبان تسویه شد").
- **Receipt Image (POS / کارتخوان):** Contains:
  - `مبلغ:` Amount in **Rials** → convert to Tomans (÷10).
  - `زمان-تاریخ:` Jalali date and time (e.g. `۱۴۰۵/۰۷/۲۱ - ۱۷:۵۵:۴۰`).
  - `پیگیری - مرجع:` Tracking & reference code (e.g. `094909118430` / `118430`).
  - Handwritten notes: Often contain the resident's last name and room number.
  - Bank / Card: Last 4 digits of card and terminal number.

### 2. Transaction Types

- **`RENT` (Default):** Monthly rent payment. Auto-computes period start/end, formats `period_name`, and updates `resident.settled_until`.
- **`DEPOSIT`:** Security deposit. Updates `resident.has_deposit = True`.
- **Split Transactions (Rent + Deposit):** When a single receipt/swipe combines rent and deposit (e.g. 5,800,000 Tomans = 2M deposit + 3.8M rent), record **two separate transactions** sharing identical receipt metadata (date, time, tracking, card, supervisor): one `DEPOSIT` and one `RENT`. Use the single `--deposit-tomans` + `--rent-tomans` invocation for atomicity.

### 3. Dedicated CLI Tool: `record_receipt` & `ReceiptProcessor`

To ensure data integrity, atomicity, and high performance, use the optimized Django management command:

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

**Key capabilities:**
- Fuzzy token matching with room priority and space/half-space normalization (handles typos like `امیدرضا جعفری` for `امیر رضا جعفری` in room 109).
- Supports native split transactions in a single execution.
- Automatically links to Supervisor ID `1` (جواد حسینی) and Dormitory ID `1`.
- Accurately advances Jalali months and computes prorated days.
- Respects explicit `--settled-until` overrides when specified by the user.
- `--dry-run` for safe preview; `--json-output` for machine-readable feedback.

### 4. Rent Discrepancy & Underpayment Flagging

- **Normal Installments (پرداخت‌های خرد):** If the user just states an amount was paid without saying "settled until X", the system advances `settled_until` proportionally (prorated). These are **completely normal** — do **NOT** flag them in `FINANCE_DOUBTS.md`.
- **Suspicious Discrepancy (flag in `FINANCE_DOUBTS.md`):** If the user or a colleague states "settled until date X" but the paid amount is less than the room's approved monthly rate for that full period (e.g., room 101 has rent 3,800,000 T but only 3,500,000 T was paid and "settled until 1st of Azar" was claimed):
  1. **Record as علی‌الحساب:** Apply settlement to the stated date anyway (`--settled-until`) so work is not blocked.
  2. **Mandatory flag in `FINANCE_DOUBTS.md`:** Log the discrepancy with full details and report to user.

### 5. Special Cases & Edge Cases

- **Name ambiguity:** If multiple residents share a name, the command returns a list with room numbers. Use `--room` or `--resident <id>` to disambiguate.
- **Prorated amounts:** System uses exact Jalali calendar day counts (months vary 29–31 days). Use `--settled-until` for explicit rounding.
- **Room rate snapshot:** At transaction creation, the room's current rate is frozen in `applicable_rent`. Future rate changes do not affect past receipts.

---

## 📦 Batch Receipt Ingestion Protocol (Excel & CSV)

When the user provides an Excel (`.xlsx`) or CSV (`.csv`) file containing multiple transactions, follow this protocol:

### 1. Workflow & Dedicated CLI Tool: `manage.py process_excel`

The system provides an automated end-to-end command (`process_excel`) that auto-detects both raw Telegram session exports (`RAW_TELEGRAM_SESSION` with embedded POS receipt images and manager notes across `Block_1`...`Block_N`) and standard tabular batch sheets (`CLEANED_BATCH`):

```bash
# 1. Always execute in Dry-Run mode first (safe preview):
.venv/bin/python manage.py process_excel --file <path_to_excel> --dry-run

# 2. Apply and commit transactions to the database:
.venv/bin/python manage.py process_excel --file <path_to_excel> --apply

# 3. Apply with automatic image extraction, cleaned sheet export, and failed rows export:
.venv/bin/python manage.py process_excel --file <path_to_excel> --apply \
  --export-cleaned media/spreadsheets/exported_cleaned.xlsx \
  --export-failed media/spreadsheets/failed_rows.xlsx \
  --archive
```

**Key capabilities:**
- Auto-extracts cell-anchored images (`openpyxl._images`) and saves them to `media/spreadsheets/extracted_images/<filename>/`.
- Parses free-form Persian colloquial text, dates (`تا اول آذر`, `۱۵ بهمن`), amounts (`دو و نیم میلیون`, `۳ میلیون و ۸۰۰ هزار`), and times.
- Detects non-financial lifecycle events: new resident registrations (`CHECK_IN`), room swaps (`ROOM_CHANGE`), and check-outs (`CHECK_OUT`).
- Automatically logs suspected underpayments and pool transfers into `FINANCE_DOUBTS.md`.

### 2. Supported Column Headers

The system recognizes both Persian and English column names:

| Persian Column | English Column | Required? | Notes |
| :--- | :--- | :---: | :--- |
| `نام مقیم` / `نام ساکن` / `نام` | `resident` / `name` | **Yes** | Full name |
| `شماره اتاق` / `اتاق` | `room` / `room_number` | Optional | Improves fuzzy matching |
| `مبلغ اجاره (تومان)` / `اجاره` | `rent_tomans` / `rent` | No | 0 if absent |
| `مبلغ ودیعه (تومان)` / `ودیعه` | `deposit_tomans` / `deposit` | No | 0 if absent |
| `تاریخ و زمان` / `تاریخ` | `date` / `datetime` | **Yes** | Jalali format: `1405/08/06 19:08:34` |
| `اطلاعات رهگیری` / `پیگیری` / `مرجع` | `ref` / `reference` | No | Tracking/reference codes |
| `روش پرداخت` / `نوع پرداخت` | `method` | No | `کارتخوان` = CARD, `کارت به کارت` = BANK_TRANSFER |
| `تسویه تا` / `تاریخ تسویه` | `settled_until` | No | e.g. `1405-09-01` |
| `توضیحات` | `desc` / `description` | No | Notes |

### 3. Execution Rules

1. **Split rows:** If both rent and deposit columns are non-zero in one row, pass both `--rent-tomans` and `--deposit-tomans` — the command creates two atomic transactions.
2. **Resident not found:** Do not abort the whole batch. Skip that row, log it in the error table, and continue.
3. **All amounts are in Tomans.** The command multiplies by 10 internally before storing in Rials.

### 4. Final Report Format

```markdown
### 📋 Batch Receipt Summary — [filename]
- **Total rows:** 15
- **Successful:** 14
- **Failed / Needs review:** 1 (reason: resident not found)
- **Total recorded:** 54,500,000 T (Rent: 44,500,000 | Deposit: 10,000,000)

| Row | #ID | Resident | Room | Amount (T) | Type | Period / Settled | Status |
...
```

---

## 🚨 AI Fraud Detection & Receipt Validation Directives

These rules apply whenever the AI processes raw notebook entries, receipt images, or spreadsheets to register or verify transactions. They are **mandatory** and must never be skipped.

### Rule 1: Flagged Source Bank Card (`621986******1491`)
Inspect the source/originating bank card on every POS receipt, bank transfer receipt, and handwritten note.
- **Condition:** Card starts with `621986` AND ends with `1491` (Saman / Blue Bank).
- **Action:** Immediately flag `[FLAG: WATCHLIST_SOURCE_CARD_621986_1491]`. Do **not** silently approve. Highlight for manual manager review — this card is on a special watchlist.

### Rule 2: Checksum & Cross-Verification (Zero-Trust on Manual Notes)
Never blindly trust handwritten notebook entries or user-typed annotations. Perform a multi-point verification on every transaction:
1. **Receipt-to-Note Checksum:**
   - **Amount:** Verify exact numeric amount. POS receipts are in **Rials**; staff notes are often in **Tomans**. Cross-check both.
   - **Date & Timestamp:** Verify receipt date/time matches the notebook entry.
   - **Trace / Reference Number (`شماره پیگیری` / `شماره مرجع`):** Extract and verify — ensure the same receipt is not used twice.
2. **Database Record Checksum:**
   - Verify resident's full name, active status, assigned room, and historical room rate (`get_rent_for_date`).
   - If a full-month settlement is claimed but the paid amount doesn't match the approved room rate, flag `[FLAG: CHECKSUM_MISMATCH]` and report the exact difference.

### Rule 3: POS Customer Copy vs. Merchant Copy (`رسید مشتری` vs. `رسید پذیرنده`)
Every POS receipt **must** be a Customer Copy (`رسید مشتری`).
- **Condition:** Receipt header says `رسید پذیرنده` (Merchant Copy).
- **Action:** Immediately flag `[FLAG: INVALID_MERCHANT_COPY_RECEIPT]` and alert the manager. A Merchant Copy submitted as proof of payment is a red flag for fraud.

### Rule 4: Prohibition of Duplicate / Reprinted POS Receipts (`چاپ مجدد`)
Inspect every POS receipt image for any reprint indicators:
- `چاپ مجدد` / `رسید مجدد` / `کپی برابر اصل` / `کپی` / `المثنی`
- **Condition:** Any reprint marking appears anywhere on the receipt.
- **Action:** Flag `[FLAG: REPRINTED_RECEIPT_DETECTED]` and cross-check the database for any prior transaction sharing the same Trace Number, Reference Number, or timestamp before allowing approval.

---

## 📋 Response Standard

After recording each transaction:
1. Provide a clean GitHub-style Markdown table summarizing the created transaction (`#ID`, resident link, room, amounts in both Tomans and Rials, type, method, period, tracking info, supervisor, and new settlement date).
2. Prompt the user for the next receipt.

**Standard receipt confirmation table:**

```markdown
### 🧾 Transaction Receipt #[ID]

| Field | Value |
| :--- | :--- |
| **Resident** | [Name] (Room [X]) |
| **Amount** | [X] Rials (**[Y] Tomans**) |
| **Type** | RENT / DEPOSIT |
| **Method** | CARD / BANK_TRANSFER |
| **Period** | [period_name] ([start] to [end]) |
| **Payment Date** | [jalali datetime] |
| **Tracking / Ref** | `[reference_number]` |
| **Recorded by** | جواد حسینی |
| **New Settlement** | **[new_settled_until]** ✅ |

---
Ready for the next receipt.
```
