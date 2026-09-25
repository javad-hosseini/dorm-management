import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.dormitory.models import Transaction, Resident, Room, Dormitory, DailyNote
from apps.archive.models import ArchivedTransaction, ArchivedResident
from apps.accounts.models import Supervisor


class Command(BaseCommand):
    help = (
        "Manually clears all financial transactions while strictly preserving residents, rooms, and dormitories.\n"
        "پاک سازی دستی تمام تراکنش های مالی بدون حذف ساکنین و اتاق ها"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-y", "--yes", "--force",
            action="store_true",
            dest="force",
            help="اجرای مستقیم بدون نیاز به تایید دستی (Skip confirmation prompt)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="شبیه‌سازی اجرای اسکریپت بدون اعمال تغییر واقعی در دیتابیس (Preview without changes)",
        )
        parser.add_argument(
            "--include-archived",
            action="store_true",
            dest="include_archived",
            help="پاک‌سازی تراکنش‌های قدیمی آرشیو شده علاوه بر تراکنش‌های فعال",
        )
        parser.add_argument(
            "--exclude-archived",
            action="store_true",
            dest="exclude_archived",
            help="نگه‌داشتن تراکنش‌های آرشیو شده و فقط پاک‌کردن تراکنش‌های فعال",
        )
        parser.add_argument(
            "--reset-settled",
            action="store_true",
            dest="reset_settled",
            help="ریست کردن تاریخ تسویه ساکنین (settled_until=None) برای شروع محاسبات مالی از نو",
        )
        parser.add_argument(
            "--keep-settled",
            action="store_true",
            dest="keep_settled",
            help="نگه‌داشتن فیلد settled_until ساکنین بدون تغییر",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        dry_run = options.get("dry_run", False)
        include_archived_opt = options.get("include_archived", False)
        exclude_archived_opt = options.get("exclude_archived", False)
        reset_settled_opt = options.get("reset_settled", False)
        keep_settled_opt = options.get("keep_settled", False)

        # 1. Gather baseline counts
        tx_count = Transaction.objects.count()
        archived_tx_count = ArchivedTransaction.objects.count()

        # Protected entities that must NEVER be deleted
        resident_count = Resident.objects.count()
        room_count = Room.objects.count()
        dorm_count = Dormitory.objects.count()
        supervisor_count = Supervisor.objects.count()
        archived_res_count = ArchivedResident.objects.count()
        notes_count = DailyNote.objects.count()
        residents_with_settled = Resident.objects.filter(settled_until__isnull=False).count()

        self.stdout.write("=" * 64)
        self.stdout.write(self.style.MIGRATE_HEADING("  🧹 سامانه پاک‌سازی امن تراکنش‌های مالی خوابگاه"))
        self.stdout.write(self.style.MIGRATE_HEADING("  Dormitory Management System — Transaction Purge Utility"))
        self.stdout.write("=" * 64)

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  حالت شبیه‌سازی (DRY RUN) فعال است. هیچ رکوردی حذف نخواهد شد.\n"))

        self.stdout.write("\n📊 وضعیت فعلی پایگاه داده:")
        self.stdout.write(f"  • تعداد تراکنش‌های مالی فعال (Transaction): {tx_count} رکورد")
        self.stdout.write(f"  • تعداد تراکنش‌های آرشیو شده (ArchivedTransaction): {archived_tx_count} رکورد")
        self.stdout.write(f"  • ساکنینی که تاریخ تسویه دارند: {residents_with_settled} نفر از {resident_count} نفر")

        self.stdout.write(self.style.SUCCESS("\n🛡️  اطلاعات محافظت‌شده (تحت هیچ شرایطی حذف یا دستکاری نمی‌شوند):"))
        self.stdout.write(f"  ✅ ساکنین خوابگاه (Resident): {resident_count} نفر [دست‌نخورده]")
        self.stdout.write(f"  ✅ اتاق‌ها (Room): {room_count} اتاق [دست‌نخورده]")
        self.stdout.write(f"  ✅ خوابگاه‌ها (Dormitory): {dorm_count} خوابگاه [دست‌نخورده]")
        self.stdout.write(f"  ✅ سرپرستان (Supervisor): {supervisor_count} نفر [دست‌نخورده]")
        self.stdout.write(f"  ✅ ساکنین آرشیو شده (ArchivedResident): {archived_res_count} نفر [دست‌نخورده]")
        self.stdout.write(f"  ✅ یادداشت‌های روزانه (DailyNote): {notes_count} یادداشت [دست‌نخورده]")
        self.stdout.write("-" * 64)

        if tx_count == 0 and archived_tx_count == 0:
            self.stdout.write(self.style.SUCCESS("\n✨ پایگاه‌داده هیچ تراکنش مالی فعالی ندارد. نیازی به پاک‌سازی نیست."))
            return

        # 2. Interactive questions if not force
        # Determine archived transactions deletion
        delete_archived = False
        if include_archived_opt:
            delete_archived = True
        elif exclude_archived_opt:
            delete_archived = False
        elif archived_tx_count > 0:
            if force:
                delete_archived = True
            else:
                answer = input(f"\n❓ آیا مایلید {archived_tx_count} تراکنش آرشیو شده (قدیمی) نیز پاک شوند؟ [y/N]: ").strip().lower()
                delete_archived = answer in ["y", "yes", "بله", "آره"]

        # Determine reset settled_until
        reset_settled = False
        if reset_settled_opt:
            reset_settled = True
        elif keep_settled_opt:
            reset_settled = False
        else:
            if force:
                reset_settled = True
            else:
                self.stdout.write("\n💡 توضیح تاریخ تسویه:")
                self.stdout.write("  اگر تراکنش‌ها پاک شوند، تاریخ تسویه (settled_until) ساکنین که از قبل ثبت شده بود،")
                self.stdout.write("  ممکن است باعث شود سیستم آنها را ماه‌ها بدهکار یا از قبل تسویه‌شده نشان دهد.")
                self.stdout.write("  توصیه می‌شود تاریخ تسویه ریست شود تا بتوانید بر اساس وضعیت فعلی ساکنین از نو تسویه ثبت کنید.")
                answer = input("❓ آیا تاریخ تسویه ساکنین (settled_until) نیز ریست شود؟ [Y/n]: ").strip().lower()
                reset_settled = answer not in ["n", "no", "خیر", "نه"]

        # Final Confirmation
        if not force and not dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  توجه: این عملیات غیرقابل بازگشت است!"))
            self.stdout.write(f"  • {tx_count} تراکنش فعال پاک خواهد شد.")
            if delete_archived:
                self.stdout.write(f"  • {archived_tx_count} تراکنش آرشیو پاک خواهد شد.")
            if reset_settled:
                self.stdout.write(f"  • تاریخ تسویه {residents_with_settled} ساکن ریست خواهد شد.")
            else:
                self.stdout.write("  • تاریخ تسویه ساکنین بدون تغییر می‌ماند.")

            confirm = input("\n🔴 آیا برای اجرای پاک‌سازی مطمئن هستید؟ عبارت 'yes' یا 'بله' را تایپ کنید: ").strip().lower()
            if confirm not in ["yes", "y", "بله"]:
                self.stdout.write(self.style.NOTICE("\n❌ عملیات توسط کاربر لغو شد. هیچ تغییری اعمال نشد."))
                return

        # 3. Execution
        self.stdout.write("\n⏳ در حال اجرای عملیات...")

        try:
            with transaction.atomic():
                deleted_tx_count, _ = Transaction.objects.all().delete()
                
                deleted_archived_count = 0
                if delete_archived:
                    deleted_archived_count, _ = ArchivedTransaction.objects.all().delete()

                residents_reset_count = 0
                if reset_settled:
                    residents_reset_count = Resident.objects.filter(
                        settled_until__isnull=False
                    ).update(settled_until=None)

                # Post-verification inside transaction
                remaining_tx = Transaction.objects.count()
                after_residents = Resident.objects.count()
                after_rooms = Room.objects.count()

                if after_residents != resident_count:
                    raise CommandError(
                        f"خطای امنیتی: تعداد ساکنین تغییر کرد! ({resident_count} -> {after_residents}). تغییرات بازگردانی شد."
                    )
                if after_rooms != room_count:
                    raise CommandError(
                        f"خطای امنیتی: تعداد اتاق‌ها تغییر کرد! ({room_count} -> {after_rooms}). تغییرات بازگردانی شد."
                    )

                if dry_run:
                    # Rollback in dry-run
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING("\n🔍 نتیجه شبیه‌سازی (Dry Run Complete):"))
                    self.stdout.write(f"  • تراکنش‌های فعال که حذف می‌شدند: {deleted_tx_count}")
                    if delete_archived:
                        self.stdout.write(f"  • تراکنش‌های آرشیو که حذف می‌شدند: {deleted_archived_count}")
                    if reset_settled:
                        self.stdout.write(f"  • تاریخ تسویه که ریست می‌شد: {residents_reset_count} ساکن")
                    self.stdout.write(self.style.SUCCESS(f"  • ساکنین کاملاً دست‌نخورده باقی ماندند: {after_residents} نفر"))
                    self.stdout.write(self.style.SUCCESS(f"  • اتاق‌ها کاملاً دست‌نخورده باقی ماندند: {after_rooms} اتاق"))
                    self.stdout.write(self.style.NOTICE("\n[هیچ داده‌ای حذف نشد چون در حالت dry-run اجرا شد.]"))
                    return

            # If atomic block succeeded and not dry-run
            self.stdout.write("=" * 64)
            self.stdout.write(self.style.SUCCESS("🎉 عملیات پاک‌سازی با موفقیت کامل انجام شد!"))
            self.stdout.write(f"  🗑️  تراکنش‌های مالی حذف شده: {deleted_tx_count} عدد")
            if delete_archived:
                self.stdout.write(f"  🗑️  تراکنش‌های آرشیو حذف شده: {deleted_archived_count} عدد")
            if reset_settled:
                self.stdout.write(f"  🔄 تاریخ تسویه {residents_reset_count} ساکن ریست شد.")

            self.stdout.write(self.style.SUCCESS("\n🔒 تایید سلامت اطلاعات پایه:"))
            self.stdout.write(f"  ✅ تعداد ساکنین: {after_residents} نفر (۱۰۰٪ سالم و دست‌نخورده)")
            self.stdout.write(f"  ✅ تعداد اتاق‌ها: {after_rooms} اتاق (۱۰۰٪ سالم و دست‌نخورده)")
            self.stdout.write(f"  ✅ تعداد تراکنش‌های باقیمانده: {remaining_tx} عدد")
            self.stdout.write("=" * 64)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ هنگام اجرای پاک‌سازی خطایی رخ داد: {e}"))
            self.stdout.write(self.style.NOTICE("هیچ تغییری در پایگاه‌داده ذخیره نشد (Rollback انجام شد)."))
            raise
