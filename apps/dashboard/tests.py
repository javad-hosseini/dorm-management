from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
import jdatetime
from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident

User = get_user_model()


class StudentDashboardSecurityAndPrivacyTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.supervisor = Supervisor.objects.create(
            first_name="مدیر",
            last_name="خوابگاه",
            national_code="0011223344"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه نوید",
            address="تهران"
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=101,
            capacity=4,
            monthly_rent=30_000_000
        )
        self.student = Resident.objects.create(
            first_name="دانشجو",
            last_name="اصلی",
            national_code="1111111111",
            phone_number="09121111111",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )
        self.roommate = Resident.objects.create(
            first_name="هم‌اتاقی",
            last_name="محرمانه",
            national_code="2222222222",
            phone_number="09122222222",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )

        # Ensure user accounts are created
        self.user = self.student.ensure_user_account()
        self.roommate_user = self.roommate.ensure_user_account()

    def test_roommate_national_code_not_in_dashboard_api(self):
        self.client.force_login(self.user)
        url = reverse('dashboard:api_student_data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        roommates = data.get('roommates', [])
        other_rm = next((r for r in roommates if r.get('id') == self.roommate.id), None)
        self.assertIsNotNone(other_rm)
        self.assertNotIn('national', other_rm)
        self.assertNotIn('national_code', other_rm)
        self.assertNotIn('2222222222', str(data.get('roommates')))

    def test_student_data_isolation_no_idor(self):
        """Verify logged-in student strictly sees their own information"""
        self.client.force_login(self.user)
        url = reverse('dashboard:api_student_data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        me = data.get('me')
        self.assertIsNotNone(me)
        self.assertEqual(me.get('id'), self.student.id)
        self.assertEqual(me.get('national_code'), "1111111111")
        self.assertEqual(me.get('phone_number'), "09121111111")

    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated requests must be redirected to accounts:login"""
        student_url = reverse('dashboard:student')
        response = self.client.get(student_url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={student_url}")

        admin_url = reverse('dashboard:admin')
        response_admin = self.client.get(admin_url)
        self.assertRedirects(response_admin, f"{reverse('accounts:login')}?next={admin_url}")

    def test_student_cannot_access_admin_dashboard(self):
        """A normal student user must not access admin dashboard"""
        self.client.force_login(self.user)
        admin_url = reverse('dashboard:admin')
        response = self.client.get(admin_url)
        # Should be redirected to their own student dashboard
        self.assertRedirects(response, reverse('dashboard:student'))

    def test_health_check_endpoint(self):
        """Health check endpoint should return 200 and healthy status"""
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('database'), 'connected')


import os
from pathlib import Path
from apps.dashboard.services.backup_service import BackupService


class BackupServiceAndApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_backup_test",
            password="password123",
            email="admin@test.com"
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            password="password123"
        )
        self.backup_dir = BackupService.get_backup_dir()

    def tearDown(self):
        # Clean up any test backups
        if self.backup_dir.exists():
            for f in self.backup_dir.glob("backup_*.sql"):
                try:
                    f.unlink()
                except OSError:
                    pass

    def test_backup_unauthenticated_denied(self):
        url = reverse("dashboard:api_backup_create")
        res = self.client.post(url)
        self.assertRedirects(res, f"{reverse('accounts:login')}?next={url}")

    def test_backup_normal_user_denied(self):
        self.client.force_login(self.normal_user)
        url = reverse("dashboard:api_backup_create")
        res = self.client.post(url)
        self.assertRedirects(res, reverse("dashboard:student"))

    def test_admin_create_backup_success(self):
        self.client.force_login(self.admin_user)
        url = reverse("dashboard:api_backup_create")
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "success")
        backup = data.get("backup", {})
        self.assertTrue(backup.get("filename", "").startswith("backup_"))
        self.assertTrue(backup.get("filename", "").endswith(".sql"))
        self.assertTrue(Path(backup["path"]).exists())
        self.assertGreater(Path(backup["path"]).stat().st_size, 0)

    def test_backup_rotation_strictly_keeps_max_5(self):
        # Create 7 dummy backup files with staggered timestamps
        dummy_files = []
        for i in range(7):
            fpath = self.backup_dir / f"backup_2026-09-28_00-00-0{i}_{1000 + i}.sql"
            fpath.write_text(f"-- test backup {i}", encoding="utf-8")
            # Set modified time so ordering is deterministic
            os.utime(str(fpath), (1000 + i * 10, 1000 + i * 10))
            dummy_files.append(fpath)

        self.assertEqual(len(BackupService.list_backups()), 7)

        # Trigger rotation
        removed = BackupService.rotate_backups(max_files=5)
        self.assertEqual(len(removed), 2)
        # The oldest two (0 and 1) should be removed
        self.assertIn("backup_2026-09-28_00-00-00_1000.sql", removed)
        self.assertIn("backup_2026-09-28_00-00-01_1001.sql", removed)

        remaining = BackupService.list_backups()
        self.assertEqual(len(remaining), 5)
        # Verify the 5 newest files are intact
        remaining_names = [f["name"] for f in remaining]
        for i in range(2, 7):
            self.assertIn(f"backup_2026-09-28_00-00-0{i}_{1000 + i}.sql", remaining_names)


class FinancialDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_fin_test",
            password="password123",
            email="admin_fin@test.com"
        )
        self.normal_user = User.objects.create_user(
            username="normal_fin_user",
            password="password123"
        )

    def test_finance_dashboard_unauthenticated_redirects(self):
        url = reverse("dashboard:finance")
        res = self.client.get(url)
        self.assertRedirects(res, f"{reverse('accounts:login')}?next={url}")

    def test_finance_dashboard_student_denied(self):
        self.client.force_login(self.normal_user)
        url = reverse("dashboard:finance")
        res = self.client.get(url)
        self.assertRedirects(res, reverse("dashboard:student"))

    def test_finance_dashboard_admin_access(self):
        self.client.force_login(self.admin_user)
        url = reverse("dashboard:finance")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "پنل جامع مدیریت و حسابداری مالی")
        self.assertIn("finance_data", res.context)

    def test_finance_api_returns_complete_structure(self):
        self.client.force_login(self.admin_user)
        url = reverse("dashboard:api_finance_data")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("today_stats", data)
        self.assertIn("seven_days_breakdown", data)
        self.assertIn("debt_stats", data)
        self.assertIn("month_stats", data)
        self.assertIn("top_debtors", data)
        self.assertIn("recent_transactions", data)

        # Check 7 days breakdown
        breakdown = data["seven_days_breakdown"]
        self.assertEqual(len(breakdown), 7)
        for d in breakdown:
            self.assertIn("date_str", d)
            self.assertIn("card_tomans", d)
            self.assertIn("transfer_tomans", d)
            self.assertIn("total_tomans", d)

        # Check debt stats
        debt_stats = data["debt_stats"]
        self.assertIn("overdue_debt_tomans", debt_stats)
        self.assertIn("projected_debt_until_next_month_tomans", debt_stats)


class PartialRentPaymentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.supervisor = Supervisor.objects.create(
            first_name="سرپرست",
            last_name="مالی",
            national_code="0011223399"
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه مرکزی",
            address="تهران"
        )
        # Room rent is 3,000,000 Tomans (30,000,000 Rials)
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=201,
            capacity=4,
            monthly_rent=30_000_000
        )
        self.resident = Resident.objects.create(
            first_name="علی",
            last_name="رضایی",
            national_code="0987654321",
            phone_number="09129876543",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 7, 1),
            monthly_payment_day=1,
            settled_until=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )
        self.admin_user = User.objects.create_superuser(
            username="admin_partial_test",
            password="password123"
        )

    def test_partial_payment_calculation_and_status(self):
        """
        When monthly rent is 3,000,000 Tomans and resident pays 2,000,000 Tomans:
        - is_partial_payment should be True
        - current_period_paid_tomans should be 2,000,000
        - current_period_remaining_tomans should be 1,000,000
        - progress_percent should be 67%
        """
        from apps.dormitory.models import Transaction

        # Step 1: Resident pays 2,000,000 Tomans (20,000,000 Rials)
        tx1 = Transaction.objects.create(
            resident=self.resident,
            dormitory=self.dormitory,
            amount=20_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
            payment_date=jdatetime.datetime(1405, 7, 2, 10, 0),
            period_start=jdatetime.date(1405, 7, 1),
            created_by=self.supervisor,
            is_approved=True
        )

        self.resident.refresh_from_db()
        status = self.resident.current_period_payment_status

        self.assertTrue(self.resident.is_partial_payment)
        self.assertTrue(status["is_partial"])
        self.assertEqual(status["total_rent_tomans"], 3_000_000)
        self.assertEqual(status["paid_tomans"], 2_000_000)
        self.assertEqual(status["remaining_tomans"], 1_000_000)
        self.assertEqual(status["progress_percent"], 67)
        self.assertIn("۲,۰۰۰,۰۰۰", status["status_label"])
        self.assertIn("۱,۰۰۰,۰۰۰", status["status_label"])
        self.assertIn("۲,۰۰۰,۰۰۰", self.resident.due_status_display)
        self.assertIn("۱,۰۰۰,۰۰۰", self.resident.due_status_display)

        # Step 2: Resident pays the remaining 1,000,000 Tomans (10,000,000 Rials)
        tx2 = Transaction.objects.create(
            resident=self.resident,
            dormitory=self.dormitory,
            amount=10_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.CASH,
            payment_date=jdatetime.datetime(1405, 7, 10, 12, 0),
            created_by=self.supervisor,
            is_approved=True
        )

        self.resident.refresh_from_db()
        status2 = self.resident.current_period_payment_status

        self.assertFalse(self.resident.is_partial_payment)
        self.assertFalse(status2["is_partial"])
        self.assertEqual(status2["remaining_tomans"], 0)
        self.assertEqual(status2["paid_tomans"], 3_000_000)
        self.assertEqual(status2["progress_percent"], 100)
        self.assertEqual(self.resident.settled_until, jdatetime.date(1405, 8, 1))

    def test_admin_dashboard_api_returns_partial_payment_data(self):
        from apps.dormitory.models import Transaction

        # Resident pays 2,000,000 Tomans
        Transaction.objects.create(
            resident=self.resident,
            dormitory=self.dormitory,
            amount=20_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.CARD,
            payment_date=jdatetime.datetime(1405, 7, 2, 10, 0),
            period_start=jdatetime.date(1405, 7, 1),
            created_by=self.supervisor,
            is_approved=True
        )

        self.client.force_login(self.admin_user)
        url = reverse('dashboard:api_admin_data')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Find resident in serialized data
        r_data = next((r for r in data["residents"] if r["id"] == self.resident.id), None)
        self.assertIsNotNone(r_data)
        self.assertTrue(r_data["is_partial_payment"])
        self.assertIn("period_payment", r_data)
        self.assertEqual(r_data["period_payment"]["paid_tomans"], 2_000_000)
        self.assertEqual(r_data["period_payment"]["remaining_tomans"], 1_000_000)

        # Check stats includes partial_residents count
        self.assertIn("partial_residents", data["stats"])
        self.assertGreaterEqual(data["stats"]["partial_residents"], 1)

    def test_transaction_with_discount_serialized_in_dashboard_api(self):
        from apps.dormitory.models import Transaction

        # Resident pays 1,100,000 Tomans with 400,000 Tomans discount
        tx = Transaction.objects.create(
            resident=self.resident,
            dormitory=self.dormitory,
            amount=11_000_000,  # 1,100,000 Tomans
            discount_amount=4_000_000,  # 400,000 Tomans
            discount_reason="کسر بابت سم‌پاشی و تعمیرات",
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.CARD,
            payment_date=jdatetime.datetime(1405, 7, 5, 10, 0),
            period_start=jdatetime.date(1405, 7, 1),
            created_by=self.supervisor,
            is_approved=True
        )

        self.client.force_login(self.admin_user)
        res = self.client.get(reverse('dashboard:api_admin_data'))
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Find transaction in serialized transactions
        tx_data = next((t for t in data["transactions"] if t["id"] == tx.id), None)
        self.assertIsNotNone(tx_data)
        self.assertTrue(tx_data["has_discount"])
        self.assertEqual(tx_data["discount_in_tomans"], 400_000)
        self.assertEqual(tx_data["discount_reason"], "کسر بابت سم‌پاشی و تعمیرات")
        self.assertEqual(tx_data["total_effective_amount_toman"], 1_500_000)



