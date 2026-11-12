"""
Excel & Spreadsheet Processor Service for Dormitory Management System.
Processes both:
1. RAW TELEGRAM BOT SESSIONS (with embedded receipt images, voice transcription notes,
   new resident registrations, room changes, checkouts, and split payments).
2. CLEANED BATCH SPREADSHEETS (conforming to BATCH_RECEIPT_PROTOCOL.md with standard headers).
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import logging
import os
import re
import shutil
import zoneinfo
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jdatetime
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from django.conf import settings
from django.db import transaction

from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Resident, Room, Transaction
from apps.dormitory.jalali_utils import (
    parse_jalali_date,
    format_period_name,
    calculate_settlement_advance,
    get_days_in_jalali_month,
    add_jalali_months,
    normalize_settlement_boundary,
)
from apps.dormitory.services.receipt_processor import (
    process_receipt,
    find_resident_smart,
    normalize_persian,
    strip_all_spaces,
    parse_jalali_datetime,
    calculate_expected_rent_tomans,
)

logger = logging.getLogger(__name__)

# Persian digits translation table
PERSIAN_DIGITS_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Persian Jalali Month Mapping
JALALI_MONTHS = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "آذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}

# Persian word values for currency amounts
WORD_VALUES = {
    "صفر": 0,
    "یک": 1,
    "یه": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "شیش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
    "صد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "پونصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
}


def parse_persian_colloquial_amount(text: str) -> int:
    """
    Robust parser converting Persian digit strings and colloquial verbal amounts into integer Tomans.
    Supports:
      '۵۰۰ هزار' -> 500,000
      '۷۰۰ هزار تومان' -> 700,000
      'سه میلیون و هشتصد' -> 3,800,000
      '۴ میلیون و ۸۰۰ هزار' -> 4,800,000
      '۳ میلیون و پانصد هزار' -> 3,500,000
      'دو میلیون' -> 2,000,000
      'دو و نیم میلیون' -> 2,500,000
      '۴,۵۰۰,۰۰۰' -> 4,500,000
    """
    if not text:
        return 0

    s = text.translate(PERSIAN_DIGITS_TRANS).strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")

    # Check for pure formatted digits like 4,500,000 or 4500000
    digit_clean = re.sub(r"[^\d]", "", s)
    if digit_clean and len(digit_clean) >= 5 and re.match(r"^[\d,.\s]+$", s.replace("تومان", "").replace("تومن", "").strip()):
        return int(digit_clean)

    # Convert colloquial "X و نیم میلیون" to "X میلیون و پانصد هزار"
    s = re.sub(r"(\b[^\s]+\b)\s+و\s+نیم\s+میلیون", r"\1 میلیون و پانصد هزار", s)
    s = s.replace("نیم میلیون", "500 هزار")
    s = s.replace("نیم", "500 هزار")

    tokens = [t.strip() for t in s.replace(" و ", " ").split() if t.strip()]
    total = 0
    current = 0
    saw_million = False

    for t in tokens:
        if t in WORD_VALUES:
            current += WORD_VALUES[t]
        elif t.isdigit():
            current += int(t)
        elif t == "میلیون":
            saw_million = True
            if current == 0:
                current = 1
            current *= 1_000_000
            total += current
            current = 0
        elif t in ("هزار", "تومان", "تومن"):
            if t == "هزار":
                if current == 0:
                    current = 1
                current *= 1_000
                total += current
                current = 0

    if current > 0:
        if saw_million and 1 <= current < 1000:
            current *= 1_000
        total += current

    return total


def extract_financial_amounts(text: str) -> Tuple[int, int, int, Optional[int]]:
    """
    Extracts rent, deposit, total amounts, and optional installment remainder from Persian note.
    Returns: (rent_tomans, deposit_tomans, total_tomans, remainder_tomans).
    """
    if not text:
        return 0, 0, 0, None

    clean_text = text.replace("\n", " ")

    # 1. Check for split: Rent + Deposit
    # e.g. "۴ میلیون و پانصد هزار تومان برای شهریه و دو میلیون تومان برای ودیعه"
    # or "سه میلیون و هشتصد هزار تومان برای اجاره و یک میلیون تومان هم برای ودیعه"
    m_rent = re.search(r"(?:که|این مبلغ|مبلغ)?\s*([^\n]+?)\s*(?:تومان|تومن)?\s+برای\s+(?:شهریه|اجاره)", clean_text)
    m_dep = re.search(r"برای\s+(?:شهریه|اجاره)\s+و\s+([^\n]+?)\s*(?:تومان|تومن)?\s+(?:هم\s+)?برای\s+ودیعه", clean_text)
    if m_rent and m_dep:
        rent_str = m_rent.group(1).split("که")[-1].split("مبلغ")[-1].strip()
        dep_str = m_dep.group(1).strip()
        rent_val = parse_persian_colloquial_amount(rent_str)
        dep_val = parse_persian_colloquial_amount(dep_str)
        if rent_val > 0 or dep_val > 0:
            return rent_val, dep_val, rent_val + dep_val, None

    # Check for installment remainder: e.g. 'مبلغ ۳ میلیون تومان دیگر باید پرداخت کند' or 'مابقی ۵۰۰ هزار تومان'
    remainder = None
    m_rem = re.search(r"(?:مبلغ\s+)?([\d\s\u0600-\u06FF]+?)\s*(?:تومان|تومن)?\s+(?:دیگر\s+باید\s+پرداخت)", clean_text)
    if not m_rem:
        m_rem = re.search(r"مابقی\s+([\d\s\u0600-\u06FF]+?)(?:\s+(?:تومان|تومن|رو|را|واریز|پرداخت|$))", clean_text)
    if m_rem:
        rem_str = m_rem.group(1).split("تصفیه")[-1].split("تسویه")[-1].split("مبلغ")[-1].strip()
        remainder = parse_persian_colloquial_amount(rem_str)

    # 2. Extract primary payment amount
    m_mablagh_all = re.findall(
        r"مبلغ\s+([\d\s\u0600-\u06FF]+?)(?=(?:\s+(?:تومان|تومن|واریز|کارت|پرداخت|در\s+تاریخ|که|ثبت|به|برای|$)))",
        clean_text,
    )
    primary_amt = 0
    for match_txt in m_mablagh_all:
        amt = parse_persian_colloquial_amount(match_txt)
        if amt > 0 and amt != remainder:
            primary_amt = amt
            break
        elif amt > 0 and primary_amt == 0:
            primary_amt = amt

    if primary_amt == 0:
        # Match 'X میلیون/هزار تومان'
        m_alt = re.search(r"((?:[\d\s]+|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|پانصد|پونصد|هشتصد|هفتصد|ششصد|چهارصد|سیصد|دویست|صد)\s*(?:میلیون|هزار))\s*(?:تومان|تومن)?", clean_text)
        if m_alt:
            primary_amt = parse_persian_colloquial_amount(m_alt.group(0))

    if "ودیعه" in clean_text and "اجاره" not in clean_text and "شهریه" not in clean_text:
        return 0, primary_amt, primary_amt, remainder
    return primary_amt, 0, primary_amt, remainder


def parse_persian_date_text(
    text: str, default_year: int = 1405
) -> Optional[jdatetime.date]:
    """Parse Jalali date expressions from Persian text."""
    if not text:
        return None

    s = text.translate(PERSIAN_DIGITS_TRANS).strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    s = s.replace("اول", "1").replace("یکم", "1")

    # Match: YYYY/MM/DD or YYYY-MM-DD
    m_num = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m_num:
        try:
            return jdatetime.date(int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3)))
        except Exception:
            pass

    # Match: "تا آخر سال" or "تا پایان سال"
    if re.search(r"تا\s+(?:آخر|پایان|ته)\s+سال", s):
        return jdatetime.date(default_year + 1, 1, 1)

    # Match: "تا آخر/پایان <month>"
    m_end_month = re.search(r"تا\s+(?:آخر|پایان|ته)\s+([\u0600-\u06FF]+)", s)
    if m_end_month:
        month_word = m_end_month.group(1).replace("ماه", "").strip()
        for m_name, m_num in JALALI_MONTHS.items():
            if m_name in month_word:
                next_m = add_jalali_months(jdatetime.date(default_year, m_num, 1), 1)
                return jdatetime.date(next_m.year, next_m.month, 1)

    # Match: "تا <day> <month>"
    m_settle = re.search(r"تا\s+(\d{1,2})\s+([\u0600-\u06FF]+)", s)
    if m_settle:
        day = int(m_settle.group(1))
        month_word = m_settle.group(2).replace("ماه", "").strip()
        for m_name, m_num in JALALI_MONTHS.items():
            if m_name in month_word:
                days_in_m = get_days_in_jalali_month(default_year, m_num)
                # If target day is the last day of month, normalize to 1st of next month
                if day == days_in_m:
                    next_m = add_jalali_months(jdatetime.date(default_year, m_num, 1), 1)
                    return jdatetime.date(next_m.year, next_m.month, 1)
                return jdatetime.date(default_year, m_num, day)

    # Match: "در تاریخ <day> <month>" or "تاریخ ورود <day> <month>"
    m_date = re.search(r"(?:تاریخ|در)\s+(\d{1,2})\s+([\u0600-\u06FF]+)", s)
    if m_date:
        day = int(m_date.group(1))
        month_word = m_date.group(2).replace("ماه", "").strip()
        for m_name, m_num in JALALI_MONTHS.items():
            if m_name in month_word:
                return jdatetime.date(default_year, m_num, day)

    return None


def parse_persian_time_text(text: str) -> Optional[Tuple[int, int]]:
    """Extract hour and minute from text like 'ساعت ۲۳/۱۲ دقیقه' or 'ساعت ۲۰:۳۷'."""
    if not text:
        return None
    s = text.translate(PERSIAN_DIGITS_TRANS).strip()
    m = re.search(r"ساعت\s*(\d{1,2})[:/.](\d{1,2})", s)
    if m:
        try:
            h = int(m.group(1))
            m_val = int(m.group(2))
            if 0 <= h <= 23 and 0 <= m_val <= 59:
                return h, m_val
        except Exception:
            pass
    return None


@dataclass
class ExtractedImage:
    """Represents an embedded receipt or ID card photo extracted from the raw spreadsheet."""

    resident_row_id: str
    cell_coord: str
    file_name: str
    saved_path: Optional[Path] = None
    image_bytes: Optional[bytes] = None


@dataclass
class TransactionRow:
    """Represents a structured transaction row (from cleaned batch spreadsheet)."""

    row_index: int
    resident_name: str
    room_number: Optional[str]
    rent_tomans: int = 0
    deposit_tomans: int = 0
    payment_date: Optional[str] = None
    reference_number: str = ""
    payment_method: str = "CARD"
    settled_until: Optional[str] = None
    description: str = ""
    row_hash: str = ""
    status: str = "PENDING"  # PENDING, SUCCESS, DUPLICATE, FAILED
    error_reason: Optional[str] = None
    resident_obj: Optional[Resident] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawResidentEvent:
    """Represents an interpreted event from a raw Telegram bot session row."""

    resident_row_id: str
    action_type: str  # PAYMENT, SPLIT_PAYMENT, CHECK_IN, CHECK_OUT, ROOM_CHANGE, DOUBT_FLAG
    resident_name: str
    room_number: Optional[str] = None
    rent_tomans: int = 0
    deposit_tomans: int = 0
    total_tomans: int = 0
    payment_method: str = "CARD"
    payment_date: Optional[str] = None
    settled_until: Optional[str] = None
    reference_number: str = ""
    notes: str = ""
    new_resident_details: Dict[str, Any] = field(default_factory=dict)
    room_change_details: Dict[str, Any] = field(default_factory=dict)
    check_out_details: Dict[str, Any] = field(default_factory=dict)
    doubt_details: Dict[str, Any] = field(default_factory=dict)
    images: List[ExtractedImage] = field(default_factory=list)


@dataclass
class ProcessReport:
    """Comprehensive summary of Excel ingestion execution."""

    mode: str  # "CLEANED_BATCH" or "RAW_TELEGRAM_SESSION"
    source_file: str
    file_hash: str
    total_rows: int = 0
    succeeded_rows: int = 0
    failed_rows: int = 0
    duplicate_rows: int = 0
    discrepancy_rows: int = 0
    total_rent_tomans: int = 0
    total_deposit_tomans: int = 0
    transactions_created: List[Dict[str, Any]] = field(default_factory=list)
    failed_items: List[Tuple[Dict[str, Any], str]] = field(default_factory=list)
    discrepancies: List[Dict[str, Any]] = field(default_factory=list)
    extracted_images: List[ExtractedImage] = field(default_factory=list)
    new_residents_registered: List[Dict[str, Any]] = field(default_factory=list)
    room_changes_applied: List[Dict[str, Any]] = field(default_factory=list)
    check_outs_applied: List[Dict[str, Any]] = field(default_factory=list)
    doubts_flagged: List[Dict[str, Any]] = field(default_factory=list)
    dry_run: bool = True
    output_cleaned_excel: Optional[str] = None
    output_failed_excel: Optional[str] = None

    @property
    def total_amount_tomans(self) -> int:
        return self.total_rent_tomans + self.total_deposit_tomans

    @property
    def total_amount_rials(self) -> int:
        return self.total_amount_tomans * 10


class DormitoryExcelProcessor:
    """
    Core engine to process dormitory spreadsheets:
    - Automatically identifies sheet type (Raw Telegram Session vs. Cleaned Batch Table).
    - Extracts embedded receipt images and correlates them with row transactions.
    - Parses Persian text notes and extracts dates, amounts, actions, and entities.
    - Applies transactions atomically via ReceiptProcessor.
    - Supports dry-run simulation, discrepancy flagging, error report generation, and dropzone archiving.
    """

    SUPPORTED_HEADERS_CLEANED = {
        "resident": ["نام مقیم", "نام ساکن", "نام", "ساکن", "resident", "name", "resident_name"],
        "room": ["شماره اتاق", "اتاق", "room", "room_number"],
        "rent_tomans": ["مبلغ اجاره (تومان)", "اجاره (تومان)", "اجاره", "مبلغ اجاره", "rent", "rent_tomans"],
        "deposit_tomans": ["مبلغ ودیعه (تومان)", "ودیعه (تومان)", "ودیعه", "مبلغ ودیعه", "deposit", "deposit_tomans"],
        "date": ["تاریخ و زمان", "تاریخ", "date", "datetime", "payment_date"],
        "ref": ["اطلاعات رهگیری", "پیگیری", "مرجع", "کد رهگیری", "ref", "reference", "tracking"],
        "method": ["روش پرداخت", "نوع پرداخت", "روش", "method", "payment_method"],
        "settled_until": ["تسویه تا", "تاریخ تسویه", "settled_until", "settle_until"],
        "desc": ["توضیحات", "شرح", "یادداشت", "desc", "description", "note", "notes"],
    }

    def __init__(self, supervisor_id: int = 1, default_year: int = 1405):
        self.supervisor_id = supervisor_id
        self.default_year = default_year
        self.tehran_tz = zoneinfo.ZoneInfo("Asia/Tehran")

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of spreadsheet file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def compute_row_hash(file_hash: str, row_index: int, row_data: Dict[str, Any]) -> str:
        """Deterministic SHA-256 hash for a single row."""
        canonical_json = json.dumps(row_data, sort_keys=True, default=str)
        payload = f"{file_hash}:{row_index}:{canonical_json}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def detect_workbook_mode(
        self, wb: openpyxl.Workbook
    ) -> Tuple[str, openpyxl.worksheet.worksheet.Worksheet]:
        """
        Determine whether workbook is RAW_TELEGRAM_SESSION or CLEANED_BATCH.
        Returns (mode, target_worksheet).
        """
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            first_row = [cell.value for cell in ws[1] if cell.value is not None]
            if not first_row:
                continue
            first_cell = str(first_row[0]).strip().lower()
            if "raw" in sheet_name.lower() or first_cell == "resident_row_id" or "resident_" in first_cell:
                return "RAW_TELEGRAM_SESSION", ws

        for sheet_name in wb.sheetnames:
            if sheet_name.startswith("_") or sheet_name.lower() == "guide":
                continue
            ws = wb[sheet_name]
            first_row = [str(cell.value).strip().lower() for cell in ws[1] if cell.value is not None]
            has_resident = any(
                any(alias.lower() in col for alias in self.SUPPORTED_HEADERS_CLEANED["resident"])
                for col in first_row
            )
            if has_resident:
                return "CLEANED_BATCH", ws

        ws_active = wb.active
        return "CLEANED_BATCH", ws_active

    # =========================================================================
    # 1. RAW TELEGRAM BOT SPREADSHEET PARSING
    # =========================================================================

    def extract_images_from_worksheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, output_dir: Optional[Path] = None
    ) -> Dict[str, List[ExtractedImage]]:
        """
        Extract all cell-anchored images in the worksheet and optionally save them to output_dir.
        Returns a dict: resident_row_id -> list[ExtractedImage].
        """
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
        images_by_resident: Dict[str, List[ExtractedImage]] = {}

        if not hasattr(ws, "_images") or not ws._images:
            return images_by_resident

        for idx, img in enumerate(ws._images, start=1):
            try:
                row_idx = img.anchor._from.row + 1
                col_idx = img.anchor._from.col + 1
                col_letter = get_column_letter(col_idx)
                coord = f"{col_letter}{row_idx}"
                resident_id = str(ws.cell(row=row_idx, column=1).value or f"Resident_{row_idx - 1}").strip()

                img_data_fn = getattr(img, "_data", None)
                if callable(img_data_fn):
                    raw_bytes = img_data_fn()
                else:
                    raw_bytes = getattr(img, "ref", None)
                    if isinstance(raw_bytes, io.BytesIO):
                        raw_bytes = raw_bytes.getvalue()
                    elif isinstance(raw_bytes, (bytes, bytearray)):
                        raw_bytes = bytes(raw_bytes)
                    else:
                        continue

                file_ext = "jpg"
                if raw_bytes.startswith(b"\x89PNG"):
                    file_ext = "png"

                target_filename = f"{resident_id}_{coord}_{idx:02d}.{file_ext}"
                target_path = None
                if output_dir:
                    target_path = output_dir / target_filename
                    target_path.write_bytes(raw_bytes)

                extracted = ExtractedImage(
                    resident_row_id=resident_id,
                    cell_coord=coord,
                    file_name=target_filename,
                    saved_path=target_path,
                    image_bytes=raw_bytes,
                )
                images_by_resident.setdefault(resident_id, []).append(extracted)

            except Exception as e:
                logger.warning("Failed to extract image at anchor %s: %s", getattr(img, "anchor", None), e)

        return images_by_resident

    def parse_raw_row_notes(
        self,
        resident_id: str,
        blocks_text: List[str],
        row_images: List[ExtractedImage],
    ) -> List[RawResidentEvent]:
        """
        Parse text notes and blocks for a single resident row in a raw Telegram session.
        Handles:
        - CHECK_IN (new resident registrations)
        - ROOM_CHANGE (transferring between rooms)
        - CHECK_OUT (resident leaving)
        - SPLIT_PAYMENT (rent + deposit)
        - PAYMENT (rent or deposit)
        - DOUBT_FLAG (installments, underpayments, university split, duplicate check requests)
        """
        full_text = " || ".join(t.strip() for t in blocks_text if t.strip())
        events: List[RawResidentEvent] = []

        raw_chunks = [b for b in blocks_text if b.strip() and not b.strip().startswith("[IMAGE_ANCHOR")]
        if not raw_chunks:
            if row_images:
                events.append(
                    RawResidentEvent(
                        resident_row_id=resident_id,
                        action_type="PAYMENT",
                        resident_name="",
                        notes=full_text,
                        images=row_images,
                    )
                )
            return events

        # Handle compound chunks
        parsed_chunks: List[str] = []
        for ch in raw_chunks:
            if "خوابگاه را ترک کرد" in ch and "جابجا شد" in ch:
                parts = re.split(r"\s+و\s+(?=[\u0600-\u06FF\s]+از\s+اتاق)", ch)
                parsed_chunks.extend(parts)
            else:
                parsed_chunks.append(ch)

        # Check if one block is payment and another is new resident details
        # e.g. Row 13 has Block 2 (split payment) and Block 4 (resident profile)
        combined_new_resident: Optional[Dict[str, Any]] = None
        for ch in parsed_chunks:
            ch_norm = normalize_persian(ch)
            ch_digits = ch_norm.translate(PERSIAN_DIGITS_TRANS)
            if "نیروی جدید" in ch_norm or "ساکن جدید" in ch_norm:
                if "کد ملی" in ch_norm or "نام پدر" in ch_norm or "شماره همراه" in ch_norm:
                    # Profile info block
                    room_m = re.search(r"اتاق\s*(\d+)", ch_digits)
                    room_num = room_m.group(1) if room_m else None

                    name = ""
                    name_m = re.search(
                        r"(?:نیروی جدید|ساکن جدید)\s+(?:برای\s+اتاق\s+\d+\s+)?(?:نام\s+)?([^\d\n]+?)(?:در\s+اتاق|نام\s+پدر|شماره|تلفن|کد\s*ملی|تاریخ\s*ورود|مبلغ|ثبت\s*بشود)",
                        ch_norm,
                    )
                    if name_m:
                        name = name_m.group(1).replace("برای", "").replace("اتاق", "").strip()

                    father_m = re.search(r"نام\s*پدر\s+([آ-ی\s]+?)(?:شماره|تلفن|همراه|کد\s*ملی|تاریخ|مبلغ|$)", ch_norm)
                    father_name = father_m.group(1).strip() if father_m else ""

                    nat_m = re.search(r"کد\s*ملی\s*[:\s]*(\d[\d\s]{8,12}\d)", ch_digits)
                    national_code = re.sub(r"\s+", "", nat_m.group(1)) if nat_m else ""

                    phone_m = re.search(r"(?:شماره همراه|تلفن همراه|شماره تماس|تلفن)\s*[:\s]*(\d[\d\s]{9,12}\d)", ch_digits)
                    phone = re.sub(r"\s+", "", phone_m.group(1)) if phone_m else ""

                    parent_m = re.search(r"(?:همراه والدین|تلفن والدین|شماره والدین|والدین)\s*[:\s]*(\d[\d\s]{9,12}\d)", ch_digits)
                    parent_phone = re.sub(r"\s+", "", parent_m.group(1)) if parent_m else ""

                    entry_d = parse_persian_date_text(ch_norm, self.default_year)

                    combined_new_resident = {
                        "name": name,
                        "room_number": room_num,
                        "father_name": father_name,
                        "national_code": national_code,
                        "phone_number": phone,
                        "parent_phone_number": parent_phone,
                        "entry_date": str(entry_d) if entry_d else str(jdatetime.date.today()),
                        "profile_chunk": ch,
                    }
                    break

        for chunk in parsed_chunks:
            ch_norm = normalize_persian(chunk)
            ch_digits = ch_norm.translate(PERSIAN_DIGITS_TRANS)

            # -------------------------------------------------------------
            # A. CHECK_IN: New Resident Registration
            # -------------------------------------------------------------
            if ("نیروی جدید" in ch_norm or "ساکن جدید" in ch_norm) and combined_new_resident:
                # If this chunk is purely the metadata block and payment was in another block, skip duplicate event
                if chunk == combined_new_resident.get("profile_chunk") and len(parsed_chunks) > 1:
                    continue

                rent_t, dep_t, tot_t, rem_t = extract_financial_amounts(ch_norm)
                room_num = combined_new_resident.get("room_number")
                if not room_num:
                    r_m = re.search(r"اتاق\s*(\d+)", ch_digits)
                    room_num = r_m.group(1) if r_m else None

                name = combined_new_resident.get("name")
                if not name:
                    name_m = re.search(r"(?:نیروی جدید|ساکن جدید)\s+([آ-ی\s]+?)\s+(?:نیروی جدید|هستش|اتاق)", ch_norm)
                    name = name_m.group(1).strip() if name_m else "ساکن جدید"

                method = "CARD"
                if "کارت به کارت" in ch_norm or "واریز" in ch_norm:
                    method = "BANK_TRANSFER"

                settle_d = parse_persian_date_text(f"تا {ch_norm.split('تا')[-1]}" if "تا" in ch_norm else "", self.default_year)
                settle_str = str(settle_d) if settle_d else None

                doubt = {}
                if rem_t:
                    doubt = {"flag_type": "INSTALLMENT_COMMITMENT", "remainder_tomans": rem_t, "note": chunk}
                elif "مابقی" in ch_norm or "کسری" in ch_norm or "تعهد" in ch_norm:
                    doubt = {"flag_type": "INSTALLMENT_COMMITMENT", "note": chunk}

                events.append(
                    RawResidentEvent(
                        resident_row_id=resident_id,
                        action_type="CHECK_IN",
                        resident_name=name,
                        room_number=room_num,
                        rent_tomans=rent_t,
                        deposit_tomans=dep_t,
                        total_tomans=tot_t,
                        payment_method=method,
                        settled_until=settle_str,
                        notes=chunk,
                        new_resident_details=combined_new_resident,
                        doubt_details=doubt,
                        images=row_images,
                    )
                )
                continue

            # -------------------------------------------------------------
            # B. ROOM_CHANGE: Resident Moving Rooms
            # -------------------------------------------------------------
            if "جابجا شد" in ch_norm or "تغییر اتاق" in ch_norm or "منتقل شد" in ch_norm:
                transfer_m = re.search(r"([آ-ی\s]+?)\s+از\s+اتاق\s*(\d+)\s+به\s*(\d+)", ch_digits)
                if transfer_m:
                    res_name = transfer_m.group(1).strip()
                    from_room = transfer_m.group(2).strip()
                    to_room = transfer_m.group(3).strip()
                    events.append(
                        RawResidentEvent(
                            resident_row_id=resident_id,
                            action_type="ROOM_CHANGE",
                            resident_name=res_name,
                            room_number=to_room,
                            room_change_details={"from_room": from_room, "to_room": to_room},
                            notes=chunk,
                            images=row_images,
                        )
                    )
                    continue

            # -------------------------------------------------------------
            # C. CHECK_OUT: Resident Leaving Dormitory
            # -------------------------------------------------------------
            if "ترک کرد" in ch_norm or "تخلیه کرد" in ch_norm or "تسویه کرد و رفت" in ch_norm:
                checkout_m = re.search(r"([آ-ی\s]+?)\s+اتاق\s*(\d+)\s+خوابگاه را ترک کرد", ch_digits)
                if checkout_m:
                    res_name = checkout_m.group(1).strip()
                    room_num = checkout_m.group(2).strip()
                else:
                    r_m = re.search(r"اتاق\s*(\d+)", ch_digits)
                    room_num = r_m.group(1) if r_m else None
                    res_name = ch_norm.split("اتاق")[0].strip()

                events.append(
                    RawResidentEvent(
                        resident_row_id=resident_id,
                        action_type="CHECK_OUT",
                        resident_name=res_name,
                        room_number=room_num,
                        check_out_details={"exit_date": str(jdatetime.date.today())},
                        notes=chunk,
                        images=row_images,
                    )
                )
                continue

            # -------------------------------------------------------------
            # D. SPECIAL DOUBT / MULTI-STUDENT POOLING (e.g. University payment)
            # -------------------------------------------------------------
            if "دانشگاه" in ch_norm and "هر دوی" in ch_norm:
                _, _, tot_t, _ = extract_financial_amounts(ch_norm)
                events.append(
                    RawResidentEvent(
                        resident_row_id=resident_id,
                        action_type="DOUBT_FLAG",
                        resident_name="واریزی دانشگاه (چند نفره)",
                        total_tomans=tot_t,
                        notes=chunk,
                        doubt_details={
                            "flag_type": "UNIVERSITY_MULTI_STUDENT_POOL",
                            "amount_tomans": tot_t,
                            "explanation": chunk,
                        },
                        images=row_images,
                    )
                )
                continue

            # -------------------------------------------------------------
            # E. STANDARD PAYMENT / SPLIT PAYMENT
            # -------------------------------------------------------------
            room_m = re.search(r"اتاق\s*(\d+)", ch_digits)
            room_num = room_m.group(1) if room_m else None

            # Resident Name
            name = ""
            if "اتاق" in ch_norm:
                name_candidate = ch_norm.split("اتاق")[0].strip()
                name_candidate = re.sub(
                    r"^.*(?:ثبت نکن|ثبت کن|چک کن|بررسی کن|نمی\u200cدونم|نمیدونم|داره)\s*",
                    "",
                    name_candidate,
                )
                name = name_candidate.strip()

            rent_t, dep_t, tot_t, rem_t = extract_financial_amounts(ch_norm)
            
            # If rent is 0 but room number is known and explicit settlement is given, deduce from room tariff
            if rent_t == 0 and tot_t == 0 and room_num:
                try:
                    target_room = Room.objects.filter(room_number=room_num).first()
                    if target_room and target_room.monthly_rent:
                        rent_t = target_room.monthly_rent // 10
                        tot_t = rent_t
                except Exception:
                    pass

            is_split = (rent_t > 0 and dep_t > 0)

            # Payment method
            method = "CARD"
            if "کارت به کارت" in ch_norm or "واریز" in ch_norm:
                method = "BANK_TRANSFER"
            elif "نقدی" in ch_norm or "نقد" in ch_norm:
                method = "CASH"

            # Settlement target date
            settle_d = parse_persian_date_text(f"تا {ch_norm.split('تا')[-1]}" if "تا" in ch_norm else "", self.default_year)
            settle_str = str(settle_d) if settle_d else None

            # Datetime
            payment_date_str = None
            date_d = parse_persian_date_text(ch_norm, self.default_year)
            time_tuple = parse_persian_time_text(ch_norm)
            if date_d:
                hour = time_tuple[0] if time_tuple else 12
                minute = time_tuple[1] if time_tuple else 0
                payment_date_str = f"{date_d.year:04d}/{date_d.month:02d}/{date_d.day:02d} {hour:02d}:{minute:02d}:00"

            doubt = {}
            if "قبلاً ثبت شده" in ch_norm or "ثبت نکن" in ch_norm:
                doubt = {"flag_type": "DUPLICATE_CHECK_REQUESTED", "note": chunk}
            elif rem_t:
                doubt = {"flag_type": "INSTALLMENT_BALANCE_REMAINING", "remainder_tomans": rem_t, "note": chunk}

            events.append(
                RawResidentEvent(
                    resident_row_id=resident_id,
                    action_type="SPLIT_PAYMENT" if is_split else "PAYMENT",
                    resident_name=name,
                    room_number=room_num,
                    rent_tomans=rent_t,
                    deposit_tomans=dep_t,
                    total_tomans=tot_t,
                    payment_method=method,
                    payment_date=payment_date_str,
                    settled_until=settle_str,
                    notes=chunk,
                    doubt_details=doubt,
                    images=row_images,
                )
            )

        return events

    def parse_raw_telegram_session(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, output_image_dir: Optional[Path] = None
    ) -> List[RawResidentEvent]:
        """Parse complete Raw_Transactions worksheet, extracting images and structured resident events."""
        images_by_resident = self.extract_images_from_worksheet(ws, output_image_dir)
        all_events: List[RawResidentEvent] = []

        rows_iter = list(ws.iter_rows(values_only=True))
        if len(rows_iter) <= 1:
            return all_events

        for row_idx, row_values in enumerate(rows_iter[1:], start=2):
            if not row_values:
                continue

            res_id = str(row_values[0] or f"Resident_{row_idx - 1}").strip()
            blocks_text = [str(val).strip() for val in row_values[1:] if val is not None and str(val).strip()]

            row_images = images_by_resident.get(res_id, [])
            row_events = self.parse_raw_row_notes(res_id, blocks_text, row_images)
            all_events.extend(row_events)

        return all_events

    # =========================================================================
    # 2. CLEANED BATCH SPREADSHEET PARSING
    # =========================================================================

    def parse_cleaned_worksheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, file_hash: str
    ) -> List[TransactionRow]:
        """Parse tabular transaction rows conforming to BATCH_RECEIPT_PROTOCOL.md."""
        rows_iter = list(ws.iter_rows(values_only=True))
        if not rows_iter:
            return []

        headers = [str(h).strip() if h is not None else "" for h in rows_iter[0]]
        col_map: Dict[str, int] = {}

        for std_key, aliases in self.SUPPORTED_HEADERS_CLEANED.items():
            for idx, h in enumerate(headers):
                h_lower = h.lower()
                if any(alias.lower() == h_lower or alias.lower() in h_lower for alias in aliases):
                    col_map[std_key] = idx
                    break

        if "resident" not in col_map:
            raise ValueError(f"Could not find required resident name column in sheet '{ws.title}'. Found headers: {headers}")

        parsed_rows: List[TransactionRow] = []

        for row_idx, row_vals in enumerate(rows_iter[1:], start=2):
            if not row_vals or all(v is None or not str(v).strip() for v in row_vals):
                continue

            def get_val(key: str) -> Any:
                idx = col_map.get(key)
                if idx is not None and idx < len(row_vals):
                    return row_vals[idx]
                return None

            raw_res = str(get_val("resident") or "").strip()
            if not raw_res:
                continue

            raw_room = get_val("room")
            room_str = str(raw_room).strip() if raw_room is not None else None

            # Amounts
            rent_val = parse_persian_colloquial_amount(str(get_val("rent_tomans") or 0))
            dep_val = parse_persian_colloquial_amount(str(get_val("deposit_tomans") or 0))

            # Date
            raw_date = get_val("date")
            date_str = None
            if isinstance(raw_date, datetime.datetime):
                jd = jdatetime.datetime.fromgregorian(datetime=raw_date)
                date_str = jd.strftime("%Y/%m/%d %H:%M:%S")
            elif isinstance(raw_date, datetime.date):
                jd = jdatetime.date.fromgregorian(date=raw_date)
                date_str = jd.strftime("%Y/%m/%d 12:00:00")
            elif raw_date:
                date_str = str(raw_date).strip()

            ref_str = str(get_val("ref") or "").strip()

            # Method
            raw_method = str(get_val("method") or "CARD").strip().upper()
            if any(k in raw_method for k in ("کارتخوان", "دستگاه", "POS", "CARD")):
                method_code = "CARD"
            elif any(k in raw_method for k in ("کارت به کارت", "واریز", "انتقال", "BANK_TRANSFER")):
                method_code = "BANK_TRANSFER"
            elif any(k in raw_method for k in ("نقد", "نقدی", "CASH")):
                method_code = "CASH"
            elif any(k in raw_method for k in ("درگاه", "اینترنتی", "ONLINE")):
                method_code = "ONLINE_GATEWAY"
            else:
                method_code = "CARD"

            # Settled until
            raw_settled = get_val("settled_until")
            settled_str = None
            if isinstance(raw_settled, (datetime.date, datetime.datetime)):
                jd = jdatetime.date.fromgregorian(date=raw_settled if isinstance(raw_settled, datetime.date) else raw_settled.date())
                settled_str = jd.strftime("%Y-%m-%d")
            elif raw_settled:
                settled_str = str(raw_settled).strip()

            desc_str = str(get_val("desc") or "").strip()

            row_dict = {
                "resident": raw_res,
                "room": room_str,
                "rent_tomans": rent_val,
                "deposit_tomans": dep_val,
                "date": date_str,
                "ref": ref_str,
                "method": method_code,
                "settled_until": settled_str,
                "desc": desc_str,
            }
            row_hash = self.compute_row_hash(file_hash, row_idx, row_dict)

            parsed_rows.append(
                TransactionRow(
                    row_index=row_idx,
                    resident_name=raw_res,
                    room_number=room_str,
                    rent_tomans=rent_val,
                    deposit_tomans=dep_val,
                    payment_date=date_str,
                    reference_number=ref_str,
                    payment_method=method_code,
                    settled_until=settled_str,
                    description=desc_str,
                    row_hash=row_hash,
                )
            )

        return parsed_rows

    # =========================================================================
    # 3. EXECUTION & DATABASE COMMIT
    # =========================================================================

    def execute_cleaned_batch(
        self,
        rows: List[TransactionRow],
        file_path: Path,
        file_hash: str,
        apply: bool = False,
    ) -> ProcessReport:
        """Process cleaned transaction rows, committing via ReceiptProcessor or dry-running."""
        report = ProcessReport(
            mode="CLEANED_BATCH",
            source_file=file_path.name,
            file_hash=file_hash,
            total_rows=len(rows),
            dry_run=not apply,
        )

        for row in rows:
            if row.reference_number:
                existing_tx = Transaction.objects.filter(reference_number=row.reference_number).first()
                if existing_tx:
                    row.status = "DUPLICATE"
                    report.duplicate_rows += 1
                    report.failed_items.append((
                        {"row_index": row.row_index, "resident": row.resident_name, "ref": row.reference_number},
                        f"تراکنش تکراری: قبلاً با شناسه #{existing_tx.id} در سیستم ثبت شده است.",
                    ))
                    continue

            try:
                res = process_receipt(
                    resident=row.resident_name,
                    room=row.room_number,
                    rent_tomans=row.rent_tomans if row.rent_tomans > 0 else None,
                    deposit_tomans=row.deposit_tomans if row.deposit_tomans > 0 else None,
                    method=row.payment_method,
                    date=row.payment_date,
                    ref=row.reference_number,
                    desc=row.description,
                    settled_until=row.settled_until,
                    supervisor_id=self.supervisor_id,
                    dry_run=not apply,
                )

                row.status = "SUCCESS"
                report.succeeded_rows += 1
                report.total_rent_tomans += row.rent_tomans
                report.total_deposit_tomans += row.deposit_tomans

                report.transactions_created.extend(res.get("transactions", []))

                if res.get("discrepancy"):
                    report.discrepancy_rows += 1
                    report.discrepancies.append(res["discrepancy"])

            except Exception as exc:
                row.status = "FAILED"
                row.error_reason = str(exc)
                report.failed_rows += 1
                report.failed_items.append((
                    {
                        "row_index": row.row_index,
                        "resident": row.resident_name,
                        "room": row.room_number,
                        "rent": row.rent_tomans,
                        "deposit": row.deposit_tomans,
                    },
                    str(exc),
                ))

        return report

    def execute_raw_events(
        self,
        events: List[RawResidentEvent],
        file_path: Path,
        file_hash: str,
        apply: bool = False,
        auto_flag_doubts: bool = True,
    ) -> ProcessReport:
        """
        Execute or simulate events from a raw Telegram bot session.
        Applies new resident registration, room changes, checkouts, payments, and doubt logging.
        """
        report = ProcessReport(
            mode="RAW_TELEGRAM_SESSION",
            source_file=file_path.name,
            file_hash=file_hash,
            total_rows=len(events),
            dry_run=not apply,
        )

        default_dorm = Dormitory.objects.first()
        supervisor = (
            Supervisor.objects.filter(id=self.supervisor_id).first()
            or Supervisor.objects.first()
        )

        for ev in events:
            for img in ev.images:
                if img not in report.extracted_images:
                    report.extracted_images.append(img)

            # -----------------------------------------------------------------
            # 1. ACTION: CHECK_IN (New Resident)
            # -----------------------------------------------------------------
            if ev.action_type == "CHECK_IN":
                try:
                    res_obj = None
                    target_room = Room.objects.filter(room_number=ev.room_number).first() if ev.room_number else None

                    parts = ev.resident_name.split(maxsplit=1)
                    f_name = parts[0] if parts else "ساکن"
                    l_name = parts[1] if len(parts) > 1 else "جدید"

                    details = ev.new_resident_details
                    entry_date = parse_jalali_date(details.get("entry_date")) or jdatetime.date.today()

                    if apply:
                        nat = details.get("national_code") or None
                        phone = details.get("phone_number") or ""
                        res_obj = Resident.objects.filter(national_code=nat).first() if nat else None
                        if not res_obj and phone:
                            res_obj = Resident.objects.filter(phone_number=phone).first()

                        if not res_obj:
                            res_obj = Resident.objects.create(
                                first_name=f_name,
                                last_name=l_name,
                                father_name=details.get("father_name") or "",
                                national_code=nat,
                                phone_number=phone or f"09{len(Resident.objects.all()) + 100:09d}",
                                parent_phone_number=details.get("parent_phone_number") or "",
                                room=target_room,
                                dormitory=default_dorm,
                                entry_date=entry_date,
                                status=Resident.Status.ACTIVE,
                                monthly_payment_day=entry_date.day,
                                registered_by=supervisor,
                            )

                    reg_record = {
                        "name": ev.resident_name,
                        "room": ev.room_number,
                        "national_code": details.get("national_code"),
                        "phone": details.get("phone_number"),
                        "entry_date": str(entry_date),
                    }
                    report.new_residents_registered.append(reg_record)

                    # Initial payment if present
                    if ev.total_tomans > 0:
                        res = process_receipt(
                            resident=res_obj or ev.resident_name,
                            room=ev.room_number,
                            rent_tomans=ev.rent_tomans if ev.rent_tomans > 0 else None,
                            deposit_tomans=ev.deposit_tomans if ev.deposit_tomans > 0 else None,
                            method=ev.payment_method,
                            date=ev.payment_date,
                            settled_until=ev.settled_until,
                            desc=ev.notes,
                            supervisor_id=self.supervisor_id,
                            dry_run=not apply,
                        )
                        report.succeeded_rows += 1
                        report.total_rent_tomans += ev.rent_tomans
                        report.total_deposit_tomans += ev.deposit_tomans
                        report.transactions_created.extend(res.get("transactions", []))
                        if res.get("discrepancy"):
                            report.discrepancy_rows += 1
                            report.discrepancies.append(res["discrepancy"])
                    else:
                        report.succeeded_rows += 1

                except Exception as e:
                    report.failed_rows += 1
                    report.failed_items.append((
                        {"resident": ev.resident_name, "room": ev.room_number, "action": "CHECK_IN"},
                        str(e),
                    ))

            # -----------------------------------------------------------------
            # 2. ACTION: ROOM_CHANGE
            # -----------------------------------------------------------------
            elif ev.action_type == "ROOM_CHANGE":
                try:
                    details = ev.room_change_details
                    to_room_obj = Room.objects.filter(room_number=details.get("to_room")).first()
                    res = find_resident_smart(ev.resident_name, details.get("from_room"))

                    if apply and res and to_room_obj:
                        res.room = to_room_obj
                        res.save(update_fields=["room"])

                    report.succeeded_rows += 1
                    report.room_changes_applied.append({
                        "resident": res.full_name if res else ev.resident_name,
                        "from_room": details.get("from_room"),
                        "to_room": details.get("to_room"),
                    })
                except Exception as e:
                    report.failed_rows += 1
                    report.failed_items.append((
                        {"resident": ev.resident_name, "action": "ROOM_CHANGE"},
                        str(e),
                    ))

            # -----------------------------------------------------------------
            # 3. ACTION: CHECK_OUT
            # -----------------------------------------------------------------
            elif ev.action_type == "CHECK_OUT":
                try:
                    last_token = ev.resident_name.split()[-1] if ev.resident_name else ""
                    res = (
                        Resident.objects.filter(
                            last_name__icontains=last_token,
                            room__room_number=ev.room_number,
                        ).first()
                        or Resident.objects.filter(last_name__icontains=last_token).first()
                    )
                    if not res:
                        res = find_resident_smart(ev.resident_name, ev.room_number)

                    if apply and res:
                        res.status = Resident.Status.LEFT
                        if not res.exit_date:
                            res.exit_date = jdatetime.date.today()
                        res.room = None
                        res.save(update_fields=["status", "exit_date", "room"])

                    report.succeeded_rows += 1
                    report.check_outs_applied.append({
                        "resident": res.full_name if res else ev.resident_name,
                        "room": ev.room_number,
                    })
                except Exception as e:
                    report.failed_rows += 1
                    report.failed_items.append((
                        {"resident": ev.resident_name, "action": "CHECK_OUT"},
                        str(e),
                    ))

            # -----------------------------------------------------------------
            # 4. ACTION: DOUBT_FLAG / SPECIAL (e.g. University pool)
            # -----------------------------------------------------------------
            elif ev.action_type == "DOUBT_FLAG":
                report.discrepancy_rows += 1
                report.doubts_flagged.append(ev.doubt_details or {"note": ev.notes})
                report.succeeded_rows += 1

            # -----------------------------------------------------------------
            # 5. ACTION: PAYMENT / SPLIT_PAYMENT
            # -----------------------------------------------------------------
            else:
                # Deduce rent if amount was 0 but room was given and settled_until requested
                rent_amount = ev.rent_tomans
                if rent_amount <= 0 and ev.total_tomans <= 0 and ev.settled_until:
                    try:
                        res_lookup = find_resident_smart(ev.resident_name, ev.room_number)
                        if res_lookup and res_lookup.room and res_lookup.room.monthly_rent:
                            rent_amount = res_lookup.room.monthly_rent // 10
                    except Exception:
                        pass

                if rent_amount <= 0 and ev.total_tomans <= 0 and not ev.images:
                    continue

                try:
                    res = process_receipt(
                        resident=ev.resident_name,
                        room=ev.room_number,
                        rent_tomans=rent_amount if rent_amount > 0 else None,
                        deposit_tomans=ev.deposit_tomans if ev.deposit_tomans > 0 else None,
                        method=ev.payment_method,
                        date=ev.payment_date,
                        ref=ev.reference_number,
                        settled_until=ev.settled_until,
                        desc=ev.notes,
                        supervisor_id=self.supervisor_id,
                        dry_run=not apply,
                    )
                    report.succeeded_rows += 1
                    report.total_rent_tomans += rent_amount
                    report.total_deposit_tomans += ev.deposit_tomans
                    report.transactions_created.extend(res.get("transactions", []))

                    if res.get("discrepancy"):
                        report.discrepancy_rows += 1
                        report.discrepancies.append(res["discrepancy"])

                except Exception as e:
                    report.failed_rows += 1
                    report.failed_items.append((
                        {"resident": ev.resident_name, "room": ev.room_number, "amount": ev.total_tomans},
                        str(e),
                    ))

        if apply and auto_flag_doubts and (report.discrepancies or report.doubts_flagged):
            self._append_to_finance_doubts(report)

        return report

    def _append_to_finance_doubts(self, report: ProcessReport) -> None:
        """Append newly detected discrepancies to FINANCE_DOUBTS.md."""
        doubts_file = Path(settings.BASE_DIR) / "FINANCE_DOUBTS.md"
        if not doubts_file.exists():
            return

        today_jalali = jdatetime.date.today().strftime("%Y/%m/%d")
        new_entries = []

        for d in report.discrepancies:
            tx_id = d.get("transaction_id", "-")
            room = d.get("room_number", "-")
            paid = d.get("paid_rent_tomans", 0)
            expected = d.get("expected_rent_tomans", 0)
            diff = abs(d.get("diff_tomans", 0))
            period = d.get("period_name", "")
            desc = f"**[FLAG: RENT_UNDERPAYMENT] تسویه کامل با کسری {diff:,} تومانی:** پرداخت {paid:,} تومان برای دوره {period} نسبت به اجاره مصوب {expected:,} تومان اتاق {room}."

            entry = f"| #{tx_id} | {d.get('resident_name', 'مقیم')} | {room} | {paid:,} | {expected:,} | {diff:,} کسری | {today_jalali} | {desc} |"
            new_entries.append(entry)

        for doubt in report.doubts_flagged:
            exp = doubt.get("explanation") or doubt.get("note") or "مورد مشکوک نیازمند بررسی سرپرست"
            entry = f"| بررسی | چند ساکن / دانشجو | - | - | - | نیاز به بررسی | {today_jalali} | **[FLAG: SPECIAL_CHECK]** {exp} |"
            new_entries.append(entry)

        if not new_entries:
            return

        content = doubts_file.read_text(encoding="utf-8")
        marker = "## 🚨 ۱. موارد با اولویت بالا و نیازمند بررسی فوری (High Priority Doubts)"
        if marker in content:
            table_header = "| شناسه | نام ساکن | اتاق | مبلغ پرداختی (تومان) | نرخ مصوب (تومان) | کسری / وضعیت | تاریخ | شرح و علت مشکوک بودن |\n|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---|"
            insertion = "\n" + "\n".join(new_entries)
            if table_header in content:
                content = content.replace(table_header, table_header + insertion)
                doubts_file.write_text(content, encoding="utf-8")
                logger.info("Successfully appended %d doubts to FINANCE_DOUBTS.md", len(new_entries))

    # =========================================================================
    # 4. EXPORT HELPERS: CLEANED WORKBOOK & FAILED REPORT
    # =========================================================================

    def export_events_to_cleaned_excel(
        self, events: List[RawResidentEvent], output_path: Path
    ) -> Path:
        """Export raw session events to standard Cleaned_Transactions workbook matching BATCH_RECEIPT_PROTOCOL.md."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Cleaned_Transactions"

        headers = [
            "نام مقیم",
            "شماره اتاق",
            "مبلغ اجاره (تومان)",
            "مبلغ ودیعه (تومان)",
            "تاریخ و زمان",
            "اطلاعات رهگیری",
            "روش پرداخت",
            "تسویه تا",
            "توضیحات",
        ]
        ws.append(headers)

        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[1].height = 25

        for ev in events:
            row_data = [
                ev.resident_name,
                ev.room_number or "",
                ev.rent_tomans if ev.rent_tomans > 0 else 0,
                ev.deposit_tomans if ev.deposit_tomans > 0 else 0,
                ev.payment_date or (str(jdatetime.date.today()) + " 12:00:00"),
                ev.reference_number or (f"PHOTO-{ev.images[0].cell_coord}" if ev.images else ""),
                "کارتخوان" if ev.payment_method == "CARD" else ("کارت به کارت" if ev.payment_method == "BANK_TRANSFER" else "نقدی"),
                ev.settled_until or "",
                ev.notes or "",
            ]
            ws.append(row_data)

        for col in ws.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

        wb.save(output_path)
        return output_path

    def export_failed_rows_report(
        self, failed_items: List[Tuple[Dict[str, Any], str]], output_path: Path
    ) -> Path:
        """Create failed_rows_report.xlsx with original row details and exact error reason."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Failed_Transactions"

        if not failed_items:
            ws.append(["Status", "Message"])
            ws.append(["INFO", "No failed transactions found."])
            wb.save(output_path)
            return output_path

        all_keys = list(failed_items[0][0].keys())
        headers = all_keys + ["Error_Reason"]
        ws.append(headers)

        header_fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[1].height = 25

        for row_dict, reason in failed_items:
            row_vals = [row_dict.get(k, "") for k in all_keys] + [reason]
            ws.append(row_vals)

        for col in ws.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

        wb.save(output_path)
        return output_path

    # =========================================================================
    # 5. PUBLIC HIGH-LEVEL WORKFLOW
    # =========================================================================

    def process_file(
        self,
        file_path: Union[str, Path],
        apply: bool = False,
        extract_images: bool = True,
        image_dir: Optional[Path] = None,
        export_cleaned_path: Optional[Path] = None,
        export_failed_path: Optional[Path] = None,
        auto_flag_doubts: bool = True,
        archive: bool = False,
    ) -> ProcessReport:
        """
        Unified processing pipeline:
        1. Validates file existence and computes hash.
        2. Loads workbook and auto-detects mode (RAW_TELEGRAM_SESSION vs CLEANED_BATCH).
        3. Parses, extracts images, and normalizes entities.
        4. Simulates or commits database changes.
        5. Generates exports and archives file if requested.
        """
        src_path = Path(file_path).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"Spreadsheet file not found: {src_path}")

        file_hash = self.compute_file_hash(src_path)

        try:
            wb = openpyxl.load_workbook(src_path, data_only=True)
        except Exception as exc:
            raise ValueError(f"Corrupted or invalid Excel file: {exc}") from exc

        mode, target_ws = self.detect_workbook_mode(wb)
        logger.info("Detected mode '%s' for file '%s' (sheet: %s)", mode, src_path.name, target_ws.title)

        if mode == "RAW_TELEGRAM_SESSION":
            img_dir = (
                image_dir
                or Path(settings.MEDIA_ROOT) / "spreadsheets" / "extracted_images" / src_path.stem
            )
            raw_events = self.parse_raw_telegram_session(
                target_ws, output_image_dir=img_dir if extract_images else None
            )

            report = self.execute_raw_events(
                raw_events,
                file_path=src_path,
                file_hash=file_hash,
                apply=apply,
                auto_flag_doubts=auto_flag_doubts,
            )

            if export_cleaned_path:
                cleaned_file = self.export_events_to_cleaned_excel(raw_events, Path(export_cleaned_path))
                report.output_cleaned_excel = str(cleaned_file)

        else:
            rows = self.parse_cleaned_worksheet(target_ws, file_hash)
            report = self.execute_cleaned_batch(
                rows,
                file_path=src_path,
                file_hash=file_hash,
                apply=apply,
            )

        wb.close()

        if export_failed_path and report.failed_items:
            failed_file = self.export_failed_rows_report(report.failed_items, Path(export_failed_path))
            report.output_failed_excel = str(failed_file)

        if archive:
            self.archive_file(src_path, success=(report.failed_rows == 0))

        return report

    def archive_file(self, source_path: Path, success: bool = True) -> Path:
        """Move spreadsheet from incoming dropzone to media/spreadsheets/processed/ or failed/."""
        dest_folder = "processed" if success else "failed"
        dest_dir = Path(settings.MEDIA_ROOT) / "spreadsheets" / dest_folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file = dest_dir / source_path.name
        if dest_file.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_file = dest_dir / f"{source_path.stem}_{ts}{source_path.suffix}"

        shutil.move(str(source_path), str(dest_file))

        companion_md = source_path.parent / f"{source_path.stem}_instructions.md"
        if companion_md.exists():
            companion_md.unlink(missing_ok=True)

        return dest_file
