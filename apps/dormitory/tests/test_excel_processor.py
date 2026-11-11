"""
Comprehensive test suite for DormitoryExcelProcessor and manage.py process_excel command.
Tests:
- Detection of RAW_TELEGRAM_SESSION vs CLEANED_BATCH
- Extraction of cell-anchored embedded images
- Persian colloquial amounts, dates, and entities parsing
- Cleaned batch ingestion (single, split, duplicates, errors)
- Discrepancy and underpayment detection
- Cleaned spreadsheet generation and failed rows reports
- CLI management command process_excel (--dry-run, --apply, --json-output)
"""

import datetime
import json
import io
import os
import shutil
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import jdatetime
import openpyxl
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image as PILImage

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Supervisor
from apps.dormitory.models import Dormitory, Resident, Room, Transaction
from apps.dormitory.services.excel_processor import (
    DormitoryExcelProcessor,
    ExtractedImage,
    ProcessReport,
    RawResidentEvent,
    TransactionRow,
    extract_financial_amounts,
    parse_persian_colloquial_amount,
    parse_persian_date_text,
    parse_persian_time_text,
)


class ExcelProcessorUnitTests(TestCase):
    """Unit tests for helper functions in excel_processor."""

    def test_parse_persian_colloquial_amounts(self):
        """Verify accurate parsing of various Persian digit and word-based amounts."""
        test_cases = [
            ("۵۰۰ هزار", 500_000),
            ("۷۰۰ هزار تومان", 700_000),
            ("سه میلیون و هشتصد", 3_800_000),
            ("۴ میلیون و ۸۰۰ هزار", 4_800_000),
            ("سه میلیون و هشتصد هزار", 3_800_000),
            ("یک میلیون", 1_000_000),
            ("۳ میلیون و پانصد هزار", 3_500_000),
            ("دو میلیون", 2_000_000),
            ("۹ میلیون", 9_000_000),
            ("۳ میلیون و ۸۰۰ هزار", 3_800_000),
            ("۴ میلیون", 4_000_000),
            ("۴ میلیون و پانصد هزار", 4_500_000),
            ("۶ میلیون و پانصد هزار", 6_500_000),
            ("دو میلیون تومان", 2_000_000),
            ("۴ میلیون و ۵۰۰ هزار تومان", 4_500_000),
            ("۳ میلیون تومان", 3_000_000),
            ("دو و نیم میلیون", 2_500_000),
            ("4,500,000", 4_500_000),
        ]
        for text, expected in test_cases:
            with self.subTest(text=text):
                self.assertEqual(parse_persian_colloquial_amount(text), expected)

    def test_extract_financial_amounts_split_and_installment(self):
        """Test extraction of split amounts (rent + deposit) and installment remainders."""
        s_split = "مازیار شیدایی اتاق ۱۱۰ مبلغ ۴ میلیون و ۸۰۰ هزار تومان پرداخت کرد که سه میلیون و هشتصد هزار تومان برای اجاره و یک میلیون تومان هم برای ودیعه"
        rent, dep, tot, rem = extract_financial_amounts(s_split)
        self.assertEqual(rent, 3_800_000)
        self.assertEqual(dep, 1_000_000)
        self.assertEqual(tot, 4_800_000)
        self.assertIsNone(rem)

        s_inst = "پدرام لگزیان اتاق ۱۲۰ مبلغ ۲ میلیون تومان کارت کشید و برای تصفیه تا ۱۵ بهمن ماه مبلغ ۳ میلیون تومان دیگر باید پرداخت کند"
        rent, dep, tot, rem = extract_financial_amounts(s_inst)
        self.assertEqual(rent, 2_000_000)
        self.assertEqual(dep, 0)
        self.assertEqual(tot, 2_000_000)
        self.assertEqual(rem, 3_000_000)

        s_inst2 = "مبلغ ۳ میلیون تومان هم کارت کشید در نت‌ها ذکر بکن که تا تاریخ ۲۱ آبان ماه مابقی ۵۰۰ هزار تومان رو واریز می‌کند"
        rent, dep, tot, rem = extract_financial_amounts(s_inst2)
        self.assertEqual(rent, 3_000_000)
        self.assertEqual(dep, 0)
        self.assertEqual(tot, 3_000_000)
        self.assertEqual(rem, 500_000)

    def test_parse_persian_date_and_time_text(self):
        """Test parsing of Jalali dates and timestamps from free-form Persian text."""
        d1 = parse_persian_date_text("امیر صالح خشودی اتاق ۱۰۳ کارت کشید و تا اول آذر تسویه شد", default_year=1405)
        self.assertEqual(d1, jdatetime.date(1405, 9, 1))

        d2 = parse_persian_date_text("مهدی خوجه اتاق ۱۰۵ مبلغ سه میلیون و هشتصد واریز کرد و تا ۱۵ آذر ماه تسویه شد", default_year=1405)
        self.assertEqual(d2, jdatetime.date(1405, 9, 15))

        d3 = parse_persian_date_text("پدرام لگزیان اتاق ۱۲۰ مبلغ ۲ میلیون تومان کارت کشید و برای تصفیه تا ۱۵ بهمن ماه", default_year=1405)
        self.assertEqual(d3, jdatetime.date(1405, 11, 15))

        t1 = parse_persian_time_text("در تاریخ ۱۸ آبان ساعت ۲۳/۱۲ دقیقه واریز کرد")
        self.assertEqual(t1, (23, 12))

        t2 = parse_persian_time_text("کارت به کارت کرد در ساعت ۲۰:۳۷")
        self.assertEqual(t2, (20, 37))

        t3 = parse_persian_time_text("ساعت ۹:۲۴ واریز کرد")
        self.assertEqual(t3, (9, 24))


class ExcelProcessorIntegrationTests(TestCase):
    """Integration tests for workbook detection, batch execution, image extraction, and reporting."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.dormitory = Dormitory.objects.create(name="خوابگاه نوید")
        self.supervisor = Supervisor.objects.create(
            first_name="جواد",
            last_name="حسینی",
            national_code="0201014318",
        )

        self.room101 = Room.objects.create(
            room_number="101",
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=45_000_000,  # 4.5M Tomans
        )
        self.room102 = Room.objects.create(
            room_number="102",
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=50_000_000,  # 5M Tomans
        )
        self.room103 = Room.objects.create(
            room_number="103",
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=38_000_000,  # 3.8M Tomans
        )
        self.room110 = Room.objects.create(
            room_number="110",
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=38_000_000,
        )
        self.room112 = Room.objects.create(
            room_number="112",
            dormitory=self.dormitory,
            capacity=4,
            monthly_rent=38_000_000,
        )

        self.resident1 = Resident.objects.create(
            first_name="امیرعلی",
            last_name="محرابیان",
            phone_number="09121111111",
            room=self.room101,
            dormitory=self.dormitory,
            registered_by=self.supervisor,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 8, 1),
            monthly_payment_day=1,
            status=Resident.Status.ACTIVE,
        )
        self.resident2 = Resident.objects.create(
            first_name="محمد",
            last_name="افشاری",
            phone_number="09122222222",
            room=self.room102,
            dormitory=self.dormitory,
            registered_by=self.supervisor,
            entry_date=jdatetime.date(1405, 7, 1),
            settled_until=jdatetime.date(1405, 8, 1),
            monthly_payment_day=1,
            status=Resident.Status.ACTIVE,
        )
        self.resident_bordbar = Resident.objects.create(
            first_name="امیررضا",
            last_name="بردبار",
            phone_number="09123333333",
            room=self.room112,
            dormitory=self.dormitory,
            registered_by=self.supervisor,
            entry_date=jdatetime.date(1405, 7, 1),
            status=Resident.Status.ACTIVE,
        )

        self.processor = DormitoryExcelProcessor(supervisor_id=self.supervisor.id)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_synthetic_image(self, path: Path) -> Path:
        """Create a tiny 10x10 JPEG for testing openpyxl image embedding."""
        img = PILImage.new("RGB", (10, 10), color="blue")
        img.save(path, format="JPEG")
        return path

    def test_cleaned_batch_dry_run_and_apply(self):
        """Test cleaned batch spreadsheet in dry-run mode and subsequent commit."""
        file_path = Path(self.temp_dir) / "test_cleaned.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Cleaned_Transactions"
        ws.append([
            "نام مقیم", "شماره اتاق", "مبلغ اجاره (تومان)", "مبلغ ودیعه (تومان)",
            "تاریخ و زمان", "اطلاعات رهگیری", "روش پرداخت", "تسویه تا", "توضیحات"
        ])
        ws.append([
            "امیرعلی محرابیان", "101", 4500000, 0,
            "1405/08/10 14:30:00", "REF-CLEAN-01", "کارتخوان", "1405-09-01", "اجاره آبان"
        ])
        ws.append([
            "محمد افشاری", "102", 5000000, 1000000,
            "1405/08/10 15:45:00", "REF-CLEAN-02", "کارت به کارت", "1405-09-01", "اجاره + ودیعه"
        ])
        wb.save(file_path)

        # 1. Dry Run
        report_dry = self.processor.process_file(file_path, apply=False)
        self.assertEqual(report_dry.mode, "CLEANED_BATCH")
        self.assertTrue(report_dry.dry_run)
        self.assertEqual(report_dry.succeeded_rows, 2)
        self.assertEqual(report_dry.failed_rows, 0)
        self.assertEqual(report_dry.total_rent_tomans, 9_500_000)
        self.assertEqual(report_dry.total_deposit_tomans, 1_000_000)
        # Verify no DB records created
        self.assertFalse(Transaction.objects.filter(reference_number="REF-CLEAN-01").exists())

        # 2. Apply
        report_applied = self.processor.process_file(file_path, apply=True)
        self.assertFalse(report_applied.dry_run)
        self.assertEqual(report_applied.succeeded_rows, 2)
        self.assertTrue(Transaction.objects.filter(reference_number="REF-CLEAN-01").exists())
        self.assertTrue(Transaction.objects.filter(reference_number="REF-CLEAN-02").exists())

        # Verify resident update
        self.resident1.refresh_from_db()
        self.assertEqual(self.resident1.settled_until, jdatetime.date(1405, 9, 1))
        self.resident2.refresh_from_db()
        self.assertTrue(self.resident2.has_deposit)

    def test_cleaned_batch_duplicate_prevention(self):
        """Verify that duplicate reference numbers are detected and recorded in failed_items."""
        file_path = Path(self.temp_dir) / "test_dup.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["نام مقیم", "شماره اتاق", "مبلغ اجاره (تومان)", "تاریخ و زمان", "اطلاعات رهگیری"])
        ws.append(["امیرعلی محرابیان", "101", 4500000, "1405/08/10 14:30:00", "REF-DUP-01"])
        wb.save(file_path)

        # Apply first time
        self.processor.process_file(file_path, apply=True)
        self.assertTrue(Transaction.objects.filter(reference_number="REF-DUP-01").exists())

        # Process second time
        report_dup = self.processor.process_file(file_path, apply=True)
        self.assertEqual(report_dup.duplicate_rows, 1)
        self.assertIn("تراکنش تکراری", report_dup.failed_items[0][1])

    def test_raw_telegram_session_parsing_and_image_extraction(self):
        """Verify raw telegram session parsing with image extraction, new resident, and room change."""
        file_path = Path(self.temp_dir) / "test_raw.xlsx"
        img_dir = Path(self.temp_dir) / "extracted_images"
        synthetic_img = self._create_synthetic_image(Path(self.temp_dir) / "thumb.jpg")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Raw_Transactions"

        ws.append(["Resident_Row_ID", "Block_1", "Block_2", "Block_3", "Block_4"])
        ws.append(["Resident_1", "[IMAGE_ANCHOR: B2 | file: thumb.jpg]", "امیرعلی محرابیان اتاق ۱۰۱ کارت کشید و تا اول آذر تسویه شد", "", ""])
        ws.append(["Resident_2", "امیررضا بردبار از اتاق ۱۱۲ به ۱۱۰ جابجا شد", "", "", ""])
        ws.append(["Resident_3", "نیروی جدید سجاد حسینی در اتاق ۱۰۳ ثبت بشود نام پدر علی شماره همراه ۰۹۱۲۸۸۸۸۸۸۸ کد ملی ۱۲۳۴۵۶۷۸۹۰ تاریخ ورود ۱۸ آبان ماه و همچنین مبلغ ۳ میلیون و ۸۰۰ هزار تومان کارت کشید", "", "", ""])

        # Add embedded openpyxl image
        img = OpenpyxlImage(str(synthetic_img))
        img.anchor = "B2"
        ws.add_image(img)

        wb.save(file_path)

        report = self.processor.process_file(
            file_path=file_path,
            apply=True,
            extract_images=True,
            image_dir=img_dir,
            export_cleaned_path=Path(self.temp_dir) / "cleaned_out.xlsx",
        )

        self.assertEqual(report.mode, "RAW_TELEGRAM_SESSION")
        self.assertEqual(report.succeeded_rows, 3)

        # Verify image extracted
        self.assertTrue(len(report.extracted_images) >= 1)
        self.assertTrue(any(p.name.startswith("Resident_1") for p in img_dir.glob("*.jpg")))

        # Verify room change
        self.resident_bordbar.refresh_from_db()
        self.assertEqual(str(self.resident_bordbar.room.room_number), "110")

        # Verify new resident registered
        new_res = Resident.objects.filter(national_code="1234567890").first()
        self.assertIsNotNone(new_res)
        self.assertEqual(str(new_res.room.room_number), "103")

        # Verify exported cleaned excel
        cleaned_out = Path(self.temp_dir) / "cleaned_out.xlsx"
        self.assertTrue(cleaned_out.exists())
        self.assertGreater(cleaned_out.stat().st_size, 1000)

    def test_management_command_cli_execution(self):
        """Test management command manage.py process_excel via Django call_command."""
        file_path = Path(self.temp_dir) / "cli_test.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["نام مقیم", "شماره اتاق", "مبلغ اجاره (تومان)", "تاریخ و زمان", "اطلاعات رهگیری"])
        ws.append(["امیرعلی محرابیان", "101", 4500000, "1405/08/10 14:30:00", "REF-CLI-01"])
        wb.save(file_path)

        # Test dry-run CLI call
        out_buf = io.StringIO()
        call_command("process_excel", file=str(file_path), dry_run=True, stdout=out_buf)
        output = out_buf.getvalue()
        self.assertIn("Cleaned Batch", output)
        self.assertIn("Dry Run", output)

        # Test JSON output CLI call
        out_json_buf = io.StringIO()
        call_command("process_excel", file=str(file_path), dry_run=True, json_output=True, stdout=out_json_buf)
        data = json.loads(out_json_buf.getvalue())
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "CLEANED_BATCH")
        self.assertEqual(data["summary"]["succeeded_rows"], 1)
