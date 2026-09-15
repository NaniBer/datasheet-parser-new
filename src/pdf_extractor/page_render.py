"""Render PDF pages to raster images for the vision path.

Vector-drawn pinouts (connection diagrams) carry no embedded raster image and
their text layer is garbled, so the only faithful way to read them is to render
the page to a picture and let a vision model read it — the same thing a human
does. Uses PyMuPDF, already a hard dependency (no new install).
"""

from __future__ import annotations

try:
    import pymupdf  # PyMuPDF >= 1.24 exposes the top-level `pymupdf` name
except ImportError:  # pragma: no cover - older PyMuPDF only ships `fitz`
    import fitz as pymupdf


def render_page_png(pdf_path: str, page_number: int, dpi: int = 200) -> bytes:
    """Render a single 1-indexed page to PNG bytes at the given DPI.

    Args:
        pdf_path: Path to the PDF.
        page_number: 1-indexed page number.
        dpi: Render resolution. 200 is a good legibility/size balance for
            connection diagrams; raise to ~300 for dense multi-package pages.

    Returns:
        PNG image bytes.

    Raises:
        IndexError: if the page number is out of range.
    """
    scale = dpi / 72.0
    with pymupdf.open(pdf_path) as doc:
        if page_number < 1 or page_number > doc.page_count:
            raise IndexError(
                f"page {page_number} out of range (1..{doc.page_count})"
            )
        page = doc[page_number - 1]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        return pix.tobytes("png")
