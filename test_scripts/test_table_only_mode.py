"""Test what table data is being sent to LLM in table-only mode."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pdf_extractor.page_detector import PageDetector
from pdf_extractor.content_extractor import ContentExtractor

def test_table_only_mode():
    """Test table-only mode on 74HC595 datasheet."""

    pdf_path = "pdfs/74HC595_TI.pdf"

    print("=" * 60)
    print("Testing Table-Only Mode")
    print("=" * 60)

    # Step 1: Detect pages with pinout tables
    print("\nStep 1: Detecting relevant pages...")
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=5)

    # Filter to pages with tables only
    table_pages = [c for c in candidates if c.has_table]
    print(f"\nPages with tables: {[c.page_number for c in table_pages]}")

    # Step 2: Extract content using hybrid approach
    print("\nStep 2: Extracting content (hybrid mode)...")
    extractor = ContentExtractor(pdf_path)

    try:
        content = extractor.extract_content(candidates)

        print(f"\nExtraction results:")
        print(f"  Pages extracted: {content.pages}")
        print(f"  Text length: {len(content.text_content)} characters")
        print(f"  Number of tables: {len(content.tables)}")
        print(f"  Number of images: {len(content.images)}")

        # Step 3: Format for LLM in table-only mode
        print("\nStep 3: Formatting for LLM (table-only mode)...")
        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_content = ContentExtractor.format_for_llm(
            content,
            tables_only=tables_only_mode
        )

        print(f"\nFormatted content length: {len(formatted_content)} characters")
        print(f"\nTable-only mode: {tables_only_mode}")

        print("\n" + "=" * 60)
        print("FORMATTED CONTENT SENT TO LLM:")
        print("=" * 60)
        print(formatted_content)
        print("=" * 60)

    finally:
        extractor.close()

if __name__ == "__main__":
    test_table_only_mode()
