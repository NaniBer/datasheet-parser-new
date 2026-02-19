#!/usr/bin/env python3
"""End-to-end test of pin extraction on all datasheet PDFs."""

import sys
import os
import re
sys.path.insert(0, '/Users/mac/Documents/Projects/datasheet-parser-new')

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm import LLMClient
import json


def extract_part_number(filename: str) -> str:
    """
    Extract part number from filename.

    Args:
        filename: PDF filename (e.g., "STM32F103RBT7.PDF")

    Returns:
        Part number (e.g., "STM32F103RBT7")
    """
    # Remove .PDF or .pdf extension
    base_name = os.path.splitext(filename)[0]

    # Common part number patterns
    # 1. Full filename is the part number (e.g., "STM32F103RBT7.PDF")
    if re.match(r'^[A-Z0-9-]+$', base_name):
        return base_name

    # 2. Part number with datasheet suffix (e.g., "NE555.PDF")
    match = re.match(r'^([A-Z0-9-]+)', base_name)
    if match:
        return match.group(1)

    return None


def test_pdf(pdf_path: str):
    """Test pin extraction on a single PDF."""
    pdf_name = os.path.basename(pdf_path)
    part_number = extract_part_number(pdf_name)

    print("\n" + "=" * 70)
    print(f"TESTING: {pdf_name}")
    if part_number:
        print(f"PART NUMBER: {part_number}")
    print("=" * 70)

    # Step 1: Detect relevant pages
    print(f"\n[1/3] Detecting relevant pages...")
    try:
        with PageDetector(pdf_path) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=5)

            if candidates:
                print(f"  ✅ Found {len(candidates)} relevant page(s):")
                for c in candidates:
                    print(f"     Page {c.page_number} (confidence: {c.confidence_score}): {', '.join(c.reasons)}")
            else:
                print(f"  ⚠️  No relevant pages found")
                print(f"  → This PDF may not be an IC with traditional pinout")
                return {"pdf": pdf_name, "status": "no_pages", "pins": 0}
    except Exception as e:
        print(f"  ❌ Detection failed: {e}")
        return {"pdf": pdf_name, "status": "error", "error": str(e), "pins": 0}

    # Step 2: Extract content
    print(f"\n[2/3] Extracting content...")
    try:
        with ContentExtractor(pdf_path) as extractor:
            content = extractor.extract_content(candidates)
            print(f"  ✅ Extracted from {len(content.pages)} page(s)")
            print(f"  - Tables: {len(content.tables)}")
            print(f"  - Images: {len(content.images)}")

            # Combine all text content
            full_text = content.text_content
            if not full_text or len(full_text) < 50:
                print(f"  ⚠️  Very little text extracted ({len(full_text)} chars)")
                print(f"  → May require visual/OCR processing")
    except Exception as e:
        print(f"  ❌ Extraction failed: {e}")
        return {"pdf": pdf_name, "status": "extraction_error", "error": str(e), "pins": 0}

    # Step 3: Extract pin data with LLM
    print(f"\n[3/3] Extracting pin data with LLM...")
    if part_number:
        print(f"  Using part number: {part_number} for package variant matching")
    try:
        llm_client = LLMClient(model="llama-3")
        pin_data = llm_client.extract_pin_data(content=full_text, part_number=part_number)

        print(f"  ✅ Pin data extracted successfully")
        print(f"\n  COMPONENT: {pin_data.component_name}")
        print(f"  PACKAGE: {pin_data.package.type}-{pin_data.package.pin_count}")
        print(f"  DIMENSIONS: {pin_data.package.width}mm x {pin_data.package.height}mm")
        print(f"  PITCH: {pin_data.package.pitch}mm" if pin_data.package.pitch else "  PITCH: N/A")
        print(f"  EXTRACTION METHOD: {pin_data.extraction_method}")
        print(f"\n  PINS EXTRACTED: {len(pin_data.pins)}")

        # Show pins (max 10 for brevity)
        print(f"\n  Pin Details (showing first 10):")
        for i, pin in enumerate(pin_data.pins[:10]):
            func_str = f" ({pin.function})" if pin.function else ""
            print(f"    {pin.number}: {pin.name}{func_str}")

        if len(pin_data.pins) > 10:
            print(f"    ... and {len(pin_data.pins) - 10} more pins")

        return {
            "pdf": pdf_name,
            "status": "success",
            "component": pin_data.component_name,
            "package": f"{pin_data.package.type}-{pin_data.package.pin_count}",
            "pin_count": len(pin_data.pins),
            "extraction_method": pin_data.extraction_method,
            "pins": pin_data.pins
        }

    except Exception as e:
        print(f"  ❌ LLM extraction failed: {e}")
        print(f"  → May need visual processing or different approach")
        return {"pdf": pdf_name, "status": "llm_error", "error": str(e), "pins": 0}


def main():
    print("=" * 70)
    print("END-TO-END PIN EXTRACTION TEST")
    print("=" * 70)
    print("\nProcessing all PDFs in pdfs/ folder...")

    # Get all PDFs
    pdf_dir = "/Users/mac/Documents/Projects/datasheet-parser-new/pdfs"
    pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')])

    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return

    print(f"Found {len(pdf_files)} PDF file(s) to process")

    # Test each PDF
    results = []
    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        result = test_pdf(pdf_path)
        results.append(result)

    # Summary
    print("\n\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Count by status
    status_counts = {}
    for r in results:
        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"\nTotal PDFs processed: {len(results)}")
    print(f"  ✅ Successful extractions: {status_counts.get('success', 0)}")
    print(f"  ⚠️  No relevant pages: {status_counts.get('no_pages', 0)}")
    print(f"  ❌ Errors: {status_counts.get('error', 0) + status_counts.get('extraction_error', 0) + status_counts.get('llm_error', 0)}")

    # Show detailed results
    print("\n" + "-" * 70)
    print("DETAILED RESULTS")
    print("-" * 70)

    for r in results:
        if r["status"] == "success":
            print(f"\n{r['pdf']}:")
            print(f"  Component: {r['component']}")
            print(f"  Package: {r['package']}")
            print(f"  Pins extracted: {r['pin_count']}")
            print(f"  Method: {r['extraction_method']}")
        else:
            print(f"\n{r['pdf']}:")
            print(f"  Status: {r['status']}")
            if 'error' in r:
                print(f"  Error: {r['error']}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
