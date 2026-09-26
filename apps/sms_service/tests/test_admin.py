from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
import jdatetime

from apps.dormitory.models import Resident, Room, Dormitory
from apps.accounts.models import Supervisor
from apps.sms_service.models import Contact, SmsCampaign, SmsRecipientLog

User = get_user_model()


class SmsAdminSecurityAndWorkflowTest(TestCase):
    def setUp(self):
        # 1. Superuser
        self.superuser = User.objects.create_superuser(
            username="super_admin",
            password="admin_password",
            email="admin@dormitory.ir",
        )

        # 2. Staff with SMS permission
        self.staff_with_perm = User.objects.create_user(
            username="staff_allowed",
            password="staff_password",
            is_staff=True,
        )
        content_type = ContentType.objects.get_for_model(SmsCampaign)
        perm = Permission.objects.get(content_type=content_type, codename="add_smscampaign")
        self.staff_with_perm.user_permissions.add(perm)

        # 3. Staff without SMS permission
        self.staff_no_perm = User.objects.create_user(
            username="staff_denied",
            password="staff_password",
            is_staff=True,
        )

        # 4. Dormitory & Resident
        self.supervisor = Supervisor.objects.create(
            first_name="سرپرست",
            last_name="تست",
            national_code="0011223377",
        )
        self.dormitory = Dormitory.objects.create(name="خوابگاه مرکزی")
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number="302",
            capacity=4,
            monthly_rent=30000000,
        )
        self.resident = Resident.objects.create(
            first_name="کامران",
            last_name="نجفی",
            phone_number="09121111111",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )

        # 5. Contact
        self.contact = Contact.objects.create(
            full_name="مخاطب تستی",
            phone_number="09122222222",
        )

        self.client = Client()
        self.send_url = reverse("admin:sms_service_send")

    def test_anonymous_user_redirected_to_login(self):
        resp = self.client.get(self.send_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_staff_without_perm_forbidden(self):
        self.client.login(username="staff_denied", password="staff_password")
        resp = self.client.get(self.send_url)
        self.assertEqual(resp.status_code, 403)

    def test_staff_with_perm_access_granted(self):
        self.client.login(username="staff_allowed", password="staff_password")
        resp = self.client.get(self.send_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "مرکز ارسال پیامک خوابگاه")

    def test_get_request_never_triggers_sms(self):
        self.client.login(username="super_admin", password="admin_password")
        initial_count = SmsCampaign.objects.count()
        resp = self.client.get(self.send_url, {"message_body": "test", "selected_residents": [self.resident.id]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SmsCampaign.objects.count(), initial_count)

    def test_post_step_preview_shows_confirmation(self):
        self.client.login(username="super_admin", password="admin_password")
        resp = self.client.post(
            self.send_url,
            {
                "step": "preview",
                "message_body": "پیامک اطلاع‌رسانی به آقای {نام} اتاق {اتاق}",
                "selected_residents": [self.resident.id],
                "selected_contacts": [self.contact.id],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تأیید و بازبینی نهایی ارسال پیامک")
        self.assertContains(resp, "کامران نجفی")
        self.assertContains(resp, "اتاق 302")

    def test_post_with_custom_contacts_json(self):
        self.client.login(username="super_admin", password="admin_password")
        resp = self.client.post(
            self.send_url,
            {
                "step": "preview",
                "message_body": "سلام به مخاطب دلخواه",
                "custom_contacts_json": '[{"name": "پدر دانشجو", "phone": "09129998877"}]',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "پدر دانشجو")
        self.assertContains(resp, "09129998877")

        # Verify the contact was saved in DB
        contact = Contact.objects.filter(phone_number="09129998877").first()
        self.assertIsNotNone(contact)
        self.assertEqual(contact.full_name, "پدر دانشجو")
