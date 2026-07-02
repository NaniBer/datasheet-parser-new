"""Extract content from identified relevant pages for LLM processing."""

import io
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

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
            pdf_path: Path to PDF datasheet
        """
        self.pdf_path = pdf_path
        self.pdf = None
        self._open_pdf()
        self.fitz_doc = None  # Lazy-opened PyMuPDF document

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

        # If the filter removed everything, use the unfiltered content as a last resort.
        # Keep partially filtered results intact so we don't reintroduce irrelevant pages.
        if not (filtered.text_content or filtered.tables or filtered.images) and extracted.text_content:
            filtered = extracted

        # Determine tables_only mode based on detection AND extraction
        # Don't just check if tables were extracted, also check if we detected them
        detected_tables = any(c.has_table for c in candidates)
        extracted_tables = len(filtered.tables) > 0
        no_images = len(filtered.images) == 0

        # tables_only if we detected tables AND successfully extracted them AND no images
        tables_only = detected_tables and extracted_tables and no_images

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
        Extract tables from a page using PyMuPDF, with pdfplumber as fallback.

        Args:
            page: pdfplumber Page object
            page_num: Page number for reference

        Returns:
            List of (page_number, table_data) tuples
        """
        # Primary: PyMuPDF table detection (no external dependencies)
        tables = self._extract_tables_with_pymupdf(page_num)

        # Fallback: pdfplumber
        if not tables:
            tables = self._extract_tables_with_pdfplumber(page, page_num)

        return tables

    def _extract_tables_with_pymupdf(
        self, page_num: int
    ) -> List[Tuple[int, List]]:
        """
        Extract tables using PyMuPDF's built-in table detector.

        No Java or ghostscript required.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            List of (page_number, table_data) tuples
        """
        if fitz is None:
            return []

        tables = []
        try:
            if self.fitz_doc is None:
                self.fitz_doc = fitz.open(self.pdf_path)

            page = self.fitz_doc[page_num - 1]
            tab_finder = page.find_tables()

            for tab in tab_finder.tables:
                rows = tab.extract()
                if not rows or len(rows) < 2:
                    continue
                # Normalise: replace None with empty string
                table_data = [
                    [cell if cell is not None else "" for cell in row]
                    for row in rows
                ]
                if any(any(cell for cell in row) for row in table_data):
                    tables.append((page_num, table_data))

        except Exception as e:
            print(f"Warning: PyMuPDF table extraction failed: {e}")

        return tables

    def _extract_tables_with_pdfplumber(
        self, page, page_num: int
    ) -> List[Tuple[int, List]]:
        """
        Extract tables using pdfplumber as fallback when OpenDataLoader fails.

        Args:
            page: pdfplumber Page object
            page_num: Page number for reference

        Returns:
            List of (page_number, table_data) tuples
        """
        tables = []

        try:
            # Find tables on the page
            page_tables = page.find_tables()

            if not page_tables:
                return tables

            for table in page_tables:
                # Convert table to our internal format
                table_data = []

                # Extract rows
                for row in table.extract():
                    row_data = []
                    for cell in row:
                        if cell is None:
                            row_data.append("")
                        elif isinstance(cell, str):
                            row_data.append(cell)
                        elif hasattr(cell, "extract"):
                            extracted_cell = cell.extract()
                            row_data.append(extracted_cell if extracted_cell is not None else "")
                        else:
                            row_data.append(str(cell))
                    if any(row_data):  # Only add non-empty rows
                        table_data.append(row_data)

                if table_data:
                    tables.append((page_num, table_data))

        except Exception as e:
            print(f"Warning: pdfplumber table extraction failed: {e}")

        return tables

    @staticmethod
    def format_for_llm(content: ExtractedContent, tables_only: bool = False) -> str:
        """
        Format extracted content for LLM input.

        Args:
            content: ExtractedContent object
            tables_only: If True, extract and format ONLY table data (no text/images)

        Returns:
            Formatted string ready for LLM processing
        """
        formatted_parts = []

        # Table-only mode: Extract ONLY table data (clean input for LLM)
        if tables_only and content.tables:
            formatted_parts.append("--- PINOUT TABLE DATA ---\n")
            formatted_parts.append("Extract the following pin configuration table to generate structured PinData:\n\n")

            for page_num, table in content.tables:
                formatted_parts.append(f"Table from page {page_num}:")
                if table and len(table) > 0:
                    # Send full table structure - let LLM figure it out
                    table_json = json.dumps(table, indent=2)
                    formatted_parts.append(table_json)
                formatted_parts.append("")

            return "\n".join(formatted_parts)

        # Normal mode: text + tables + images
        # Add page numbers
        formatted_parts.append(f"Relevant pages: {', '.join(map(str, content.pages))}\n")

        # Add text content (filtered to pinout-related)
        if content.text_content:
            formatted_parts.append("--- Pinout Information ---\n")
            formatted_parts.append(content.text_content)
            formatted_parts.append("")

        # Add tables as JSON (structured format)
        if content.tables:
            formatted_parts.append("\n--- Pinout Tables (JSON) ---\n")
            for page_num, table in content.tables:
                formatted_parts.append(f"\nTable from page {page_num}:")
                if table and len(table) > 0:
                    # Convert to JSON for structured parsing
                    table_json = json.dumps(table, indent=2)
                    formatted_parts.append(table_json)

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
        if self.fitz_doc:
            self.fitz_doc.close()
            self.fitz_doc = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
