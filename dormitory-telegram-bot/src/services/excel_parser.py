"""Excel parser for extracting cleaned dormitory transaction tables and generating error reports."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


@dataclass
class ParsedSheetData:
    """Represents parsed transaction rows from a cleaned spreadsheet."""

    file_name: str
    file_hash: str
    sheet_name: str
    headers: List[str]
    rows: List[Dict[str, Any]]  # List of {col_name: value}
    row_hashes: List[str]  # Parallel list of SHA-256 hashes per row


class ExcelParser:
    """Parses cleaned transaction sheets and produces error report workbooks."""

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Calculate the SHA-256 checksum of an uploaded file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def compute_row_hash(file_hash: str, row_index: int, row_data: Dict[str, Any]) -> str:
        """Generate a deterministic SHA-256 hash for a single row."""
        canonical_json = json.dumps(row_data, sort_keys=True, default=str)
        payload = f"{file_hash}:{row_index}:{canonical_json}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def parse_cleaned_workbook(
        self, file_path: Path, original_file_name: Optional[str] = None
    ) -> ParsedSheetData:
        """Parse the first data sheet of an uploaded workbook into a structured list of dictionaries."""
        file_hash = self.compute_file_hash(file_path)
        display_name = original_file_name or file_path.name

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
        except Exception as exc:
            raise ValueError(f"Invalid or corrupted Excel spreadsheet: {exc}") from exc

        # Select the target sheet, avoiding meta tabs like _AI_EXTRACTION_GUIDE
        target_ws: Optional[openpyxl.worksheet.worksheet.Worksheet] = None
        for sheet_name in wb.sheetnames:
            if not sheet_name.startswith("_") and sheet_name.lower() != "guide":
                target_ws = wb[sheet_name]
                break

        if target_ws is None:
            target_ws = wb.active

        sheet_title = target_ws.title
        rows_iter = list(target_ws.iter_rows(values_only=True))

        if not rows_iter:
            wb.close()
            raise ValueError("Spreadsheet is completely empty and missing header row.")

        # Row 1: Headers
        raw_headers = rows_iter[0]
        if not raw_headers or all(h is None or not str(h).strip() for h in raw_headers):
            wb.close()
            raise ValueError("Spreadsheet header row is missing or empty.")

        headers: List[str] = []
        for i, h in enumerate(raw_headers):
            if h is not None and str(h).strip():
                headers.append(str(h).strip())
            else:
                headers.append(f"Column_{i + 1}")

        parsed_rows: List[Dict[str, Any]] = []
        row_hashes: List[str] = []

        # Subsequent rows
        for row_idx, row_values in enumerate(rows_iter[1:], start=2):
            if not row_values:
                continue

            # Check if entire row is empty
            if all(v is None or (isinstance(v, str) and not v.strip()) for v in row_values):
                continue

            row_dict: Dict[str, Any] = {}
            for col_idx, col_name in enumerate(headers):
                val = row_values[col_idx] if col_idx < len(row_values) else None

                # Normalize datetimes/dates to ISO-8601 strings
                if isinstance(val, datetime.datetime):
                    if val.time() == datetime.time(0, 0, 0):
                        val = val.date().isoformat()
                    else:
                        val = val.isoformat()
                elif isinstance(val, datetime.date):
                    val = val.isoformat()
                elif isinstance(val, str):
                    val = val.strip()

                row_dict[col_name] = val

            r_hash = self.compute_row_hash(file_hash, row_idx, row_dict)
            parsed_rows.append(row_dict)
            row_hashes.append(r_hash)

        wb.close()

        if not parsed_rows:
            raise ValueError("Spreadsheet contains zero valid data rows.")

        return ParsedSheetData(
            file_name=display_name,
            file_hash=file_hash,
            sheet_name=sheet_title,
            headers=headers,
            rows=parsed_rows,
            row_hashes=row_hashes,
        )

    def generate_failed_rows_report(
        self,
        headers: List[str],
        failed_items: List[Tuple[Dict[str, Any], str]],
        output_path: Path,
    ) -> Path:
        """Create an Excel report containing only the failed rows with an 'Error_Reason' column."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Failed_Transactions"

        report_headers = list(headers) + ["Error_Reason"]
        ws.append(report_headers)

        header_font = Font(name="Calibri", size=11, bold=True, color="1F497D")
        header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        error_header_fill = PatternFill(
            start_color="FCE4D6", end_color="FCE4D6", fill_type="solid"
        )
        error_header_font = Font(name="Calibri", size=11, bold=True, color="C00000")

        thin_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3"),
        )

        for col_idx, col_name in enumerate(report_headers, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if col_name == "Error_Reason":
                cell.font = error_header_font
                cell.fill = error_header_fill
            else:
                cell.font = header_font
                cell.fill = header_fill

        ws.row_dimensions[1].height = 28

        # Populate failed rows
        for row_idx, (row_data, error_reason) in enumerate(failed_items, start=2):
            row_vals: List[Any] = []
            for col_name in headers:
                row_vals.append(row_data.get(col_name, ""))
            row_vals.append(error_reason)
            ws.append(row_vals)

            ws.row_dimensions[row_idx].height = 24
            for c_idx in range(1, len(report_headers) + 1):
                c = ws.cell(row=row_idx, column=c_idx)
                c.border = thin_border
                c.font = Font(name="Calibri", size=10)
                if c_idx == len(report_headers):
                    c.font = Font(name="Calibri", size=10, color="C00000", italic=True)

        # Auto-adjust column widths
        for col_idx, col_name in enumerate(report_headers, start=1):
            letter = get_column_letter(col_idx)
            max_len = max(
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(1, len(failed_items) + 2)
            )
            ws.column_dimensions[letter].width = max(max_len + 4, 15)

        wb.save(output_path)
        return output_path
