"""
Bank Statement Reconciliation Engine
------------------------------------
Ingests bank statement spreadsheets (CSV / XLSX), normalizes deposits,
matches them against DB transactions (BANK_TRANSFER), detects suspected fake
receipts, updates reference numbers and approval statuses, and generates
audit reports.
"""

import os
import re
import datetime
import zoneinfo
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union

import pandas as pd
import jdatetime
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.accounts.models import Supervisor
from apps.dormitory.models import Transaction, Resident, DailyNote
from apps.dormitory.jalali_utils import to_persian_digits


TEHRAN_TZ = zoneinfo.ZoneInfo("Asia/Tehran")


def normalize_persian_text(text: Any) -> str:
    """Normalize Arabic/Persian characters and digits."""
    if text is None:
        return ""
    s = str(text).strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("\u200c", " ")
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(trans)


def parse_jalali_to_datetime(dt_str: str) -> Tuple[jdatetime.datetime, datetime.datetime]:
    """
    Parse a Jalali date/datetime string into both jdatetime.datetime
    and standard datetime.datetime (tz-aware in Asia/Tehran).
    Supported formats:
      - 1405/08/13 06:54
      - 1405/08/13  06:54
      - 1405/08/13 06:54:00
      - 1405-08-13 06:54
      - 1405/08/13
    """
    s = normalize_persian_text(dt_str)
    # Remove multiple spaces
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(
        r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[\sT]+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$",
        s,
    )
    if not m:
        raise ValueError(f"فرمت تاریخ و زمان شمسی نامعتبر است: {dt_str}")

    year = int(m.group(1))
    month = int(m.group(2))
    day = int(m.group(3))
    hour = int(m.group(4) or 12)
    minute = int(m.group(5) or 0)
    second = int(m.group(6) or 0)

    jdt = jdatetime.datetime(year, month, day, hour, minute, second, tzinfo=TEHRAN_TZ)
    gdt = jdt.togregorian()
    return jdt, gdt


@dataclass
class BankDepositItem:
    """Represents a single parsed bank deposit row from the statement."""
    row_id: int
    description: str
    amount_rials: int
    transaction_type: str  # 'واریز'
    jalali_datetime_str: str
    jalali_dt: jdatetime.datetime
    gregorian_dt: datetime.datetime
    balance: Optional[int] = None
    
    # Extracted fields
    tracking_code: str = ""
    origin_card: str = ""
    origin_card_last4: str = ""
    dest_card: str = ""
    origin_account: str = ""
    dest_account: str = ""
    deposit_iban: str = ""
    deposit_category: str = "CARD"  # CARD, SHAPARAK, POL, SATNA_PAYA, INTERNAL, REVERSAL, OTHER
    raw_row: Dict[str, Any] = field(default_factory=dict)

    @property
    def amount_tomans(self) -> int:
        return self.amount_rials // 10


@dataclass
class MatchResult:
    """Represents the matching between a DB Transaction and a BankDepositItem."""
    transaction: Transaction
    bank_item: BankDepositItem
    tier: int  # 1 = Exact Ref/Code, 2 = Dynamic Proximity
    confidence_score: int  # 0 to 100
    time_diff_minutes: float
    notes: str = ""


class BankStatementParser:
    """Parses Iranian bank statements (e.g. Bank Mehr Iran) from CSV / Excel."""

    def __init__(self, file_path_or_buffer: Union[str, Any]):
        self.source = file_path_or_buffer
        self.metadata: Dict[str, Any] = {}
        self.deposits: List[BankDepositItem] = []

    def parse(self) -> List[BankDepositItem]:
        """Parse the input file and extract all incoming deposit rows."""
        lines = self._read_lines()
        self.deposits = self._parse_lines(lines)
        return self.deposits

    def _read_lines(self) -> List[str]:
        """Read lines from file path or buffer with robust encoding detection."""
        if hasattr(self.source, "read"):
            content = self.source.read()
            if isinstance(content, bytes):
                for enc in ["utf-8-sig", "utf-8", "cp1256", "latin1"]:
                    try:
                        return content.decode(enc).splitlines()
                    except UnicodeDecodeError:
                        continue
                return content.decode("utf-8", errors="replace").splitlines()
            return str(content).splitlines()

        if isinstance(self.source, str):
            # Check if Excel file
            if self.source.lower().endswith((".xlsx", ".xls")):
                return self._read_excel_lines(self.source)

            # Try reading as text/CSV
            for enc in ["utf-8-sig", "utf-8", "cp1256", "latin1"]:
                try:
                    with open(self.source, "r", encoding=enc) as f:
                        return f.read().splitlines()
                except UnicodeDecodeError:
                    continue
            with open(self.source, "r", encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()

        return []

    def _read_excel_lines(self, path: str) -> List[str]:
        """Convert Excel sheet rows into CSV-like lines for uniform parsing."""
        df = pd.read_excel(path, header=None)
        lines = []
        for _, row in df.iterrows():
            cells = ["" if pd.isna(c) else str(c).strip() for c in row]
            lines.append(",".join(cells))
        return lines

    def _parse_lines(self, lines: List[str]) -> List[BankDepositItem]:
        items: List[BankDepositItem] = []
        seen_keys = set()
        current_header_map: Optional[Dict[str, int]] = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Check for metadata
            norm_line = normalize_persian_text(line)
            if "شماره حساب:" in norm_line:
                acc_m = re.search(r"شماره حساب:\s*(\d+)", norm_line)
                if acc_m:
                    self.metadata["account_number"] = acc_m.group(1)
            if "منبع گزارش:" in norm_line:
                src_m = re.search(r"منبع گزارش:\s*([^,]+)", norm_line)
                if src_m:
                    self.metadata["report_source"] = src_m.group(1).strip()
            if "از تاریخ" in norm_line and "تا" in norm_line:
                date_m = re.search(r"از تاریخ\s*([0-9/]+)\s*تا\s*([0-9/]+)", norm_line)
                if date_m:
                    self.metadata["date_from"] = date_m.group(1)
                    self.metadata["date_to"] = date_m.group(2)

            # Detect Header row
            if ("ردیف" in norm_line or "رديف" in norm_line) and (
                "مبلغ" in norm_line or "توضیح" in norm_line or "توضيح" in norm_line
            ):
                current_header_map = self._extract_header_indices(line)
                continue

            if not current_header_map:
                continue

            # Parse Data Row
            parsed_item = self._parse_data_row(line, current_header_map)
            if parsed_item:
                # Deduplicate if overlapping sections exist
                dedup_key = (
                    parsed_item.tracking_code or parsed_item.description,
                    parsed_item.jalali_datetime_str,
                    parsed_item.amount_rials,
                )
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    items.append(parsed_item)

        return items

    def _extract_header_indices(self, header_line: str) -> Dict[str, int]:
        """Locate indices for column names."""
        parts = [p.strip().strip('"').strip("'") for p in header_line.split(",")]
        mapping: Dict[str, int] = {}
        for idx, col in enumerate(parts):
            c_norm = normalize_persian_text(col)
            if re.search(r"^(ردیف|رديف)$", c_norm):
                mapping["row_id"] = idx
            elif "توضیح" in c_norm or "توضيح" in c_norm or "شرح" in c_norm:
                mapping["description"] = idx
            elif "مبلغ" in c_norm:
                mapping["amount"] = idx
            elif "نوع" in c_norm:
                mapping["type"] = idx
            elif "زمان" in c_norm or "تاریخ" in c_norm or "تاريخ" in c_norm:
                mapping["datetime"] = idx
            elif "مانده" in c_norm:
                mapping["balance"] = idx
        return mapping

    def _parse_data_row(
        self, line: str, header_map: Dict[str, int]
    ) -> Optional[BankDepositItem]:
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]
        
        # Check if line has enough columns
        req_keys = ["row_id", "description", "amount"]
        if not all(k in header_map and header_map[k] < len(parts) for k in req_keys):
            return None

        row_str = parts[header_map["row_id"]]
        if not normalize_persian_text(row_str).isdigit():
            return None

        row_id = int(normalize_persian_text(row_str))
        desc = parts[header_map["description"]]
        
        amount_raw = parts[header_map["amount"]]
        amount_clean = re.sub(r"[^\d]", "", normalize_persian_text(amount_raw))
        if not amount_clean:
            return None
        amount_rials = int(amount_clean)

        type_str = ""
        if "type" in header_map and header_map["type"] < len(parts):
            type_str = normalize_persian_text(parts[header_map["type"]])

        # Only process incoming deposits (واریز)
        if type_str and "واریز" not in type_str and "وارده" not in type_str and "credit" not in type_str.lower():
            return None

        dt_str = ""
        if "datetime" in header_map and header_map["datetime"] < len(parts):
            dt_str = parts[header_map["datetime"]].strip()

        if not dt_str:
            return None

        try:
            jdt, gdt = parse_jalali_to_datetime(dt_str)
        except Exception:
            return None

        balance = None
        if "balance" in header_map and header_map["balance"] < len(parts):
            bal_clean = re.sub(r"[^\d]", "", normalize_persian_text(parts[header_map["balance"]]))
            if bal_clean:
                balance = int(bal_clean)

        # Extract structured details from description
        desc_norm = normalize_persian_text(desc)
        tracking_code = self._extract_tracking_code(desc_norm)
        origin_card, origin_last4 = self._extract_origin_card(desc_norm)
        dest_card = self._extract_dest_card(desc_norm)
        origin_acc = self._extract_origin_account(desc_norm)
        dest_acc = self._extract_dest_account(desc_norm)
        iban = self._extract_iban(desc_norm)
        category = self._classify_deposit(desc_norm)

        return BankDepositItem(
            row_id=row_id,
            description=desc,
            amount_rials=amount_rials,
            transaction_type=type_str or "واریز",
            jalali_datetime_str=dt_str,
            jalali_dt=jdt,
            gregorian_dt=gdt,
            balance=balance,
            tracking_code=tracking_code,
            origin_card=origin_card,
            origin_card_last4=origin_last4,
            dest_card=dest_card,
            origin_account=origin_acc,
            dest_account=dest_acc,
            deposit_iban=iban,
            deposit_category=category,
        )

    def _extract_tracking_code(self, desc: str) -> str:
        """Extract tracing / tracking number from description."""
        # Check standard Iranian card-to-card tracking codes
        m = re.search(r"(?:کدرهگیری|کد\s*رهگیری|کدرهگيري|کد\s*رهگيري|کدپیگیری|کد\s*پیگیری|کدپيگيري|کد\s*پيگيري)\s*[:\s]*(\d+)", desc)
        if m:
            return m.group(1).strip()

        # Check Pol tracking numbers (often starts with 1405...)
        m_pol = re.search(r"(?:کدپیگیری|کدپيگيري|کد\s*پیگیری|کد\s*پيگيري)\s*[:\s]*(\d{10,32})", desc)
        if m_pol:
            return m_pol.group(1).strip()

        # Check Shaparak / Paya codes starting with 'پ'
        m_p = re.search(r"پ(\d{10,32})", desc)
        if m_p:
            return m_p.group(1).strip()

        return ""

    def _extract_origin_card(self, desc: str) -> Tuple[str, str]:
        """Extract origin 16-digit card number and last 4 digits."""
        m = re.search(r"(?:انتقال\s*(?:وجه\s*)?از|از\s*کارت|از)\s*(\d{16})", desc)
        if m:
            card = m.group(1).strip()
            return card, card[-4:]
        return "", ""

    def _extract_dest_card(self, desc: str) -> str:
        """Extract destination card number."""
        m = re.search(r"(?:به\s*کارت|به)\s*(\d{16})", desc)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_origin_account(self, desc: str) -> str:
        m = re.search(r"از\s*سپرده\s*(\d+)", desc)
        return m.group(1).strip() if m else ""

    def _extract_dest_account(self, desc: str) -> str:
        m = re.search(r"به\s*(?:سپرده\s*)?(\d{12,24})", desc)
        return m.group(1).strip() if m else ""

    def _extract_iban(self, desc: str) -> str:
        m = re.search(r"(?:به\s*)?(?:شبای|شباي)\s*[:\s]*(IR\d{24})", desc, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _classify_deposit(self, desc: str) -> str:
        if "شاپرک" in desc or "شاپرکي" in desc:
            return "SHAPARAK"
        if "پل" in desc or "دستورپرداخت وارده پل" in desc:
            return "POL"
        if "پایا" in desc or "ساتنا" in desc or "دستور پرداخت وارده" in desc:
            return "SATNA_PAYA"
        if "برگشت" in desc:
            return "REVERSAL"
        if "سپرده" in desc:
            return "INTERNAL"
        if "انتقال" in desc:
            return "CARD"
        return "OTHER"


class BankReconciliationEngine:
    """
    Core matching and reconciliation engine.
    Matches BankDepositItem records with Django Transaction records.
    """

    def __init__(
        self,
        bank_deposits: List[BankDepositItem],
        start_date: Optional[jdatetime.date] = None,
        end_date: Optional[jdatetime.date] = None,
        time_window_minutes: int = 1440,  # Default 24h search window for Tier 2
    ):
        self.bank_deposits = bank_deposits
        self.start_date = start_date
        self.end_date = end_date
        self.time_window_minutes = time_window_minutes

        self.verified_matches: List[MatchResult] = []
        self.unverified_transactions: List[Transaction] = []
        self.unmatched_bank_deposits: List[BankDepositItem] = []

    def run(self) -> Dict[str, Any]:
        """Execute reconciliation algorithm."""
        # Determine statement date bounds if not explicitly passed
        if self.bank_deposits:
            all_dates = [b.jalali_dt.date() for b in self.bank_deposits]
            min_date = min(all_dates) - datetime.timedelta(days=2)
            max_date = max(all_dates) + datetime.timedelta(days=2)
            if not self.start_date:
                self.start_date = min_date
            if not self.end_date:
                self.end_date = max_date

        # Fetch DB transactions with BANK_TRANSFER
        qs = Transaction.objects.filter(payment_method="BANK_TRANSFER").select_related("resident", "resident__room")
        if self.start_date:
            qs = qs.filter(payment_date__gte=jdatetime.datetime(self.start_date.year, self.start_date.month, self.start_date.day, 0, 0, 0, tzinfo=TEHRAN_TZ))
        if self.end_date:
            qs = qs.filter(payment_date__lte=jdatetime.datetime(self.end_date.year, self.end_date.month, self.end_date.day, 23, 59, 59, tzinfo=TEHRAN_TZ))

        db_txs = list(qs)

        assigned_tx_ids = set()
        assigned_bank_row_ids = set()

        # ---------------------------------------------------------
        # TIER 1: Exact Match by Tracking Code + Amount
        # ---------------------------------------------------------
        for b in self.bank_deposits:
            if not b.tracking_code:
                continue

            for tx in db_txs:
                if tx.id in assigned_tx_ids:
                    continue
                if tx.amount != b.amount_rials:
                    continue

                # Check if tracking code exists in reference_number or description
                ref_norm = normalize_persian_text(tx.reference_number)
                desc_norm = normalize_persian_text(tx.description)
                
                if b.tracking_code in ref_norm or b.tracking_code in desc_norm:
                    time_diff = self._calc_time_diff_minutes(tx, b)
                    self.verified_matches.append(
                        MatchResult(
                            transaction=tx,
                            bank_item=b,
                            tier=1,
                            confidence_score=100,
                            time_diff_minutes=time_diff,
                            notes="تطبیق قطعی با کد رهگیری و مبلغ",
                        )
                    )
                    assigned_tx_ids.add(tx.id)
                    assigned_bank_row_ids.add(b.row_id)
                    break

        # ---------------------------------------------------------
        # TIER 2: Smart Match by Amount + Dynamic Proximity Window
        # ---------------------------------------------------------
        candidate_pairs = []

        for b in self.bank_deposits:
            if b.row_id in assigned_bank_row_ids:
                continue
            if b.deposit_category == "SHAPARAK":
                # Shaparak batches are multi-transaction settlements, not single resident transfers
                continue

            for tx in db_txs:
                if tx.id in assigned_tx_ids:
                    continue
                if tx.amount != b.amount_rials:
                    continue

                time_diff = self._calc_time_diff_minutes(tx, b)
                if time_diff > self.time_window_minutes:
                    continue

                # Compute Score
                score = 70  # Base score for same amount and within window
                notes = []

                if time_diff <= 30:
                    score += 25
                    notes.append("اختلاف زمانی کمتر از ۳۰ دقیقه")
                elif time_diff <= 120:
                    score += 15
                    notes.append("اختلاف زمانی کمتر از ۲ ساعت")
                elif time_diff <= 720:
                    score += 5
                    notes.append("همان روز (اختلاف کمتر از ۱۲ ساعت)")
                else:
                    score -= 10
                    notes.append("اختلاف بیش از ۱۲ ساعت")

                # Bonus for card last 4 match
                if b.origin_card_last4:
                    combined_tx_text = normalize_persian_text(f"{tx.reference_number} {tx.description} {tx.resident.phone_number}")
                    if b.origin_card_last4 in combined_tx_text:
                        score += 15
                        notes.append(f"تطبیق ۴ رقم آخر کارت ({b.origin_card_last4})")

                # Bonus for resident name match in bank description
                res_name = normalize_persian_text(tx.resident.full_name)
                for part in res_name.split():
                    if len(part) > 2 and part in normalize_persian_text(b.description):
                        score += 15
                        notes.append(f"تطبیق نام ساکن ({part})")
                        break

                candidate_pairs.append({
                    "tx": tx,
                    "bank": b,
                    "score": score,
                    "time_diff": time_diff,
                    "notes": " / ".join(notes),
                })

        # Sort candidate pairs by score DESC, then time_diff ASC
        candidate_pairs.sort(key=lambda x: (-x["score"], x["time_diff"]))

        for pair in candidate_pairs:
            tx = pair["tx"]
            b = pair["bank"]
            if tx.id in assigned_tx_ids or b.row_id in assigned_bank_row_ids:
                continue

            # Minimum threshold for confidence
            if pair["score"] >= 60:
                self.verified_matches.append(
                    MatchResult(
                        transaction=tx,
                        bank_item=b,
                        tier=2,
                        confidence_score=min(pair["score"], 98),
                        time_diff_minutes=pair["time_diff"],
                        notes=pair["notes"],
                    )
                )
                assigned_tx_ids.add(tx.id)
                assigned_bank_row_ids.add(b.row_id)

        # ---------------------------------------------------------
        # CLASSIFY UNMATCHED
        # ---------------------------------------------------------
        for tx in db_txs:
            if tx.id not in assigned_tx_ids:
                self.unverified_transactions.append(tx)

        for b in self.bank_deposits:
            if b.row_id not in assigned_bank_row_ids:
                self.unmatched_bank_deposits.append(b)

        return self.get_summary()

    def _calc_time_diff_minutes(self, tx: Transaction, b: BankDepositItem) -> float:
        """Calculate absolute difference in minutes between tx.payment_date and b.jalali_dt."""
        if not tx.payment_date:
            return float("inf")
        try:
            tx_gdt = tx.payment_date.togregorian()
            b_gdt = b.gregorian_dt
            diff_seconds = abs((tx_gdt - b_gdt).total_seconds())
            return diff_seconds / 60.0
        except Exception:
            return float("inf")

    def apply_updates(self, supervisor: Optional[Supervisor] = None) -> Dict[str, int]:
        """
        Apply database updates:
        1. For Verified matches:
           - Update transaction reference_number with bank tracking code & card info if missing
           - Ensure is_approved = True
        2. For Unverified transactions (Suspected Fake):
           - Set is_approved = False
           - Create a warning DailyNote (DISCIPLINARY) for the resident
        """
        if supervisor is None:
            supervisor = (
                Supervisor.objects.filter(id=3).first()
                or Supervisor.objects.first()
            )

        updated_tx_count = 0
        marked_unverified_count = 0
        created_notes_count = 0

        with db_transaction.atomic():
            # 1. Update Verified
            for m in self.verified_matches:
                tx = m.transaction
                b = m.bank_item
                changed = False

                # Format new reference if tracking code exists
                if b.tracking_code:
                    clean_ref = f"کد رهگیری: {b.tracking_code}"
                    if b.origin_card_last4:
                        clean_ref += f" (کارت: {b.origin_card_last4})"
                    
                    if not tx.reference_number:
                        tx.reference_number = clean_ref
                        changed = True
                    elif b.tracking_code not in tx.reference_number:
                        tx.reference_number = f"{tx.reference_number} | {clean_ref}"
                        changed = True

                if not tx.is_approved:
                    tx.is_approved = True
                    changed = True

                if changed:
                    tx.save()
                    updated_tx_count += 1

            # 2. Flag Unverified / Suspected Fake
            for tx in self.unverified_transactions:
                tx.is_approved = False
                tx.save()
                marked_unverified_count += 1

                # Create DailyNote warning
                tx_date_str = tx.payment_date.strftime("%Y/%m/%d %H:%M") if tx.payment_date else "نامشخص"
                room_str = f"اتاق {tx.resident.room.room_number}" if tx.resident.room else "بدون اتاق"
                
                title = f"🚨 مغایرت بانکی: فیش نامعتبر/تایید نشده (تراکنش #{tx.id})"
                content = (
                    f"در فرآیند مغایرت‌گیری صورت‌حساب بانکی، واریزی برای تراکنش شماره #{tx.id} "
                    f"به مبلغ {tx.amount // 10:,} تومان ({tx.amount:,} ریال) ثبت‌شده در تاریخ {tx_date_str} "
                    f"به نام ساکن {tx.resident.full_name} ({room_str}) در حساب بانکی یافت نشد.\n"
                    f"وضعیت تراکنش به «عدم تایید» تغییر یافت. نیاز به اخذ اصل فیش و بررسی مجدد دارد."
                )

                note_date = tx.payment_date.date() if hasattr(tx.payment_date, "date") else jdatetime.date.today()
                
                # Avoid duplicate identical daily notes
                existing_note = DailyNote.objects.filter(
                    resident=tx.resident,
                    title__contains=f"تراکنش #{tx.id}",
                ).first()

                if not existing_note and supervisor:
                    DailyNote.objects.create(
                        dormitory=tx.dormitory,
                        date=note_date,
                        title=title,
                        content=content,
                        note_type=DailyNote.NoteType.DISCIPLINARY,
                        room=tx.resident.room,
                        resident=tx.resident,
                        is_resolved=False,
                        created_by=supervisor,
                    )
                    created_notes_count += 1

        return {
            "verified_updated": updated_tx_count,
            "unverified_flagged": marked_unverified_count,
            "warning_notes_created": created_notes_count,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Return executive statistics of reconciliation."""
        total_bank_deposits = len(self.bank_deposits)
        total_bank_rials = sum(b.amount_rials for b in self.bank_deposits)

        verified_count = len(self.verified_matches)
        verified_rials = sum(m.transaction.amount for m in self.verified_matches)

        unverified_count = len(self.unverified_transactions)
        unverified_rials = sum(t.amount for t in self.unverified_transactions)

        shaparak_deposits = [b for b in self.unmatched_bank_deposits if b.deposit_category == "SHAPARAK"]
        shaparak_rials = sum(b.amount_rials for b in shaparak_deposits)

        other_unmatched = [b for b in self.unmatched_bank_deposits if b.deposit_category != "SHAPARAK"]
        other_unmatched_rials = sum(b.amount_rials for b in other_unmatched)

        return {
            "total_bank_deposits": total_bank_deposits,
            "total_bank_rials": total_bank_rials,
            "total_bank_tomans": total_bank_rials // 10,
            "verified_count": verified_count,
            "verified_rials": verified_rials,
            "verified_tomans": verified_rials // 10,
            "unverified_count": unverified_count,
            "unverified_rials": unverified_rials,
            "unverified_tomans": unverified_rials // 10,
            "shaparak_count": len(shaparak_deposits),
            "shaparak_rials": shaparak_rials,
            "shaparak_tomans": shaparak_rials // 10,
            "other_unmatched_count": len(other_unmatched),
            "other_unmatched_rials": other_unmatched_rials,
            "other_unmatched_tomans": other_unmatched_rials // 10,
        }

    def generate_markdown_report(self) -> str:
        """Generate structured audit report in GitHub-flavored Markdown."""
        summary = self.get_summary()

        report = [
            "# 🏦 گزارش جامع مغایرت‌گیری صورت‌حساب بانکی و شناسایی فیش‌های نامعتبر",
            "",
            "> گزارش خودکار تطبیق تراکنش‌های انتقال بانکی با صورت‌حساب رسمی بانک قرض‌الحسنه مهر ایران",
            "",
            "## 📊 خلاصه آمار عملکرد",
            "",
            "| شاخص مالی و عملیاتی | تعداد | مبلغ به تومان | مبلغ به ریال |",
            "| :--- | :---: | :---: | :---: |",
            f"| **کل واریزهای صورت‌حساب بانکی** | {summary['total_bank_deposits']} | {summary['total_bank_tomans']:,} تومان | {summary['total_bank_rials']:,} ریال |",
            f"| ✅ **تراکنش‌های تایید و تطبیق‌شده (معتبر)** | {summary['verified_count']} | {summary['verified_tomans']:,} تومان | {summary['verified_rials']:,} ریال |",
            f"| 🚨 **تراکنش‌های فاقد واریز (مشکوک به فیش جعلی)** | {summary['unverified_count']} | {summary['unverified_tomans']:,} تومان | {summary['unverified_rials']:,} ریال |",
            f"| 💳 **تسویه‌های تجمیعی پوز شاپرک** | {summary['shaparak_count']} | {summary['shaparak_tomans']:,} تومان | {summary['shaparak_rials']:,} ریال |",
            f"| ℹ️ **واریزهای ثبت‌نشده در سامانه / متفرقه** | {summary['other_unmatched_count']} | {summary['other_unmatched_tomans']:,} تومان | {summary['other_unmatched_rials']:,} ریال |",
            "",
            "---",
            "",
        ]

        # Section 1: Verified Matches
        report.append("## ✅ لیست تراکنش‌های معتبر و تطبیق‌شده")
        if self.verified_matches:
            report.append("")
            report.append("| شناسه | نام ساکن | اتاق | مبلغ (تومان) | زمان سامانه | زمان بانک | اختلاف زمان | سطح تطبیق | کد رهگیری |")
            report.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for m in self.verified_matches:
                tx = m.transaction
                b = m.bank_item
                room_str = str(tx.resident.room.room_number) if tx.resident.room else "-"
                tx_time_str = tx.payment_date.strftime("%Y/%m/%d %H:%M") if tx.payment_date else "-"
                diff_str = f"{int(m.time_diff_minutes)} دقیقه" if m.time_diff_minutes < 120 else f"{m.time_diff_minutes / 60:.1f} ساعت"
                tier_str = "سطح ۱ (کد رهگیری)" if m.tier == 1 else f"سطح ۲ ({m.confidence_score}٪)"
                code_str = b.tracking_code or "-"
                report.append(
                    f"| {tx.id} | {tx.resident.full_name} | {room_str} | {tx.amount // 10:,} | {tx_time_str} | {b.jalali_datetime_str} | {diff_str} | {tier_str} | `{code_str}` |"
                )
        else:
            report.append("\n*هیچ تراکنشی تطبیق داده نشد.*")

        report.append("")
        report.append("---")
        report.append("")

        # Section 2: Unverified / Fake Receipts
        report.append("## 🚨 تراکنش‌های مشکوک / فاقد واریز در صورت‌حساب (احتمال فیش جعلی)")
        if self.unverified_transactions:
            report.append("")
            report.append("> [!WARNING]")
            report.append("> تراکنش‌های زیر در سامانه با عنوان `BANK_TRANSFER` ثبت شده‌اند، اما هیچ واریزی با این مشخصات در بازه صورت‌حساب در بانک یافت نشد.")
            report.append("")
            report.append("| شناسه تراکنش | نام ساکن | اتاق | مبلغ (تومان) | تاریخ ثبت سامانه | کد رهگیری ثبت‌شده در سامانه | وضعیت |")
            report.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
            for tx in self.unverified_transactions:
                room_str = str(tx.resident.room.room_number) if tx.resident.room else "-"
                tx_time_str = tx.payment_date.strftime("%Y/%m/%d %H:%M") if tx.payment_date else "-"
                ref_str = tx.reference_number or "ثبت‌نشده"
                report.append(
                    f"| {tx.id} | {tx.resident.full_name} | {room_str} | {tx.amount // 10:,} | {tx_time_str} | {ref_str} | ❌ عدم تایید |"
                )
        else:
            report.append("\n*تبریک! هیچ تراکنش مشکوک یا فاقد واریزی یافت نشد.*")

        report.append("")
        report.append("---")
        report.append("")

        # Section 3: Unmatched Bank Deposits
        report.append("## ℹ️ واریزهای صورت‌حساب بدون رکورد متناظر در سامانه")
        other_unmatched = [b for b in self.unmatched_bank_deposits if b.deposit_category != "SHAPARAK"]
        if other_unmatched:
            report.append("")
            report.append("| ردیف بانک | نوع واریز | مبلغ (تومان) | تاریخ و ساعت | کد رهگیری | کارت مبدا | شرح بانک |")
            report.append("| :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
            for b in other_unmatched[:50]:  # Limit to 50 for readability
                report.append(
                    f"| {b.row_id} | {b.deposit_category} | {b.amount_tomans:,} | {b.jalali_datetime_str} | `{b.tracking_code or '-'}` | {b.origin_card_last4 or '-'} | {b.description[:60]}... |"
                )
        else:
            report.append("\n*همه واریزهای انفرادی تطبیق داده شده‌اند.*")

        return "\n".join(report)
