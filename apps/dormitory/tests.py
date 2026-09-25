import jdatetime
import datetime
from datetime import timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident, Transaction, DailyNote
from apps.dormitory.queries import ReportQueries
from apps.dormitory.admin import RoomForm, TransactionForm, ResidentAdmin, DailyNoteAdmin
from django.contrib.admin.sites import AdminSite


class DormitoryCoreTests(TestCase):
    def setUp(self):
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه مرکزی",
            address="خیابان اصلی، پلاک ۱"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=101,
            capacity=4,
            monthly_rent=35_000_000  # 3.5 Million Tomans in Rials
        )

    def test_resident_debt_calculation_jalali(self):
        """Test is_in_debt accurately compares Jalali dates, not Gregorian"""
        today = jdatetime.date.today()

        # Resident settled until next month -> NOT in debt
        future_date = today + timedelta(days=30)
        resident_settled = Resident.objects.create(
            first_name="ساکن",
            last_name="خوش‌حساب",
            national_code="1111111111",
            phone_number="09121111111",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today - timedelta(days=60),
            settled_until=future_date,
            registered_by=self.supervisor
        )
        self.assertFalse(resident_settled.is_in_debt)

        # Resident settled in the past -> IN debt
        past_date = today - timedelta(days=10)
        resident_debt = Resident.objects.create(
            first_name="ساکن",
            last_name="بدهکار",
            national_code="2222222222",
            phone_number="09122222222",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today - timedelta(days=60),
            settled_until=past_date,
            registered_by=self.supervisor
        )
        self.assertTrue(resident_debt.is_in_debt)

        # Resident never settled -> IN debt
        resident_unsettled = Resident.objects.create(
            first_name="ساکن",
            last_name="بدون‌تسویه",
            national_code="3333333333",
            phone_number="09123333333",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today,
            settled_until=None,
            registered_by=self.supervisor
        )
        self.assertTrue(resident_unsettled.is_in_debt)

    def test_transaction_approval_logic(self):
        """CASH and BANK_TRANSFER require approval; CARD and ONLINE_GATEWAY do not"""
        today = jdatetime.date.today()
        resident = Resident.objects.create(
            first_name="رضا",
            last_name="احمدی",
            national_code="4444444444",
            phone_number="09124444444",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today,
            registered_by=self.supervisor
        )

        t_cash = Transaction(
            resident=resident,
            dormitory=self.dormitory,
            amount=25_000_000,
            transaction_type='RENT',
            payment_method='CASH',
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )
        self.assertTrue(t_cash.needs_approval)

        t_bank = Transaction(
            resident=resident,
            dormitory=self.dormitory,
            amount=25_000_000,
            transaction_type='RENT',
            payment_method='BANK_TRANSFER',
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )
        self.assertTrue(t_bank.needs_approval)

        t_card = Transaction(
            resident=resident,
            dormitory=self.dormitory,
            amount=25_000_000,
            transaction_type='RENT',
            payment_method='CARD',
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )
        self.assertFalse(t_card.needs_approval)

        t_online = Transaction(
            resident=resident,
            dormitory=self.dormitory,
            amount=25_000_000,
            transaction_type='RENT',
            payment_method='ONLINE_GATEWAY',
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )
        self.assertFalse(t_online.needs_approval)

    def test_transaction_currency_conversions(self):
        """Test conversion helpers between Rials, Tomans, and Million Tomans"""
        resident = Resident.objects.create(
            first_name="امیر",
            last_name="کریمی",
            national_code="5555555555",
            phone_number="09125555555",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        # 35,000,000 Rials = 3,500,000 Tomans = 3.5 Million Tomans
        t = Transaction.objects.create(
            resident=resident,
            dormitory=self.dormitory,
            amount=35_000_000,
            transaction_type='RENT',
            payment_method='CARD',
            is_approved=True,
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )
        self.assertEqual(t.amount_in_tomans, 3_500_000)
        self.assertEqual(t.amount_in_million_tomans, 3.5)

    def test_report_queries(self):
        """Ensure queries execute properly without any missing imports or crashes"""
        start = jdatetime.date.today() - timedelta(days=30)
        end = jdatetime.date.today() + timedelta(days=1)
        income = ReportQueries.get_total_income(start, end)
        self.assertGreaterEqual(income, 0)
        self.assertIsNotNone(ReportQueries.get_occupied_rooms())
        self.assertIsNotNone(ReportQueries.get_empty_rooms())
        self.assertIsNotNone(ReportQueries.get_residents_not_paid_recently(30))

    def test_jalali_calendar_arithmetic_and_period_naming(self):
        """Test Jalali month arithmetic, day clamping, and Persian period naming"""
        from apps.dormitory.jalali_utils import add_jalali_months, format_period_name

        # 1. Standard 1 month addition
        d1 = jdatetime.date(1405, 7, 1)
        self.assertEqual(add_jalali_months(d1, 1), jdatetime.date(1405, 8, 1))

        # 2. Clamping 31 days to 30 days (Shahrivar to Mehr)
        d_31 = jdatetime.date(1405, 6, 31)
        self.assertEqual(add_jalali_months(d_31, 1), jdatetime.date(1405, 7, 30))

        # 3. Crossing year boundary (Esfand to Farvardin)
        d_esfand = jdatetime.date(1405, 12, 15)
        self.assertEqual(add_jalali_months(d_esfand, 1), jdatetime.date(1406, 1, 15))

        # 4. Period naming for 1st of month: covers Mehr -> "اجاره مهر ماه ۱۴۰۵"
        p_name1 = format_period_name(jdatetime.date(1405, 7, 1), jdatetime.date(1405, 8, 1))
        self.assertEqual(p_name1, "اجاره مهر ماه ۱۴۰۵")

        # 5. Period naming for mid-month: e.g. 15th to 15th
        p_name2 = format_period_name(jdatetime.date(1405, 7, 15), jdatetime.date(1405, 8, 15))
        self.assertEqual(p_name2, "اجاره دوره ۱۵ مهر تا ۱۵ آبان ۱۴۰۵")

    def test_prepayment_settlement_and_daily_delay(self):
        """
        Verify real-world pre-payment scenario:
        - Resident pre-pays at start of period.
        - While period is active: settled to the day, remaining days countdown.
        - When period lapses: exact delay in days calculated.
        - Unpaid month explicitly named.
        - Debt is strictly monthly (NOT penalized daily).
        """
        today = jdatetime.date.today()

        # Resident settled 20 days into the future
        future_date = today + timedelta(days=20)
        res_settled = Resident.objects.create(
            first_name="سروش",
            last_name="صالحی",
            national_code="6666666666",
            phone_number="09126666666",
            dormitory=self.dormitory,
            room=self.room,  # rent = 3,500,000 Tomans
            entry_date=today - timedelta(days=10),
            settled_until=future_date,
            registered_by=self.supervisor
        )
        self.assertFalse(res_settled.is_in_debt)
        self.assertEqual(res_settled.overdue_days, 0)
        self.assertEqual(res_settled.days_until_due, 20)
        self.assertEqual(res_settled.total_debt_amount_tomans, 0)
        self.assertEqual(res_settled.unpaid_periods, [])
        self.assertEqual(res_settled.financial_status_summary["status"], "SETTLED")

        # Resident with 5 days delay
        # settled_until was 5 days ago
        past_date = today - timedelta(days=5)
        res_overdue = Resident.objects.create(
            first_name="مهدی",
            last_name="کاظمی",
            national_code="7777777777",
            phone_number="09127777777",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today - timedelta(days=35),
            settled_until=past_date,
            registered_by=self.supervisor
        )
        self.assertTrue(res_overdue.is_in_debt)
        self.assertEqual(res_overdue.overdue_days, 5)
        self.assertEqual(res_overdue.days_until_due, 0)
        # Total debt is exactly 1 month room rent = 3,500,000 Tomans (not daily penalized)
        self.assertEqual(res_overdue.total_debt_amount_tomans, 3_500_000)
        self.assertEqual(len(res_overdue.unpaid_periods), 1)
        self.assertIn("اجاره", res_overdue.unpaid_months_display)
        self.assertEqual(res_overdue.financial_status_summary["status"], "OVERDUE")
        self.assertEqual(res_overdue.financial_status_summary["overdue_days"], 5)

    def test_transaction_auto_advances_settled_until_on_approval(self):
        """
        Testing the automated workflow:
        1. Resident has settled_until = 1405/07/01.
        2. A CASH transaction is created with is_approved=False.
           -> settled_until does NOT change yet.
           -> period_name is pre-calculated ("اجاره مهر ماه ۱۴۰۵").
        3. Supervisor approves the transaction.
           -> settled_until advances automatically to 1405/08/01.
        """
        resident = Resident.objects.create(
            first_name="حسین",
            last_name="مرادی",
            national_code="8888888888",
            phone_number="09128888888",
            dormitory=self.dormitory,
            room=self.room,  # 35,000,000 Rials rent
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )

        # Step 1: Create unapproved CASH payment for 1 month
        t = Transaction.objects.create(
            resident=resident,
            dormitory=self.dormitory,
            amount=35_000_000,  # 1 month rent
            transaction_type='RENT',
            payment_method='CASH',
            is_approved=False,
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )

        resident.refresh_from_db()
        # Still not advanced because not approved yet
        self.assertEqual(resident.settled_until, jdatetime.date(1405, 7, 1))
        self.assertEqual(t.period_name, "اجاره مهر ماه ۱۴۰۵")
        self.assertEqual(t.period_start, jdatetime.date(1405, 7, 1))
        self.assertEqual(t.period_end, jdatetime.date(1405, 8, 1))

        # Step 2: Approve the payment
        t.is_approved = True
        t.save()

        resident.refresh_from_db()
        # Automatically advanced to 1405/08/01!
        self.assertEqual(resident.settled_until, jdatetime.date(1405, 8, 1))

    def test_pos_card_auto_approval_and_settlement(self):
        """CARD (POS) payment is auto-approved and advances settled_until immediately"""
        resident = Resident.objects.create(
            first_name="نوید",
            last_name="باقری",
            national_code="9999999999",
            phone_number="09129999999",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )

        t = Transaction.objects.create(
            resident=resident,
            dormitory=self.dormitory,
            amount=35_000_000,
            transaction_type='RENT',
            payment_method='CARD',
            is_approved=True,
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor
        )

        resident.refresh_from_db()
        self.assertEqual(resident.settled_until, jdatetime.date(1405, 8, 1))
        self.assertEqual(t.period_name, "اجاره مهر ماه ۱۴۰۵")


class AILoaderTests(TestCase):
    def setUp(self):
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه نوید",
            address="تهران"
        )
        self.room_101 = Room.objects.create(
            dormitory=self.dormitory,
            room_number=101,
            capacity=2,
            monthly_rent=30_000_000  # 3M Tomans
        )
        self.room_102 = Room.objects.create(
            dormitory=self.dormitory,
            room_number=102,
            capacity=2,
            monthly_rent=35_000_000
        )
        self.resident1 = Resident.objects.create(
            first_name="علی",
            last_name="حسینی",
            national_code="1000000001",
            phone_number="09120000001",
            dormitory=self.dormitory,
            room=self.room_101,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE
        )
        self.resident2 = Resident.objects.create(
            first_name="محمدرضا",
            last_name="اکبری",
            national_code="1000000002",
            phone_number="09120000002",
            dormitory=self.dormitory,
            room=self.room_102,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE
        )

    def test_persian_normalization(self):
        from apps.dormitory.services.ai_loader import normalize_persian_text
        self.assertEqual(normalize_persian_text("على كریمى"), "علی کریمی")
        self.assertEqual(normalize_persian_text("آقای رضا  محمدی‌پور"), "رضا محمدی پور")

    def test_resident_matching(self):
        from apps.dormitory.services.ai_loader import match_resident
        # Match with room and name
        res = match_resident("علی حسینی", room_number=101, dormitory=self.dormitory)
        self.assertEqual(res["status"], "EXACT")
        self.assertEqual(res["resident"], self.resident1)

        # Match with partial name across dorm
        res2 = match_resident("محمد رضا اکبری", dormitory=self.dormitory)
        self.assertEqual(res2["status"], "EXACT")
        self.assertEqual(res2["resident"], self.resident2)

    def test_preview_and_execute_rent_and_checkout(self):
        from apps.dormitory.services.ai_loader import preview_events, execute_events
        payload = {
            "report_date": "1405/07/05",
            "summary": "گزارش روزانه",
            "events": [
                {
                    "action": "RENT_PAYMENT",
                    "resident_name": "علی حسینی",
                    "room_number": 101,
                    "amount_tomans": 3000000,
                    "payment_date": "1405/07/05",
                    "payment_method": "CASH",
                    "description": "اجاره مهر ماه"
                },
                {
                    "action": "CHECK_OUT",
                    "resident_name": "محمدرضا اکبری",
                    "room_number": 102,
                    "exit_date": "1405/07/05"
                },
                {
                    "action": "MAINTENANCE_NOTE",
                    "title": "تعمیر مهتابی",
                    "room_number": 101,
                    "content": "مهتابی اتاق سوخته است"
                }
            ]
        }

        # Test preview
        preview = preview_events(payload, self.supervisor, self.dormitory)
        self.assertTrue(preview["success"])
        self.assertEqual(preview["ready_count"], 3)
        self.assertEqual(preview["error_count"], 0)

        # Test execution
        execution = execute_events(preview["events"], self.supervisor, self.dormitory)
        self.assertTrue(execution["success"])
        self.assertEqual(execution["created_transactions"], 1)
        self.assertEqual(execution["updated_residents"], 1)
        self.assertEqual(execution["created_notes"], 1)

        # Verify resident 1 settled_until advanced
        self.resident1.refresh_from_db()
        self.assertEqual(self.resident1.settled_until, jdatetime.date(1405, 8, 1))

        # Verify resident 2 checked out
        self.resident2.refresh_from_db()
        self.assertEqual(self.resident2.status, Resident.Status.LEFT)
        self.assertEqual(self.resident2.exit_date, jdatetime.date(1405, 7, 5))

    def test_ai_loader_view_get_and_post(self):
        from django.contrib.auth.models import User
        import json
        admin_user = User.objects.create_superuser(username='admin_test', password='password123', email='admin@test.com')
        self.client.login(username='admin_test', password='password123')

        # Test GET
        response = self.client.get('/admin/ai-loader/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ثبت هوشمند")

        # Test POST preview
        preview_payload = {
            "report_date": "1405/07/05",
            "events": [
                {
                    "action": "RENT_PAYMENT",
                    "resident_name": "علی حسینی",
                    "room_number": 101,
                    "amount_tomans": 3000000
                }
            ]
        }
        res_preview = self.client.post(
            '/admin/ai-loader/',
            data=json.dumps({"action": "preview", "payload": preview_payload}),
            content_type="application/json"
        )
        self.assertEqual(res_preview.status_code, 200)
        data = res_preview.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["ready_count"], 1)


class ClearTransactionsCommandTests(TestCase):
    def setUp(self):
        self.dormitory = Dormitory.objects.create(name="خوابگاه مرکزی", address="تهران")
        self.supervisor = Supervisor.objects.create(
            first_name="مدیر", last_name="خوابگاه", national_code="1234567899"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory, room_number=201, capacity=4, monthly_rent=30_000_000
        )
        self.resident = Resident.objects.create(
            first_name="سارا",
            last_name="رضایی",
            national_code="0987654321",
            phone_number="09129998877",
            room=self.room,
            dormitory=self.dormitory,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            monthly_payment_day=1,
            registered_by=self.supervisor,
        )
        self.transaction = Transaction.objects.create(
            resident=self.resident,
            dormitory=self.dormitory,
            amount=30_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.CARD,
            payment_date=jdatetime.datetime.now(),
            created_by=self.supervisor,
            is_approved=True,
        )

    def test_clear_transactions_command(self):
        from django.core.management import call_command
        from io import StringIO

        tx_count_before = Transaction.objects.count()
        self.assertEqual(tx_count_before, 1)
        res_count_before = Resident.objects.count()
        room_count_before = Room.objects.count()

        # 1. Test Dry Run
        out = StringIO()
        call_command("clear_transactions", "--dry-run", "--yes", stdout=out)
        self.assertIn("حالت شبیه‌سازی", out.getvalue())
        self.assertEqual(Transaction.objects.count(), tx_count_before)
        self.assertEqual(Resident.objects.count(), res_count_before)

        # 2. Test Execution with --yes
        out2 = StringIO()
        call_command("clear_transactions", "--yes", "--reset-settled", stdout=out2)
        self.assertIn("عملیات پاک‌سازی با موفقیت کامل انجام شد", out2.getvalue())
        self.assertEqual(Transaction.objects.count(), 0)
        # Verify residents and rooms are strictly preserved
        self.assertEqual(Resident.objects.count(), res_count_before)

class IncompleteProfileTests(TestCase):
    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from apps.dormitory.admin import ResidentAdmin

        self.site = AdminSite()
        self.admin = ResidentAdmin(Resident, self.site)
        self.dormitory = Dormitory.objects.create(name="خوابگاه آزمایشی", address="خیابان آزادی")
        self.supervisor = Supervisor.objects.create(
            first_name="مدیر", last_name="تست", national_code="9876543210"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory, room_number=301, capacity=4, monthly_rent=30_000_000
        )

    def test_incomplete_profile_properties(self):
        # 1. Missing both national code and parent phone (and has id image)
        res_both = Resident.objects.create(
            first_name="ساکن", last_name="بدون‌مدارک",
            father_name="پدر",
            phone_number="09120000001",
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_both.has_incomplete_profile)
        self.assertIn("کد ملی", res_both.missing_profile_fields)
        self.assertIn("شماره تماس والدین", res_both.missing_profile_fields)
        self.assertEqual(res_both.profile_completion_status, "MISSING_BOTH")

        # 2. Missing parent phone only
        res_phone = Resident.objects.create(
            first_name="ساکن", last_name="با‌کدملی",
            father_name="پدر",
            national_code="1234567891",
            phone_number="09120000002",
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_phone.has_incomplete_profile)
        self.assertEqual(res_phone.missing_profile_fields, ["شماره تماس والدین"])
        self.assertEqual(res_phone.profile_completion_status, "MISSING_PARENT_PHONE")

        # 3. Missing national code only
        res_nat = Resident.objects.create(
            first_name="ساکن", last_name="با‌والدین",
            father_name="پدر",
            phone_number="09120000003",
            parent_phone_number="09129990001",
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_nat.has_incomplete_profile)
        self.assertEqual(res_nat.missing_profile_fields, ["کد ملی"])
        self.assertEqual(res_nat.profile_completion_status, "MISSING_NATIONAL_CODE")

        # 4. Complete (has all fields, lease, and ID card photo)
        res_complete = Resident.objects.create(
            first_name="ساکن", last_name="کامل",
            father_name="پدر",
            national_code="1234567892",
            phone_number="09120000004",
            parent_phone_number="09129990002",
            has_lease=True,
            has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertFalse(res_complete.has_incomplete_profile)
        self.assertEqual(res_complete.missing_profile_fields, [])
        self.assertEqual(res_complete.profile_completion_status, "COMPLETE")

        # 5. Missing lease only
        res_lease = Resident.objects.create(
            first_name="ساکن", last_name="بدون‌اجاره‌نامه",
            father_name="پدر",
            national_code="1234567893",
            phone_number="09120000005",
            parent_phone_number="09129990003",
            has_lease=False,
            has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_lease.has_incomplete_profile)
        self.assertEqual(res_lease.missing_profile_fields, ["اجاره‌نامه"])
        self.assertEqual(res_lease.profile_completion_status, "MISSING_LEASE")
        badge = self.admin.document_status_badge(res_lease)
        self.assertIn("فاقد اجاره‌نامه", badge)

        # 6. Missing deposit does NOT cause incomplete profile (only for Jazzmin display)
        res_no_dep = Resident.objects.create(
            first_name="ساکن", last_name="بدون‌ودیعه",
            father_name="پدر",
            national_code="1234567894",
            phone_number="09120000006",
            parent_phone_number="09129990004",
            has_lease=True,
            has_deposit=False,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertFalse(res_no_dep.has_incomplete_profile)
        self.assertEqual(res_no_dep.missing_profile_fields, [])
        self.assertEqual(res_no_dep.profile_completion_status, "COMPLETE")
        dep_badge = self.admin.deposit_status_badge(res_no_dep)
        self.assertIn("فاقد ودیعه", dep_badge)
        has_dep_badge = self.admin.deposit_status_badge(res_lease)
        self.assertIn("دارد", has_dep_badge)

        # 7. Missing father name only
        res_father = Resident.objects.create(
            first_name="ساکن", last_name="بدون‌نام‌پدر",
            father_name=None,
            national_code="1234567895",
            phone_number="09120000007",
            parent_phone_number="09129990005",
            has_lease=True,
            has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_father.has_incomplete_profile)
        self.assertEqual(res_father.missing_profile_fields, ["نام پدر"])
        self.assertEqual(res_father.profile_completion_status, "MISSING_FATHER_NAME")
        badge_father = self.admin.document_status_badge(res_father)
        self.assertIn("فاقد نام پدر", badge_father)

        # 8. Missing ID card image only
        res_id_img = Resident.objects.create(
            first_name="ساکن", last_name="بدون‌عکس‌مدارک",
            father_name="پدر",
            national_code="1234567896",
            phone_number="09120000008",
            parent_phone_number="09129990006",
            has_lease=True,
            has_deposit=True,
            id_card_image=None,
            id_card_image_2=None,
            id_card_image_3=None,
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertTrue(res_id_img.has_incomplete_profile)
        self.assertEqual(res_id_img.missing_profile_fields, ["عکس مدرک شناسایی"])
        self.assertEqual(res_id_img.profile_completion_status, "MISSING_ID_IMAGE")
        badge_id_img = self.admin.document_status_badge(res_id_img)
        self.assertIn("فاقد عکس مدارک", badge_id_img)
        self.assertIn("بدون عکس", self.admin.id_documents_badge(res_id_img))

    def test_placeholder_normalization_to_none(self):
        """Test that placeholder values like 'ندارد', '-', 'null', '0' normalize to None"""
        placeholders = ["ندارد", "-", "null", "None", "", "0", "0000000000", "نامشخص"]
        for i, val in enumerate(placeholders):
            res = Resident.objects.create(
                first_name=f"تست_{i}", last_name="پلیس‌هولدر",
                national_code=val,
                parent_phone_number=val,
                phone_number=f"091900000{i:02d}",
                dormitory=self.dormitory, room=self.room,
                entry_date=jdatetime.date(1405, 1, 1),
                registered_by=self.supervisor
            )
            res.refresh_from_db()
            self.assertIsNone(res.national_code, f"Failed for placeholder: {val}")
            self.assertIsNone(res.parent_phone_number, f"Failed for placeholder: {val}")
            self.assertTrue(res.has_incomplete_profile)

    def test_persian_digits_normalization(self):
        """Test that Persian digits are converted to English digits on save"""
        res = Resident.objects.create(
            first_name="ساکن", last_name="اعدادفارسی",
            father_name="پدر",
            national_code="۰۱۲۳۴۵۶۷۸۹",
            phone_number="۰۹۱۲۱۱۱۲۲۳۳",
            parent_phone_number="۰۹۱۸۴۴۴۵۵۶۶",
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        res.refresh_from_db()
        self.assertEqual(res.national_code, "0123456789")
        self.assertEqual(res.phone_number, "09121112233")
        self.assertEqual(res.parent_phone_number, "09184445566")
        self.assertFalse(res.has_incomplete_profile)

    def test_multiple_residents_with_none_national_code_allowed(self):
        """Multiple residents without national code must not violate unique constraint"""
        res1 = Resident.objects.create(
            first_name="علی", last_name="بدون‌کد۱",
            national_code=None, phone_number="09110000001",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        res2 = Resident.objects.create(
            first_name="حسن", last_name="بدون‌کد۲",
            national_code="ندارد", phone_number="09110000002",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        res3 = Resident.objects.create(
            first_name="حسین", last_name="بدون‌کد۳",
            national_code="", phone_number="09110000003",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            registered_by=self.supervisor
        )
        self.assertIsNone(res1.national_code)
        self.assertIsNone(res2.national_code)
        self.assertIsNone(res3.national_code)
        self.assertEqual(Resident.objects.filter(national_code__isnull=True).count(), 3)


class ResidentExportTests(TestCase):
    def setUp(self):
        from django.test import RequestFactory
        from django.contrib.admin.sites import AdminSite
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.dormitory = Dormitory.objects.create(name="خوابگاه نوید", address="خیابان انقلاب")
        self.supervisor = Supervisor.objects.create(
            first_name="جواد", last_name="حسینی", national_code="1112223334"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory, room_number=102, capacity=4, monthly_rent=30_000_000
        )
        self.resident = Resident.objects.create(
            first_name="علی",
            last_name="حسینی",
            national_code="0012345678",
            phone_number="09121234567",
            parent_phone_number="09129876543",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1403, 7, 1),
            settled_until=jdatetime.date(1403, 8, 1),
            monthly_payment_day=1,
            occupation="STUDENT",
            status=Resident.Status.ACTIVE,
            registered_by=self.supervisor,
        )

    def test_get_export_dict_and_text(self):
        d = self.resident.get_export_dict()
        self.assertEqual(d["full_name"], "علی حسینی")
        self.assertEqual(d["national_code"], "0012345678")
        self.assertEqual(d["phone_number"], "09121234567")
        self.assertEqual(d["parent_phone_number"], "09129876543")
        self.assertEqual(d["room_number"], "102")
        self.assertEqual(d["occupation"], "دانشجو")
        self.assertEqual(d["dormitory"], "خوابگاه نوید")

        text = self.resident.get_export_text()
        self.assertIn("علی حسینی", text)
        self.assertIn("0012345678", text)
        self.assertIn("09121234567", text)
        self.assertIn("09129876543", text)
        self.assertIn("شماره اتاق: 102", text)
        self.assertIn("دانشجو", text)
        self.assertIn("خوابگاه نوید", text)
        # Excludes payment transactions
        self.assertNotIn("تراکنش", text)
        self.assertNotIn("شماره پیگیری", text)

    def test_admin_copy_profile_action(self):
        from apps.dormitory.admin import ResidentAdmin
        admin_obj = ResidentAdmin(Resident, self.site)
        html_out = admin_obj.copy_profile_action(self.resident)
        self.assertIn("copyResidentClipboard(this)", html_out)
        self.assertIn("📋 کپی مشخصات", html_out)
        self.assertIn("علی حسینی", html_out)

    def test_admin_export_selected_to_clipboard(self):
        from apps.dormitory.admin import ResidentAdmin
        admin_obj = ResidentAdmin(Resident, self.site)
        request = self.factory.get('/admin/dormitory/resident/')
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()

        qs = Resident.objects.filter(id=self.resident.id)
        response = admin_obj.export_selected_to_clipboard(request, qs)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("علی حسینی", content)
        self.assertIn("0012345678", content)

    def test_admin_export_selected_to_csv(self):
        from apps.dormitory.admin import ResidentAdmin
        admin_obj = ResidentAdmin(Resident, self.site)
        request = self.factory.get('/admin/dormitory/resident/')

        qs = Resident.objects.filter(id=self.resident.id)
        response = admin_obj.export_selected_to_csv(request, qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8-sig')
        content = response.content.decode('utf-8-sig')
        self.assertIn("نام و نام خانوادگی", content)
        self.assertIn("علی حسینی", content)
        self.assertIn("0012345678", content)

class ForeignResidentTests(TestCase):
    def setUp(self):
        from apps.accounts.models import Supervisor
        from django.contrib.admin.sites import AdminSite
        from apps.dormitory.admin import ResidentAdmin

        self.site = AdminSite()
        self.admin = ResidentAdmin(Resident, self.site)
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه بین‌الملل",
            address="خیابان انقلاب"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=305,
            capacity=2,
            monthly_rent=40_000_000
        )

    def test_create_foreign_resident_with_passport(self):
        """Foreign resident with alphanumeric passport is created and uppercased"""
        res = Resident.objects.create(
            first_name="جان",
            last_name="دو",
            father_name="ویلیام",
            is_foreign=True,
            national_code="p98765432a",
            phone_number="09129998877",
            parent_phone_number="09129998876",
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        self.assertTrue(res.is_foreign)
        # Verify letters are converted to uppercase
        self.assertEqual(res.national_code, "P98765432A")
        self.assertEqual(res.identity_title, "شماره پاسپورت / کد فراگیر")
        self.assertEqual(res.identity_display, "P98765432A (اتباع)")
        self.assertFalse(res.has_incomplete_profile)
        self.assertEqual(res.profile_completion_status, "COMPLETE")

    def test_foreign_resident_missing_documents(self):
        """Missing passport is identified properly in missing_profile_fields and profile_completion_status"""
        res = Resident.objects.create(
            first_name="الکس",
            last_name="اسمیت",
            father_name="جان",
            is_foreign=True,
            national_code=None,
            phone_number="09129991122",
            parent_phone_number=None,
            has_lease=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        self.assertTrue(res.has_incomplete_profile)
        self.assertEqual(res.profile_completion_status, "MISSING_BOTH")
        self.assertIn("شماره پاسپورت یا کد فراگیر", res.missing_profile_fields)

        # Admin badge handles MISSING_BOTH for foreign resident
        badge = self.admin.document_status_badge(res)
        self.assertIn("فاقد پاسپورت و والدین", badge)

    def test_foreign_resident_admin_displays(self):
        """Admin national_code_display renders the foreign badge"""
        res = Resident.objects.create(
            first_name="سارا",
            last_name="کانر",
            is_foreign=True,
            national_code="OA1234567",
            phone_number="09125554433",
            parent_phone_number="09125554434",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        display_html = self.admin.national_code_display(res)
        self.assertIn("OA1234567", display_html)
        self.assertIn("اتباع", display_html)

    def test_foreign_resident_export_text(self):
        """Export text uses passport title for foreign resident"""
        res = Resident.objects.create(
            first_name="مایکل",
            last_name="براون",
            is_foreign=True,
            national_code="N7654321",
            phone_number="09127778899",
            parent_phone_number="09127778898",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        text = res.get_export_text()
        self.assertIn("شماره پاسپورت/فراگیر (اتباع)", text)
        self.assertIn("N7654321", text)


class DepositAndLeaseTests(TestCase):
    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from apps.dormitory.admin import ResidentAdmin, IncompleteProfileFilter
        from apps.accounts.models import Supervisor

        self.site = AdminSite()
        self.admin = ResidentAdmin(Resident, self.site)
        self.supervisor = Supervisor.objects.create(
            first_name="مدیر",
            last_name="سیستم",
            national_code="0011223344"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه سپهر",
            address="خیابان ولیعصر"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=105,
            capacity=3,
            monthly_rent=25_000_000
        )

    def test_deposit_and_lease_defaults(self):
        """Newly created resident defaults to has_deposit=False and has_lease=False"""
        res = Resident.objects.create(
            first_name="مهدی",
            last_name="کریمی",
            father_name="پدر",
            national_code="0019876543",
            phone_number="09121110001",
            parent_phone_number="09121110002",
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        self.assertFalse(res.has_deposit)
        self.assertFalse(res.has_lease)
        # Because has_lease is False, resident profile is incomplete
        self.assertTrue(res.has_incomplete_profile)
        self.assertIn("اجاره‌نامه", res.missing_profile_fields)
        self.assertEqual(res.profile_completion_status, "MISSING_LEASE")

    def test_missing_deposit_alone_does_not_trigger_deficiency_alert(self):
        """Lack of deposit is NOT a document deficiency; it only shows in admin"""
        res = Resident.objects.create(
            first_name="رضا",
            last_name="صادقی",
            father_name="پدر",
            national_code="0029876543",
            phone_number="09121110003",
            parent_phone_number="09121110004",
            has_lease=True,
            has_deposit=False,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        self.assertFalse(res.has_incomplete_profile)
        self.assertEqual(res.missing_profile_fields, [])
        self.assertEqual(res.profile_completion_status, "COMPLETE")
        # In admin list, deposit badge highlights missing deposit
        dep_badge = self.admin.deposit_status_badge(res)
        self.assertIn("فاقد ودیعه", dep_badge)
        doc_badge = self.admin.document_status_badge(res)
        self.assertIn("کامل", doc_badge)

    def test_deposit_badge_display(self):
        """deposit_status_badge shows green when has_deposit=True and red badge when False"""
        res_with = Resident.objects.create(
            first_name="امیر",
            last_name="حیدری",
            father_name="پدر",
            national_code="0039876543",
            phone_number="09121110005",
            has_deposit=True,
            has_lease=True,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        res_without = Resident.objects.create(
            first_name="وحید",
            last_name="نادری",
            father_name="پدر",
            national_code="0049876543",
            phone_number="09121110006",
            has_deposit=False,
            has_lease=True,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        self.assertIn("دارد", self.admin.deposit_status_badge(res_with))
        self.assertIn("فاقد ودیعه", self.admin.deposit_status_badge(res_without))

    def test_document_status_badge_for_missing_lease(self):
        """document_status_badge displays missing lease warning"""
        res = Resident.objects.create(
            first_name="سعید",
            last_name="قاسمی",
            father_name="پدر",
            national_code="0059876543",
            phone_number="09121110007",
            parent_phone_number="09121110008",
            has_lease=False,
            has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        badge = self.admin.document_status_badge(res)
        self.assertIn("فاقد اجاره‌نامه", badge)

    def test_admin_incomplete_profile_filter_missing_lease(self):
        """IncompleteProfileFilter properly filters residents missing a lease"""
        from apps.dormitory.admin import IncompleteProfileFilter
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.get('/admin/dormitory/resident/')

        # 1. Complete resident
        r_complete = Resident.objects.create(
            first_name="شخص", last_name="کامل",
            father_name="احمد",
            national_code="0069876543", phone_number="09121110009",
            parent_phone_number="09121110010", has_lease=True, has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date.today(), registered_by=self.supervisor
        )
        # 2. Resident missing lease only
        r_no_lease = Resident.objects.create(
            first_name="شخص", last_name="بدون‌اجاره",
            father_name="احمد",
            national_code="0079876543", phone_number="09121110011",
            parent_phone_number="09121110012", has_lease=False, has_deposit=True,
            id_card_image="id_cards/sample.jpg",
            dormitory=self.dormitory, room=self.room,
            entry_date=jdatetime.date.today(), registered_by=self.supervisor
        )

        qs = Resident.objects.filter(id__in=[r_complete.id, r_no_lease.id])

        # Filter by missing_lease
        f_lease = IncompleteProfileFilter(req, {'profile_status': ['missing_lease']}, Resident, self.admin)
        filtered_lease = f_lease.queryset(req, qs)
        self.assertIn(r_no_lease, filtered_lease)
        self.assertNotIn(r_complete, filtered_lease)

        # Filter by incomplete
        f_inc = IncompleteProfileFilter(req, {'profile_status': ['incomplete']}, Resident, self.admin)
        filtered_inc = f_inc.queryset(req, qs)
        self.assertIn(r_no_lease, filtered_inc)
        self.assertNotIn(r_complete, filtered_inc)

        # Filter by complete
        f_comp = IncompleteProfileFilter(req, {'profile_status': ['complete']}, Resident, self.admin)
        filtered_comp = f_comp.queryset(req, qs)
        self.assertIn(r_complete, filtered_comp)
        self.assertNotIn(r_no_lease, filtered_comp)

    def test_archive_preserves_has_deposit_and_has_lease(self):
        """Archiving a LEFT resident copies has_deposit and has_lease to ArchivedResident"""
        from apps.archive.models import ArchivedResident
        from django.test import RequestFactory

        res_left = Resident.objects.create(
            first_name="بهرام",
            last_name="افشاری",
            father_name="پدر",
            national_code="0089876543",
            phone_number="09121110013",
            has_deposit=True,
            has_lease=True,
            status=Resident.Status.LEFT,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            exit_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        rf = RequestFactory()
        req = rf.get('/')
        req.user = self.supervisor
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        self.admin.archive_left_residents(req, Resident.objects.filter(id=res_left.id))

        archived = ArchivedResident.objects.filter(original_id=res_left.id).first()
        self.assertIsNotNone(archived)
        self.assertTrue(archived.has_deposit)
        self.assertTrue(archived.has_lease)

    def test_dashboard_serialization_includes_deposit_and_lease(self):
        """Dashboard get_admin_dashboard_data serializes deposit, lease, and counts missing lease in incomplete_residents"""
        from apps.dashboard.views import get_admin_dashboard_data

        res = Resident.objects.create(
            first_name="سامان",
            last_name="مقدم",
            father_name="پدر",
            national_code="0099876543",
            phone_number="09121110014",
            parent_phone_number="09121110015",
            has_deposit=False,
            has_lease=False,
            status=Resident.Status.ACTIVE,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        data = get_admin_dashboard_data()
        serialized = next((r for r in data["residents"] if r["id"] == res.id), None)
        self.assertIsNotNone(serialized)
        self.assertFalse(serialized["has_deposit"])
        self.assertFalse(serialized["has_lease"])
        self.assertTrue(serialized["has_incomplete_profile"])
        self.assertIn("اجاره‌نامه", serialized["missing_profile_fields"])
        self.assertIn("has_id_card_image", serialized)
        self.assertIn("id_images_count", serialized)
        self.assertIn("settled_until_display", serialized)
        self.assertIn("next_due_date_display", serialized)
        self.assertIn("due_status_display", serialized)
        self.assertGreaterEqual(data["stats"]["incomplete_residents"], 1)

    def test_settlement_and_next_due_date_properties(self):
        """Test settled_until_display, next_due_date, and due_status_display in settled and overdue states"""
        today = jdatetime.date.today()
        # 1. Settled resident (settled 10 days in future)
        res_settled = Resident.objects.create(
            first_name="کیوان",
            last_name="راد",
            father_name="پدر",
            national_code="0099876544",
            phone_number="09121110016",
            parent_phone_number="09121110017",
            has_deposit=True,
            has_lease=True,
            status=Resident.Status.ACTIVE,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today - jdatetime.timedelta(days=20),
            settled_until=today + jdatetime.timedelta(days=10),
            registered_by=self.supervisor
        )
        self.assertEqual(res_settled.next_due_date, res_settled.settled_until)
        self.assertEqual(res_settled.settled_until_display, res_settled.settled_until.strftime('%Y/%m/%d'))
        self.assertEqual(res_settled.next_due_date_display, res_settled.settled_until.strftime('%Y/%m/%d'))
        self.assertIn("10 روز مانده تا سررسید", res_settled.due_status_display)
        self.assertFalse(res_settled.is_in_debt)

        # 2. Overdue resident (settled_until 5 days in the past)
        res_overdue = Resident.objects.create(
            first_name="نوید",
            last_name="طاهری",
            father_name="پدر",
            national_code="0099876545",
            phone_number="09121110018",
            parent_phone_number="09121110019",
            has_deposit=True,
            has_lease=True,
            status=Resident.Status.ACTIVE,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=today - jdatetime.timedelta(days=35),
            settled_until=today - jdatetime.timedelta(days=5),
            registered_by=self.supervisor
        )
        self.assertEqual(res_overdue.next_due_date, res_overdue.settled_until)
        self.assertTrue(res_overdue.is_in_debt)
        self.assertEqual(res_overdue.overdue_days, 5)
        self.assertIn("5 روز تاخیر", res_overdue.due_status_display)

        # 3. Export dict & text include settlement & due date
        exp = res_settled.get_export_dict()
        self.assertIn("next_due_date_display", exp)
        self.assertIn("due_status_display", exp)
        self.assertIn("settled_until_display", exp)
        txt = res_settled.get_export_text()
        self.assertIn("سررسید موعد", txt)
        self.assertIn("تسویه تا", txt)


from django.test import override_settings
import tempfile


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class IDCardImageAndCompressionTests(TestCase):
    """Test identity document photos upload, auto-compression under 1MB, 3-photo limit, and deficiency alerts"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = ResidentAdmin(Resident, self.site)
        self.supervisor = Supervisor.objects.create(
            first_name="مدیر",
            last_name="سامانه",
            national_code="0011223344"
        )
        self.dormitory = Dormitory.objects.create(name="خوابگاه تست مدارک")
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=501,
            capacity=3,
            monthly_rent=35_000_000
        )

    def _create_dummy_image_file(self, filename="doc.jpg", size=(800, 600), color=(100, 150, 200)):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        buf = io.BytesIO()
        img = Image.new("RGB", size, color=color)
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return SimpleUploadedFile(filename, buf.read(), content_type="image/jpeg")

    def test_compress_image_utility_reduces_size_and_dimensions(self):
        """compress_image resizes dimensions to max 1920 and enforces target byte size"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.dormitory.image_utils import compress_image

        # Create a large image 2400x1800
        buf = io.BytesIO()
        img = Image.new("RGB", (2400, 1800), color=(200, 100, 50))
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        uploaded = SimpleUploadedFile("large_card.jpg", buf.read(), content_type="image/jpeg")

        # Compress to max 80KB to verify strict target byte budget and dimension downscaling
        compressed = compress_image(uploaded, max_size_bytes=80 * 1024, max_dimension=1200)
        self.assertLessEqual(compressed.size, 80 * 1024)

        # Verify dimensions were downscaled <= 1200
        comp_img = Image.open(compressed)
        self.assertLessEqual(max(comp_img.size), 1200)

    def test_resident_save_auto_compresses_uploaded_photos(self):
        """Resident.save() compresses uploaded files to ensure they never exceed 1 MB"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Create large uploaded image file
        buf = io.BytesIO()
        img = Image.new("RGB", (2200, 1600), color=(50, 120, 220))
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        uploaded_file = SimpleUploadedFile("national_card_front.jpg", buf.read(), content_type="image/jpeg")

        res = Resident.objects.create(
            first_name="سهراب",
            last_name="سپهری",
            father_name="میرزا",
            national_code="0019988776",
            phone_number="09121113344",
            parent_phone_number="09121113355",
            has_lease=True,
            has_deposit=True,
            id_card_image=uploaded_file,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        res.refresh_from_db()

        self.assertTrue(res.id_card_image)
        # Check size is within 1 MB (1,048,576 bytes)
        self.assertLessEqual(res.id_card_image.size, 1024 * 1024)
        self.assertTrue(res.has_id_card_image)
        self.assertEqual(res.uploaded_id_images_count, 1)

    def test_resident_supports_up_to_three_id_photos(self):
        """Resident supports up to 3 separate ID document photos"""
        img1 = self._create_dummy_image_file("card_front.jpg", color=(10, 20, 30))
        img2 = self._create_dummy_image_file("card_back.jpg", color=(40, 50, 60))
        img3 = self._create_dummy_image_file("passport_page.jpg", color=(70, 80, 90))

        res = Resident.objects.create(
            first_name="فرهاد",
            last_name="مهراد",
            father_name="رضا",
            national_code="0029988776",
            phone_number="09121113366",
            parent_phone_number="09121113377",
            has_lease=True,
            has_deposit=True,
            id_card_image=img1,
            id_card_image_2=img2,
            id_card_image_3=img3,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        res.refresh_from_db()

        self.assertTrue(res.has_id_card_image)
        self.assertEqual(res.uploaded_id_images_count, 3)
        self.assertEqual(len(res.id_cards_images_list), 3)

        # Admin badge
        badge = self.admin.id_documents_badge(res)
        self.assertIn("3 تصویر", badge)

        # Export text
        export_text = res.get_export_text()
        self.assertIn("📸 عکس مدارک شناسایی: 3 تصویر", export_text)

    def test_missing_id_image_triggers_deficiency_alert(self):
        """Absence of ID photos triggers document deficiency alert like national code"""
        res = Resident.objects.create(
            first_name="نیما",
            last_name="یوشیج",
            father_name="ابراهیم",
            national_code="0039988776",
            phone_number="09121113388",
            parent_phone_number="09121113399",
            has_lease=True,
            has_deposit=True,
            id_card_image=None,
            id_card_image_2=None,
            id_card_image_3=None,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        self.assertFalse(res.has_id_card_image)
        self.assertEqual(res.uploaded_id_images_count, 0)
        self.assertTrue(res.has_incomplete_profile)
        self.assertIn("عکس مدرک شناسایی", res.missing_profile_fields)
        self.assertEqual(res.profile_completion_status, "MISSING_ID_IMAGE")

        # Admin badges
        doc_badge = self.admin.document_status_badge(res)
        self.assertIn("فاقد عکس مدارک", doc_badge)
        img_badge = self.admin.id_documents_badge(res)
        self.assertIn("بدون عکس", img_badge)

        # Export text shows missing alert
        export_text = res.get_export_text()
        self.assertIn("📸 عکس مدارک شناسایی: ⚠️ ندارد (کسری مدرک)", export_text)

    def test_admin_change_view_dispatches_missing_image_warning(self):
        """Opening a resident without ID image in admin change view generates a warning message"""
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.auth.models import User

        admin_user = User.objects.create_superuser('test_admin_user', 'admin@example.com', 'pass123')

        res = Resident.objects.create(
            first_name="پروین",
            last_name="اعتصامی",
            father_name="یوسف",
            national_code="0049988776",
            phone_number="09121114400",
            parent_phone_number="09121114411",
            has_lease=True,
            has_deposit=True,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        rf = RequestFactory()
        req = rf.get(f'/admin/dormitory/resident/{res.id}/change/')
        req.user = admin_user
        setattr(req, 'session', {})
        messages_storage = FallbackStorage(req)
        setattr(req, '_messages', messages_storage)

        self.admin.change_view(req, str(res.id))
        all_msgs = [str(m.message) for m in messages_storage]
        self.assertTrue(any("تصویر مدارک شناسایی" in m for m in all_msgs))

    def test_admin_filter_by_missing_id_image(self):
        """IncompleteProfileFilter filters residents by missing_id_image"""
        from apps.dormitory.admin import IncompleteProfileFilter
        from django.test import RequestFactory

        img = self._create_dummy_image_file("id_front.jpg")
        r_with_img = Resident.objects.create(
            first_name="ساکن",
            last_name="با‌عکس",
            father_name="پدر",
            national_code="0059988776",
            phone_number="09121114422",
            parent_phone_number="09121114433",
            has_lease=True,
            id_card_image=img,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )
        r_no_img = Resident.objects.create(
            first_name="ساکن",
            last_name="بدون‌عکس",
            father_name="پدر",
            national_code="0069988776",
            phone_number="09121114444",
            parent_phone_number="09121114455",
            has_lease=True,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        rf = RequestFactory()
        req = rf.get('/admin/dormitory/resident/')
        qs = Resident.objects.filter(id__in=[r_with_img.id, r_no_img.id])

        f = IncompleteProfileFilter(req, {'profile_status': ['missing_id_image']}, Resident, self.admin)
        filtered = f.queryset(req, qs)
        self.assertIn(r_no_img, filtered)
        self.assertNotIn(r_with_img, filtered)

    def test_archiving_resident_preserves_all_three_id_images(self):
        """Archiving a resident copies all 3 ID document images to ArchivedResident"""
        from apps.archive.models import ArchivedResident
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage

        img1 = self._create_dummy_image_file("a1.jpg")
        img2 = self._create_dummy_image_file("a2.jpg")
        img3 = self._create_dummy_image_file("a3.jpg")

        res_left = Resident.objects.create(
            first_name="صادق",
            last_name="هدایت",
            father_name="هدایت‌قلی",
            national_code="0079988776",
            phone_number="09121114466",
            parent_phone_number="09121114477",
            has_deposit=True,
            has_lease=True,
            id_card_image=img1,
            id_card_image_2=img2,
            id_card_image_3=img3,
            status=Resident.Status.LEFT,
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date.today(),
            exit_date=jdatetime.date.today(),
            registered_by=self.supervisor
        )

        rf = RequestFactory()
        req = rf.get('/')
        req.user = self.supervisor
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        self.admin.archive_left_residents(req, Resident.objects.filter(id=res_left.id))

        archived = ArchivedResident.objects.filter(original_id=res_left.id).first()
        self.assertIsNotNone(archived)
        self.assertTrue(archived.id_card_image)
        self.assertTrue(archived.id_card_image_2)
        self.assertTrue(archived.id_card_image_3)


class PersianJalaliDatepickerAndDefaultDateTests(TestCase):
    """
    Test Persian Jalali datepicker integration, default yesterday date pre-fill
    for DailyNote and Resident add forms, and date formatting compatibility.
    """

    def setUp(self):
        self.site = AdminSite()
        self.resident_admin = ResidentAdmin(Resident, self.site)
        self.dailynote_admin = DailyNoteAdmin(DailyNote, self.site)
        self.yesterday = jdatetime.date.today() - datetime.timedelta(days=1)
        self.rf = RequestFactory()
        self.user = User.objects.create_superuser('admin_tester', 'tester@example.com', 'pass123')

    def test_dailynote_model_default_date_is_yesterday(self):
        """DailyNote model instances default date to yesterday's Jalali date"""
        note = DailyNote()
        self.assertEqual(note.date, self.yesterday)

    def test_dailynote_admin_changeform_initial_data_is_yesterday(self):
        """DailyNoteAdmin pre-fills 'date' with yesterday's Jalali date on add form"""
        req = self.rf.get('/admin/dormitory/dailynote/add/')
        req.user = self.user
        initial = self.dailynote_admin.get_changeform_initial_data(req)
        self.assertIn('date', initial)
        self.assertEqual(initial['date'], self.yesterday)

    def test_resident_admin_changeform_initial_data_entry_date_is_yesterday(self):
        """ResidentAdmin pre-fills 'entry_date' with yesterday's Jalali date on add form"""
        req = self.rf.get('/admin/dormitory/resident/add/')
        req.user = self.user
        initial = self.resident_admin.get_changeform_initial_data(req)
        self.assertIn('entry_date', initial)
        self.assertEqual(initial['entry_date'], self.yesterday)

    def test_admin_persian_date_widget_classes_and_media(self):
        """AdminPersianDateWidget sets 'vjDateField form-control' and includes custom static assets"""
        from apps.dormitory.admin import AdminPersianDateWidget
        widget = AdminPersianDateWidget()
        self.assertIn('vjDateField', widget.attrs.get('class', ''))
        self.assertIn('form-control', widget.attrs.get('class', ''))

        media_html = str(widget.media)
        self.assertIn('admin_jalali_datepicker.css', media_html)
        self.assertIn('admin_jalali_datepicker.js', media_html)

    def test_resident_status_tab_date_fields_use_persian_widget(self):
        """
        All date fields in 'وضعیت اقامت و تاریخ‌ها' tab (entry_date, exit_date, settled_until)
        use AdminPersianDateWidget.
        """
        from apps.dormitory.admin import AdminPersianDateWidget
        req = self.rf.get('/admin/dormitory/resident/add/')
        req.user = self.user
        form_class = self.resident_admin.get_form(req)
        form = form_class()

        for field_name in ['entry_date', 'exit_date', 'settled_until']:
            field = form.fields.get(field_name)
            self.assertIsNotNone(field, f"Field {field_name} missing from Resident form")
            self.assertIsInstance(
                field.widget,
                AdminPersianDateWidget,
                f"Field {field_name} widget is {type(field.widget)}, expected AdminPersianDateWidget"
            )

    def test_hyphenated_jalali_date_format_passes_validation(self):
        """
        django_jalali jDateField validates YYYY-MM-DD hyphen format successfully.
        """
        from django_jalali import forms as jforms
        field = jforms.jDateField()
        formatted_date = f"{self.yesterday.year:04d}-{self.yesterday.month:02d}-{self.yesterday.day:02d}"
        cleaned = field.clean(formatted_date)
        self.assertEqual(cleaned, self.yesterday)











