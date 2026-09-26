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
