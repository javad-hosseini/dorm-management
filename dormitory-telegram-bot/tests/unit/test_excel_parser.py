"""Unit tests for Excel parser validation, noise filtering, and failed rows reports."""

import datetime
from pathlib import Path
import openpyxl
import pytest

from src.services.excel_parser import ExcelParser


def test_valid_parsing_and_date_normalization(tmp_path: Path):
    """Verify parsing multi-row spreadsheet, trimming headers, and normalizing dates to ISO-8601."""
    file_path = tmp_path / "valid_transactions.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dorm_Ledger"

    # Headers with extra whitespace to verify stripping
    ws.append(["  Room Number ", " Resident Name  ", "Amount_IRR", "Transaction_Date "])
    ws.append([101, "Ali Hosseini", 4500000, datetime.date(2026, 11, 4)])
    ws.append([102, "Sara Karimi", 7500000, datetime.datetime(2026, 11, 4, 14, 30)])

    wb.save(file_path)

    parser = ExcelParser()
    parsed = parser.parse_cleaned_workbook(file_path)

    assert parsed.file_name == "valid_transactions.xlsx"
    assert parsed.sheet_name == "Dorm_Ledger"
    assert parsed.headers == ["Room Number", "Resident Name", "Amount_IRR", "Transaction_Date"]
    assert len(parsed.rows) == 2
    assert len(parsed.row_hashes) == 2

    # Check date conversion
    assert parsed.rows[0]["Transaction_Date"] == "2026-11-04"
    assert parsed.rows[1]["Transaction_Date"] == "2026-11-04T14:30:00"


def test_noise_filtering_and_guide_sheet_ignored(tmp_path: Path):
    """Verify that empty rows are skipped and metadata guide sheets are ignored."""
    file_path = tmp_path / "noise_test.xlsx"
    wb = openpyxl.Workbook()

    # Data sheet
    ws_data = wb.active
    ws_data.title = "Cleaned_Data"
    ws_data.append(["Room", "Amount"])
    ws_data.append([101, 5000000])
    ws_data.append([None, None])  # Blank row
    ws_data.append(["   ", "   "])  # Whitespace blank row
    ws_data.append([102, 6000000])

    # Metadata tab to be ignored
    ws_guide = wb.create_sheet(title="_AI_EXTRACTION_GUIDE")
    ws_guide.append(["Ignore This Metadata"])

    wb.save(file_path)

    parser = ExcelParser()
    parsed = parser.parse_cleaned_workbook(file_path)

    assert parsed.sheet_name == "Cleaned_Data"
    assert len(parsed.rows) == 2
    assert parsed.rows[0]["Room"] == 101
    assert parsed.rows[1]["Room"] == 102


def test_invalid_file_handling(tmp_path: Path):
    """Verify clean descriptive ValueError raised for missing header, zero data rows, or corrupt bytes."""
    parser = ExcelParser()

    # 1. Corrupted binary bytes
    corrupt_file = tmp_path / "corrupt.xlsx"
    corrupt_file.write_bytes(b"NOT_A_VALID_ZIP_OR_XLSX_DATA")
    with pytest.raises(ValueError, match="Invalid or corrupted Excel spreadsheet"):
        parser.parse_cleaned_workbook(corrupt_file)

    # 2. Empty workbook with zero data rows
    empty_file = tmp_path / "empty_no_rows.xlsx"
    wb_empty = openpyxl.Workbook()
    ws = wb_empty.active
    ws.append(["Room", "Amount"])  # Only header, no data rows
    wb_empty.save(empty_file)

    with pytest.raises(ValueError, match="Spreadsheet contains zero valid data rows"):
        parser.parse_cleaned_workbook(empty_file)

    # 3. Missing header row
    no_header_file = tmp_path / "no_header.xlsx"
    wb_no_header = openpyxl.Workbook()
    wb_no_header.save(no_header_file)
    with pytest.raises(ValueError, match="Spreadsheet is completely empty|header row is missing"):
        parser.parse_cleaned_workbook(no_header_file)


def test_failed_rows_report_generation(tmp_path: Path):
    """Verify generation of failed_rows_report.xlsx with original columns plus Error_Reason."""
    parser = ExcelParser()
    output_path = tmp_path / "failed_rows_report.xlsx"

    headers = ["Room", "Resident", "Amount"]
    failed_items = [
        ({"Room": 105, "Resident": "Ali", "Amount": "invalid_num"}, "Non-numeric amount"),
        ({"Room": "", "Resident": "Unknown", "Amount": 4000000}, "Missing room number"),
        ({"Room": 202, "Resident": "Reza", "Amount": -1000}, "Negative amount not allowed"),
    ]

    report = parser.generate_failed_rows_report(headers, failed_items, output_path)
    assert report.exists()

    wb = openpyxl.load_workbook(report)
    ws = wb.active
    assert ws.title == "Failed_Transactions"

    # Header check
    assert [cell.value for cell in ws[1]] == ["Room", "Resident", "Amount", "Error_Reason"]

    # Exactly 3 failed rows
    assert ws.max_row == 4  # 1 header + 3 data rows
    assert ws.cell(row=2, column=4).value == "Non-numeric amount"
    assert ws.cell(row=3, column=4).value == "Missing room number"
    assert ws.cell(row=4, column=4).value == "Negative amount not allowed"

