"""Unit tests for OpenPyXL raw spreadsheet builder, cell anchoring geometry, and AI extraction."""

from pathlib import Path
import openpyxl
from PIL import Image as PILImage

from src.database.repository import BlockRecord
from src.services.excel_builder import ExcelBuilder


def test_excel_builder_geometry_and_ai_extraction(tmp_path: Path, synthetic_receipt_image: Path):
    """Verify headers, image resizing, strict cell anchoring, cell dimensions, and AI extraction."""
    output_file = tmp_path / "raw_transactions_geometry_test.xlsx"
    builder = ExcelBuilder(max_dimension_px=320)

    # Resident 1: 1 Image (Block 1 = B2), 1 Text (Block 2 = C2)
    # Resident 2: 2 Images (Block 1 = B3, Block 2 = C3), 1 Text (Block 3 = D3)
    blocks = [
        # Resident 1
        BlockRecord(
            id=1,
            session_id="test_geo",
            row_index=1,
            col_index=1,
            block_type="IMAGE",
            text_content=None,
            file_path=str(synthetic_receipt_image),
            created_at="2026-11-04T10:00:00",
        ),
        BlockRecord(
            id=2,
            session_id="test_geo",
            row_index=1,
            col_index=2,
            block_type="TEXT",
            text_content="Room 101 - 5,000,000 IRR Deposit",
            file_path=None,
            created_at="2026-11-04T10:01:00",
        ),
        # Resident 2
        BlockRecord(
            id=3,
            session_id="test_geo",
            row_index=2,
            col_index=1,
            block_type="IMAGE",
            text_content=None,
            file_path=str(synthetic_receipt_image),
            created_at="2026-11-04T10:02:00",
        ),
        BlockRecord(
            id=4,
            session_id="test_geo",
            row_index=2,
            col_index=2,
            block_type="IMAGE",
            text_content=None,
            file_path=str(synthetic_receipt_image),
            created_at="2026-11-04T10:03:00",
        ),
        BlockRecord(
            id=5,
            session_id="test_geo",
            row_index=2,
            col_index=3,
            block_type="TEXT",
            text_content="Room 205 - Ali Rezaei - 8,000,000 IRR Rent",
            file_path=None,
            created_at="2026-11-04T10:04:00",
        ),
    ]

    generated_path = builder.build_raw_workbook("test_geo", blocks, output_file)
    assert generated_path.exists()

    # 1. Inspect Structure & Headers
    wb = openpyxl.load_workbook(generated_path)
    assert "Raw_Transactions" in wb.sheetnames
    assert "_AI_EXTRACTION_GUIDE" in wb.sheetnames

    ws = wb["Raw_Transactions"]
    header_values = [cell.value for cell in ws[1]]
    assert header_values == ["Resident_Row_ID", "Block_1", "Block_2", "Block_3"]

    # 2. Verify Image Resizing
    # Thumbnails directory contains generated thumbnails
    thumbnails = list((tmp_path / "thumbnails").glob("*.jpg"))
    assert len(thumbnails) >= 1
    with PILImage.open(thumbnails[0]) as thumb:
        w, h = thumb.size
        assert w <= 320 and h <= 320
        # Aspect ratio of 1200x1600 (0.75) preserved
        assert abs((w / h) - (1200 / 1600)) < 0.05

    # 3. Verify Strict Cell Anchoring
    # Exactly 3 images embedded
    assert len(ws._images) == 3

    anchors = set()
    for img in ws._images:
        row_idx = img.anchor._from.row  # 0-indexed: row 2 -> 1, row 3 -> 2
        col_idx = img.anchor._from.col  # 0-indexed: Col B -> 1, Col C -> 2
        anchors.add((row_idx, col_idx))

    # Expected 0-indexed anchors:
    # Resident 1 Image: B2 -> row 1, col 1
    # Resident 2 Image 1: B3 -> row 2, col 1
    # Resident 2 Image 2: C3 -> row 2, col 2
    assert (1, 1) in anchors  # B2
    assert (2, 1) in anchors  # B3
    assert (2, 2) in anchors  # C3

    # Verify fallback string in cells
    assert "[IMAGE_ANCHOR: B2" in str(ws["B2"].value)
    assert "[IMAGE_ANCHOR: B3" in str(ws["B3"].value)
    assert "[IMAGE_ANCHOR: C3" in str(ws["C3"].value)
    assert ws["C2"].value == "Room 101 - 5,000,000 IRR Deposit"
    assert ws["D3"].value == "Room 205 - Ali Rezaei - 8,000,000 IRR Rent"

    # 4. Cell Dimensions
    # Row 2 and Row 3 contain images -> height >= 180
    assert ws.row_dimensions[2].height >= 180
    assert ws.row_dimensions[3].height >= 180
    # Column B and Column C contain images -> width >= 35
    assert ws.column_dimensions["B"].width >= 35
    assert ws.column_dimensions["C"].width >= 35

    # 5. Secondary AI Extraction Simulation
    # Reconstruct mapping of {resident_row_id: {col_name: content}}
    extracted_mapping = {}
    for r in range(2, ws.max_row + 1):
        res_id = ws.cell(row=r, column=1).value
        extracted_mapping[res_id] = {}
        for c in range(2, ws.max_column + 1):
            col_header = ws.cell(row=1, column=c).value
            cell_val = ws.cell(row=r, column=c).value
            if cell_val is not None:
                extracted_mapping[res_id][col_header] = cell_val

    # Verify extracted mapping
    assert "Resident_1" in extracted_mapping
    assert "Block_1" in extracted_mapping["Resident_1"]
    assert "IMAGE_ANCHOR: B2" in extracted_mapping["Resident_1"]["Block_1"]
    assert extracted_mapping["Resident_1"]["Block_2"] == "Room 101 - 5,000,000 IRR Deposit"

    assert "Resident_2" in extracted_mapping
    assert "IMAGE_ANCHOR: B3" in extracted_mapping["Resident_2"]["Block_1"]
    assert "IMAGE_ANCHOR: C3" in extracted_mapping["Resident_2"]["Block_2"]
    assert extracted_mapping["Resident_2"]["Block_3"] == "Room 205 - Ali Rezaei - 8,000,000 IRR Rent"

