import datetime
import zoneinfo
import re
from typing import Optional, Dict, Any, List, Union

import jdatetime
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import Supervisor
from apps.dormitory.models import Resident, Transaction, Room
from apps.dormitory.jalali_utils import (
    parse_jalali_date,
    format_period_name,
    calculate_settlement_advance,
)


def normalize_persian(text: str) -> str:
    """Normalize Arabic/Persian characters and digits."""
    if not text:
        return ""
    s = str(text).strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("\u200c", " ")
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(trans)


def strip_all_spaces(text: str) -> str:
    """Strip all whitespace and punctuation for fuzzy matching."""
    s = normalize_persian(text).lower()
    return re.sub(r"[\s\-_/\\,.]+", "", s)


def parse_jalali_datetime(dt_str: Optional[str], tehran_tz=None) -> jdatetime.datetime:
    """Parse string to timezone-aware Jalali datetime."""
    if tehran_tz is None:
        tehran_tz = zoneinfo.ZoneInfo("Asia/Tehran")

    if not dt_str:
        now_gregorian = datetime.datetime.now(tehran_tz)
        return jdatetime.datetime.fromgregorian(datetime=now_gregorian)

    s = normalize_persian(dt_str).strip()
    m = re.match(
        r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[\sT-]+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$",
        s,
    )
    if not m:
        # Try fallback today with given time
        raise ValueError(f"فرمت تاریخ و زمان شمسی نامعتبر است: {dt_str}")

    year = int(m.group(1))
    month = int(m.group(2))
    day = int(m.group(3))
    hour = int(m.group(4) or 12)
    minute = int(m.group(5) or 0)
    second = int(m.group(6) or 0)

    return jdatetime.datetime(year, month, day, hour, minute, second, tzinfo=tehran_tz)


def find_resident_smart(query: str, room_num: Optional[Union[str, int]] = None) -> Resident:
    """
    Intelligent resident search engine:
    1. By ID or National Code
    2. Room-prioritized matching (fuzzy token overlap)
    3. Global matching across active residents
    4. Fallback across all residents
    """
    q_norm = normalize_persian(query)
    q_stripped = strip_all_spaces(q_norm)
    r_norm = str(room_num).strip() if room_num is not None else ""

    # 1. ID lookup
    if q_norm.isdigit() and len(q_norm) < 7:
        res = Resident.objects.filter(id=int(q_norm)).first()
        if res:
            return res

    # 2. National Code lookup
    if q_norm.isdigit() and len(q_norm) == 10:
        res = Resident.objects.filter(national_code=q_norm).first()
        if res:
            return res

    # 3. Room-scoped search (Highest accuracy when room is provided)
    if r_norm:
        room_residents = list(Resident.objects.filter(room__room_number=r_norm, status="ACTIVE"))
        if not room_residents:
            room_residents = list(Resident.objects.filter(room__room_number=r_norm))

        if len(room_residents) == 1:
            # Single resident in that room
            return room_residents[0]

        if room_residents:
            # Check exact stripped match
            for r in room_residents:
                if strip_all_spaces(r.full_name) == q_stripped:
                    return r

            # Check if query words overlap with resident name
            q_tokens = [w for w in q_norm.split() if len(w) > 1]
            best_match = None
            best_score = 0

            for r in room_residents:
                r_full = normalize_persian(r.full_name)
                r_tokens = r_full.split()
                score = 0

                # Check tokens
                for qt in q_tokens:
                    qt_stripped = strip_all_spaces(qt)
                    for rt in r_tokens:
                        rt_stripped = strip_all_spaces(rt)
                        if qt_stripped == rt_stripped:
                            score += 10
                        elif qt_stripped in rt_stripped or rt_stripped in qt_stripped:
                            score += 5

                # Check last name specifically (weight = 15)
                r_last = strip_all_spaces(r.last_name)
                for qt in q_tokens:
                    qt_stripped = strip_all_spaces(qt)
                    if qt_stripped in r_last or r_last in qt_stripped:
                        score += 15

                if score > best_score:
                    best_score = score
                    best_match = r

            if best_match and best_score >= 10:
                return best_match

    # 4. Global Search across active residents
    active_qs = list(Resident.objects.filter(status="ACTIVE"))
    for r in active_qs:
        if strip_all_spaces(r.full_name) == q_stripped:
            return r

    q_tokens = [w for w in q_norm.split() if len(w) > 1]
    candidates = []

    for r in active_qs:
        r_full = normalize_persian(r.full_name)
        score = 0
        r_tokens = r_full.split()
        r_last = strip_all_spaces(r.last_name)

        for qt in q_tokens:
            qt_s = strip_all_spaces(qt)
            for rt in r_tokens:
                rt_s = strip_all_spaces(rt)
                if qt_s == rt_s:
                    score += 10
                elif qt_s in rt_s or rt_s in qt_s:
                    score += 5
            if qt_s in r_last or r_last in qt_s:
                score += 15

        if r_norm and r.room and str(r.room.room_number) == r_norm:
            score += 25

        if score > 0:
            candidates.append((score, r))

    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates:
        top_score, top_resident = candidates[0]
        # Ensure unambiguous winner if multiple candidates
        if len(candidates) == 1 or top_score >= candidates[1][0] + 5:
            return top_resident

    raise ValueError(f"هیچ ساکنی با مشخصات '{query}' (اتاق: {room_num or 'هر اتاقی'}) یافت نشد.")


def process_receipt(
    resident: Union[str, int, Resident],
    room: Optional[Union[str, int]] = None,
    # Amounts
    amount_tomans: Optional[int] = None,
    deposit_tomans: Optional[int] = None,
    rent_tomans: Optional[int] = None,
    # Metadata
    type: str = "RENT",
    method: str = "CARD",
    date: Optional[str] = None,
    ref: str = "",
    desc: str = "",
    # Settlement & Period
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    settled_until: Optional[str] = None,
    supervisor_id: int = 1,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Unified, ultra-fast transaction processor supporting:
    - Single RENT or DEPOSIT transactions
    - Native SPLIT transactions (deposit_tomans + rent_tomans) in one single atomic operation
    - Smart resident auto-matching
    - Auto Jalali period and settlement computation
    """
    # 1. Resolve Resident
    if isinstance(resident, Resident):
        res_obj = resident
    else:
        res_obj = find_resident_smart(str(resident), room)

    # 2. Resolve Supervisor
    supervisor = (
        Supervisor.objects.filter(id=supervisor_id).first()
        or Supervisor.objects.first()
    )

    # 3. Resolve Datetime
    tehran_tz = zoneinfo.ZoneInfo("Asia/Tehran")
    payment_datetime = parse_jalali_datetime(date, tehran_tz)

    # 4. Check if Split Transaction
    is_split = (deposit_tomans is not None and deposit_tomans > 0) and (
        (rent_tomans is not None and rent_tomans > 0)
        or (amount_tomans is not None and amount_tomans > deposit_tomans)
    )

    if is_split:
        dep_amount = deposit_tomans
        r_amount = rent_tomans if rent_tomans is not None else (amount_tomans - dep_amount)
    else:
        if deposit_tomans is not None and deposit_tomans > 0:
            type = "DEPOSIT"
            dep_amount = deposit_tomans
            r_amount = 0
        elif rent_tomans is not None and rent_tomans > 0:
            type = "RENT"
            dep_amount = 0
            r_amount = rent_tomans
        else:
            if amount_tomans is None or amount_tomans <= 0:
                raise ValueError("مبلغ پرداختی الزامی است.")
            if type == "DEPOSIT":
                dep_amount = amount_tomans
                r_amount = 0
            else:
                dep_amount = 0
                r_amount = amount_tomans

    total_tomans = dep_amount + r_amount
    results = []
    old_settled = res_obj.settled_until

    with transaction.atomic():
        # A. Process DEPOSIT if any
        if dep_amount > 0:
            dep_desc = desc or ("ودیعه / بیعانه" + (f" - بخش اول از پرداخت ترکیبی {total_tomans:,} تومانی" if is_split else ""))
            dep_tx = Transaction.objects.create(
                resident=res_obj,
                dormitory=res_obj.dormitory,
                amount=dep_amount * 10,
                transaction_type=Transaction.TransactionType.DEPOSIT,
                payment_method=method,
                payment_date=payment_datetime,
                reference_number=ref,
                description=dep_desc,
                created_by=supervisor,
            )
            res_obj.has_deposit = True
            res_obj.save(update_fields=["has_deposit"])

            results.append({
                "transaction_id": dep_tx.id,
                "type": "DEPOSIT",
                "type_display": "Deposit",
                "amount_tomans": dep_amount,
                "amount_rials": dep_amount * 10,
                "method": method,
                "method_display": dep_tx.get_payment_method_display(),
                "payment_date": str(dep_tx.payment_date),
                "reference_number": ref,
                "period_start": None,
                "period_end": None,
                "period_name": "",
                "description": dep_desc,
            })

        # B. Process RENT if any
        if r_amount > 0:
            rent_desc = desc or ("اجاره ماهانه" + (f" - بخش دوم از پرداخت ترکیبی {total_tomans:,} تومانی" if is_split else ""))
            p_start_d = parse_jalali_date(period_start) if period_start else None
            p_end_d = parse_jalali_date(period_end) if period_end else None
            settled_until_d = parse_jalali_date(settled_until) if settled_until else None

            rent_rate = (
                res_obj.room.monthly_rent
                if res_obj.room and res_obj.room.monthly_rent
                else r_amount * 10
            )

            if not p_start_d:
                p_start_d = res_obj.settled_until or res_obj.entry_date or payment_datetime.date()

            if settled_until_d:
                p_end_d = settled_until_d
                p_name = format_period_name(p_start_d, p_end_d)
            elif p_end_d:
                p_name = format_period_name(p_start_d, p_end_d)
            else:
                rent_resolver = res_obj.room.get_rent_for_date if res_obj.room else None
                computed_end, _, computed_name = calculate_settlement_advance(
                    start_date=p_start_d,
                    amount_rials=r_amount * 10,
                    monthly_rent_rials=rent_rate,
                    rent_resolver=rent_resolver,
                    anchor_day=res_obj.monthly_payment_day,
                )
                p_end_d = computed_end
                p_name = computed_name

            rent_tx = Transaction.objects.create(
                resident=res_obj,
                dormitory=res_obj.dormitory,
                amount=r_amount * 10,
                transaction_type=Transaction.TransactionType.RENT,
                payment_method=method,
                payment_date=payment_datetime,
                reference_number=ref,
                description=rent_desc,
                created_by=supervisor,
                applicable_rent=rent_rate,
                period_start=p_start_d,
                period_end=p_end_d,
                period_name=p_name,
            )

            new_settled = settled_until_d or p_end_d
            if new_settled and (not res_obj.settled_until or new_settled > res_obj.settled_until or settled_until_d):
                res_obj.settled_until = new_settled
                res_obj.save(update_fields=["settled_until"])

            results.append({
                "transaction_id": rent_tx.id,
                "type": "RENT",
                "type_display": "Monthly Rent",
                "amount_tomans": r_amount,
                "amount_rials": r_amount * 10,
                "method": method,
                "method_display": rent_tx.get_payment_method_display(),
                "payment_date": str(rent_tx.payment_date),
                "reference_number": ref,
                "period_start": str(p_start_d),
                "period_end": str(p_end_d),
                "period_name": p_name,
                "description": rent_desc,
            })

        res_obj.refresh_from_db()

        if dry_run:
            transaction.set_rollback(True)

    output = {
        "success": True,
        "is_split": is_split,
        "resident_id": res_obj.id,
        "resident_name": res_obj.full_name,
        "room": res_obj.room.room_number if res_obj.room else "ندارد",
        "total_amount_tomans": total_tomans,
        "total_amount_rials": total_tomans * 10,
        "old_settled_until": str(old_settled) if old_settled else None,
        "new_settled_until": str(res_obj.settled_until) if res_obj.settled_until else None,
        "has_deposit": res_obj.has_deposit,
        "supervisor": supervisor.full_name if supervisor else "جواد حسینی",
        "transactions": results,
        "dry_run": dry_run,
    }

    return output

