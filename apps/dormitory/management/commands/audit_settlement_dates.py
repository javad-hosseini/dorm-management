"""
Audit and Realignment command for resident settlement dates.
Detects and resolves the ±1 day tolerance discrepancy caused by Jalali month-end boundaries
(e.g., settled_until set to 1405-07-30 or 1405-08-30 when monthly_payment_day is 1).
"""

import sys
import jdatetime
from tabulate import tabulate

from django.core.management.base import BaseCommand
from apps.dormitory.models import Resident
from apps.dormitory.jalali_utils import get_days_in_jalali_month, normalize_settlement_boundary


class Command(BaseCommand):
    help = (
        "Audit and realign resident settlement dates that have a ±1 day tolerance\n"
        "due to Jalali calendar month length differences (31, 30, and 29 days)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit normalized settlement dates to the database",
        )
        parser.add_argument(
            "--dormitory",
            type=int,
            default=1,
            help="Dormitory ID to audit (default: 1)",
        )

    def handle(self, *args, **options):
        apply = options.get("apply", False)
        dorm_id = options.get("dormitory", 1)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔍 در حال بررسی تاریخ‌های تسویه ساکنان بر اساس طول ماه‌های تقویم جلالی..."
        ))

        residents = Resident.objects.filter(
            dormitory_id=dorm_id,
            status=Resident.Status.ACTIVE,
            settled_until__isnull=False,
        ).order_by("room__room_number", "id")

        affected = []
        for res in residents:
            su = res.settled_until
            days_in_m = get_days_in_jalali_month(su.year, su.month)
            pay_day = res.monthly_payment_day or 1

            if pay_day == 1 and su.day == days_in_m:
                norm_date = normalize_settlement_boundary(su, pay_day)
                affected.append({
                    "id": res.id,
                    "resident": res.full_name,
                    "room": res.room.room_number if res.room else "-",
                    "pay_day": f"{pay_day}ام ماه",
                    "current_settled": str(su),
                    "normalized_settled": str(norm_date),
                    "reason": f"پایان ماه {su.month} ({days_in_m} روزه) ⬅️ اول ماه بعد",
                    "resident_obj": res,
                    "target_date": norm_date,
                })

        if not affected:
            self.stdout.write(self.style.SUCCESS(
                "✅ تمامی تاریخ‌های تسویه مقیمان با روزهای سررسید و طول ماه‌های شمسی کاملاً همگام است. هیچ مغایرتی یافت نشد."
            ))
            return

        table_rows = []
        for item in affected:
            table_rows.append([
                f"#{item['id']}",
                item["resident"],
                f"اتاق {item['room']}",
                item["pay_day"],
                item["current_settled"],
                item["normalized_settled"],
                item["reason"],
            ])

        headers = [
            "شناسه",
            "نام ساکن",
            "اتاق",
            "موعد پرداخت",
            "تسویه فعلی (با تلورانس)",
            "تسویه اصلاح‌شده",
            "علت اصلاح",
        ]

        self.stdout.write(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))
        self.stdout.write(f"\n📊 تعداد موارد شناسایی‌شده: {len(affected)} نفر")

        if apply:
            for item in affected:
                res = item["resident_obj"]
                res.settled_until = item["target_date"]
                res.save(update_fields=["settled_until"])
            self.stdout.write(self.style.SUCCESS(
                f"✅ تغییرات با موفقیت در پایگاه داده ثبت شد: {len(affected)} مقیم اصلاح گردیدند."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\n💡 حالت پیش‌نمایش (Dry Run): تغییری در پایگاه داده اعمال نشد.\n"
                "جهت اعمال رسمی اصلاحات، دستور را با فلگ --apply اجرا فرمایید:\n"
                "  .venv/bin/python manage.py audit_settlement_dates --apply\n"
            ))
