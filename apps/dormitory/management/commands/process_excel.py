"""
Django management command to process dormitory Excel spreadsheets.
Supports both:
1. Cleaned batch spreadsheets conforming to BATCH_RECEIPT_PROTOCOL.md
2. Raw Telegram bot workbooks with embedded receipt images and supervisor notes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from django.core.management.base import BaseCommand, CommandError
from tabulate import tabulate

from apps.dormitory.services.excel_processor import DormitoryExcelProcessor, ProcessReport


class Command(BaseCommand):
    help = (
        "پردازش، اعتبارسنجی و ثبت دسته‌ای تراکنش‌ها از فایل‌های اکسل (Cleaned Batch و Raw Telegram Bot)\n"
        "Processes, validates, and ingests batch dormitory transactions from Excel (.xlsx) files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-f",
            "--file",
            type=str,
            required=True,
            help="مسیر فایل اکسل ورودی (.xlsx یا .csv)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="اعمال قطعی در پایگاه داده (در صورت عدم ارسال، به صورت پیش‌نمایش dry-run اجرا می‌شود)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="صرفاً پیش‌نمایش و شبیه‌سازی بدون تغییر در دیتابیس (حالت پیش‌فرض)",
        )
        parser.add_argument(
            "--no-extract-images",
            action="store_true",
            default=False,
            help="عدم استخراج تصاویر رسیدی از شیت‌های خام تلگرام",
        )
        parser.add_argument(
            "--image-dir",
            type=str,
            default="",
            help="مسیر سفارشی ذخیره تصاویر استخراج‌شده از فیش‌ها",
        )
        parser.add_argument(
            "--export-cleaned",
            type=str,
            default="",
            help="مسیر ذخیره فایل اکسل استانداردسازی‌شده (Cleaned) برگرفته از شیت خام",
        )
        parser.add_argument(
            "--export-failed",
            type=str,
            default="",
            help="مسیر ذخیره گزارش اکسل سطرهای ناموفق (failed_rows_report.xlsx)",
        )
        parser.add_argument(
            "--json-output",
            action="store_true",
            default=False,
            help="خروجی با فرمت JSON برای استفاده ربات تلگرام یا عامل‌های هوش مصنوعی",
        )
        parser.add_argument(
            "--archive",
            action="store_true",
            default=False,
            help="انتقال فایل ورودی به پوشه processed/ یا failed/ پس از پردازش",
        )
        parser.add_argument(
            "--no-auto-flag",
            action="store_true",
            default=False,
            help="عدم ثبت خودکار موارد مشکوک در سند FINANCE_DOUBTS.md",
        )
        parser.add_argument(
            "--supervisor",
            type=int,
            default=1,
            help="شناسه سرپرست ثبت‌کننده (پیش‌فرض: ۱ - جواد حسینی)",
        )

    def handle(self, *args, **options):
        file_path_str = options["file"]
        apply_changes = options["apply"] and not options["dry_run"]
        extract_images = not options["no_extract_images"]
        image_dir = Path(options["image_dir"]) if options["image_dir"] else None
        export_cleaned = Path(options["export_cleaned"]) if options["export_cleaned"] else None
        export_failed = Path(options["export_failed"]) if options["export_failed"] else None
        json_output = options["json_output"]
        archive = options["archive"]
        auto_flag = not options["no_auto_flag"]
        supervisor_id = options["supervisor"]

        file_path = Path(file_path_str).resolve()
        if not file_path.exists():
            raise CommandError(f"فایل مشخص‌شده یافت نشد: {file_path}")

        processor = DormitoryExcelProcessor(supervisor_id=supervisor_id)

        try:
            report: ProcessReport = processor.process_file(
                file_path=file_path,
                apply=apply_changes,
                extract_images=extract_images,
                image_dir=image_dir,
                export_cleaned_path=export_cleaned,
                export_failed_path=export_failed,
                auto_flag_doubts=auto_flag,
                archive=archive,
            )
        except Exception as exc:
            if json_output:
                self.stdout.write(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
                return
            raise CommandError(f"خطا در پردازش فایل اکسل: {exc}")

        # JSON Output
        if json_output:
            data = {
                "success": report.failed_rows == 0,
                "mode": report.mode,
                "file": report.source_file,
                "file_hash": report.file_hash,
                "dry_run": report.dry_run,
                "summary": {
                    "total_rows": report.total_rows,
                    "succeeded_rows": report.succeeded_rows,
                    "failed_rows": report.failed_rows,
                    "duplicate_rows": report.duplicate_rows,
                    "discrepancy_rows": report.discrepancy_rows,
                    "total_amount_tomans": report.total_amount_tomans,
                    "total_amount_rials": report.total_amount_rials,
                    "rent_tomans": report.total_rent_tomans,
                    "deposit_tomans": report.total_deposit_tomans,
                    "extracted_images_count": len(report.extracted_images),
                },
                "transactions": report.transactions_created,
                "failed_items": [{"data": it[0], "error": it[1]} for it in report.failed_items],
                "discrepancies": report.discrepancies,
                "doubts": report.doubts_flagged,
                "new_residents": report.new_residents_registered,
                "room_changes": report.room_changes_applied,
                "check_outs": report.check_outs_applied,
                "output_cleaned_excel": report.output_cleaned_excel,
                "output_failed_excel": report.output_failed_excel,
            }
            self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
            return

        # Pretty Terminal Output
        mode_title = "شیت خام تلگرام (Raw Session)" if report.mode == "RAW_TELEGRAM_SESSION" else "جدول استاندارد (Cleaned Batch)"
        status_mode = self.style.WARNING("حالت پیش‌نمایش (Dry Run) — بدون تغییر در پایگاه داده") if report.dry_run else self.style.SUCCESS("حالت اعمال قطعی (Applied) — با ثبت در دیتابیس")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.NOTICE(f"📊 گزارش پردازش اکسل خوابگاه نوید | {mode_title}"))
        self.stdout.write(f"📁 فایل ورودی: {report.source_file}")
        self.stdout.write(f"🔒 وضعیت اجرا: {status_mode}")
        self.stdout.write("=" * 70)

        # Metrics Summary Table
        summary_table = [
            ["تعداد کل سطور پردازش‌شده", report.total_rows],
            ["سطور موفق / معتبر", self.style.SUCCESS(str(report.succeeded_rows))],
            ["سطور ناموفق / دارای خطا", self.style.ERROR(str(report.failed_rows)) if report.failed_rows else "0"],
            ["تراکنش‌های تکراری", self.style.WARNING(str(report.duplicate_rows)) if report.duplicate_rows else "0"],
            ["مغایرت‌ها و کسری‌های ثبت‌شده", self.style.WARNING(str(report.discrepancy_rows)) if report.discrepancy_rows else "0"],
            ["مجموع مبالغ (تومان)", f"{report.total_amount_tomans:,} تومان"],
            ["مجموع مبالغ (ریال)", f"{report.total_amount_rials:,} ریال"],
            ["سهم اجاره (تومان)", f"{report.total_rent_tomans:,} تومان"],
            ["سهم ودیعه (تومان)", f"{report.total_deposit_tomans:,} تومان"],
        ]
        if report.extracted_images:
            summary_table.append(["تصاویر فیش‌های استخراج‌شده", f"{len(report.extracted_images)} تصویر"])
        if report.new_residents_registered:
            summary_table.append(["پذیرش و ثبت ساکنین جدید", f"{len(report.new_residents_registered)} نفر"])
        if report.room_changes_applied:
            summary_table.append(["جابجایی اتاق‌های اعمال‌شده", f"{len(report.room_changes_applied)} مورد"])
        if report.check_outs_applied:
            summary_table.append(["تخلیه و خروج ساکن", f"{len(report.check_outs_applied)} نفر"])

        self.stdout.write(tabulate(summary_table, headers=["شاخص", "مقدار"], tablefmt="fancy_grid"))

        # Transactions Table
        if report.transactions_created:
            self.stdout.write("\n" + self.style.NOTICE("🧾 تراکنش‌های مالی پردازش‌شده:"))
            tx_rows = []
            for t in report.transactions_created:
                tx_id = f"#{t['transaction_id']}" if t.get("transaction_id") else "-"
                tx_rows.append([
                    tx_id,
                    t.get("type_display", t.get("type", "RENT")),
                    f"{t.get('amount_tomans', 0):,} تومان",
                    t.get("method_display", t.get("method", "CARD")),
                    t.get("period_name") or "-",
                    t.get("payment_date", "-"),
                    t.get("reference_number") or "-",
                ])
            self.stdout.write(
                tabulate(
                    tx_rows,
                    headers=["شناسه", "نوع", "مبلغ", "روش", "دوره پوشش", "تاریخ", "کد رهگیری / ارجاع"],
                    tablefmt="simple",
                )
            )

        # New Residents Table
        if report.new_residents_registered:
            self.stdout.write("\n" + self.style.NOTICE("👤 ساکنین جدید شناسایی‌شده:"))
            res_rows = [
                [r["name"], r["room"] or "-", r.get("national_code") or "-", r.get("phone") or "-", r.get("entry_date") or "-"]
                for r in report.new_residents_registered
            ]
            self.stdout.write(tabulate(res_rows, headers=["نام و نام خانوادگی", "اتاق", "کد ملی", "تلفن همراه", "تاریخ ورود"], tablefmt="simple"))

        # Discrepancies Table
        if report.discrepancies:
            self.stdout.write("\n" + self.style.WARNING("⚠️ موارد کسری پرداختی و مغایرت با نرخ مصوب اتاق:"))
            disc_rows = [
                [
                    d.get("room_number", "-"),
                    f"{d.get('paid_rent_tomans', 0):,} تومان",
                    f"{d.get('expected_rent_tomans', 0):,} تومان",
                    f"{abs(d.get('diff_tomans', 0)):,} تومان کسری",
                    d.get("period_name", "-"),
                ]
                for d in report.discrepancies
            ]
            self.stdout.write(tabulate(disc_rows, headers=["اتاق", "پرداختی", "نرخ مصوب", "کسری", "دوره تسویه"], tablefmt="simple"))

        # Doubts Table
        if report.doubts_flagged:
            self.stdout.write("\n" + self.style.WARNING("🔍 یادداشت‌های نیازمند بررسی سرپرست (Finance Doubts):"))
            doubt_rows = [
                [d.get("flag_type", "CHECK"), d.get("explanation") or d.get("note", "-")]
                for d in report.doubts_flagged
            ]
            self.stdout.write(tabulate(doubt_rows, headers=["نوع موضوع", "توضیحات"], tablefmt="simple"))

        # Failed Items Table
        if report.failed_items:
            self.stdout.write("\n" + self.style.ERROR("❌ سطور ناموفق:"))
            err_rows = [
                [str(item[0].get("resident") or item[0].get("name") or item[0]), item[1]]
                for item in report.failed_items
            ]
            self.stdout.write(tabulate(err_rows, headers=["ردیف / ساکن", "علت خطا"], tablefmt="simple"))

        # Export Files feedback
        if report.output_cleaned_excel:
            self.stdout.write(self.style.SUCCESS(f"\n✔ فایل اکسل استانداردسازی‌شده ذخیره شد: {report.output_cleaned_excel}"))
        if report.output_failed_excel:
            self.stdout.write(self.style.ERROR(f"\n✔ گزارش اکسل سطور ناموفق ذخیره شد: {report.output_failed_excel}"))

        if report.dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    "\n💡 برای ثبت قطعی در پایگاه داده، دستور را مجدداً با سویچ --apply اجرا فرمایید:\n"
                    f"   .venv/bin/python manage.py process_excel --file \"{file_path}\" --apply\n"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\n🎉 تمامی عملیات با موفقیت در پایگاه داده ثبت شد."))
