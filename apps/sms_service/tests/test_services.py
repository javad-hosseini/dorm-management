from django.test import TestCase
from django.contrib.auth import get_user_model
import jdatetime

from apps.dormitory.models import Resident, Room, Dormitory
from apps.accounts.models import Supervisor
from apps.sms_service.models import Contact, SmsCampaign, SmsRecipientLog
from apps.sms_service.services.campaign_service import send_campaign, prepare_campaign_preview
from apps.sms_service.services.provider import BaseSmsProvider, ProviderResult

User = get_user_model()


class MockCustomProvider(BaseSmsProvider):
    def __init__(
        self,
        succeed: bool = True,
        fail_for_phones: list[str] | None = None,
        blacklist_phones: list[str] | None = None,
        exception_phones: list[str] | None = None,
    ):
        self.succeed = succeed
        self.fail_for_phones = fail_for_phones or []
        self.blacklist_phones = blacklist_phones or []
        self.exception_phones = exception_phones or []
        self.calls: list[dict] = []

    def send_simple_sms(self, recipients: list[str], text: str, is_flash: bool = False) -> ProviderResult:
        self.calls.append({"recipients": recipients, "text": text, "is_flash": is_flash})
        for exc_phone in self.exception_phones:
            if exc_phone in recipients:
                raise ConnectionResetError("Connection abruptly closed by peer")

        for bl_phone in self.blacklist_phones:
            if bl_phone in recipients:
                return ProviderResult(
                    success=False,
                    error_code="BLACKLIST",
                    error_message="⛔ لیست سیاه مخابرات: دریافت پیامک تبلیغاتی توسط مخاطب مسدود شده است (خط ۵۰۰۰).",
                    is_blacklist=True,
                )

        for f_phone in self.fail_for_phones:
            if f_phone in recipients:
                return ProviderResult(success=False, error_code="MOCK_FAIL", error_message="ارسال با خطا مواجه شد.")

        if self.succeed:
            return ProviderResult(success=True, rec_id="123456789")
        return ProviderResult(success=False, error_code="GENERAL_FAIL", error_message="شکست در ارسال")


class CampaignServiceTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_sender",
            password="pass",
            is_staff=True,
        )
        self.supervisor = Supervisor.objects.create(
            first_name="سرپرست",
            last_name="تست",
            national_code="0011223388",
        )
        self.dormitory = Dormitory.objects.create(name="خوابگاه مرکزی")
        self.room1 = Room.objects.create(
            dormitory=self.dormitory,
            room_number="101",
            capacity=4,
            monthly_rent=30000000,
        )
        self.res1 = Resident.objects.create(
            first_name="محمد",
            last_name="علوی",
            phone_number="09121111111",
            dormitory=self.dormitory,
            room=self.room1,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )
        self.res2 = Resident.objects.create(
            first_name="حسین",
            last_name="کاظمی",
            phone_number="09122222222",
            dormitory=self.dormitory,
            room=self.room1,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )
        self.contact1 = Contact.objects.create(
            full_name="مخاطب الف",
            phone_number="09123333333",
        )

    def test_preview_deduplication_and_precedence(self):
        # Create a contact with the same phone number as resident res1
        contact_duplicate = Contact.objects.create(
            full_name="مخاطب با شماره ساکن ۱",
            phone_number="09121111111",
        )

        preview = prepare_campaign_preview(
            resident_ids=[self.res1.id, self.res2.id],
            contact_ids=[self.contact1.id, contact_duplicate.id],
            message_body="سلام آقای {نام} اتاق {اتاق}",
        )

        self.assertEqual(preview["total_selected"], 4)
        self.assertEqual(preview["valid_count"], 3)  # res1, res2, contact1
        self.assertEqual(preview["duplicate_count"], 1)

        # Confirm duplicate was the contact, not the resident
        dup = preview["duplicates"][0]
        self.assertEqual(dup.recipient_type, "contact")
        self.assertEqual(dup.phone_number, "09121111111")

    def test_send_campaign_personalized(self):
        mock_provider = MockCustomProvider(succeed=True)

        result = send_campaign(
            sender_user=self.admin_user,
            resident_ids=[self.res1.id, self.res2.id],
            contact_ids=[self.contact1.id],
            message_body="آقای {نام} اتاق {اتاق} موعد شما فرا رسیده است.",
            provider=mock_provider,
        )

        campaign = result["campaign"]
        self.assertEqual(campaign.status, SmsCampaign.Status.COMPLETED)
        self.assertEqual(campaign.successful_count, 3)
        self.assertEqual(campaign.failed_count, 0)

        # Verify logs in DB
        logs = list(campaign.recipients.order_by("id"))
        self.assertEqual(len(logs), 3)

        # Res1 personalized message
        res1_log = campaign.recipients.get(phone_number="09121111111")
        self.assertEqual(res1_log.recipient_type, SmsRecipientLog.RecipientType.RESIDENT)
        self.assertEqual(res1_log.resident, self.res1)
        self.assertIn("محمد علوی", res1_log.final_message)
        self.assertIn("اتاق 101", res1_log.final_message)

    def test_send_campaign_with_blacklist_isolation(self):
        # res2 has advertising SMS blocked (blacklist)
        mock_provider = MockCustomProvider(
            succeed=True,
            blacklist_phones=["09122222222"],
        )

        result = send_campaign(
            sender_user=self.admin_user,
            resident_ids=[self.res1.id, self.res2.id],
            contact_ids=[self.contact1.id],
            message_body="سلام {نام}",
            provider=mock_provider,
        )

        campaign = result["campaign"]
        # Batch was NOT cancelled!
        self.assertEqual(campaign.status, SmsCampaign.Status.PARTIAL_FAILURE)
        self.assertEqual(campaign.successful_count, 2)
        self.assertEqual(campaign.failed_count, 1)
        self.assertEqual(campaign.blocked_count, 1)

        # Successful recipients received it
        self.assertEqual(len(result["successful_recipients"]), 2)
        # Blocked recipient recorded with BLOCKED_ADVERTISING
        self.assertEqual(len(result["blocked_recipients"]), 1)
        self.assertEqual(result["blocked_recipients"][0]["phone_number"], "09122222222")

        res2_log = campaign.recipients.get(phone_number="09122222222")
        self.assertEqual(res2_log.status, SmsRecipientLog.Status.BLOCKED_ADVERTISING)
        self.assertIn("لیست سیاه", res2_log.error_message)

        # res1 and contact1 succeeded
        res1_log = campaign.recipients.get(phone_number="09121111111")
        self.assertEqual(res1_log.status, SmsRecipientLog.Status.SUCCESS)

    def test_send_campaign_with_exception_isolation(self):
        # res1 raises an unexpected network exception during sending
        mock_provider = MockCustomProvider(
            succeed=True,
            exception_phones=["09121111111"],
        )

        result = send_campaign(
            sender_user=self.admin_user,
            resident_ids=[self.res1.id, self.res2.id],
            message_body="اطلاعیه خوابگاه",
            provider=mock_provider,
        )

        campaign = result["campaign"]
        # Unexpected error on res1 did not crash the campaign or cancel res2
        self.assertEqual(campaign.status, SmsCampaign.Status.PARTIAL_FAILURE)
        self.assertEqual(campaign.successful_count, 1)
        self.assertEqual(campaign.failed_count, 1)

        res2_log = campaign.recipients.get(phone_number="09122222222")
        self.assertEqual(res2_log.status, SmsRecipientLog.Status.SUCCESS)

        res1_log = campaign.recipients.get(phone_number="09121111111")
        self.assertEqual(res1_log.status, SmsRecipientLog.Status.FAILED)
        self.assertEqual(res1_log.error_code, "UNEXPECTED_ERROR")
