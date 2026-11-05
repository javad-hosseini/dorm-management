"""
Management command to reconcile bank statements with database transactions.
Detects fraudulent/unverified receipts, matches legitimate payments,
and updates database records with official bank tracking codes.
"""

import os
import sys
from typing import Optional

import jdatetime
from tabulate import tabulate
from django.core.management.base import BaseCommand, CommandError

from apps.dormitory.services.bank_reconciliation import (
    BankStatementParser,
    BankReconciliationEngine,
    parse_jalali_to_datetime,
)


class Command(BaseCommand):
    help = "مغایرت‌گیری صورت‌حساب بانکی با تراکنش‌های سامانه و کشف فیش‌های نامعتبر یا جعلی"

    def add_arguments(self, parser):
        parser.add_argument(
            "-f",
            "--file",
            type=str,
            required=True,
            help="مسیر فایل صورت‌حساب بانکی (CSV یا XLSX)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="اعمال واقعی تغییرات در دیتابیس (تایید و ثبت کدرهگیری برای موارد منطبق، و رد تایید و ثبت اخطار برای فیش‌های جعلی)",
        )
        parser.add_argument(
            "--export-report",
            type=str,
            default="",
            help="مسیر اختیاری برای ذخیره گزارش جامع مغایرت‌گیری در قالب Markdown",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            default="",
            help="فیلتر شروع تاریخ شمسی (مثال: 1405/07/01)",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default="",
            help="فیلتر پایان تاریخ شمسی (مثال: 1405/08/13)",
        )
        parser.add_argument(
            "--time-window",
            type=int,
            default=1440,
            help="حداکثر پنجره جستجوی زمانی مجاز در سطح ۲ بر حسب دقیقه (پیش‌فرض: ۱۴۴۰ دقیقه / ۲۴ ساعت)",
        )

    def handle(self, *args, **options):
        # Configure stdout encoding for Persian
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        file_path = options["file"]
        apply_changes = options["apply"]
        export_path = options["export_report"]
        start_date_str = options["start_date"]
        end_date_str = options["end_date"]
        time_window = options["time_window"]

        if not os.path.exists(file_path):
            raise CommandError(f"فایل مشخص‌شده یافت نشد: {file_path}")

        self.stdout.write(self.style.NOTICE(f"\n📂 در حال خواندن و تحلیل صورت‌حساب بانکی: {file_path}"))

        # 1. Parse statement
        parser = BankStatementParser(file_path)
        try:
            deposits = parser.parse()
        except Exception as e:
            raise CommandError(f"خطا در خواندن فایل صورت‌حساب: {str(e)}")

        if not deposits:
            self.stdout.write(self.style.WARNING("هیچ واریزی در فایل صورت‌حساب یافت نشد."))
            return

        self.stdout.write(self.style.SUCCESS(f"✔ {len(deposits)} ردیف واریزی معتبر با موفقیت استخراج شد."))
        if parser.metadata:
            meta_str = " | ".join(f"{k}: {v}" for k, v in parser.metadata.items())
            self.stdout.write(f"ℹ️ مشخصات صورت‌حساب: {meta_str}")

        # Parse date filters if provided
        start_date = None
        end_date = None
        if start_date_str:
            jdt, _ = parse_jalali_to_datetime(start_date_str)
            start_date = jdt.date()
        if end_date_str:
            jdt, _ = parse_jalali_to_datetime(end_date_str)
            end_date = jdt.date()

        # 2. Run Reconciliation Engine
        self.stdout.write(self.style.NOTICE("🔍 در حال اجرای موتور هوشمند مغایرت‌گیری دو سطحی..."))
        engine = BankReconciliationEngine(
            bank_deposits=deposits,
            start_date=start_date,
            end_date=end_date,
            time_window_minutes=time_window,
        )
        summary = engine.run()

        # 3. Print Executive Table
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.HTTP_INFO("📊 خلاصه نتایج مغایرت‌گیری بانکی"))
        self.stdout.write("=" * 70)

        summary_table = [
            ["کل واریزهای صورت‌حساب بانکی", f"{summary['total_bank_deposits']:,}", f"{summary['total_bank_tomans']:,} تومان", f"{summary['total_bank_rials']:,} ریال"],
            ["✅ تراکنش‌های معتبر و منطبق (Verified)", f"{summary['verified_count']:,}", f"{summary['verified_tomans']:,} تومان", f"{summary['verified_rials']:,} ریال"],
            ["🚨 فیش‌های فاقد واریز / مشکوک (Unverified)", f"{summary['unverified_count']:,}", f"{summary['unverified_tomans']:,} تومان", f"{summary['unverified_rials']:,} ریال"],
            ["💳 واریزی‌های تجمیعی پوز شاپرک", f"{summary['shaparak_count']:,}", f"{summary['shaparak_tomans']:,} تومان", f"{summary['shaparak_rials']:,} ریال"],
            ["ℹ️ واریزی‌های ثبت‌نشده در سامانه / متفرقه", f"{summary['other_unmatched_count']:,}", f"{summary['other_unmatched_tomans']:,} تومان", f"{summary['other_unmatched_rials']:,} ریال"],
        ]
        self.stdout.write(tabulate(summary_table, headers=["شاخص", "تعداد", "مبلغ (تومان)", "مبلغ (ریال)"], tablefmt="grid"))

        # Highlight Suspected Fakes if any
        if engine.unverified_transactions:
            self.stdout.write("\n" + self.style.ERROR(f"🚨 هشدار: {len(engine.unverified_transactions)} تراکنش مشکوک بدون واریز معادل یافت شد:"))
            fake_table = []
            for tx in engine.unverified_transactions[:15]:
                room_str = str(tx.resident.room.room_number) if tx.resident.room else "-"
                date_str = tx.payment_date.strftime("%Y/%m/%d %H:%M") if tx.payment_date else "-"
                fake_table.append([tx.id, tx.resident.full_name, room_str, f"{tx.amount // 10:,}", date_str, tx.reference_number or "-"])
            self.stdout.write(tabulate(fake_table, headers=["شناسه", "نام ساکن", "اتاق", "مبلغ (تومان)", "تاریخ ثبت", "کد رهگیری ادعایی"], tablefmt="simple"))
            if len(engine.unverified_transactions) > 15:
                self.stdout.write(f"... و {len(engine.unverified_transactions) - 15} مورد دیگر.")

        # 4. Apply DB Updates if requested
        if apply_changes:
            self.stdout.write(self.style.WARNING("\n⚙️ در حال اعمال تغییرات بر روی پایگاه‌داده..."))
            db_res = engine.apply_updates()
            self.stdout.write(self.style.SUCCESS(
                f"✔ عملیات با موفقیت انجام شد:\n"
                f"  - {db_res['verified_updated']} تراکنش معتبر با کدرهگیری رسمی بانک بروزرسانی شدند.\n"
                f"  - {db_res['unverified_flagged']} تراکنش مشکوک رد تایید (is_approved=False) شدند.\n"
                f"  - {db_res['warning_notes_created']} یادداشت انضباطی هشدار مغایرت در پرونده ساکنین ایجاد شد."
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                "\n💡 حالت پیش‌نمایش (Dry Run): هیچ تغییری در پایگاه‌داده اعمال نشد.\n"
                "برای اعمال رسمی تغییرات و ثبت کدهای رهگیری، دستور را با فلگ --apply اجرا کنید."
            ))

        # 5. Export Report if requested
        if export_path:
            md_content = engine.generate_markdown_report()
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            self.stdout.write(self.style.SUCCESS(f"\n📄 گزارش کامل مغایرت‌گیری در فایل زیر ذخیره شد:\n  {export_path}"))
