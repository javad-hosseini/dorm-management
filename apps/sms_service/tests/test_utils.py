from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
import jdatetime

from apps.dormitory.models import Resident, Room, Dormitory
from apps.accounts.models import Supervisor
from apps.sms_service.utils import (
    normalize_phone_number,
    is_valid_iranian_mobile,
    validate_iranian_mobile,
    format_personalized_message,
    calculate_sms_parts,
    render_resident_sms_template,
    calculate_resident_debt_details,
    DEFAULT_DEBT_REMINDER_TEMPLATE,
)

User = get_user_model()


class PhoneNumberUtilsTest(TestCase):
    def test_normalize_standard_09_format(self):
        self.assertEqual(normalize_phone_number("09123456789"), "09123456789")

    def test_normalize_persian_and_arabic_digits(self):
        self.assertEqual(normalize_phone_number("۰۹۱۲۳۴۵۶۷۸۹"), "09123456789")
        self.assertEqual(normalize_phone_number("٠٩١٢٣٤٥٦٧٨٩"), "09123456789")

    def test_normalize_with_plus_98_prefix(self):
        self.assertEqual(normalize_phone_number("+989123456789"), "09123456789")
        self.assertEqual(normalize_phone_number("+۹۸۹۱۲۳۴۵۶۷۸۹"), "09123456789")

    def test_normalize_with_0098_prefix(self):
        self.assertEqual(normalize_phone_number("00989123456789"), "09123456789")

    def test_normalize_with_98_prefix(self):
        self.assertEqual(normalize_phone_number("989123456789"), "09123456789")

    def test_normalize_without_leading_zero(self):
        self.assertEqual(normalize_phone_number("9123456789"), "09123456789")

    def test_normalize_with_formatting_spaces_and_dashes(self):
        self.assertEqual(normalize_phone_number("0912-345-6789"), "09123456789")
        self.assertEqual(normalize_phone_number("0912 345 6789"), "09123456789")
        self.assertEqual(normalize_phone_number("(+98) 912 345 6789"), "09123456789")

    def test_invalid_phone_numbers(self):
        invalid_numbers = [
            "",
            None,
            "02188888888",      # Tehran landline
            "091234567",        # Too short
            "0912345678901",    # Too long
            "abcdefghijk",      # Letters
            "0900000000a",      # Contains letter
            "+14155552671",     # US number
        ]
        for num in invalid_numbers:
            with self.subTest(phone=num):
                self.assertFalse(is_valid_iranian_mobile(num))
                with self.assertRaises(ValidationError):
                    normalize_phone_number(num)
                with self.assertRaises(ValidationError):
                    validate_iranian_mobile(num)


class ResidentTemplateRenderingTest(TestCase):
    def setUp(self):
        self.supervisor = Supervisor.objects.create(
            first_name="سرپرست",
            last_name="تست",
            national_code="0011223399",
        )
        self.dormitory = Dormitory.objects.create(name="خوابگاه مرکزی")
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number="205",
            capacity=4,
            monthly_rent=35000000,  # 3,500,000 Tomans
        )
        self.resident = Resident.objects.create(
            first_name="سهراب",
            last_name="سپهری",
            phone_number="09123334455",
            dormitory=self.dormitory,
            room=self.room,
            entry_date=jdatetime.date(1405, 1, 1),
            settled_until=jdatetime.date(1405, 6, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )

    def test_render_resident_template_replaces_tags(self):
        template = "آقای {نام} اتاق {اتاق} موعد شما {موعد_تسویه} بدهی {مبلغ_بدهی} و بدهی دوره {بدهی_دوره} تومان"
        rendered = render_resident_sms_template(
            self.resident,
            template,
            today_date=jdatetime.date(1405, 7, 1),
        )
        self.assertIn("سهراب سپهری", rendered)
        self.assertIn("اتاق 205", rendered)
        self.assertIn("1405/06/01", rendered)
        self.assertIn("7,000,000", rendered)
        self.assertIn("3,500,000", rendered)

    def test_default_debt_template_rendering(self):
        rendered = render_resident_sms_template(
            self.resident,
            DEFAULT_DEBT_REMINDER_TEMPLATE,
            today_date=jdatetime.date(1405, 7, 1),
        )
        self.assertIn("سهراب سپهری", rendered)
        self.assertIn("205", rendered)
        self.assertIn("1405/06/01", rendered)
        self.assertIn("اتاق سرپرستی", rendered)

    def test_calculate_sms_parts(self):
        self.assertEqual(calculate_sms_parts(""), 0)
        self.assertEqual(calculate_sms_parts("سلام"), 1)
        self.assertEqual(calculate_sms_parts("a" * 70), 1)
        self.assertEqual(calculate_sms_parts("a" * 71), 2)
        self.assertEqual(calculate_sms_parts("a" * 137), 2)
        self.assertEqual(calculate_sms_parts("a" * 138), 3)
