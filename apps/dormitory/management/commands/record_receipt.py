import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from django.core.management.base import BaseCommand, CommandError
from apps.dormitory.services.receipt_processor import process_receipt, find_resident_smart


class Command(BaseCommand):
    help = (
        "Optimized tool to record dormitory transactions from receipt data.\n"
        "ثبت فوق سریع و هوشمند تراکنش‌های مالی خوابگاه (تک‌تراکنش و ترکیبی)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json-input",
            type=str,
            help="JSON string containing all transaction arguments",
        )
        parser.add_argument(
            "--resident",
            type=str,
            help="Resident identifier: ID, National Code, or Name",
        )
        parser.add_argument(
            "--room",
            type=str,
            help="Room number (helps filter resident)",
        )
        parser.add_argument(
            "--amount-tomans",
            type=int,
            help="Total amount paid in Tomans (for single transaction)",
        )
        parser.add_argument(
            "--amount-rials",
            type=int,
            help="Total amount paid in Rials",
        )
        # Split transaction options
        parser.add_argument(
            "--deposit-tomans",
            type=int,
            help="Deposit portion in Tomans (for split or pure deposit)",
        )
        parser.add_argument(
            "--rent-tomans",
            type=int,
            help="Rent portion in Tomans (for split or pure rent)",
        )
        parser.add_argument(
            "--type",
            choices=["RENT", "DEPOSIT"],
            default="RENT",
            help="Transaction type: RENT or DEPOSIT (default: RENT)",
        )
        parser.add_argument(
            "--method",
            choices=["CARD", "CASH", "BANK_TRANSFER", "ONLINE_GATEWAY"],
            default="CARD",
            help="Payment method: CARD, CASH, BANK_TRANSFER, ONLINE_GATEWAY (default: CARD)",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Payment datetime (Jalali, e.g. '1405/07/21 17:55:40' or '1405-07-21')",
        )
        parser.add_argument(
            "--ref",
            type=str,
            default="",
            help="Reference / Tracking number / Card / Terminal info",
        )
        parser.add_argument(
            "--desc",
            type=str,
            default="",
            help="Description / Notes",
        )
        parser.add_argument(
            "--period-start",
            type=str,
            help="Explicit start date of rent period (Jalali, e.g. '1405-08-01')",
        )
        parser.add_argument(
            "--period-end",
            type=str,
            help="Explicit end date of rent period (Jalali, e.g. '1405-09-01')",
        )
        parser.add_argument(
            "--settled-until",
            type=str,
            help="Explicit date to set resident settled_until (Jalali, e.g. '1405-09-01')",
        )
        parser.add_argument(
            "--supervisor-id",
            type=int,
            default=1,
            help="Supervisor ID who recorded transaction (default: 1 - جواد حسینی)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate execution without committing changes to DB",
        )
        parser.add_argument(
            "--json-output",
            action="store_true",
            help="Output result formatted as JSON",
        )

    def handle(self, *args, **options):
        # Handle JSON input if supplied
        if options.get("json_input"):
            try:
                j_data = json.loads(options["json_input"])
                for k, v in j_data.items():
                    opt_key = k.replace("-", "_")
                    options[opt_key] = v
            except Exception as e:
                raise CommandError(f"خطا در خواندن json-input: {e}")

        resident_query = options.get("resident")
        if not resident_query:
            raise CommandError("پارامتر --resident الزامی است.")

        amount_tomans = options.get("amount_tomans")
        amount_rials = options.get("amount_rials")
        if amount_tomans is None and amount_rials is not None:
            amount_tomans = amount_rials // 10

        deposit_tomans = options.get("deposit_tomans")
        rent_tomans = options.get("rent_tomans")

        try:
            res = process_receipt(
                resident=resident_query,
                room=options.get("room"),
                amount_tomans=amount_tomans,
                deposit_tomans=deposit_tomans,
                rent_tomans=rent_tomans,
                type=options.get("type") or "RENT",
                method=options.get("method") or "CARD",
                date=options.get("date"),
                ref=options.get("ref") or "",
                desc=options.get("desc") or "",
                period_start=options.get("period_start"),
                period_end=options.get("period_end"),
                settled_until=options.get("settled_until"),
                supervisor_id=options.get("supervisor_id") or 1,
                dry_run=options.get("dry_run", False),
            )
        except Exception as e:
            raise CommandError(str(e))

        if options.get("json_output"):
            self.stdout.write(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            prefix = "[DRY RUN] " if res["dry_run"] else ""
            self.stdout.write(self.style.SUCCESS(f"\n{prefix}✅ تراکنش با موفقیت پردازش و ثبت گردید:"))
            self.stdout.write(f"• ساکن: {res['resident_name']} (اتاق {res['room']}) - شناسه: #{res['resident_id']}")
            self.stdout.write(f"• مبلغ کل: {res['total_amount_tomans']:,} تومان ({res['total_amount_rials']:,} ریال)")
            self.stdout.write(f"• وضعیت ودیعه: {'✅ دارد' if res['has_deposit'] else '❌ ندارد'}")
            self.stdout.write(f"• تسویه قبلی: {res['old_settled_until']} ⬅️ تسویه جدید: {res['new_settled_until']}")
            self.stdout.write("\n--- تراکنش‌های ایجاد شده ---")
            for t in res["transactions"]:
                self.stdout.write(
                    f"  #ID: {t['transaction_id']} | نوع: {t['type']} | مبلغ: {t['amount_tomans']:,} تومان | "
                    f"روش: {t['method']} | دوره: {t['period_name'] or '—'}"
                )
            self.stdout.write(f"• ثبت‌کننده: {res['supervisor']}\n")

            if res.get("discrepancy") and res["discrepancy"]["is_underpaid"]:
                disc = res["discrepancy"]
                diff_abs = abs(disc["diff_tomans"])
                self.stdout.write(self.style.WARNING(
                    f"⚠️  هشدار مغایرت مبلغ اجاره (FLAGGED DISCREPANCY):\n"
                    f"   • اجاره مصوب اتاق {disc['room_number']} برای دوره ({disc['period_name']}): {disc['expected_rent_tomans']:,} تومان\n"
                    f"   • مبلغ دریافتی ثبت‌شده بابت اجاره: {disc['paid_rent_tomans']:,} تومان\n"
                    f"   • کسری پرداختی: {diff_abs:,} تومان\n"
                    f"   • تسویه تا تاریخ {res['new_settled_until']} به صورت «علی‌الحساب» اعمال شد.\n"
                    f"   • سوال جهت بررسی: علت کسری {diff_abs:,} تومانی (تخفیف، سم‌پاشی، توافق مدیریت یا مانده بدهی) چیست؟\n"
                ))
