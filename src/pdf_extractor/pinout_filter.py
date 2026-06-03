"""
Pinout content filtering for better LLM extraction.

Filters extracted PDF content to include only pinout-relevant information,
reducing LLM confusion from irrelevant content.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class FilteredContent:
    """Filtered content containing only pinout-relevant information."""
    pages: List[int]  # Page numbers
    text_content: str  # Only pinout-related text
    tables: List[Tuple[int, List]]  # Only pinout tables (page_num, table_data)
    images: List[Tuple[int, bytes]]  # All images (for multimodal)


@dataclass
class PinoutFilter:
    """Filter extracted content to only pinout-relevant information."""

    # Keywords that indicate pinout sections
    PINOUT_SECTION_KEYWORDS = [
        'pinout', 'pin configuration', 'pin description', 'pin mapping',
        'pin names', 'pin functions', 'pin assignments', 'pin details',
        'package pinout', 'component pinout', 'device pinout',
        'pin diagram', 'pin table', 'pin list', 'pinout table',
        'pin definition'
    ]

    # Keywords that indicate pinout table columns
    PINOUT_TABLE_KEYWORDS = [
        'pin', 'no.', 'number', 'num', '#',
        'name', 'function', 'description', 'desc',
        'signal', 'io', 'power', 'ground', 'vcc', 'vdd', 'gnd', 'vss',
        'reset', 'clock', 'oscillator', 'xtal', 'xtal', 'crystal',
        'adc', 'dac', 'pwm', 'spi', 'i2c', 'uart', 'usart',
        'pa', 'pb', 'pc', 'pd', 'pe', 'pf'  # Common port names
    ]

    # Strong phrases that usually indicate packaging/materials pages, not pinout data.
    NON_PINOUT_SECTION_KEYWORDS = [
        'package materials information', 'ordering information',
        'electrical characteristics', 'recommended operating conditions',
        'absolute maximum ratings', 'absolute maximum',
        'mechanical dimensions', 'physical dimensions', 'package dimensions',
        'electrical specifications', 'pcb design guidelines',
        'symbols', 'parameters', 'pad dimensions', 'i/o land design dimensions',
        'tape and reel', 'pack materials', 'packaging information',
        'soldering', 'footprint', 'storage', 'transportation', 'handling',
        'mounting', 'assembly'
    ]

    # Strong phrases that should help pinout detection even when the page also
    # contains package-related wording.
    STRONG_PINOUT_SECTION_KEYWORDS = [
        'pin configuration', 'pin configurations', 'pin functions',
        'pin function', 'pin description', 'pin assignments',
        'pin mapping', 'pinout -', 'pinout table', 'table 5-1. pin functions'
    ]

    # Strong phrases that should suppress table matches when present.
    NON_PINOUT_TABLE_KEYWORDS = [
        'package materials information', 'ordering information',
        'electrical characteristics', 'recommended operating conditions',
        'absolute maximum ratings', 'absolute maximum',
        'tape and reel', 'pack materials'
    ]

    @staticmethod
    def _normalize_cell_text(cell) -> str:
        """Normalize a table cell to a compact single-line string."""
        if cell is None:
            return ""
        return " ".join(str(cell).replace("\r", " ").replace("\n", " ").split()).strip()

    def _normalize_table(self, table: List) -> List[List[str]]:
        """Normalize table rows/cells for scoring."""
        normalized_rows = []
        for row in table or []:
            normalized_row = [self._normalize_cell_text(cell) for cell in row]
            if any(normalized_row):
                normalized_rows.append(normalized_row)
        return normalized_rows

    def _table_text(self, table: List[List[str]]) -> str:
        """Flatten table rows into searchable lowercase text."""
        return " ".join(
            " ".join(cell for cell in row if cell).lower()
            for row in table
        )

    def _looks_like_pin_label(self, text: str) -> bool:
        """Heuristic check for pin labels like GND, VCC, QA, A0, or 12."""
        if not text:
            return False

        normalized = self._normalize_cell_text(text)
        if not normalized:
            return False

        compact = re.sub(r"[\s/_-]+", "", normalized).upper()

        if compact.isdigit():
            return True

        if compact in {
            "GND", "VCC", "VDD", "VSS", "OE", "MR", "CLR", "SER", "SRCLK",
            "RCLK", "SCK", "MOSI", "MISO", "SDA", "SCL", "RESET", "CLK", "CS",
            "NC", "TRIG", "OUT", "CTRL", "THRES", "DISCH"
        }:
            return True

        if re.fullmatch(r"[A-Z]\d{1,2}", compact):
            return True

        if re.fullmatch(r"[A-Z]{2,6}\d{0,2}", compact):
            return True

        if "/" in normalized:
            parts = [
                re.sub(r"[^A-Z0-9']+", "", part.upper())
                for part in re.split(r"\s*/\s*", normalized)
                if part.strip()
            ]
            if len(parts) >= 2 and all(
                part and len(part) <= 8 and re.fullmatch(r"[A-Z0-9']+", part)
                for part in parts
            ):
                return True

        return False

    def is_pinout_table(self, table: List) -> bool:
        """Check if a table is a pinout table."""
        normalized_rows = self._normalize_table(table)
        if len(normalized_rows) < 3:
            return False

        table_text = self._table_text(normalized_rows)
        if any(keyword in table_text for keyword in self.NON_PINOUT_TABLE_KEYWORDS):
            return False

        header_text = self._table_text(normalized_rows[:3])
        score = 0

        if "pin" in header_text:
            score += 1
        if any(kw in header_text for kw in ["name", "function", "description", "signal", "io"]):
            score += 1
        if any(self._looks_like_pin_label(row[0]) for row in normalized_rows[1:10] if row):
            score += 1
        if sum(1 for row in normalized_rows[1:] if any(cell for cell in row[1:])) >= 2:
            score += 1
        if any(
            any(term in row_text for term in ["ground", "vcc", "vdd", "vss", "reset", "clock", "power pin", "no connection"])
            for row_text in (" ".join(row).lower() for row in normalized_rows[1:])
        ):
            score += 1

        return score >= 3

    def filter_text_content(self, text_content: str, pages: List[int]) -> str:
        """
        Filter only text content, preserving all text from pages with tables.

        Args:
            text_content: Combined text from all pages
            pages: List of page numbers

        Returns:
            Filtered text content (all text preserved)
        """
        if not text_content:
            return ""

        # Split text by page markers
        text_blocks = []
        current_page = None
        current_block = []

        for line in text_content.split('\n'):
            if line.strip().startswith('--- Page'):
                if current_page is not None and current_block:
                    text_blocks.append((current_page, "\n".join(current_block)))
                current_block = []
                try:
                    current_page = int(line.strip().replace('--- Page', '').replace('---', '').strip())
                except:
                    current_page = None
            elif current_page is not None:
                current_block.append(line)

        # Add last block
        if current_page is not None and current_block:
            text_blocks.append((current_page, "\n".join(current_block)))

        # Combine all text blocks (no filtering on table pages)
        filtered_text = "\n\n".join(
            block_text for page_num, block_text in text_blocks
        )

        return filtered_text

    def is_pinout_section(self, text: str) -> bool:
        """Check if text block is from a pinout section."""
        if not text:
            return False

        text_lower = " ".join(text.replace("\r", " ").replace("\n", " ").split()).lower()

        # Check for pinout section keywords
        has_pinout_kw = any(kw in text_lower for kw in self.PINOUT_SECTION_KEYWORDS)

        # Check for strong pinout indicators (should override non-pinout keywords)
        # These are very specific to pinout content
        has_strong_indicator = any(kw in text_lower for kw in self.STRONG_PINOUT_SECTION_KEYWORDS)

        # Check for pinout figure/diagram text patterns
        # Look for lines like "(PCINT8/XCK0/T0) PB0 PA0"
        # This is the format of pinout diagrams extracted as text
        pinout_diagram_pattern = (
            r'\([a-z0-9]+/[a-z0-9]+/[a-z0-9]+/t?\d*\)\s*[a-z]+\d+\s+[a-z]+\d+\s*\('
        )
        has_diagram_format = bool(re.search(pinout_diagram_pattern, text_lower, re.IGNORECASE))

        has_strong_non_pinout = any(kw in text_lower for kw in self.NON_PINOUT_SECTION_KEYWORDS)

        if has_strong_indicator or has_diagram_format:
            return True

        if has_strong_non_pinout:
            return False

        return has_pinout_kw

    def filter_tables(self, tables: List[Tuple[int, List]]) -> List[Tuple[int, List]]:
        """Filter to only pinout tables."""
        filtered = []

        for page_num, table_data in tables:
            if self.is_pinout_table(table_data):
                filtered.append((page_num, table_data))

        return filtered

    def filter_content(self, extracted) -> FilteredContent:
        """Filter extracted content to only pinout-relevant information."""
        # Filter tables
        filtered_tables = self.filter_tables(extracted.tables)

        # Get pages that have pinout tables
        pages_with_pinout_tables = {page_num for page_num, _ in filtered_tables}

        # Split text into blocks by page markers
        text_blocks = []
        current_page = None
        current_block = []

        for line in extracted.text_content.split('\n'):
            if line.strip().startswith('--- Page'):
                if current_page is not None and current_block:
                    text_blocks.append((current_page, "\n".join(current_block)))
                current_block = []
                try:
                    current_page = int(line.strip().replace('--- Page', '').replace('---', '').strip())
                except:
                    current_page = None
            elif current_page is not None:
                current_block.append(line)

        # Add last block
        if current_page is not None and current_block:
            text_blocks.append((current_page, "\n".join(current_block)))

        # Filter text blocks with improved logic
        filtered_text_blocks = []
        filtered_pages = []

        for page_num, block_text in text_blocks:
            # Check pinout status with multiple indicators
            is_pinout_page = page_num in pages_with_pinout_tables
            is_pinout_text = self.is_pinout_section(block_text)

            # Additional check: keep pages with very strong pinout indicators
            # even if text filter fails
            block_lower = block_text.lower()
            has_strong_pinout_heading = any(
                kw in block_lower for kw in ['pinout -', 'figure 1-1. pinout',
                                               'figure 1-2. pinout', 'figure 1-3. pinout',
                                               'pin configurations']
            )

            # Keep block if ANY condition matches:
            # 1. Page has a pinout table, OR
            # 2. Block text matches pinout section keywords, OR
            # 3. Has strong pinout heading
            if is_pinout_page or is_pinout_text or has_strong_pinout_heading:
                # Add page marker back
                marked_block = f"--- Page {page_num} ---\n{block_text}"
                filtered_text_blocks.append(marked_block)
                if page_num not in filtered_pages:
                    filtered_pages.append(page_num)

        # Combine filtered text
        filtered_text = "\n\n".join(filtered_text_blocks)

        # Keep only pages that survived filtering, plus any pages with pinout tables.
        pages = list(dict.fromkeys(filtered_pages))
        for page_num in pages_with_pinout_tables:
            if page_num not in pages:
                pages.append(page_num)

        # If filtering removed everything, fall back to the original candidate pages
        # rather than returning an empty page list.
        if not pages and extracted.pages:
            pages = extracted.pages

        return FilteredContent(
            pages=pages,
            text_content=filtered_text,
            tables=filtered_tables,
            images=extracted.images  # Keep all images for multimodal
        )

    def format_for_llm(self, filtered: FilteredContent) -> str:
        """Format filtered content for LLM input."""
        parts = []

        # Add page information
        parts.append(f"Relevant pages: {', '.join(map(str, filtered.pages))}\n")

        # Add text content
        if filtered.text_content:
            parts.append("--- Pinout Information ---\n")
            parts.append(filtered.text_content)
            parts.append("")

        # Add tables (limit to avoid overwhelming the LLM)
        if filtered.tables:
            parts.append("--- Pinout Tables ---\n")
            for i, (page_num, table_data) in enumerate(filtered.tables):
                parts.append(f"\nTable from page {page_num}:")
                if table_data and len(table_data) > 0:
                    # Header
                    header = " | ".join(str(cell) for cell in table_data[0])
                    parts.append(f"| {header} |")
                    # Data rows
                    for row in table_data[1:12]:  # Limit to 12 rows
                        row_text = " | ".join(str(cell) for cell in row)
                        parts.append(f"| {row_text} |")
                parts.append("")

        return "\n".join(parts)
