"""Extract content from identified relevant pages for LLM processing."""

import io
import json
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import opendataloader_pdf
except ImportError:
    opendataloader_pdf = None

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
        self.opendataloader_cache = None  # Cache for OpenDataLoader results

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
        Extract tables from a page using OpenDataLoader (hybrid mode).

        Falls back to pdfplumber if OpenDataLoader fails.

        Args:
            page: pdfplumber Page object
            page_num: Page number for reference

        Returns:
            List of (page_number, table_data) tuples
        """
        # Try OpenDataLoader first
        tables = []

        try:
            if opendataloader_pdf is None:
                raise ImportError(
                    "opendataloader-pdf is required for table extraction. "
                    "Install with: pip install opendataloader-pdf"
                )

            # Use cached OpenDataLoader results if available
            if self.opendataloader_cache is None:
                self.opendataloader_cache = self._extract_with_opendataloader()

            # Find tables for this page from OpenDataLoader results
            for element in self.opendataloader_cache:
                if element.get("type") == "table" and element.get("page number") == page_num:
                    # Convert OpenDataLoader table to our format
                    table_data = self._convert_opendataloader_table(element)
                    if table_data and len(table_data) >= 2:  # Header + at least 1 row
                        tables.append((page_num, table_data))

        except ImportError:
            # OpenDataLoader not installed - skip it
            pass
        except Exception as e:
            # OpenDataLoader failed (Java issue) - fall back to pdfplumber
            print(f"Warning: OpenDataLoader failed, falling back to pdfplumber: {e}")
            pass

        # Fallback: If OpenDataLoader failed or returned no tables, try pdfplumber
        if not tables:
            tables = self._extract_tables_with_pdfplumber(page, page_num)

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

    def _extract_with_opendataloader(self) -> dict:
        """
        Extract all content using OpenDataLoader (for table extraction).

        Returns:
            Dict containing OpenDataLoader results
        """
        import os

        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract to temporary directory
            try:
                opendataloader_pdf.convert(
                    input_path=[self.pdf_path],
                    output_dir=temp_dir,
                    format="json"
                )

                # Read the JSON output
                output_file = os.path.join(temp_dir, f"{Path(self.pdf_path).stem}.json")
                if not os.path.exists(output_file):
                    return {}

                with open(output_file, 'r') as f:
                    data = json.load(f)

                # Return the 'kids' array which contains all elements
                return data.get("kids", [])

            except Exception as e:
                print(f"Warning: OpenDataLoader extraction failed: {e}")
                return {}

    def _convert_opendataloader_table(self, odl_table: dict) -> List[List]:
        """
        Convert OpenDataLoader table format to our internal format.

        Args:
            odl_table: OpenDataLoader table element

        Returns:
            2D list of table cells (rows x columns)
        """
        rows_data = odl_table.get("rows", [])
        if not rows_data:
            return []

        # Convert each row
        converted_table = []
        for row in rows_data:
            cells = row.get("cells", [])
            row_data = []

            # Convert each cell
            for cell in cells:
                # Extract text from kids (paragraphs)
                cell_text = ""
                kids = cell.get("kids", [])
                if kids:
                    for kid in kids:
                        if kid.get("type") == "paragraph":
                            cell_text = kid.get("content", "")
                            break
                row_data.append(cell_text)

            converted_table.append(row_data)

        return converted_table

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

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
