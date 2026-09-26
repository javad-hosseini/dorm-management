from django.contrib.auth import get_user_model, authenticate
from django.test import TestCase, Client
from django.urls import reverse
import jdatetime

from apps.accounts.backends import NationalCodeOrPhoneBackend, normalize_input_digits
from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident

User = get_user_model()


class AccountsAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.backend = NationalCodeOrPhoneBackend()

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

        # Create resident without user initially
        self.resident = Resident.objects.create(
            first_name="رضا",
            last_name="محمدی",
            national_code="0012345678",
            phone_number="09123456789",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor
        )

    def test_normalize_input_digits(self):
        persian_str = "۰۹۱۲۳۴۵۶۷۸۹"
        self.assertEqual(normalize_input_digits(persian_str), "09123456789")

    def test_resident_ensure_user_account(self):
        # Resident save should have created or linked user account
        user = self.resident.user
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "0012345678")
        # Default password is the national code
        self.assertTrue(user.check_password("0012345678"))

    def test_authenticate_with_national_code(self):
        user = authenticate(username="0012345678", password="0012345678")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "0012345678")

    def test_authenticate_with_persian_digits_national_code(self):
        # User types Persian digits on keyboard
        user = authenticate(username="۰۰۱۲۳۴۵۶۷۸", password="0012345678")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "0012345678")

    def test_authenticate_with_phone_number(self):
        # Resident logs in using phone number instead of national code
        user = authenticate(username="09123456789", password="0012345678")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "0012345678")

    def test_authenticate_invalid_password(self):
        user = authenticate(username="0012345678", password="WrongPassword123")
        self.assertIsNone(user)

    def test_login_view_get(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ورود به سامانه خوابگاه")
        self.assertContains(response, "کد ملی یا شماره همراه")

    def test_student_login_redirects_to_student_dashboard(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': '0012345678',
            'password': '0012345678',
            'remember_me': 'on',
        })
        self.assertRedirects(response, reverse('dashboard:student'))

    def test_staff_login_redirects_to_admin_dashboard(self):
        staff_user = User.objects.create_user(
            username="admin_user",
            password="adminpassword",
            is_staff=True
        )
        response = self.client.post(reverse('accounts:login'), {
            'username': 'admin_user',
            'password': 'adminpassword',
        })
        self.assertRedirects(response, reverse('dashboard:admin'))

    def test_logout_view(self):
        self.client.login(username="0012345678", password="0012345678")
        response = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'))
        # Ensure user is logged out
        response_dash = self.client.get(reverse('dashboard:student'))
        self.assertRedirects(response_dash, f"{reverse('accounts:login')}?next={reverse('dashboard:student')}")
