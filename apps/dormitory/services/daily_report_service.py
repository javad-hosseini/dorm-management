import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
import jdatetime
from django.db.models import Sum

from apps.dormitory.models import Transaction, Resident, Room, Dormitory
from apps.dormitory.jalali_utils import (
    calculate_unpaid_periods,
    get_jalali_month_name,
    to_persian_digits,
    parse_jalali_date,
)


class DailyReportService:
    """Service to generate daily executive dormitory reports and SMS texts."""
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
    PERSIAN_WEEKDAYS = ['شنبه', 'یک‌شنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']

    @classmethod
    def get_daily_report_data(
        cls,
        target_date: Optional[jdatetime.date] = None,
        dormitory_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculates all performance metrics for the target date (default: yesterday),
        the current month-to-date, outstanding debt, and room vacancy.
        If dormitory_id is None, aggregates metrics across all dormitories in the system,
        ensuring 100% synchronization with the main database and Financial Dashboard.
        """
        tz = cls.TEHRAN_TZ
        today = jdatetime.date.today()

        if target_date is None:
            # Default to yesterday
            target_date = today - datetime.timedelta(days=1)

        weekday_name = cls.PERSIAN_WEEKDAYS[target_date.weekday()]
        target_date_str = target_date.strftime("%Y/%m/%d")

        # 1. Target Date (Yesterday) Transactions
        start_dt = jdatetime.datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz)
        end_dt = jdatetime.datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=tz)

        tx_qs = Transaction.objects.filter(payment_date__gte=start_dt, payment_date__lte=end_dt)
        if dormitory_id:
            tx_qs = tx_qs.filter(dormitory_id=dormitory_id)

        card_tomans = sum(t.amount for t in tx_qs.filter(payment_method="CARD")) // 10
        transfer_tomans = sum(t.amount for t in tx_qs.filter(payment_method="BANK_TRANSFER")) // 10
        cash_tomans = sum(t.amount for t in tx_qs.filter(payment_method="CASH")) // 10
        online_tomans = sum(t.amount for t in tx_qs.filter(payment_method="ONLINE_GATEWAY")) // 10
        yesterday_total_tomans = sum(t.amount for t in tx_qs) // 10
        yesterday_count = tx_qs.count()

        # 2. Month-to-Date Collections (Synchronized with target month)
        first_of_this_month = jdatetime.date(target_date.year, target_date.month, 1)
        month_start_dt = jdatetime.datetime(first_of_this_month.year, first_of_this_month.month, 1, 0, 0, 0, tzinfo=tz)
        if target_date.year == today.year and target_date.month == today.month:
            # Current month: include up to end of today to perfectly match Financial Dashboard
            month_end_dt = jdatetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=tz)
        else:
            # Historical month: include up to target date
            month_end_dt = jdatetime.datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=tz)

        month_qs = Transaction.objects.filter(payment_date__gte=month_start_dt, payment_date__lte=month_end_dt)
        if dormitory_id:
            month_qs = month_qs.filter(dormitory_id=dormitory_id)

        month_total_tomans = sum(t.amount for t in month_qs) // 10
        month_count = month_qs.count()
        month_name = f"{get_jalali_month_name(target_date.month)} {target_date.year}"

        # 3. Debt Calculation (Overdue debt as of today & Projected rent until 1st of next month)
        if target_date.month < 12:
            next_month = target_date.month + 1
            next_month_year = target_date.year
        else:
            next_month = 1
            next_month_year = target_date.year + 1
        first_of_next_month = jdatetime.date(next_month_year, next_month, 1)

        active_residents = Resident.objects.filter(status="ACTIVE").select_related("room", "dormitory")
        if dormitory_id:
            active_residents = active_residents.filter(dormitory_id=dormitory_id)

        # A. Overdue debt as of today (matches Financial Dashboard Card 3)
        overdue_debt_tomans = 0
        overdue_debtors_count = 0
        for r in active_residents:
            debt_now = r.total_debt_amount_tomans
            if debt_now > 0:
                overdue_debt_tomans += debt_now
                overdue_debtors_count += 1

        # B. Projected debt until first of next month (matches Financial Dashboard Card 3)
        projected_debt_tomans = 0
        indebted_count = 0
        for r in active_residents:
            if not r.room or not r.room.monthly_rent:
                continue
            base_date = r.settled_until or r.entry_date
            if base_date and base_date < first_of_next_month:
                periods = calculate_unpaid_periods(
                    start_date=base_date,
                    as_of_date=first_of_next_month,
                    monthly_rent_rials=r.room.monthly_rent,
                    rent_resolver=r.room.get_rent_for_date,
                )
                debt = sum(p["amount_tomans"] for p in periods)
                if debt > 0:
                    projected_debt_tomans += debt
                    indebted_count += 1

        # 4. Room Vacancies and Empty Beds
        room_qs = Room.objects.all().order_by("room_number")
        if dormitory_id:
            room_qs = room_qs.filter(dormitory_id=dormitory_id)

        vacant_rooms = []
        total_empty_beds = 0
        for room in room_qs:
            avail = room.available_capacity
            if avail > 0:
                total_empty_beds += avail
                vacant_rooms.append({
                    "room_number": room.room_number,
                    "empty_beds": avail,
                    "capacity": room.capacity,
                })

        # Resolve Dormitory Name
        if dormitory_id:
            dorm = Dormitory.objects.filter(id=dormitory_id).first()
            dorm_name = dorm.name if dorm else f"خوابگاه {dormitory_id}"
        else:
            dorms = list(Dormitory.objects.values_list("name", flat=True))
            if len(dorms) == 1:
                dorm_name = dorms[0]
            elif len(dorms) > 1:
                dorm_name = "مجموعه خوابگاه‌ها"
            else:
                dorm_name = "خوابگاه نوید"

        return {
            "dorm_name": dorm_name,
            "target_date": target_date,
            "target_date_str": target_date_str,
            "weekday_name": weekday_name,
            "yesterday_total_tomans": yesterday_total_tomans,
            "yesterday_count": yesterday_count,
            "card_tomans": card_tomans,
            "transfer_tomans": transfer_tomans,
            "cash_tomans": cash_tomans,
            "online_tomans": online_tomans,
            "month_name": month_name,
            "month_total_tomans": month_total_tomans,
            "month_count": month_count,
            "overdue_debt_tomans": overdue_debt_tomans,
            "overdue_debtors_count": overdue_debtors_count,
            "projected_debt_tomans": projected_debt_tomans,
            "indebted_count": indebted_count,
            "total_empty_beds": total_empty_beds,
            "vacant_rooms": vacant_rooms,
        }

    @classmethod
    def generate_sms_text(
        cls,
        target_date: Optional[jdatetime.date] = None,
        dormitory_id: Optional[int] = None,
    ) -> str:
        """
        Builds the exact SMS text requested by user where every item
        and every vacant room is on its own separate line.
        """
        data = cls.get_daily_report_data(target_date=target_date, dormitory_id=dormitory_id)

        y_date_p = to_persian_digits(data["target_date_str"])
        y_total_str = to_persian_digits(f"{data['yesterday_total_tomans']:,}")
        y_count_str = to_persian_digits(data["yesterday_count"])
        lines = [
            f"گزارش روزانه {data['dorm_name']} (دیروز: {data['weekday_name']} {y_date_p})",
            f"• درآمد دیروز: {y_total_str} تومان",
            f"• تعداد تراکنش دیروز: {y_count_str} تراکنش",
        ]

        # Method breakdown if income occurred yesterday
        if data["card_tomans"] > 0:
            c_str = to_persian_digits(f"{data['card_tomans']:,}")
            lines.append(f"• کارتخوان: {c_str} تومان")
        if data["transfer_tomans"] > 0:
            t_str = to_persian_digits(f"{data['transfer_tomans']:,}")
            lines.append(f"• کارت به کارت: {t_str} تومان")
        if data["cash_tomans"] > 0:
            cash_str = to_persian_digits(f"{data['cash_tomans']:,}")
            lines.append(f"• نقدی: {cash_str} تومان")
        if data["online_tomans"] > 0:
            on_str = to_persian_digits(f"{data['online_tomans']:,}")
            lines.append(f"• درگاه آنلاین: {on_str} تومان")

        # Month progress & Debt (Both overdue and projected until end of month)
        m_total_str = to_persian_digits(f"{data['month_total_tomans']:,}")
        o_debt_str = to_persian_digits(f"{data['overdue_debt_tomans']:,}")
        o_count_str = to_persian_digits(data["overdue_debtors_count"])
        p_debt_str = to_persian_digits(f"{data['projected_debt_tomans']:,}")

        lines.append(f"• درآمد ماه جاری تا امروز: {m_total_str} تومان")
        lines.append(f"• بدهی معوق قطعی تا امروز: {o_debt_str} تومان ({o_count_str} نفر)")
        lines.append(f"• کل مطالبات تا پایان ماه: {p_debt_str} تومان")

        # Empty rooms and beds: each on its own line
        empty_beds_str = to_persian_digits(data["total_empty_beds"])
        lines.append(f"• مجموع تخت‌های خالی: {empty_beds_str} تخت")
        if data["vacant_rooms"]:
            for vr in data["vacant_rooms"]:
                r_num = to_persian_digits(vr["room_number"])
                b_count = to_persian_digits(vr["empty_beds"])
                lines.append(f"- اتاق {r_num}: {b_count} تخت")
        else:
            lines.append("- تمام اتاق‌ها تکمیل ظرفیت است")

        return "\n".join(lines)
