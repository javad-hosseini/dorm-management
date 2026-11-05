import jdatetime
from io import StringIO
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident, Transaction
from apps.dormitory.services.daily_report_service import DailyReportService
from apps.sms_service.services.provider import ProviderResult


class SendReportCommandTests(TestCase):
    def setUp(self):
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318",
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه نوید",
        )
        # Create rooms
        self.room1 = Room.objects.create(
            room_number="101",
            dormitory=self.dormitory,
            capacity=2,
            monthly_rent=38000000,
        )
        self.room2 = Room.objects.create(
            room_number="102",
            dormitory=self.dormitory,
            capacity=3,
            monthly_rent=38000000,
        )

        # 1 active resident in room1 (leaves 1 empty bed in room1)
        self.resident1 = Resident.objects.create(
            first_name="رضا",
            last_name="علوی",
            room=self.room1,
            dormitory=self.dormitory,
            national_code="0123456789",
            phone_number="09123333333",
            entry_date=jdatetime.date(1405, 7, 1),
            status="ACTIVE",
            settled_until=jdatetime.date(1405, 8, 1),
            registered_by=self.supervisor,
        )
        # room2 has no residents (leaves 3 empty beds in room2)

    def test_daily_report_service_data(self):
        target_date = jdatetime.date(1405, 8, 5)
        # Create transaction on target date
        Transaction.objects.create(
            resident=self.resident1,
            dormitory=self.dormitory,
            amount=38000000,
            transaction_type="RENT",
            payment_method="CARD",
            payment_date=jdatetime.datetime(1405, 8, 5, 14, 30, 0),
            created_by=self.supervisor,
        )

        data = DailyReportService.get_daily_report_data(
            target_date=target_date,
            dormitory_id=self.dormitory.id,
        )
        self.assertEqual(data["yesterday_total_tomans"], 3800000)
        self.assertEqual(data["yesterday_count"], 1)
        self.assertEqual(data["card_tomans"], 3800000)
        self.assertEqual(data["transfer_tomans"], 0)
        self.assertEqual(data["total_empty_beds"], 4)  # 1 in room1 + 3 in room2

    def test_daily_report_service_sms_formatting(self):
        target_date = jdatetime.date(1405, 8, 5)
        Transaction.objects.create(
            resident=self.resident1,
            dormitory=self.dormitory,
            amount=38000000,
            transaction_type="RENT",
            payment_method="CARD",
            payment_date=jdatetime.datetime(1405, 8, 5, 14, 30, 0),
            created_by=self.supervisor,
        )

        sms_text = DailyReportService.generate_sms_text(
            target_date=target_date,
            dormitory_id=self.dormitory.id,
        )
        self.assertIn("گزارش روزانه خوابگاه نوید", sms_text)
        self.assertIn("• درآمد دیروز:", sms_text)
        self.assertIn("• تعداد تراکنش دیروز:", sms_text)
        self.assertIn("• مجموع تخت‌های خالی:", sms_text)
        # Verify each vacant room is on its own line
        self.assertIn("- اتاق ۱۰۱: ۱ تخت", sms_text)
        self.assertIn("- اتاق ۱۰۲: ۳ تخت", sms_text)

    def test_sendreport_command_dry_run(self):
        out = StringIO()
        call_command("sendreport", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("[DRY RUN]", output)
        self.assertIn("09210431554", output)
        self.assertIn("گزارش روزانه خوابگاه نوید", output)
        self.assertIn("حالت پیش‌نمایش (Dry-Run)", output)

    def test_sendreport_command_custom_phone_and_date(self):
        out = StringIO()
        call_command(
            "sendreport",
            "--dry-run",
            "--phone", "09129876543",
            "--date", "1405/08/05",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("09129876543", output)
        self.assertIn("1405/08/05", output)

    @patch("apps.sms_service.management.commands.sendreport.get_sms_provider")
    def test_sendreport_command_dispatches_sms(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.send_simple_sms.return_value = ProviderResult(
            success=True,
            rec_id="99887766",
        )
        mock_get_provider.return_value = mock_provider

        out = StringIO()
        call_command("sendreport", stdout=out)
        output = out.getvalue()

        self.assertIn("پیامک با موفقیت به 09210431554 ارسال شد", output)
        self.assertIn("99887766", output)
        mock_provider.send_simple_sms.assert_called_once()
        args, kwargs = mock_provider.send_simple_sms.call_args
        self.assertEqual(kwargs["recipients"], ["09210431554"])
        self.assertIn("گزارش روزانه خوابگاه نوید", kwargs["text"])

    def test_sendreport_invalid_phone(self):
        with self.assertRaises(CommandError):
            call_command("sendreport", "--phone", "invalid-number")

    def test_sendreport_invalid_date(self):
        with self.assertRaises(CommandError):
            call_command("sendreport", "--date", "invalid-date")
