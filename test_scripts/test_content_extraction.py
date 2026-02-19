#!/usr/bin/env python3
"""Test content extraction from detected pages."""

import sys
sys.path.insert(0, '/Users/mac/Documents/Projects/datasheet-parser-new')

from src.pdf_extractor import PageDetector, ContentExtractor


def test_content_extraction(pdf_path):
    """Test content extraction on a PDF."""
    print(f"\n{'='*70}")
    print(f"Testing Content Extraction: {pdf_path}")
    print(f"{'='*70}\n")

    try:
        # First detect relevant pages
        with PageDetector(pdf_path) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=5)

            if not candidates:
                print("No relevant pages found with confidence >=5")
                candidates = detector.detect_relevant_pages(min_confidence=3)

            if not candidates:
                print("No relevant pages found even with confidence >=3")
                return

            print(f"Found {len(candidates)} candidate page(s)")

        # Then extract content
        with ContentExtractor(pdf_path) as extractor:
            content = extractor.extract_content(candidates)

            print(f"\nExtracted from pages: {content.pages}")
            print(f"Number of tables found: {len(content.tables)}")
            print(f"Number of images found: {len(content.images)}")

            # Show sample of text content
            print(f"\n{'-'*70}")
            print("TEXT CONTENT (first 2000 chars):")
            print(f"{'-'*70}")
            print(content.text_content[:2000])
            if len(content.text_content) > 2000:
                print(f"\n... ({len(content.text_content)} total characters)")

            # Show tables
            if content.tables:
                print(f"\n{'-'*70}")
                print("EXTRACTED TABLES:")
                print(f"{'-'*70}")
                for page_num, table in content.tables:
                    print(f"\n--- Table from page {page_num} ---")
                    # Show first 15 rows
                    for row_idx, row in enumerate(table[:15]):
                        row_text = " | ".join(str(cell or "") for cell in row)
                        print(row_text)
                    if len(table) > 15:
                        print(f"... (table has {len(table)} rows total)")

            # Show formatted output for LLM
            print(f"\n{'-'*70}")
            print("FORMATTED FOR LLM (preview):")
            print(f"{'-'*70}")
            formatted = extractor.format_for_llm(content)
            print(formatted[:3000])
            if len(formatted) > 3000:
                print(f"\n... ({len(formatted)} total characters)")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test with NE555 first
    print("\n" + "="*70)
    print("CONTENT EXTRACTION TEST")
    print("="*70)

    # Test with all PDFs
    pdfs = [
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/NE555.PDF",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/TPS63060.PDF",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/STM32F103RBT7.PDF",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/TVS-Diode-SMBJ-Datasheet.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/pages.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/foo.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/test.pdf",
    ]

    for pdf_path in pdfs:
        test_content_extraction(pdf_path)

    print("\n" + "="*70)
    print("CONTENT EXTRACTION TEST COMPLETE")
    print("="*70 + "\n")
