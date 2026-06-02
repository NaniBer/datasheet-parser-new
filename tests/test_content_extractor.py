"""Tests for table extraction fallback behavior."""

from src.pdf_extractor import content_extractor as content_extractor_module
from src.pdf_extractor.content_extractor import ContentExtractor


def test_pdfplumber_fallback_extracts_tables_when_opendataloader_unavailable(monkeypatch):
    """Fallback extraction should work even when OpenDataLoader is disabled."""
    monkeypatch.setattr(content_extractor_module, "opendataloader_pdf", None)

    with ContentExtractor("pdfs/74HC595_TI.pdf") as extractor:
        page = extractor.pdf.pages[2]
        tables = extractor._extract_tables_from_page(page, 3)

    assert tables, "Expected pdfplumber fallback to extract at least one table"
    page_num, table_data = tables[0]
    assert page_num == 3
    assert len(table_data) >= 2
    assert table_data[0][0] == "PIN"
    assert all(isinstance(cell, str) for row in table_data for cell in row)
