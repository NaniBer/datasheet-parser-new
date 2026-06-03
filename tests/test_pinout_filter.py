"""Tests for pinout filtering heuristics."""

from src.pdf_extractor.content_extractor import ContentExtractor, ExtractedContent
from src.pdf_extractor.pinout_filter import PinoutFilter


def _build_74hc595_raw_content():
    """Build raw extracted content for the known-good pinout page and known-bad packaging page."""
    pdf_path = "pdfs/74HC595_TI.pdf"
    with ContentExtractor(pdf_path) as extractor:
        pinout_page = extractor.pdf.pages[2]
        package_page = extractor.pdf.pages[20]

        tables = extractor._extract_tables_with_pdfplumber(pinout_page, 3)
        text_content = (
            extractor._extract_text_from_page(pinout_page, 3)
            + "\n\n"
            + extractor._extract_text_from_page(package_page, 21)
        )

    return ExtractedContent(
        pages=[3, 21],
        text_content=text_content,
        images=[],
        tables=tables,
    )


def test_pinout_filter_keeps_pinout_page_and_drops_package_materials_page():
    """The filter should keep the real pinout page and exclude package-materials pages."""
    extracted = _build_74hc595_raw_content()
    filtered = PinoutFilter().filter_content(extracted)

    assert filtered.pages == [3]
    assert [page_num for page_num, _ in filtered.tables] == [3]
    assert "--- Page 3 ---" in filtered.text_content
    assert "--- Page 21 ---" not in filtered.text_content


def test_pdfplumber_table_shape_is_recognized_as_pinout_table():
    """Sparse pdfplumber table headers should still be recognized as pinout tables."""
    extracted = _build_74hc595_raw_content()
    table_data = extracted.tables[0][1]

    assert PinoutFilter().is_pinout_table(table_data)
