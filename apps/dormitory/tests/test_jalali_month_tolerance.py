"""
Test suite for Jalali calendar month length dynamics (31, 30, and 29 days)
and the elimination of the ±1 day tolerance trap in settled_until.
"""

import jdatetime
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Resident, Room, Transaction
from apps.dormitory.jalali_utils import (
    get_days_in_jalali_month,
    add_jalali_months,
    normalize_settlement_boundary,
    calculate_settlement_advance,
    format_period_name,
)
from apps.dormitory.services.excel_processor import parse_persian_date_text
from apps.dormitory.services.receipt_processor import process_receipt, calculate_expected_rent_tomans


class JalaliMonthToleranceTests(TestCase):
    """Verify precise calendar length behaviors and zero-drift settlement math."""

    def test_jalali_month_lengths_and_leap_year(self):
        """Verify 31 days for M1-M6, 30 days for M7-M11, and 29/30 for M12."""
        # 1405 is a normal year
        for m in range(1, 7):
            self.assertEqual(get_days_in_jalali_month(1405, m), 31)
        for m in range(7, 12):
            self.assertEqual(get_days_in_jalali_month(1405, m), 30)
        self.assertEqual(get_days_in_jalali_month(1405, 12), 29)

        # 1403 is a leap year (کبیسه)
        self.assertEqual(get_days_in_jalali_month(1403, 12), 30)

    def test_normalize_settlement_boundary(self):
        """Verify normalization of month-end eve dates to 1st of next month for anchor 1."""
        # Mehr 30 (end of 30-day month) -> Aban 1
        d_mehr_end = jdatetime.date(1405, 7, 30)
        self.assertEqual(normalize_settlement_boundary(d_mehr_end, anchor_day=1), jdatetime.date(1405, 8, 1))

        # Shahrivar 31 (end of 31-day month) -> Mehr 1
        d_shah_end = jdatetime.date(1405, 6, 31)
        self.assertEqual(normalize_settlement_boundary(d_shah_end, anchor_day=1), jdatetime.date(1405, 7, 1))

        # Esfand 29 (end of 29-day month) -> Farvardin 1 of next year
        d_esfand_end = jdatetime.date(1405, 12, 29)
        self.assertEqual(normalize_settlement_boundary(d_esfand_end, anchor_day=1), jdatetime.date(1406, 1, 1))

        # Mid-month date should NEVER be modified
        d_mid = jdatetime.date(1405, 7, 15)
        self.assertEqual(normalize_settlement_boundary(d_mid, anchor_day=1), d_mid)

        # Mid-month anchor (e.g. 15) should NOT normalize month-end dates
        self.assertEqual(normalize_settlement_boundary(d_mehr_end, anchor_day=15), d_mehr_end)

    def test_calculate_settlement_advance_starting_from_month_eve(self):
        """
        Verify that paying full month rent when previous settled_until was Mehr 30
        advances cleanly to Azar 1 without the 1-day trap (was stuck at Aban 30).
        """
        start = jdatetime.date(1405, 7, 30)
        rent_rials = 38_000_000

        end_date, days_adv, name = calculate_settlement_advance(
            start_date=start,
            amount_rials=rent_rials,
            monthly_rent_rials=rent_rials,
            anchor_day=1,
        )
        # Should cleanly land on 1405/09/01 (1st of Azar) covering the entire month of Aban
        self.assertEqual(end_date, jdatetime.date(1405, 9, 1))
        self.assertEqual(days_adv, 30)
        self.assertIn("آبان", name)

    def test_anchor_day_31_preservation_across_all_12_months(self):
        """
        Verify anchor day 31 smoothly caps at 30 in Mehr, 29 in Esfand,
        and automatically recovers to 31 in Farvardin without degrading.
        """
        rent_rials = 38_000_000
        cursor = jdatetime.date(1405, 6, 31)

        # Move through Mehr, Aban, Azar, Dey, Bahman, Esfand, Farvardin
        for expected_m, expected_day in [
            (7, 30), (8, 30), (9, 30), (10, 30), (11, 30), (12, 29), (1, 31)
        ]:
            next_y = 1405 if expected_m != 1 else 1406
            end_date, _, _ = calculate_settlement_advance(
                start_date=cursor,
                amount_rials=rent_rials,
                monthly_rent_rials=rent_rials,
                anchor_day=31,
            )
            self.assertEqual(end_date, jdatetime.date(next_y, expected_m, expected_day))
            cursor = end_date

    def test_format_period_name_eve_and_first(self):
        """Verify format_period_name correctly identifies full months whether ending on eve or 1st."""
        # 1405/07/01 to 1405/08/01 -> اجاره مهر ماه ۱۴۰۵
        self.assertEqual(
            format_period_name(jdatetime.date(1405, 7, 1), jdatetime.date(1405, 8, 1)),
            "اجاره مهر ماه ۱۴۰۵"
        )
        # 1405/07/01 to 1405/07/30 (eve) -> اجاره مهر ماه ۱۴۰۵
        self.assertEqual(
            format_period_name(jdatetime.date(1405, 7, 1), jdatetime.date(1405, 7, 30)),
            "اجاره مهر ماه ۱۴۰۵"
        )
        # 1405/07/01 to 1405/08/30 (2 full months ending on eve) -> اجاره مهر و آبان ماه ۱۴۰۵
        self.assertEqual(
            format_period_name(jdatetime.date(1405, 7, 1), jdatetime.date(1405, 8, 30)),
            "اجاره مهر و آبان ماه ۱۴۰۵"
        )

    def test_excel_processor_parse_persian_date_text_month_ends(self):
        """Verify parse_persian_date_text accurately normalizes colloquial month ends."""
        # تا آخر مهر -> 1405/08/01
        self.assertEqual(parse_persian_date_text("تا آخر مهر ماه"), jdatetime.date(1405, 8, 1))
        # تا پایان آبان -> 1405/09/01
        self.assertEqual(parse_persian_date_text("تا پایان آبان"), jdatetime.date(1405, 9, 1))
        # تا ۳۰ مهر -> 1405/08/01
        self.assertEqual(parse_persian_date_text("تا ۳۰ مهر"), jdatetime.date(1405, 8, 1))
        # تا ۳۱ شهریور -> 1405/07/01
        self.assertEqual(parse_persian_date_text("تا ۳۱ شهریور"), jdatetime.date(1405, 7, 1))
        # تا ۲۹ اسفند -> 1406/01/01
        self.assertEqual(parse_persian_date_text("تا ۲۹ اسفند"), jdatetime.date(1406, 1, 1))
        # تا پایان سال -> 1406/01/01
        self.assertEqual(parse_persian_date_text("تا پایان سال تسویه شد"), jdatetime.date(1406, 1, 1))
        # تا ۱۵ آذر (mid-month should remain 15)
        self.assertEqual(parse_persian_date_text("تا ۱۵ آذر"), jdatetime.date(1405, 9, 15))


class ReceiptProcessorSettlementToleranceIntegrationTests(TestCase):
    """Integration tests for receipt processing with month-end dates and audit command."""

    def setUp(self):
        self.dormitory = Dormitory.objects.create(name="خوابگاه نوید")
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318",
        )
        self.room = Room.objects.create(
            room_number=101,
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=38_000_000,
        )
        self.resident = Resident.objects.create(
            first_name="علیرضا",
            last_name="احمدی",
            phone_number="09121111199",
            room=self.room,
            dormitory=self.dormitory,
            registered_by=self.supervisor,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 7, 1),
            monthly_payment_day=1,
            status=Resident.Status.ACTIVE,
        )

    def test_process_receipt_normalizes_explicit_month_end_settled_until(self):
        """
        When user specifies --settled-until '1405-07-30' for a 1st-of-month resident,
        it should normalize to 1405-08-01 without flagging an underpayment discrepancy.
        """
        res = process_receipt(
            resident=self.resident,
            amount_tomans=3_800_000,
            type="RENT",
            settled_until="1405-07-30",
            supervisor_id=self.supervisor.id,
        )

        self.resident.refresh_from_db()
        # Normalized to 1405-08-01
        self.assertEqual(self.resident.settled_until, jdatetime.date(1405, 8, 1))
        # No discrepancy since full month was satisfied
        self.assertIsNone(res.get("discrepancy"))

    def test_audit_settlement_dates_command(self):
        """Verify audit_settlement_dates detects and realigns residents on day 30."""
        # Artificially set settled_until to 1405-08-30 (last day of Aban)
        self.resident.settled_until = jdatetime.date(1405, 8, 30)
        self.resident.save(update_fields=["settled_until"])

        # Run command with --apply
        call_command("audit_settlement_dates", apply=True)

        self.resident.refresh_from_db()
        # Should be realigned to 1405-09-01
        self.assertEqual(self.resident.settled_until, jdatetime.date(1405, 9, 1))
