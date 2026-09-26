"""
Django management command to test SMS sending directly from the CLI.
Usage:
    python manage.py send_test_sms 09123456789
    python manage.py send_test_sms 09123456789 --text "Hello test SMS"
    python manage.py send_test_sms 09123456789 --real
"""

import sys
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.sms_service.utils import normalize_phone_number
from apps.sms_service.services.provider import (
    MeliPayamakRestProvider,
    ConsoleSmsProvider,
    get_sms_provider,
)


class Command(BaseCommand):
    help = "Send a test SMS to verify MeliPayamak gateway connectivity."

    def add_arguments(self, parser):
        parser.add_argument(
            "phone",
            type=str,
            help="Recipient mobile number (e.g. 09123456789 or +989123456789)",
        )
        parser.add_argument(
            "--text",
            type=str,
            default="پیامک آزمایشی سامانه مدیریت خوابگاه",
            help="SMS message text to send",
        )
        parser.add_argument(
            "--real",
            action="store_true",
            help="Force real send via MeliPayamak gateway even if SMS_CONSOLE_MODE is True",
        )

    def handle(self, *args, **options):
        # Ensure utf-8 encoding on Windows console if needed
        if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        raw_phone = options["phone"]
        text = options["text"]
        force_real = options["real"]

        try:
            phone = normalize_phone_number(raw_phone)
        except Exception as e:
            raise CommandError(f"شماره موبایل نامعتبر است: {e}")

        self.stdout.write(self.style.NOTICE("=== بررسی وضعیت درگاه ملی‌پیامک ==="))
        self.stdout.write(f"گیرنده: {phone}")
        self.stdout.write(f"متن پیامک: {text}")

        # Resolve provider
        if force_real:
            self.stdout.write(self.style.WARNING("درخواست ارسال واقعی (--real) انتخاب شده است."))
            try:
                provider = MeliPayamakRestProvider()
            except Exception as e:
                raise CommandError(f"خطا در تنظیمات ملی‌پیامک: {e}")
        else:
            provider = get_sms_provider()

        if isinstance(provider, ConsoleSmsProvider):
            self.stdout.write(
                self.style.WARNING(
                    "[حالت کنسول فعال است] پیامک در کنسول شبیه‌سازی شد و به درگاه ارسال نشد.\n"
                    "برای ارسال واقعی یا مقدار SMS_CONSOLE_MODE را در .env به False تغییر دهید یا سوئیچ --real را اضافه کنید."
                )
            )
        else:
            sender = getattr(settings, "MELIPAYAMAK_SENDER", "")
            self.stdout.write(f"شماره فرستنده: {sender}")
            self.stdout.write("توکن درگاه: [تنظیم شده و ایمن]")
            self.stdout.write("در حال ارسال درخواست به سرور ملی‌پیامک...")

        result = provider.send_simple_sms(recipients=[phone], text=text)

        if result.success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ پیامک با موفقیت ارسال شد!\nشناسه رسید درگاه (recId): {result.rec_id}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"✗ ارسال پیامک با خطا مواجه شد!\n"
                    f"کد خطا: {result.error_code}\n"
                    f"پیام خطا: {result.error_message}\n"
                    f"پاسخ خام درگاه: {result.raw_response}"
                )
            )

