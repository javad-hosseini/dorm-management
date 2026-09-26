import re
import datetime
import jdatetime
from typing import List, Dict, Any, Optional, Callable, Tuple

JALALI_MONTH_NAMES = [
    "",
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند"
]


def get_jalali_month_name(month: int) -> str:
    """Return Persian name of Jalali month (1-12)"""
    if 1 <= month <= 12:
        return JALALI_MONTH_NAMES[month]
    return f"ماه {month}"


def get_days_in_jalali_month(year: int, month: int) -> int:
    """Return number of days in a given Jalali month"""
    if 1 <= month <= 6:
        return 31
    elif 7 <= month <= 11:
        return 30
    elif month == 12:
        return 30 if jdatetime.date(year, 1, 1).isleap() else 29
    return 30


def add_jalali_months(orig_date: jdatetime.date, months: int = 1) -> jdatetime.date:
    """
    Safely add (or subtract) months to a Jalali date, handling variable month lengths,
    year boundaries, and leap years.
    """
    if orig_date is None:
        return None
    total_months = (orig_date.year * 12) + (orig_date.month - 1) + months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1

    max_days = get_days_in_jalali_month(new_year, new_month)
    new_day = min(orig_date.day, max_days)
    return jdatetime.date(new_year, new_month, new_day)


def to_persian_digits(value: Any) -> str:
    """Convert digits in a string or number to Persian digits"""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    english_digits = "0123456789"
    trans = str.maketrans(english_digits, persian_digits)
    return str(value).translate(trans)


def format_period_name(start_date: jdatetime.date, end_date: jdatetime.date) -> str:
    """
    Return human-readable Persian description of rent period.
    Examples:
    - 1405/07/01 to 1405/08/01 -> "اجاره مهر ماه ۱۴۰۵"
    - 1405/07/01 to 1405/09/01 -> "اجاره مهر و آبان ماه ۱۴۰۵"
    - 1405/07/01 to 1405/07/21 -> "اجاره دوره ۱ تا ۲۱ مهر ۱۴۰۵"
    - 1405/07/15 to 1405/08/15 -> "اجاره دوره ۱۵ مهر تا ۱۵ آبان ۱۴۰۵"
    """
    if not start_date or not end_date:
        return "دوره نامشخص"

    start_m_name = get_jalali_month_name(start_date.month)
    end_m_name = get_jalali_month_name(end_date.month)
    s_year = to_persian_digits(start_date.year)
    e_year = to_persian_digits(end_date.year)
    s_day = to_persian_digits(start_date.day)
    e_day = to_persian_digits(end_date.day)

    # Check if this is a standard 1st-of-month full cycle
    if start_date.day == 1 and (end_date.day == 1 or end_date.day in [29, 30, 31]):
        month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        if month_diff <= 1:
            return f"اجاره {start_m_name} ماه {s_year}"
        elif month_diff == 2:
            next_m_name = get_jalali_month_name((start_date.month % 12) + 1)
            return f"اجاره {start_m_name} و {next_m_name} ماه {s_year}"
        else:
            diff_str = to_persian_digits(month_diff)
            return f"اجاره {diff_str} ماهه ({start_m_name} تا {end_m_name} {s_year})"
    else:
        # Mid-month or partial cycle
        if start_date.year == end_date.year:
            if start_date.month == end_date.month:
                return f"اجاره دوره {s_day} تا {e_day} {start_m_name} {s_year}"
            return f"اجاره دوره {s_day} {start_m_name} تا {e_day} {end_m_name} {s_year}"
        else:
            return f"اجاره دوره {s_day} {start_m_name} {s_year} تا {e_day} {end_m_name} {e_year}"


def parse_jalali_date(val: Any) -> Optional[jdatetime.date]:
    """
    Safely parse various Jalali date representations into jdatetime.date.
    Supports jdatetime.date, datetime.date, or strings like '1405/07/01' or '1405-07-01'.
    """
    if not val:
        return None
    if isinstance(val, jdatetime.date):
        return val
    if isinstance(val, jdatetime.datetime):
        return val.date()
    # If Gregorian date
    if isinstance(val, datetime.date) and not isinstance(val, jdatetime.date):
        return jdatetime.date.fromgregorian(date=val)

    # String format
    s = str(val).strip()
    # Normalize Persian digits
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    s = s.translate(trans)
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        try:
            return jdatetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def calculate_settlement_advance(
    start_date: jdatetime.date,
    amount_rials: int,
    monthly_rent_rials: int,
    rent_resolver: Optional[Callable[[jdatetime.date], int]] = None
) -> Tuple[jdatetime.date, int, str]:
    """
    Calculate advancing settled_until from start_date given an amount in Rials.
    Supports accurate prorated daily calculation across Jalali calendar months.
    Returns:
        (new_settled_date, total_days_advanced, period_name)
    """
    if not start_date or amount_rials <= 0:
        return start_date, 0, ""

    cursor = start_date
    remaining_amount = amount_rials
    total_days_advanced = 0

    while remaining_amount > 0:
        effective_monthly_rent = rent_resolver(cursor) if rent_resolver else monthly_rent_rials
        if not effective_monthly_rent or effective_monthly_rent <= 0:
            cursor = cursor + datetime.timedelta(days=30)
            total_days_advanced += 30
            break

        days_in_cur_month = get_days_in_jalali_month(cursor.year, cursor.month)
        daily_rate = effective_monthly_rent / days_in_cur_month

        remaining_days_in_month = days_in_cur_month - cursor.day + 1
        cost_for_rest_of_month = int(round(remaining_days_in_month * daily_rate))

        if remaining_amount >= cost_for_rest_of_month:
            cursor = cursor + datetime.timedelta(days=remaining_days_in_month)
            total_days_advanced += remaining_days_in_month
            remaining_amount -= cost_for_rest_of_month
        else:
            days_covered = int(round(remaining_amount / daily_rate))
            days_covered = max(1, min(remaining_days_in_month, days_covered))
            cursor = cursor + datetime.timedelta(days=days_covered)
            total_days_advanced += days_covered
            remaining_amount = 0
            break

    period_name = format_period_name(start_date, cursor)
    if total_days_advanced > 0 and (start_date.day != 1 or cursor.day != 1):
        p_days = to_persian_digits(total_days_advanced)
        if "روز" not in period_name:
            period_name = f"{period_name} ({p_days} روز)"

    return cursor, total_days_advanced, period_name


def calculate_unpaid_periods(
    start_date: jdatetime.date,
    as_of_date: Optional[jdatetime.date] = None,
    monthly_rent_rials: int = 0,
    rent_resolver: Optional[Callable[[jdatetime.date], int]] = None
) -> List[Dict[str, Any]]:
    """
    Calculates unpaid periods from start_date up to as_of_date.
    Supports prorated partial-month periods if start_date is mid-month,
    followed by full monthly periods for subsequent months.
    """
    if not start_date:
        return []

    if as_of_date is None:
        as_of_date = jdatetime.date.today()

    periods = []
    cursor = start_date

    while cursor <= as_of_date:
        days_in_month = get_days_in_jalali_month(cursor.year, cursor.month)
        period_rent_rials = rent_resolver(cursor) if rent_resolver else monthly_rent_rials
        daily_rate_rials = (period_rent_rials / days_in_month) if days_in_month else 0

        if cursor.day == 1:
            next_cursor = cursor + datetime.timedelta(days=days_in_month)
            name = format_period_name(cursor, next_cursor)
            amount_rials = period_rent_rials
        else:
            remaining_days = days_in_month - cursor.day + 1
            next_cursor = cursor + datetime.timedelta(days=remaining_days)
            amount_rials = int(round(remaining_days * daily_rate_rials))
            s_m_name = get_jalali_month_name(cursor.month)
            s_year = to_persian_digits(cursor.year)
            s_days = to_persian_digits(remaining_days)
            name = f"اجاره {s_days} روز باقیمانده {s_m_name} ماه {s_year} ({to_persian_digits(cursor.day)} {s_m_name} تا ۱ {get_jalali_month_name(next_cursor.month)})"

        overdue_days_for_period = (as_of_date - cursor).days

        periods.append({
            "start_date": cursor,
            "end_date": next_cursor,
            "name": name,
            "overdue_days": overdue_days_for_period,
            "amount_rials": amount_rials,
            "amount_tomans": amount_rials // 10,
        })
        cursor = next_cursor

    return periods

