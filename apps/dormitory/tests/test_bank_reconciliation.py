import os
import datetime
import tempfile
import zoneinfo
from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone
import jdatetime

from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Room, Resident, Transaction, DailyNote
from apps.dormitory.services.bank_reconciliation import (
    BankStatementParser,
    BankReconciliationEngine,
    BankDepositItem,
    parse_jalali_to_datetime,
    normalize_persian_text,
    TEHRAN_TZ,
)


class BankReconciliationTests(TestCase):
    def setUp(self):
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318",
        )
        self.dormitory = Dormitory.objects.create(
            name="خوابگاه مرکزی",
            address="خیابان اصلی، پلاک ۱",
        )
        self.room = Room.objects.create(
            dormitory=self.dormitory,
            room_number=101,
            capacity=4,
            monthly_rent=38_000_000,  # 3.8M Tomans in Rials
        )
        self.resident1 = Resident.objects.create(
            dormitory=self.dormitory,
            room=self.room,
            first_name="محمد",
            last_name="افشاری",
            national_code="0011223344",
            phone_number="09121111111",
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )
        self.resident2 = Resident.objects.create(
            dormitory=self.dormitory,
            room=self.room,
            first_name="هادی",
            last_name="جلالی",
            national_code="0022334455",
            phone_number="09122222222",
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )
        self.resident_fake = Resident.objects.create(
            dormitory=self.dormitory,
            room=self.room,
            first_name="رضا",
            last_name="مشکوک",
            national_code="0033445566",
            phone_number="09123333333",
            entry_date=jdatetime.date(1405, 7, 1),
            registered_by=self.supervisor,
            status=Resident.Status.ACTIVE,
        )

    def test_parser_single_lines_and_extraction(self):
        csv_content = """شماره حساب: 362470005745164001,,,,,,,,,زمان گزارش: 1405/08/13 ساعت 11:58,,
"موجودی کل: 1,599,389 ریال",,,,,,,,,از تاریخ 1405/07/01 تا 1405/07/30 ,,
منبع گزارش: همراه بانک مهر ایران,,,,,,,,,,
ردیف,توضیح,,,,,مبلغ (ریال),,نوع,زمان تراکنش,,مانده
,,,,,,,,,,,
1,انتقال از 5894631257202200 به 6063731058230666 با کدرهگيري 938146 ,,,,,42000000,,واریز,1405/07/26 13:19,,49604132
2,دستورپرداخت وارده پل کدپيگيري 140507230123212936974 ازبانک ملت به بانک قرض الحسنه مهر ايران به شباي IR020120020000001211397143 ,,,,,10000000,,واریز,1405/07/23 21:29,,13421682
3,دستور پرداخت وارده (شاپرکي) شاپرکDRPA-EMPTY*000000011000ش واريزEMPTY ش فIR150930000000000001006182پ050812091100000021155132247729مرکزشاپرک,,,,,47000000,,واریز,1405/08/13 06:54,,48610839
4,انتقال وجه اينترنتي از سپرده 100446417528 به سپرده 362470005745164001 ,,,,,48000000,,واریز,1405/08/06 18:00,,49621782
5,خرید از کارتخوان ,,,,,5000000,,برداشت,1405/08/01 10:00,,40000000
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            parser = BankStatementParser(temp_path)
            items = parser.parse()

            # Row 5 is 'برداشت' (withdrawal), so it must be ignored
            self.assertEqual(len(items), 4)

            # Metadata check
            self.assertEqual(parser.metadata.get("account_number"), "362470005745164001")
            self.assertEqual(parser.metadata.get("date_from"), "1405/07/01")
            self.assertEqual(parser.metadata.get("date_to"), "1405/07/30")

            # Item 1: Card transfer
            it1 = items[0]
            self.assertEqual(it1.row_id, 1)
            self.assertEqual(it1.amount_rials, 42_000_000)
            self.assertEqual(it1.amount_tomans, 4_200_000)
            self.assertEqual(it1.tracking_code, "938146")
            self.assertEqual(it1.origin_card, "5894631257202200")
            self.assertEqual(it1.origin_card_last4, "2200")
            self.assertEqual(it1.deposit_category, "CARD")

            # Item 2: Pol transfer
            it2 = items[1]
            self.assertEqual(it2.tracking_code, "140507230123212936974")
            self.assertEqual(it2.deposit_category, "POL")
            self.assertEqual(it2.deposit_iban, "IR020120020000001211397143")

            # Item 3: Shaparak batch
            it3 = items[2]
            self.assertEqual(it3.deposit_category, "SHAPARAK")
            self.assertTrue(it3.tracking_code.startswith("050812"))

            # Item 4: Internal account transfer
            it4 = items[3]
            self.assertEqual(it4.deposit_category, "INTERNAL")
            self.assertEqual(it4.origin_account, "100446417528")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_reconciliation_tier1_exact_tracking_code(self):
        # Create DB transaction with pre-recorded reference number
        tx_date = jdatetime.datetime(1405, 7, 26, 13, 19, 0, tzinfo=TEHRAN_TZ)
        tx = Transaction.objects.create(
            resident=self.resident1,
            dormitory=self.dormitory,
            amount=42_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
            payment_date=tx_date,
            reference_number="رسید بانکی با کد 938146",
            is_approved=True,
            created_by=self.supervisor,
        )

        b_item = BankDepositItem(
            row_id=1,
            description="انتقال از 5894631257202200 با کدرهگیری 938146",
            amount_rials=42_000_000,
            transaction_type="واریز",
            jalali_datetime_str="1405/07/26 13:19",
            jalali_dt=tx_date,
            gregorian_dt=tx_date.togregorian(),
            tracking_code="938146",
            origin_card="5894631257202200",
            origin_card_last4="2200",
            deposit_category="CARD",
        )

        engine = BankReconciliationEngine([b_item])
        summary = engine.run()

        self.assertEqual(summary["verified_count"], 1)
        self.assertEqual(len(engine.verified_matches), 1)
        match = engine.verified_matches[0]
        self.assertEqual(match.tier, 1)
        self.assertEqual(match.confidence_score, 100)
        self.assertEqual(match.transaction.id, tx.id)

    def test_reconciliation_tier2_smart_proximity(self):
        # Create DB transaction without tracking code, but matching amount and close timestamp
        tx_date = jdatetime.datetime(1405, 7, 16, 0, 1, 0, tzinfo=TEHRAN_TZ)
        tx = Transaction.objects.create(
            resident=self.resident2,
            dormitory=self.dormitory,
            amount=33_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
            payment_date=tx_date,
            reference_number="",  # No reference number yet
            is_approved=False,
            created_by=self.supervisor,
        )

        # Bank deposit timestamp is 1 minute earlier
        bank_date = jdatetime.datetime(1405, 7, 16, 0, 0, 0, tzinfo=TEHRAN_TZ)
        b_item = BankDepositItem(
            row_id=94,
            description="انتقال از 6219861927846989 به 6063731058230666 با کدرهگيري 738122",
            amount_rials=33_000_000,
            transaction_type="واریز",
            jalali_datetime_str="1405/07/16 00:00",
            jalali_dt=bank_date,
            gregorian_dt=bank_date.togregorian(),
            tracking_code="738122",
            origin_card="6219861927846989",
            origin_card_last4="6989",
            deposit_category="CARD",
        )

        engine = BankReconciliationEngine([b_item])
        summary = engine.run()

        self.assertEqual(summary["verified_count"], 1)
        self.assertEqual(len(engine.verified_matches), 1)
        match = engine.verified_matches[0]
        self.assertEqual(match.tier, 2)
        self.assertGreaterEqual(match.confidence_score, 90)
        self.assertAlmostEqual(match.time_diff_minutes, 1.0, delta=0.5)

        # Test apply updates
        db_res = engine.apply_updates(self.supervisor)
        self.assertEqual(db_res["verified_updated"], 1)

        tx.refresh_from_db()
        self.assertTrue(tx.is_approved)
        self.assertIn("738122", tx.reference_number)
        self.assertIn("6989", tx.reference_number)

    def test_fraud_fake_receipt_detection(self):
        # Create a suspicious transaction claiming to have paid, but no matching money entered bank
        tx_date = jdatetime.datetime(1405, 7, 20, 10, 0, 0, tzinfo=TEHRAN_TZ)
        fake_tx = Transaction.objects.create(
            resident=self.resident_fake,
            dormitory=self.dormitory,
            amount=50_000_000,
            transaction_type=Transaction.TransactionType.RENT,
            payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
            payment_date=tx_date,
            reference_number="فیش ساختگی ۹۹۹۹۹",
            is_approved=True,
            created_by=self.supervisor,
        )

        # Bank has only completely different transactions (different date/amount)
        bank_date = jdatetime.datetime(1405, 7, 20, 10, 0, 0, tzinfo=TEHRAN_TZ)
        real_item = BankDepositItem(
            row_id=1,
            description="انتقال با کدرهگیری 111111",
            amount_rials=10_000_000,  # 10M instead of 50M
            transaction_type="واریز",
            jalali_datetime_str="1405/07/20 10:00",
            jalali_dt=bank_date,
            gregorian_dt=bank_date.togregorian(),
            tracking_code="111111",
            deposit_category="CARD",
        )

        engine = BankReconciliationEngine([real_item], start_date=jdatetime.date(1405, 7, 19), end_date=jdatetime.date(1405, 7, 21))
        summary = engine.run()

        self.assertEqual(summary["verified_count"], 0)
        self.assertEqual(summary["unverified_count"], 1)
        self.assertEqual(engine.unverified_transactions[0].id, fake_tx.id)

        # Apply updates
        db_res = engine.apply_updates(self.supervisor)
        self.assertEqual(db_res["unverified_flagged"], 1)
        self.assertEqual(db_res["warning_notes_created"], 1)

        fake_tx.refresh_from_db()
        self.assertFalse(fake_tx.is_approved)

        # Verify DailyNote was created
        note = DailyNote.objects.filter(resident=self.resident_fake).first()
        self.assertIsNotNone(note)
        self.assertEqual(note.note_type, DailyNote.NoteType.DISCIPLINARY)
        self.assertIn(f"تراکنش #{fake_tx.id}", note.title)
        self.assertIn("مغایرت بانکی", note.title)
        self.assertIn("5,000,000 تومان", note.content)

    def test_management_command_execution(self):
        # Test full command invocation with report export
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "sample_bank_statement.csv"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as f:
            report_out = f.name

        try:
            call_command(
                "reconcile_bank_statement",
                file=fixture_path,
                export_report=report_out,
            )
            self.assertTrue(os.path.exists(report_out))
            with open(report_out, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("گزارش جامع مغایرت‌گیری صورت‌حساب بانکی", content)
            self.assertIn("خلاصه آمار عملکرد", content)
        finally:
            if os.path.exists(report_out):
                os.remove(report_out)
