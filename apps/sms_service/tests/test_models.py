from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth import get_user_model
import jdatetime

from apps.dormitory.models import Resident, Room, Dormitory
from apps.accounts.models import Supervisor
from apps.sms_service.models import Contact, SmsCampaign, SmsRecipientLog

User = get_user_model()


class ContactModelTest(TestCase):
    def test_create_contact_normalizes_phone(self):
        contact = Contact.objects.create(
            full_name="رضا رضایی",
            phone_number="+989121112233",
            notes="مشتری یا پرسنل",
        )
        self.assertEqual(contact.phone_number, "09121112233")
        self.assertIn("رضا رضایی", str(contact))

    def test_create_contact_persian_digits_normalized(self):
        contact = Contact.objects.create(
            full_name="مهدی حسینی",
            phone_number="۰۹۱۲۹۹۹۸۸۷۷",
        )
        self.assertEqual(contact.phone_number, "09129998877")

    def test_contact_phone_uniqueness_enforced(self):
        Contact.objects.create(
            full_name="مخاطب اول",
            phone_number="09121112233",
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            Contact.objects.create(
                full_name="مخاطب دوم",
                phone_number="+989121112233",  # Will normalize to 09121112233
            )

    def test_contact_invalid_phone_validation(self):
        contact = Contact(
            full_name="نامعتبر",
            phone_number="02188888888",
        )
        with self.assertRaises(ValidationError):
            contact.full_clean()


class SmsCampaignAndLogModelTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="sms_admin",
            password="admin_password",
            first_name="مدیر",
            last_name="سامانه",
        )
        self.supervisor = Supervisor.objects.create(
            first_name="سرپرست",
            last_name="اول",
            national_code="0011223344",
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه مرکزی",
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number="101",
            capacity=4,
            monthly_rent=30000000,
        )
        self.resident = Resident.objects.create(
            first_name="علی",
            last_name="محمدی",
            phone_number="09123456789",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )

    def test_create_campaign_and_logs_with_resident(self):
        campaign = SmsCampaign.objects.create(
            sender=self.admin_user,
            message_body="پیامک تستی یادآوری اجاره",
            recipient_source=SmsCampaign.Source.RESIDENTS,
            total_selected=1,
            total_deduplicated=1,
            successful_count=1,
            failed_count=0,
            status=SmsCampaign.Status.COMPLETED,
        )
        self.assertEqual(campaign.status, SmsCampaign.Status.COMPLETED)
        self.assertIn("کمپین #", str(campaign))

        log = SmsRecipientLog.objects.create(
            campaign=campaign,
            recipient_type=SmsRecipientLog.RecipientType.RESIDENT,
            resident=self.resident,
            phone_number="09123456789",
            final_message="آقای علی محمدی عزیز؛ اتاق 101 بدهی شما 3,000,000 تومان است.",
            status=SmsRecipientLog.Status.SUCCESS,
            provider_rec_id="987654321",
        )
        self.assertEqual(campaign.recipients.count(), 1)
        self.assertEqual(log.resident, self.resident)
        self.assertEqual(log.status, SmsRecipientLog.Status.SUCCESS)
