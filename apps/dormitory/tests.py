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
