"""
tests/e2e/fixtures.py
Zero-dependency mock spreadsheet and companion instruction generators.
Uses Python standard library zipfile and XML to produce valid .xlsx and .csv files.
"""

import io
import csv
import zipfile
import hashlib
from pathlib import Path
from typing import List, Any, Optional, Dict, Union, Tuple


def _xml_escape(text: Any) -> str:
    """Escapes special XML characters in string values."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _generate_xlsx_bytes(sheet_name: str, rows: List[List[Any]]) -> bytes:
    """
    Constructs a minimal, strictly standard-compliant OpenXML (.xlsx) archive
    using only Python standard library zipfile.
    Compatible with openpyxl, pandas, Excel, and LibreOffice.
    """
    clean_sheet_name = _xml_escape(sheet_name)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        '  <Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
        '</Types>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>\n'
        '</Relationships>'
    )

    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>\n'
        '</Relationships>'
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <sheets>\n'
        f'    <sheet name="{clean_sheet_name}" sheetId="1" r:id="rId1"/>\n'
        '  </sheets>\n'
        '</workbook>'
    )

    row_xml_parts = []
    for r_idx, row in enumerate(rows, start=1):
        cell_parts = []
        for c_idx, val in enumerate(row, start=1):
            if c_idx <= 26:
                col_letter = chr(64 + c_idx)
            else:
                col_letter = f"{chr(64 + (c_idx - 1) // 26)}{chr(65 + (c_idx - 1) % 26)}"
            ref = f"{col_letter}{r_idx}"

            if val is None or val == "":
                continue
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                cell_parts.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                escaped = _xml_escape(val)
                cell_parts.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')

        row_xml_parts.append(f'<row r="{r_idx}">{" ".join(cell_parts)}</row>')

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'  <sheetData>{" ".join(row_xml_parts)}</sheetData>\n'
        '</worksheet>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)

    return buf.getvalue()


# -----------------------------------------------------------------------------
# Transaction Spreadsheet Generators (ExcelParser Schema)
# -----------------------------------------------------------------------------

DEFAULT_TRANSACTION_HEADERS = [
    "نام مقیم",
    "شماره اتاق",
    "مبلغ اجاره (تومان)",
    "مبلغ ودیعه (تومان)",
    "تاریخ و زمان",
    "اطلاعات رهگیری",
    "روش پرداخت",
    "تسویه تا",
    "توضیحات"
]

DEFAULT_TRANSACTION_ROWS = [
    [
        "امیرعلی محرابیان",
        "101",
        4500000,
        0,
        "1405/08/10 14:30:00",
        "POS-112233",
        "کارتخوان",
        "1405-09-01",
        "اجاره آبان ماه ۱۴۰۵"
    ],
    [
        "محمد افشاری",
        "106",
        5000000,
        0,
        "1405/08/10 15:45:00",
        "CARD-445566",
        "کارتخوان",
        "1405-09-01",
        "اجاره آبان ماه ۱۴۰۵"
    ],
    [
        "سید حسین آقایی",
        "107",
        4000000,
        2000000,
        "1405/08/11 11:20:00",
        "TRANS-778899",
        "کارت به کارت",
        "1405-09-01",
        "اجاره آبان + ودیعه تکمیلی"
    ]
]


def create_valid_transaction_xlsx(
    file_path: Union[str, Path],
    rows: Optional[List[List[Any]]] = None,
    sheet_name: str = "Cleaned_Transactions"
) -> Path:
    """Creates a valid dormitory transaction spreadsheet formatted for ExcelParser."""
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data_rows = rows if rows is not None else DEFAULT_TRANSACTION_ROWS
    full_table = [DEFAULT_TRANSACTION_HEADERS] + data_rows
    content = _generate_xlsx_bytes(sheet_name, full_table)

    target_path.write_bytes(content)
    return target_path


# -----------------------------------------------------------------------------
# Iranian Bank Statement Generators (BankStatementParser Schema)
# -----------------------------------------------------------------------------

DEFAULT_BANK_HEADERS = ["ردیف", "تاریخ/زمان", "شرح", "مبلغ", "نوع", "مانده"]

DEFAULT_BANK_ROWS = [
    [
        1,
        "1405/08/10 10:15:00",
        "انتقال وجه از کارت 6037991827364512 به کارت 5022291082736451 کدپیگیری: 9876543210",
        30000000,
        "واریز",
        150000000
    ],
    [
        2,
        "1405/08/11 16:30:00",
        "دستورپرداخت وارده پل از 12345678 به 87654321 کدپیگیری: 1405081100998877",
        40000000,
        "واریز",
        190000000
    ],
    [
        3,
        "1405/08/12 09:45:00",
        "واریز نقدی از شعبه با کدپیگیری: 5544332211",
        45000000,
        "واریز",
        235000000
    ]
]


def create_valid_bank_statement_xlsx(
    file_path: Union[str, Path],
    rows: Optional[List[List[Any]]] = None,
    bank_name: str = "سامانه بانکداری مهر ایران",
    account_no: str = "1234567890"
) -> Path:
    """Creates a valid Iranian bank statement Excel workbook."""
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_rows = [
        [f"شماره حساب: {account_no}", "", "", "", "", ""],
        [f"منبع گزارش: {bank_name}", "", "", "", "", ""],
        ["از تاریخ 1405/08/01 تا 1405/08/30", "", "", "", "", ""],
        ["", "", "", "", "", ""]
    ]

    data_rows = rows if rows is not None else DEFAULT_BANK_ROWS
    full_table = metadata_rows + [DEFAULT_BANK_HEADERS] + data_rows
    content = _generate_xlsx_bytes("Transactions", full_table)

    target_path.write_bytes(content)
    return target_path


def create_valid_bank_statement_csv(
    file_path: Union[str, Path],
    rows: Optional[List[List[Any]]] = None
) -> Path:
    """Creates a valid Iranian bank statement CSV file."""
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data_rows = rows if rows is not None else DEFAULT_BANK_ROWS

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(DEFAULT_BANK_HEADERS)
        for r in data_rows:
            writer.writerow(r)

    return target_path


# -----------------------------------------------------------------------------
# Malformed / Corrupted Spreadsheet Generators
# -----------------------------------------------------------------------------

def create_malformed_xlsx(
    file_path: Union[str, Path],
    corruption_type: str = "truncated_zip"
) -> Path:
    """Creates corrupted or schema-invalid files for quarantine testing."""
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if corruption_type == "truncated_zip":
        # Truncated PK header
        target_path.write_bytes(b"PK\x03\x04\x00\x00\xff\xff\xde\xad\xbe\xef\xca\xfe\xba\xbe")
    elif corruption_type == "empty":
        target_path.write_bytes(b"")
    elif corruption_type == "non_spreadsheet_text":
        target_path.write_text("This is an unformatted plain text document, not an Excel workbook.\n", encoding="utf-8")
    elif corruption_type == "missing_headers":
        # Valid xlsx structure but missing required schema headers
        junk_rows = [
            ["Data 1", "Data 2", "Data 3"],
            [123, 456, 789],
            [999, 888, 777]
        ]
        target_path.write_bytes(_generate_xlsx_bytes("Sheet1", junk_rows))
    else:
        target_path.write_bytes(b"CORRUPTED_STREAM")

    return target_path


# -----------------------------------------------------------------------------
# Companion Instructions & Deduplication Helpers
# -----------------------------------------------------------------------------

def create_companion_instructions(
    file_path: Union[str, Path],
    instructions_text: Optional[str] = None
) -> Path:
    """Creates a companion markdown instruction file alongside a spreadsheet."""
    p = Path(file_path)
    # If passed a .xlsx, convert stem to <stem>_instructions.md
    if p.suffix.lower() == ".xlsx" or p.suffix.lower() == ".csv":
        target_path = p.parent / f"{p.stem}_instructions.md"
    else:
        target_path = p

    target_path.parent.mkdir(parents=True, exist_ok=True)

    body = instructions_text or (
        "# Batch Spreadsheet Ingestion Instructions\n\n"
        "Please ingest and reconcile this monthly transaction sheet according to the protocol.\n\n"
        "- Period: Aban 1405\n"
        "- Default settlement: Next month 1st\n"
        "- Auto-reconciliation: Enabled\n"
    )

    target_path.write_text(body, encoding="utf-8")
    return target_path


def compute_row_hash(row: List[Any]) -> str:
    """Computes a deterministic SHA-256 hash across row fields."""
    normalized = "|".join(str(val).strip() for val in row if val is not None)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def create_deduplication_pair(path_a: Union[str, Path], path_b: Union[str, Path]) -> Tuple[Path, Path]:
    """
    Creates two batches where Batch B contains an exact duplicate of Batch A's first row
    along with new unique rows.
    """
    p_a = Path(path_a)
    p_b = Path(path_b)

    batch_a_rows = [
        ["امیرعلی محرابیان", "101", 4500000, 0, "1405/08/10 10:00:00", "BATCH-A-01", "کارتخوان", "1405-09-01", "قسط اول"],
        ["محمد افشاری", "106", 5000000, 0, "1405/08/10 10:05:00", "BATCH-A-02", "کارتخوان", "1405-09-01", "قسط اول"],
        ["سید حسین آقایی", "107", 3500000, 0, "1405/08/10 10:10:00", "BATCH-A-03", "کارتخوان", "1405-09-01", "قسط اول"],
    ]

    # Batch B: Row 1 is exact duplicate of Batch A Row 1
    batch_b_rows = [
        ["امیرعلی محرابیان", "101", 4500000, 0, "1405/08/10 10:00:00", "BATCH-A-01", "کارتخوان", "1405-09-01", "قسط اول"],
        ["امیر حسین غفاری", "120", 6000000, 0, "1405/08/10 11:00:00", "BATCH-B-02", "کارتخوان", "1405-09-01", "قسط دوم"],
        ["کمیل باقری قلعه جوقی", "124", 7000000, 0, "1405/08/10 11:15:00", "BATCH-B-03", "کارتخوان", "1405-09-01", "قسط دوم"],
    ]

    create_valid_transaction_xlsx(p_a, rows=batch_a_rows)
    create_valid_transaction_xlsx(p_b, rows=batch_b_rows)
    return p_a, p_b
