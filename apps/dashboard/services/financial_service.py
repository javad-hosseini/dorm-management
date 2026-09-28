import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List
import jdatetime
from django.db.models import Sum, Count, Q
from apps.dormitory.models import Transaction, Resident, Room, Dormitory
from apps.dormitory.jalali_utils import (
    calculate_unpaid_periods,
    get_jalali_month_name,
    to_persian_digits
)


class FinancialService:
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")

    @classmethod
    def get_financial_dashboard_data(cls) -> Dict[str, Any]:
        today = jdatetime.date.today()
        tz = cls.TEHRAN_TZ

        # 1. Today's start and end datetimes
        today_start = jdatetime.datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=tz)
        today_end = jdatetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=tz)

        # Yesterday's start and end
        yesterday = today - datetime.timedelta(days=1)
        yesterday_start = jdatetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=tz)
        yesterday_end = jdatetime.datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, tzinfo=tz)

        # Today's Query
        today_qs = Transaction.objects.filter(payment_date__gte=today_start, payment_date__lte=today_end)
        today_card = sum(t.amount for t in today_qs.filter(payment_method="CARD")) // 10
        today_transfer = sum(t.amount for t in today_qs.filter(payment_method="BANK_TRANSFER")) // 10
        today_cash = sum(t.amount for t in today_qs.filter(payment_method="CASH")) // 10
        today_online = sum(t.amount for t in today_qs.filter(payment_method="ONLINE_GATEWAY")) // 10
        today_total = today_card + today_transfer + today_cash + today_online
        today_count = today_qs.count()

        # Yesterday Total for comparison
        yesterday_qs = Transaction.objects.filter(payment_date__gte=yesterday_start, payment_date__lte=yesterday_end)
        yesterday_total = sum(t.amount for t in yesterday_qs) // 10
        if yesterday_total > 0:
            diff_vs_yesterday = round(((today_total - yesterday_total) / yesterday_total) * 100, 1)
        else:
            diff_vs_yesterday = 100.0 if today_total > 0 else 0.0

        today_stats = {
            "date_str": today.strftime("%Y/%m/%d"),
            "date_display": f"{today.strftime('%A')} {today.day} {get_jalali_month_name(today.month)} {today.year}",
            "total_tomans": today_total,
            "count": today_count,
            "card_tomans": today_card,
            "transfer_tomans": today_transfer,
            "cash_tomans": today_cash,
            "online_tomans": today_online,
            "yesterday_total_tomans": yesterday_total,
            "diff_vs_yesterday_percent": diff_vs_yesterday
        }

        # 2. 7-Day Inflow Breakdown
        seven_days_breakdown: List[Dict[str, Any]] = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            d_start = jdatetime.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
            d_end = jdatetime.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=tz)
            d_qs = Transaction.objects.filter(payment_date__gte=d_start, payment_date__lte=d_end)

            c_card = sum(t.amount for t in d_qs.filter(payment_method="CARD")) // 10
            c_transfer = sum(t.amount for t in d_qs.filter(payment_method="BANK_TRANSFER")) // 10
            c_cash = sum(t.amount for t in d_qs.filter(payment_method="CASH")) // 10
            c_online = sum(t.amount for t in d_qs.filter(payment_method="ONLINE_GATEWAY")) // 10
            d_total = c_card + c_transfer + c_cash + c_online

            seven_days_breakdown.append({
                "date_str": d.strftime("%Y/%m/%d"),
                "short_date": f"{d.month:02d}/{d.day:02d}",
                "day_name": d.strftime("%A"),
                "total_tomans": d_total,
                "card_tomans": c_card,
                "transfer_tomans": c_transfer,
                "cash_tomans": c_cash,
                "online_tomans": c_online,
                "count": d_qs.count()
            })

        # 3. Debt Calculation (Today's overdue & until 1st of next month)
        if today.month < 12:
            next_month_year = today.year
            next_month = today.month + 1
        else:
            next_month_year = today.year + 1
            next_month = 1
        first_of_next_month = jdatetime.date(next_month_year, next_month, 1)

        overdue_debt_tomans = 0
        projected_debt_tomans = 0
        indebted_residents_count = 0
        top_debtors_list = []

        active_residents = Resident.objects.filter(status="ACTIVE").select_related("room", "dormitory")
        for r in active_residents:
            debt_now = r.total_debt_amount_tomans
            if debt_now > 0:
                overdue_debt_tomans += debt_now
                indebted_residents_count += 1
                top_debtors_list.append({
                    "id": r.id,
                    "name": r.full_name,
                    "room_number": r.room.room_number if r.room else "-",
                    "dormitory": r.dormitory.name if r.dormitory else "-",
                    "debt_tomans": debt_now,
                    "overdue_days": r.overdue_days,
                    "phone": r.phone_number,
                    "unpaid_months": r.unpaid_months_display
                })

            # Calculate rent/due up to 1st of next month
            s = r.settled_until or r.entry_date
            if s and r.room and s < first_of_next_month:
                periods = calculate_unpaid_periods(
                    start_date=s,
                    as_of_date=first_of_next_month,
                    monthly_rent_rials=r.room.monthly_rent,
                    rent_resolver=r.room.get_rent_for_date
                )
                projected_debt_tomans += sum(p["amount_tomans"] for p in periods)

        top_debtors_list.sort(key=lambda x: x["debt_tomans"], reverse=True)
        top_debtors = top_debtors_list[:6]

        debt_stats = {
            "overdue_debt_tomans": overdue_debt_tomans,
            "projected_debt_until_next_month_tomans": projected_debt_tomans,
            "indebted_residents_count": indebted_residents_count,
            "active_residents_count": active_residents.count(),
            "first_of_next_month_str": first_of_next_month.strftime("%Y/%m/%d"),
            "next_month_name": f"{get_jalali_month_name(next_month)} {next_month_year}"
        }

        # 4. Current Month Stats (Month-to-Date)
        first_of_this_month = jdatetime.date(today.year, today.month, 1)
        month_start = jdatetime.datetime(first_of_this_month.year, first_of_this_month.month, 1, 0, 0, 0, tzinfo=tz)
        month_qs = Transaction.objects.filter(payment_date__gte=month_start, payment_date__lte=today_end)

        month_rent = sum(t.amount for t in month_qs.filter(transaction_type="RENT")) // 10
        month_deposit = sum(t.amount for t in month_qs.filter(transaction_type="DEPOSIT")) // 10
        month_total = month_rent + month_deposit

        method_card = sum(t.amount for t in month_qs.filter(payment_method="CARD")) // 10
        method_transfer = sum(t.amount for t in month_qs.filter(payment_method="BANK_TRANSFER")) // 10
        method_cash = sum(t.amount for t in month_qs.filter(payment_method="CASH")) // 10
        method_online = sum(t.amount for t in month_qs.filter(payment_method="ONLINE_GATEWAY")) // 10

        month_stats = {
            "month_name": f"{get_jalali_month_name(today.month)} {today.year}",
            "month_total_tomans": month_total,
            "month_rent_tomans": month_rent,
            "month_deposit_tomans": month_deposit,
            "method_card_tomans": method_card,
            "method_transfer_tomans": method_transfer,
            "method_cash_tomans": method_cash,
            "method_online_tomans": method_online,
            "month_tx_count": month_qs.count()
        }

        # 5. Recent Transactions List
        tx_qs = Transaction.objects.select_related("resident", "dormitory").order_by("-payment_date")[:100]
        recent_transactions = []
        method_map = {
            "CARD": "کارتخوان 💳",
            "BANK_TRANSFER": "کارت به کارت 🏦",
            "CASH": "نقدی 💵",
            "ONLINE_GATEWAY": "درگاه آنلاین 🌐"
        }
        for t in tx_qs:
            p_date = t.payment_date
            date_str = p_date.strftime("%Y/%m/%d") if p_date else "-"
            time_str = p_date.strftime("%H:%M") if p_date else "-"
            recent_transactions.append({
                "id": t.id,
                "resident_name": t.resident.full_name if t.resident else "ساکن نامشخص",
                "room_number": t.resident.room.room_number if (t.resident and t.resident.room) else "-",
                "dormitory": t.dormitory.name if t.dormitory else "-",
                "amount_tomans": t.amount // 10,
                "amount_formatted": f"{(t.amount // 10):,}",
                "type": t.transaction_type,
                "type_display": "اجاره" if t.transaction_type == "RENT" else "ودیعه",
                "method": t.payment_method,
                "method_display": method_map.get(t.payment_method, t.payment_method),
                "period_name": t.period_name or ("اجاره ماهیانه" if t.transaction_type == "RENT" else "ودیعه تضمین"),
                "reference_number": t.reference_number or "-",
                "date_str": date_str,
                "time_str": time_str,
                "is_approved": getattr(t, "is_approved", True),
                "has_discount": getattr(t, "has_discount", False),
                "discount_amount": getattr(t, "discount_amount", 0) or 0,
                "discount_in_tomans": getattr(t, "discount_in_tomans", 0) or 0,
                "discount_reason": getattr(t, "discount_reason", "") or "",
                "total_effective_amount_toman": getattr(t, "total_effective_amount_in_tomans", t.amount // 10),
            })

        return {
            "today_stats": today_stats,
            "seven_days_breakdown": seven_days_breakdown,
            "debt_stats": debt_stats,
            "month_stats": month_stats,
            "top_debtors": top_debtors,
            "recent_transactions": recent_transactions
        }
