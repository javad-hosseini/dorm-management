"""Excel workbook builder generating cell-anchored raw spreadsheets with embedded receipt photos."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import openpyxl
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage, ImageOps

from src.database.repository import BlockRecord

logger = logging.getLogger(__name__)

EXTRACTION_GUIDE_CODE = '''import openpyxl

wb = openpyxl.load_workbook("raw_transactions.xlsx")
ws = wb["Raw_Transactions"]

# Map embedded receipt images to exact resident row and block column
image_map = {}
for img in ws._images:
    # 0-indexed row & col converted to 1-indexed Excel coordinates
    row = img.anchor._from.row + 1
    col = img.anchor._from.col + 1
    resident_id = ws.cell(row=row, column=1).value
    coord = ws.cell(row=row, column=col).coordinate
    image_map.setdefault(resident_id, []).append({
        "cell": coord,
        "image_data": img._data(),  # Raw bytes for OCR / LLM Vision processing
    })

print(f"Extracted {len(ws._images)} images across {len(image_map)} residents.")
'''


class ExcelBuilder:
    """Builds a formatted .xlsx workbook with cell-anchored images and code interpreter guide."""

    def __init__(self, max_dimension_px: int = 320) -> None:
        self.max_dimension_px = max_dimension_px

    def build_raw_workbook(
        self,
        session_id: str,
        blocks: List[BlockRecord],
        output_path: Path,
    ) -> Path:
        """Generate the raw .xlsx spreadsheet containing all resident blocks.

        Args:
            session_id: Unique identifier of the data entry session.
            blocks: List of all BlockRecords recorded in the session.
            output_path: Path where the generated .xlsx file will be saved.

        Returns:
            The Path to the generated Excel file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb = openpyxl.Workbook()

        # Sheet 1: Raw_Transactions
        ws_raw = wb.active
        ws_raw.title = "Raw_Transactions"

        # Organize blocks by row_index: dict[row_index -> list[BlockRecord]]
        rows_map: Dict[int, List[BlockRecord]] = {}
        for block in blocks:
            rows_map.setdefault(block.row_index, []).append(block)

        # Sort blocks within each row by col_index
        for r_idx in rows_map:
            rows_map[r_idx].sort(key=lambda b: b.col_index)

        # Determine total resident rows and max block columns
        all_row_indices = sorted(rows_map.keys()) if rows_map else [1]
        max_blocks = max((len(b_list) for b_list in rows_map.values()), default=1)
        max_blocks = max(max_blocks, 1)

        # Build Headers: Col A = "Resident_Row_ID", Col B = "Block_1", ...
        headers = ["Resident_Row_ID"] + [f"Block_{i}" for i in range(1, max_blocks + 1)]
        ws_raw.append(headers)

        header_font = Font(name="Calibri", size=11, bold=True, color="1F497D")
        header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="B0C4DE"),
            right=Side(style="thin", color="B0C4DE"),
            top=Side(style="thin", color="B0C4DE"),
            bottom=Side(style="thin", color="B0C4DE"),
        )
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col_idx in range(1, len(headers) + 1):
            cell = ws_raw.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = header_alignment

        ws_raw.row_dimensions[1].height = 28
        ws_raw.column_dimensions["A"].width = 20

        # Styles for data cells
        data_font = Font(name="Calibri", size=10)
        text_align = Alignment(horizontal="left", vertical="top", wrap_text=True)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Process each resident row
        for row_num_idx, r_id in enumerate(all_row_indices, start=1):
            excel_row = row_num_idx + 1  # Row 1 is header
            row_blocks = rows_map.get(r_id, [])

            # Col A: Resident label
            resident_cell = ws_raw.cell(row=excel_row, column=1, value=f"Resident_{r_id}")
            resident_cell.font = Font(name="Calibri", size=11, bold=True)
            resident_cell.alignment = center_align
            resident_cell.border = thin_border

            # Default row height
            current_row_height = 30.0
            ws_raw.row_dimensions[excel_row].height = current_row_height

            for b_idx, block in enumerate(row_blocks, start=1):
                excel_col = b_idx + 1
                col_letter = get_column_letter(excel_col)
                target_cell = ws_raw.cell(row=excel_row, column=excel_col)
                target_cell.border = thin_border

                if block.block_type == "TEXT":
                    target_cell.value = block.text_content or ""
                    target_cell.font = data_font
                    target_cell.alignment = text_align
                    current_width = ws_raw.column_dimensions[col_letter].width or 0
                    ws_raw.column_dimensions[col_letter].width = max(current_width, 35)

                elif block.block_type == "IMAGE" and block.file_path:
                    src_image_path = Path(block.file_path)
                    if src_image_path.exists():
                        resized_path = self._prepare_thumbnail(
                            src_image_path,
                            output_path.parent / "thumbnails" / f"thumb_{src_image_path.name}",
                        )
                        # Explicit cell anchor string for text-based readers / audit
                        cell_anchor_label = (
                            f"[IMAGE_ANCHOR: {col_letter}{excel_row} | file: {src_image_path.name}]"
                        )
                        target_cell.value = cell_anchor_label
                        target_cell.font = Font(name="Calibri", size=9, italic=True, color="595959")
                        target_cell.alignment = text_align

                        # OpenPyXL drawing image
                        openpyxl_img = OpenpyxlImage(str(resized_path))
                        openpyxl_img.anchor = f"{col_letter}{excel_row}"
                        ws_raw.add_image(openpyxl_img)

                        # Set row height and column width to keep image comfortably inside cell
                        ws_raw.row_dimensions[excel_row].height = max(
                            ws_raw.row_dimensions[excel_row].height or 0, 250
                        )
                        col_width = ws_raw.column_dimensions[col_letter].width or 0
                        ws_raw.column_dimensions[col_letter].width = max(col_width, 45)
                    else:
                        target_cell.value = f"[IMAGE_MISSING: {block.file_path}]"
                        target_cell.font = data_font

        # Sheet 2: _AI_EXTRACTION_GUIDE
        ws_guide = wb.create_sheet(title="_AI_EXTRACTION_GUIDE")
        ws_guide.column_dimensions["A"].width = 25
        ws_guide.column_dimensions["B"].width = 85

        guide_title_font = Font(name="Calibri", size=14, bold=True, color="1F497D")
        guide_body_font = Font(name="Consolas", size=10)
        guide_explain_font = Font(name="Calibri", size=11)

        ws_guide.cell(row=1, column=1, value="AI Extraction & Code Interpreter Guide").font = (
            guide_title_font
        )
        ws_guide.cell(
            row=3,
            column=1,
            value="Instructions for LLM / Code Interpreter:",
        ).font = Font(name="Calibri", size=11, bold=True)

        explanation = (
            "This workbook contains raw receipts and manager notes. Embedded images in "
            "'Raw_Transactions' are strictly anchored to specific cells. Use the Python "
            "snippet below in your Code Interpreter sandbox to extract image bytes and "
            "correlate them with each resident row."
        )
        ws_guide.cell(row=4, column=1, value=explanation).font = guide_explain_font
        ws_guide.merge_cells("A4:B4")
        ws_guide.row_dimensions[4].height = 40

        ws_guide.cell(row=6, column=1, value="Python Extraction Snippet:").font = Font(
            name="Calibri", size=11, bold=True
        )

        # Insert snippet into cell
        code_cell = ws_guide.cell(row=7, column=1, value=EXTRACTION_GUIDE_CODE.strip())
        code_cell.font = guide_body_font
        code_cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws_guide.merge_cells("A7:B7")
        ws_guide.row_dimensions[7].height = 260

        wb.save(output_path)
        logger.info("Raw workbook created successfully at %s", output_path)
        return output_path

    def _prepare_thumbnail(self, src_path: Path, dst_path: Path) -> Path:
        """Resize image proportionally while handling EXIF orientation."""
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with PILImage.open(src_path) as img:
            # Handle mobile phone orientation metadata
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail(
                (self.max_dimension_px, self.max_dimension_px),
                PILImage.Resampling.LANCZOS,
            )
            img.save(dst_path, format="JPEG", quality=88, optimize=True)
        return dst_path

