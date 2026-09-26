"""
Centralized phone number normalization, validation, and SMS formatting utilities.

This module serves as the single source of truth for Iranian mobile phone
validation and normalization across the application.
"""

import re
from django.core.exceptions import ValidationError


PERSIAN_ARABIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "01234567890123456789"
DIGIT_TRANSLATION_TABLE = str.maketrans(PERSIAN_ARABIC_DIGITS, ASCII_DIGITS)

IRANIAN_MOBILE_REGEX = re.compile(r"^09\d{9}$")


def normalize_phone_number(raw_phone: str) -> str:
    """
    Normalize an input phone string into canonical Iranian mobile format: 09xxxxxxxxx.

    Handles:
    - Persian and Arabic numerals (e.g. ۰۹۱۲۳۴۵۶۷۸۹ -> 09123456789)
    - International prefixes: +98, 0098, 98
    - Missing leading zero: 9123456789
    - Formatting characters: spaces, hyphens, parentheses, pluses

    Returns:
        str: 11-digit canonical mobile string starting with '09'.

    Raises:
        ValidationError: If the input cannot be resolved to a valid Iranian mobile.
    """
    if not raw_phone:
        raise ValidationError("شماره موبایل نمی‌تواند خالی باشد.")

    # 1. Convert Persian/Arabic digits to ASCII
    text = str(raw_phone).strip().translate(DIGIT_TRANSLATION_TABLE)

    # 2. Extract only digits and leading plus
    has_plus = text.startswith("+")
    clean = "".join(ch for ch in text if ch.isdigit())

    # 3. Handle prefixes
    # +989...
    if has_plus and clean.startswith("98"):
        clean = clean[2:]
    # 00989...
    elif clean.startswith("0098"):
        clean = clean[4:]
    # 989... (12 digits)
    elif clean.startswith("98") and len(clean) == 12:
        clean = clean[2:]

    # If it starts with 9 and has 10 digits (e.g. 9123456789) -> prepend 0
    if clean.startswith("9") and len(clean) == 10:
        clean = "0" + clean

    # 4. Final validation against 09xxxxxxxxx
    if not IRANIAN_MOBILE_REGEX.match(clean):
        raise ValidationError(
            f"شماره موبایل '{raw_phone}' نامعتبر است. شماره موبایل معتبر باید ۱۱ رقم بوده و با ۰۹ شروع شود."
        )

    return clean


def is_valid_iranian_mobile(raw_phone: str) -> bool:
    """
    Check whether a phone number is a valid Iranian mobile number.

    Returns:
        bool: True if valid, False otherwise.
    """
    try:
        normalize_phone_number(raw_phone)
        return True
    except (ValidationError, TypeError, ValueError):
        return False


def validate_iranian_mobile(value: str) -> None:
    """
    Django field and form validator for Iranian mobile numbers.
    """
    normalize_phone_number(value)


def format_personalized_message(user, base_message: str) -> str:
    """
    Format a personalized SMS message for a registered site user.

    Rule:
    - If user has a non-empty full name:
      {user full name} عزیز
      {message body}
    - If user has no name (missing/blank first and last name):
      کاربر گرامی
      {message body}

    Args:
        user: The User instance.
        base_message: The admin-composed text body.

    Returns:
        str: The final personalized message.
    """
    base_text = (base_message or "").strip()

    full_name = ""
    if hasattr(user, "get_full_name"):
        full_name = user.get_full_name().strip()
    elif hasattr(user, "first_name") or hasattr(user, "last_name"):
        first = getattr(user, "first_name", "") or ""
        last = getattr(user, "last_name", "") or ""
        full_name = f"{first} {last}".strip()

    if full_name:
        greeting = f"{full_name} عزیز"
    else:
        greeting = "کاربر گرامی"

    return f"{greeting}\n{base_text}"


def calculate_sms_parts(text: str) -> int:
    """
    Calculate the number of SMS segments for a given text.
    Standard Iranian SMS encoding (Unicode / Persian):
    - 1 part: up to 70 characters
    - Subsequent parts: 67 characters each
    """
    if not text:
        return 0
    length = len(text)
    if length <= 70:
        return 1
    return 1 + (length - 70 + 66) // 67


# Default Recommended Templates
DEFAULT_DEBT_REMINDER_TEMPLATE = (
    "آقای {نام} عزیز؛ اتاق {اتاق}\n"
    "موعد اجاره شما {موعد_تسویه} بوده است و تا امروز {امروز} مبلغ {مبلغ_بدهی} تومان بدهی دارید. "
    "لطفاً جهت تسویه حساب به اتاق سرپرستی مراجعه فرمایید."
)

DEFAULT_GENERAL_ANNOUNCEMENT_TEMPLATE = (
    "ساکن گرامی جناب آقای {نام} (اتاق {اتاق})؛\n"
    "با سلام و احترام، به اطلاع می‌رساند ...\n"
    "با تشکر - مدیریت خوابگاه"
)


def calculate_resident_debt_details(resident, today_date=None) -> dict:
    """
    Calculates period debt, accumulated total debt, overdue days, and smart debt for a resident.
    """
    import jdatetime
    from apps.dormitory.services.excel_export import get_period_debt_tomans

    today = today_date or jdatetime.date.today()
    overdue_days = resident.overdue_days if hasattr(resident, "overdue_days") else 0
    total_debt = resident.total_debt_amount_tomans if hasattr(resident, "total_debt_amount_tomans") else 0
    
    try:
        period_debt = get_period_debt_tomans(resident)
    except Exception:
        period_debt = total_debt

    # Smart debt calculation:
    # If delay is within 1 monthly period (<= 30 days), show period debt
    # If delay exceeds 1 monthly period (> 30 days), show total accumulated/daily overdue debt
    if overdue_days <= 30:
        smart_debt = period_debt if period_debt > 0 else total_debt
    else:
        smart_debt = total_debt if total_debt > 0 else period_debt

    # Dates
    if resident.settled_until:
        settled_str = resident.settled_until.strftime('%Y/%m/%d')
    elif resident.entry_date:
        settled_str = f"{resident.entry_date.strftime('%Y/%m/%d')} (ورود)"
    else:
        settled_str = "ثبت‌نشده"

    room_str = str(resident.room.room_number) if (resident.room and resident.room.room_number) else "بدون اتاق"
    unpaid_months_str = resident.unpaid_months_display if hasattr(resident, "unpaid_months_display") else ""

    return {
        "name": resident.full_name,
        "room": room_str,
        "settled_until": settled_str,
        "today": today.strftime('%Y/%m/%d'),
        "smart_debt": smart_debt,
        "smart_debt_formatted": f"{smart_debt:,}",
        "period_debt": period_debt,
        "period_debt_formatted": f"{period_debt:,}",
        "total_debt": total_debt,
        "total_debt_formatted": f"{total_debt:,}",
        "overdue_days": overdue_days,
        "unpaid_months": unpaid_months_str,
    }


def render_resident_sms_template(resident, template_text: str, today_date=None) -> str:
    """
    Renders dynamic placeholders in an SMS template for a specific resident.

    Supported tags:
    - {نام}, {name}, {نام_ساکن}, {resident_name}
    - {اتاق}, {room}, {شماره_اتاق}, {room_number}
    - {موعد_تسویه}, {settled_until}, {تاریخ_تسویه}
    - {امروز}, {today}, {تاریخ_امروز}
    - {مبلغ_بدهی}, {debt}, {بدهی}
    - {بدهی_دوره}, {period_debt}
    - {بدهی_کل}, {total_debt}
    - {روزهای_تاخیر}, {overdue_days}, {تاخیر}
    - {ماه_های_معوق}, {unpaid_months}
    """
    if not template_text:
        return ""

    if resident is None:
        return template_text

    data = calculate_resident_debt_details(resident, today_date=today_date)

    replacements = {
        "{نام}": data["name"],
        "{name}": data["name"],
        "{نام_ساکن}": data["name"],
        "{resident_name}": data["name"],

        "{اتاق}": data["room"],
        "{room}": data["room"],
        "{شماره_اتاق}": data["room"],
        "{room_number}": data["room"],

        "{موعد_تسویه}": data["settled_until"],
        "{settled_until}": data["settled_until"],
        "{تاریخ_تسویه}": data["settled_until"],

        "{امروز}": data["today"],
        "{today}": data["today"],
        "{تاریخ_امروز}": data["today"],

        "{مبلغ_بدهی}": data["smart_debt_formatted"],
        "{debt}": data["smart_debt_formatted"],
        "{بدهی}": data["smart_debt_formatted"],

        "{بدهی_دوره}": data["period_debt_formatted"],
        "{period_debt}": data["period_debt_formatted"],

        "{بدهی_کل}": data["total_debt_formatted"],
        "{total_debt}": data["total_debt_formatted"],

        "{روزهای_تاخیر}": str(data["overdue_days"]),
        "{overdue_days}": str(data["overdue_days"]),
        "{تاخیر}": str(data["overdue_days"]),

        "{ماه_های_معوق}": data["unpaid_months"],
        "{unpaid_months}": data["unpaid_months"],
    }

    result = template_text
    for tag, val in replacements.items():
        result = result.replace(tag, str(val))

    return result


