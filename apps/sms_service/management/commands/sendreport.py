"""
Django management command to compile and send the daily executive report SMS.

Usage:
    # Standard run (sends yesterday's report to 09210431554):
    python manage.py sendreport

    # Preview report in console without sending SMS:
    python manage.py sendreport --dry-run

    # Send report for a specific Jalali date:
    python manage.py sendreport --date "1405/08/10"

    # Send to custom phone number:
    python manage.py sendreport --phone "09123456789"

    # Force real send even if SMS_CONSOLE_MODE=True:
    python manage.py sendreport --real
"""

import sys
import jdatetime
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.sms_service.utils import normalize_phone_number
from apps.sms_service.services.provider import get_sms_provider
from apps.dormitory.services.daily_report_service import DailyReportService
from apps.dormitory.jalali_utils import parse_jalali_date


class Command(BaseCommand):
    help = "Compile yesterday's executive dormitory report and send it via SMS to 09210431554."

    DEFAULT_RECIPIENT = "09210431554"

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone",
            type=str,
            default=self.DEFAULT_RECIPIENT,
            help=f"Recipient mobile number (default: {self.DEFAULT_RECIPIENT})",
        )
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target Jalali date in YYYY/MM/DD format (defaults to yesterday)",
        )
        parser.add_argument(
            "--dormitory",
            "--dorm-id",
            dest="dormitory",
            type=str,
            default=None,
            help="Dormitory ID to report for (default: None for all dormitories / کل مجموعه خوابگاه‌ها). Pass e.g. 1 for خوابگاه نوید.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview report in console without sending actual SMS",
        )
        parser.add_argument(
            "--real",
            action="store_true",
            help="Force real SMS dispatch via MeliPayamak even if SMS_CONSOLE_MODE is True",
        )

    def handle(self, *args, **options):
        # Configure console encoding for UTF-8 compatibility
        if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        raw_phone = options.get("phone") or self.DEFAULT_RECIPIENT
        date_str = options.get("date")
        dorm_raw = options.get("dormitory")
        dormitory_id = None
        if dorm_raw is not None and str(dorm_raw).strip() not in ("", "all", "ALL", "0"):
            try:
                dormitory_id = int(dorm_raw)
            except ValueError:
                raise CommandError(f"شناسه خوابگاه نامعتبر است ({dorm_raw}). لطفاً یک عدد وارد کنید یا خالی بگذارید.")
        is_dry_run = options.get("dry_run", False)
        force_real = options.get("real", False)

        # 1. Normalize recipient phone number
        try:
            phone = normalize_phone_number(raw_phone)
        except Exception as e:
            raise CommandError(f"شماره موبایل گیرنده نامعتبر است ({raw_phone}): {e}")

        # 2. Parse target date if provided
        target_date = None
        if date_str:
            target_date = parse_jalali_date(date_str)
            if not target_date:
                raise CommandError(f"فرمت تاریخ نامعتبر است ({date_str}). لطفاً از فرمت YYYY/MM/DD استفاده کنید.")

        # 3. Generate report data and SMS text
        try:
            report_data = DailyReportService.get_daily_report_data(
                target_date=target_date,
                dormitory_id=dormitory_id,
            )
            sms_text = DailyReportService.generate_sms_text(
                target_date=target_date,
                dormitory_id=dormitory_id,
            )
        except Exception as e:
            raise CommandError(f"خطا در محاسبه و تولید گزارش روزانه: {e}")

        # 4. Print clean console presentation
        prefix = "[DRY RUN] " if is_dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"\n{prefix}📊 گزارش مدیریتی روزانه خوابگاه:"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 55))
        self.stdout.write(f"• خوابگاه: {report_data['dorm_name']}")
        self.stdout.write(f"• تاریخ گزارش: {report_data['weekday_name']} {report_data['target_date_str']}")
        self.stdout.write(f"• گیرنده پیامک: {phone}")
        self.stdout.write(f"• طول متن پیامک: {len(sms_text)} کاراکتر")
        self.stdout.write(self.style.MIGRATE_HEADING("-" * 55))
        self.stdout.write("متن پیامک ارسالی:")
        self.stdout.write(sms_text)
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 55))

        # 5. Dispatch SMS if not dry-run
        if is_dry_run:
            self.stdout.write(self.style.WARNING("⚠️ حالت پیش‌نمایش (Dry-Run): پیامکی ارسال نشد.\n"))
            return

        # Handle force real send
        if force_real:
            from apps.sms_service.services.provider import MeliPayamakRestProvider
            try:
                provider = MeliPayamakRestProvider()
            except Exception as e:
                raise CommandError(f"خطا در ایجاد اتصال ملی‌پیامک: {e}")
        else:
            provider = get_sms_provider()

        self.stdout.write(f"در حال ارسال پیامک از طریق درگاه ({type(provider).__name__})...")

        result = provider.send_simple_sms(
            recipients=[phone],
            text=sms_text,
        )

        if result.success:
            self.stdout.write(self.style.SUCCESS(f"✅ پیامک با موفقیت به {phone} ارسال شد."))
            if result.rec_id:
                self.stdout.write(f"• شناسه پیگیری درگاه (rec_id): {result.rec_id}")
            self.stdout.write("")
        else:
            self.stdout.write(self.style.ERROR(f"❌ ارسال پیامک به {phone} با خطا مواجه شد."))
            self.stdout.write(f"• کد خطا: {result.error_code}")
            self.stdout.write(f"• پیام خطا: {result.error_message}")
            if result.raw_response:
                self.stdout.write(f"• پاسخ خام: {result.raw_response}")
            self.stdout.write("")
            raise CommandError(f"خطا در ارسال پیامک: {result.error_message or result.error_code}")
