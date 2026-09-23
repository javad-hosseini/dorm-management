import jdatetime
from typing import List, Dict, Any, Optional

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

    # Check if this is a standard 1st-of-month cycle
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
        # Mid-month cycle (e.g. 15th to 15th)
        if start_date.year == end_date.year:
            return f"اجاره دوره {s_day} {start_m_name} تا {e_day} {end_m_name} {s_year}"
        else:
            return f"اجاره دوره {s_day} {start_m_name} {s_year} تا {e_day} {end_m_name} {e_year}"


def calculate_unpaid_periods(
    start_date: jdatetime.date,
    as_of_date: Optional[jdatetime.date] = None,
    monthly_rent_rials: int = 0
) -> List[Dict[str, Any]]:
    """
    Calculates monthly periods from start_date up to as_of_date.
    Each period represents 1 prepaid monthly rent cycle.
    Billing is strictly monthly (not daily pro-rated).
    """
    if not start_date:
        return []

    if as_of_date is None:
        as_of_date = jdatetime.date.today()

    periods = []
    cursor = start_date

    # While the period start has arrived or passed as_of_date
    while cursor <= as_of_date:
        next_cursor = add_jalali_months(cursor, 1)
        name = format_period_name(cursor, next_cursor)
        
        # Calculate how many days this period is overdue relative to as_of_date
        overdue_days_for_period = (as_of_date - cursor).days

        periods.append({
            "start_date": cursor,
            "end_date": next_cursor,
            "name": name,
            "overdue_days": overdue_days_for_period,
            "amount_rials": monthly_rent_rials,
            "amount_tomans": monthly_rent_rials // 10,
        })
        cursor = next_cursor

    return periods
