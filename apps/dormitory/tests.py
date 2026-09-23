import jdatetime
from datetime import timedelta
from django.test import TestCase
from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident, Transaction
from apps.dormitory.queries import ReportQueries
from apps.dormitory.admin import RoomForm, TransactionForm


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

