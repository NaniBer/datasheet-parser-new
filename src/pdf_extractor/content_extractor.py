"""Extract content from identified relevant pages for LLM processing."""

import io
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .page_detector import PageCandidate
from .pinout_filter import PinoutFilter


@dataclass
class ExtractedContent:
    """Content extracted from relevant pages."""
    pages: List[int]  # Page numbers
    text_content: str  # Combined text from all pages
    images: List[Tuple[int, bytes]]  # (page_number, image_data)
    tables: List[Tuple[int, List]]  # (page_number, table_data)


class ContentExtractor:
    """Extract text, images, and tables from relevant pages."""

    def __init__(self, pdf_path: str):
        """
        Initialize content extractor.

        Args:
            pdf_path: Path to the PDF datasheet
        """
        self.pdf_path = pdf_path
        self.pdf = None
        self._open_pdf()

    def _open_pdf(self) -> None:
        """Open the PDF file."""
        if pdfplumber is None:
            raise ImportError(
                "pdfplumber is required. Install with: pip install pdfplumber"
            )
        self.pdf = pdfplumber.open(self.pdf_path)

    def extract_content(
        self, candidates: List[PageCandidate]
    ) -> ExtractedContent:
        """
        Extract content from the given page candidates.

        Args:
            candidates: List of PageCandidate objects to extract from

        Returns:
            ExtractedContent object with extracted data (already filtered)
        """
        # First extract all content
        extracted = ExtractedContent(
            pages=[c.page_number for c in candidates],
            text_content="",
            images=[],
            tables=[],
        )

        # Sort candidates by page number
        sorted_candidates = sorted(candidates, key=lambda x: x.page_number)

        for candidate in sorted_candidates:
            page = self.pdf.pages[candidate.page_number - 1]

            # Extract text
            text = self._extract_text_from_page(page, candidate.page_number)
            extracted.text_content += text + "\n\n"

            # Extract images if page has diagrams
            if candidate.has_diagram:
                images = self._extract_images_from_page(page, candidate.page_number)
                extracted.images.extend(images)

            # Extract tables if page has tables
            if candidate.has_table:
                tables = self._extract_tables_from_page(page, candidate.page_number)
                extracted.tables.extend(tables)

        # Apply pinout filtering to reduce content to only relevant information
        # TEMPORARILY DISABLED: Some datasheets use different wording that gets filtered out
        filter = PinoutFilter()
        filtered = filter.filter_content(extracted)

        # If filter removes all content, use unfiltered as fallback
        if not filtered.text_content and extracted.text_content:
            filtered = extracted

        # Return filtered content
        return ExtractedContent(
            pages=filtered.pages,
            text_content=filtered.text_content,
            tables=filtered.tables,
            images=filtered.images
        )

    def _extract_text_from_page(
        self, page, page_num: int
    ) -> str:
        """
        Extract text from a page with page number annotations.

        Args:
            page: pdfplumber Page object
            page_num: Page number for annotation

        Returns:
            Extracted text with page markers
        """
        text = page.extract_text() or ""
        return f"--- Page {page_num} ---\n{text}"

    def _extract_images_from_page(
        self, page, page_num: int
    ) -> List[Tuple[int, bytes]]:
        """
        Extract images from a page.

        Args:
            page: pdfplumber Page object
            page_num: Page number for reference

        Returns:
            List of (page_number, image_data) tuples
        """
        images = []
        for img_index, img_obj in enumerate(page.images):
            try:
                # Get the image from the PDF
                image_data = None
                if hasattr(img_obj, "stream"):
                    # For direct stream access (pypdf-style)
                    stream = img_obj.stream
                    image_data = stream.get_data()
                else:
                    # Fallback - try to get image via page.to_image
                    try:
                        pil_image = page.to_image()
                        image_data = io.BytesIO()
                        pil_image.save(image_data, format="PNG")
                        image_data = image_data.getvalue()
                    except Exception:
                        continue

                if image_data:
                    images.append((page_num, image_data))
            except Exception:
                # Skip problematic images
                continue

        return images

    def _extract_tables_from_page(
        self, page, page_num: int
    ) -> List[Tuple[int, List]]:
        """
        Extract tables from a page.

        Args:
            page: pdfplumber Page object
            page_num: Page number for reference

        Returns:
            List of (page_number, table_data) tuples
        """
        tables = []
        extracted_tables = page.extract_tables()
        if not extracted_tables:
            return tables

        for table_data in extracted_tables:
            if table_data and len(table_data) >= 2:  # Header + at least 1 row
                tables.append((page_num, table_data))

        return tables

    def format_for_llm(self, content: ExtractedContent) -> str:
        """
        Format extracted content for LLM input.

        Args:
            content: ExtractedContent object

        Returns:
            Formatted string ready for LLM processing
        """
        formatted_parts = []

        # Add page numbers
        formatted_parts.append(f"Relevant pages: {', '.join(map(str, content.pages))}\n")

        # Add text content (filtered to pinout-related)
        if content.text_content:
            formatted_parts.append("--- Pinout Information ---\n")
            formatted_parts.append(content.text_content)
            formatted_parts.append("")

        # Add tables (filtered to pinout tables)
        if content.tables:
            formatted_parts.append("\n--- Pinout Tables ---\n")
            for page_num, table in content.tables:
                formatted_parts.append(f"\nTable from page {page_num}:")
                if table and len(table) > 0:
                    # Header
                    header = " | ".join(str(cell) for cell in table[0])
                    formatted_parts.append(f"| {header} |")
                    # Data rows (limit to 15 for context)
                    for row_idx, row in enumerate(table):
                        if row_idx < 15:
                            row_text = " | ".join(str(cell) for cell in row)
                            formatted_parts.append(f"| {row_text} |")
                        elif row_idx == 15:
                            formatted_parts.append("| ... (truncated)")
                            break

        # Note about images
        if content.images:
            formatted_parts.append("\n--- Note ---\n")
            formatted_parts.append(
                f"This content includes {len(content.images)} diagram image(s). "
                f"Use these for visual reference of pinout diagrams."
            )

        return "\n".join(formatted_parts)

    def extract_single_page(self, page_num: int) -> str:
        """
        Extract content from a single page.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            Extracted text from the page
        """
        page = self.pdf.pages[page_num - 1]
        return page.extract_text() or ""

    def close(self) -> None:
        """Close the PDF file."""
        if self.pdf:
            self.pdf.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
