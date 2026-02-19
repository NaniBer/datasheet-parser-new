#!/usr/bin/env python3
"""Test page detection on datasheet PDFs."""

import sys
sys.path.insert(0, '/Users/mac/Documents/Projects/datasheet-parser-new')

from src.pdf_extractor import PageDetector


def test_pdf(pdf_path, min_confidence=5):
    """Test page detection on a single PDF."""
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_path}")
    print(f"{'='*70}\n")

    try:
        with PageDetector(pdf_path) as detector:
            print(f"Total pages in PDF: {detector.total_pages}\n")

            # Detect relevant pages
            candidates = detector.detect_relevant_pages(min_confidence=min_confidence)

            if not candidates:
                print("No relevant pages found with current confidence threshold.")
                print("\nTrying with lower confidence (3)...")
                candidates = detector.detect_relevant_pages(min_confidence=3)

            if candidates:
                print(f"Found {len(candidates)} relevant page(s):\n")
                for i, candidate in enumerate(candidates, 1):
                    print(f"  [{i}] Page {candidate.page_number}")
                    print(f"      Confidence score: {candidate.confidence_score}")
                    print(f"      Has table: {candidate.has_table}")
                    print(f"      Has diagram: {candidate.has_diagram}")
                    print(f"      Needs verification: {candidate.needs_verification}")
                    print(f"      Reasons: {', '.join(candidate.reasons)}")
                    print()

                    # Show first 500 chars of text
                    if candidate.text:
                        preview = candidate.text[:300].replace('\n', ' ')
                        print(f"      Text preview: ...{preview}...")
                        print()
            else:
                print("No relevant pages found even with lower confidence.\n")

    except FileNotFoundError:
        print(f"Error: File not found: {pdf_path}")
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test with NE555 first (simple DIP-8)
    print("\n" + "="*70)
    print("TESTING PAGE DETECTION - Starting with NE555 (DIP-8)")
    print("="*70)

    pdfs = [
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/NE555.PDF",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/TPS63060.PDF",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/TVS-Diode-SMBJ-Datasheet.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/pages.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/foo.pdf",
        "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs/test.pdf"
    ]

    for pdf_path in pdfs:
        test_pdf(pdf_path, min_confidence=5)

    print("\n" + "="*70)
    print("PAGE DETECTION TEST COMPLETE")
    print("="*70 + "\n")
