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


def normalize_settlement_boundary(
    target_date: Optional[jdatetime.date],
    anchor_day: Optional[int] = 1,
) -> Optional[jdatetime.date]:
    """
    Normalizes a settlement date if it represents an end-of-month eve.
    If anchor_day is 1 (or None / default) and target_date is the last day
    of its Jalali month (day 31 in months 1-6, day 30 in months 7-11, or day 29/30 in month 12),
    advances to the 1st of the next month to prevent the ±1 day tolerance trap.
    """
    if not target_date:
        return target_date

    eff_anchor = anchor_day if anchor_day is not None else 1
    days_in_m = get_days_in_jalali_month(target_date.year, target_date.month)

    if eff_anchor == 1 and target_date.day == days_in_m:
        next_m = add_jalali_months(jdatetime.date(target_date.year, target_date.month, 1), 1)
        return jdatetime.date(next_m.year, next_m.month, 1)
    return target_date


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

    # If start_date is on month-end eve and end_date is in a future month aligned with anchor,
    # normalize start to the 1st of the next month for clean naming (e.g. 1405/07/30 -> 1405/09/01 is Aban rent)
    days_in_sm = get_days_in_jalali_month(start_date.year, start_date.month)
    if start_date.day == days_in_sm and (end_date.day == 1 or end_date.day in [29, 30, 31]):
        norm_start = add_jalali_months(jdatetime.date(start_date.year, start_date.month, 1), 1)
        if norm_start < end_date:
            return format_period_name(norm_start, end_date)

    start_m_name = get_jalali_month_name(start_date.month)
    end_m_name = get_jalali_month_name(end_date.month)
    s_year = to_persian_digits(start_date.year)
    e_year = to_persian_digits(end_date.year)
    s_day = to_persian_digits(start_date.day)
    e_day = to_persian_digits(end_date.day)

    # Check if this is a standard 1st-of-month full cycle
    if start_date.day == 1 and (end_date.day == 1 or end_date.day in [29, 30, 31]):
        if end_date.day in [29, 30, 31] and end_date.day == get_days_in_jalali_month(end_date.year, end_date.month):
            month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        else:
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
    rent_resolver: Optional[Callable[[jdatetime.date], int]] = None,
    anchor_day: Optional[int] = None,
) -> Tuple[jdatetime.date, int, str]:
    """
    Calculate advancing settled_until from start_date given an amount in Rials.
    Accurately respects the variable lengths of all 12 Jalali months:
    - Months 1-6 (Farvardin - Shahrivar): 31 days
    - Months 7-11 (Mehr - Bahman): 30 days
    - Month 12 (Esfand): 29 days (or 30 days in leap years)
    Prevents any ±1 or ±2 day drift when crossing month boundaries or paying multi-month rent.
    Returns:
        (new_settled_date, total_days_advanced, period_name)
    """
    if not start_date or amount_rials <= 0:
        return start_date, 0, ""

    if anchor_day is None:
        days_in_start = get_days_in_jalali_month(start_date.year, start_date.month)
        if start_date.day == days_in_start:
            anchor_day = 1
        else:
            anchor_day = start_date.day

    cursor = start_date
    # If anchor_day is 1 and cursor is on the last day of the month (the eve of anchor day),
    # advance to the 1st of the next month at 0 cost to avoid stealing 1 day from the payment.
    days_in_cur_m = get_days_in_jalali_month(cursor.year, cursor.month)
    if anchor_day == 1 and cursor.day == days_in_cur_m:
        cursor = normalize_settlement_boundary(cursor, anchor_day=1)

    remaining_amount = amount_rials
    total_days_advanced = 0

    while remaining_amount > 0:
        effective_monthly_rent = rent_resolver(cursor) if rent_resolver else monthly_rent_rials
        if not effective_monthly_rent or effective_monthly_rent <= 0:
            cursor = cursor + datetime.timedelta(days=30)
            total_days_advanced += 30
            break

        days_in_m = get_days_in_jalali_month(cursor.year, cursor.month)
        cur_target_day = min(anchor_day, days_in_m)

        if cursor.day != cur_target_day:
            # Cursor is not on anchor day (e.g. following previous partial payment).
            # Determine next anchor boundary to complete the current cycle.
            if cursor.day < cur_target_day:
                next_boundary = jdatetime.date(cursor.year, cursor.month, cur_target_day)
            else:
                next_m = add_jalali_months(jdatetime.date(cursor.year, cursor.month, 1), 1)
                nb_days_in_m = get_days_in_jalali_month(next_m.year, next_m.month)
                next_boundary = jdatetime.date(next_m.year, next_m.month, min(anchor_day, nb_days_in_m))

            prev_boundary = add_jalali_months(next_boundary, -1)
            full_cycle_days = (next_boundary - prev_boundary).days
            needed_days = (next_boundary - cursor).days
            cost_to_boundary = int(round(needed_days * (effective_monthly_rent / full_cycle_days)))

            if remaining_amount >= cost_to_boundary:
                cursor = next_boundary
                total_days_advanced += needed_days
                remaining_amount -= cost_to_boundary
                # If remaining amount is negligible (< 0.5 day's cost of next cycle), consume it cleanly
                next_cycle_length = get_days_in_jalali_month(cursor.year, cursor.month)
                next_daily_rate = effective_monthly_rent / next_cycle_length
                if remaining_amount < next_daily_rate * 0.5:
                    remaining_amount = 0
                    break
            else:
                days_covered = int(round(remaining_amount * full_cycle_days / effective_monthly_rent))
                if total_days_advanced == 0:
                    days_covered = max(1, min(needed_days, days_covered))
                else:
                    days_covered = min(needed_days, days_covered)
                if days_covered >= needed_days:
                    cursor = next_boundary
                elif days_covered > 0:
                    cursor = cursor + datetime.timedelta(days=days_covered)
                total_days_advanced += days_covered
                remaining_amount = 0
                break
        else:
            # Cursor is aligned with anchor day: advance full monthly cycle
            next_m = add_jalali_months(jdatetime.date(cursor.year, cursor.month, 1), 1)
            days_in_nm = get_days_in_jalali_month(next_m.year, next_m.month)
            next_cycle_end = jdatetime.date(next_m.year, next_m.month, min(anchor_day, days_in_nm))
            cycle_days = (next_cycle_end - cursor).days

            if remaining_amount >= effective_monthly_rent:
                cursor = next_cycle_end
                total_days_advanced += cycle_days
                remaining_amount -= effective_monthly_rent
            else:
                days_covered = int(round(remaining_amount * cycle_days / effective_monthly_rent))
                if total_days_advanced == 0:
                    days_covered = max(1, min(cycle_days, days_covered))
                else:
                    days_covered = min(cycle_days, days_covered)

                if days_covered >= cycle_days:
                    cursor = next_cycle_end
                elif days_covered > 0:
                    cursor = cursor + datetime.timedelta(days=days_covered)
                total_days_advanced += days_covered
                remaining_amount = 0
                break

    days_in_s = get_days_in_jalali_month(start_date.year, start_date.month)
    is_eve_start = (anchor_day == 1 and start_date.day == days_in_s)
    period_name = format_period_name(start_date, cursor)
    if total_days_advanced > 0 and not ((start_date.day == 1 or is_eve_start) and cursor.day == 1):
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

