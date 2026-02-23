"""
Pinout content filtering for better LLM extraction.

Filters extracted PDF content to include only pinout-relevant information,
reducing LLM confusion from irrelevant content.
"""

from dataclasses import dataclass, field
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
        'pin diagram', 'package drawing', 'mechanical drawing',
        'pindescription', 'pindefinitions', 'pindescription', 'pin description',
        'pin definition', 'pin description', 'pinout', 'pin assignments',
        'pin table', 'pin list', 'pinout table', 'pin configuration'
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

    # Keywords that suggest content is NOT pinout-related (to be filtered out)
    NON_PINOUT_KEYWORDS = [
        'absolute maximum', 'absolute minimum', 'electrical characteristics',
        'recommended operating conditions', 'thermal information',
        'ordering information', 'packaging information',
        'dimensions', 'mechanical', 'physical',
        'soldering', 'footprint', 'package drawing',
        'package variants', 'package ordering',
        'reeling information', 'marking', 'labeling',
        'storage', 'transportation', 'handling'
    ]

    def is_pinout_table(self, table: List) -> bool:
        """Check if a table is a pinout table."""
        if not table or len(table) == 0:
            return False

        # Check header row for pinout keywords
        header_text = " ".join(str(cell) for cell in table[0]).lower()

        # Must have at least 2 pinout keywords
        pinout_kw_count = sum(1 for kw in self.PINOUT_TABLE_KEYWORDS if kw in header_text)

        return pinout_kw_count >= 2

    def is_pinout_section(self, text: str) -> bool:
        """Check if text block is from a pinout section."""
        if not text:
            return False

        text_lower = text.lower()

        # Check for pinout section keywords
        has_pinout_kw = any(kw in text_lower for kw in self.PINOUT_SECTION_KEYWORDS)

        # Filter out non-pinout content
        has_non_pinout_kw = any(kw in text_lower for kw in self.NON_PINOUT_KEYWORDS)

        return has_pinout_kw and not has_non_pinout_kw

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

        # Filter text blocks
        filtered_text_blocks = []
        filtered_pages = []

        for page_num, block_text in text_blocks:
            # Keep block if:
            # 1. Page has a pinout table, OR
            # 2. Block text matches pinout section keywords
            is_pinout_page = page_num in pages_with_pinout_tables
            is_pinout_text = self.is_pinout_section(block_text)

            if is_pinout_page or is_pinout_text:
                # Add page marker back
                marked_block = f"--- Page {page_num} ---\n{block_text}"
                filtered_text_blocks.append(marked_block)
                if page_num not in filtered_pages:
                    filtered_pages.append(page_num)

        # Combine filtered text
        filtered_text = "\n\n".join(filtered_text_blocks)

        # Filter pages - keep pages with pinout tables or pinout text
        if filtered_pages:
            # Keep all pages that were in candidates
            pages = extracted.pages
        else:
            pages = []

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
