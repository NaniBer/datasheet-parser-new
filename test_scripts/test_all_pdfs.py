"""
Test pin extraction on ALL PDFs in the pdfs directory.
"""

import sys
import os
import dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.page_detector import PageDetector
from src.pdf_extractor.content_extractor import ContentExtractor
from src.llm.client import LLMClient


def print_separator(char="=", length=80):
    print(char * length)


def test_single_pdf(pdf_path, api_key=None):
    """Test pin extraction on a single PDF."""
    filename = os.path.basename(pdf_path)

    print_separator()
    print(f"Testing: {filename}")
    print_separator()

    # Run extraction
    try:
        print("RUNNING EXTRACTION...")

        # Step 1: Page Detection
        page_detector = PageDetector(pdf_path)
        candidates = page_detector.detect_relevant_pages(min_confidence=5)
        print(f"  Pages detected: {len(candidates)}")
        if candidates:
            for i, candidate in enumerate(candidates[:3]):
                print(f"    Page {candidate.page_number}: confidence_score={candidate.confidence_score:.1f}")

        # Step 2: Content Extraction
        content_extractor = ContentExtractor(pdf_path)
        extracted_content = content_extractor.extract_content(candidates)
        print(f"  Text extracted: {len(extracted_content.text_content)} chars")
        print(f"  Tables extracted: {len(extracted_content.tables)}")
        print(f"  Images extracted: {len(extracted_content.images)}")

        # Step 3: LLM Extraction
        llm_client = LLMClient(api_key=api_key)
        pin_data = llm_client.extract_pin_data(
            content=extracted_content.text_content,
            part_number=filename.replace('.pdf', '').upper(),
            hint=""
        )

        # Results
        print_separator()
        print("ACTUAL RESULTS:")
        print(f"  Component: {pin_data.component_name}")
        print(f"  Package:   {pin_data.package.type}")
        print(f"  Pin Count: {pin_data.package.pin_count}")
        print(f"  Dimensions: {pin_data.package.width} x {pin_data.package.height} mm")
        print()
        print(f"  Extracted Pins ({len(pin_data.pins)}):")
        for pin in pin_data.pins[:30]:
            function_str = f" - {pin.function}" if pin.function else ""
            print(f"    Pin {pin.number:3d}: {pin.name:20s}{function_str}")
        if len(pin_data.pins) > 30:
            print(f"    ... and {len(pin_data.pins) - 30} more")

        return pin_data

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("COMPREHENSIVE PIN EXTRACTION TEST - ALL PDFs")
    print_separator()

    dotenv.load_dotenv()
    api_key = os.getenv("FASTCHAT_API_KEY")

    if not api_key:
        print("❌ FASTCHAT_API_KEY not found in environment")
        return

    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Get all PDFs
    pdfs_dir = "pdfs"
    all_pdfs = sorted([f for f in os.listdir(pdfs_dir) if f.endswith('.pdf')])

    # Remove corrupted files
    skip_pdfs = [
        "foo.pdf",
        "test.pdf",
        "Unconfirmed 181557.crdownload",  # Not a PDF
    ]

    pdfs_to_test = []
    for pdf in all_pdfs:
        full_path = os.path.join(pdfs_dir, pdf)
        # Skip if in skip list or corrupted
        if any(skip in pdf for skip in skip_pdfs):
            continue

        # Check if file is valid PDF (not corrupted)
        try:
            with open(full_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    print(f"⚠️  Skipping {pdf} - not a valid PDF (corrupted or HTML)")
                    continue
        except Exception as e:
            print(f"⚠️  Skipping {pdf} - error reading: {e}")
            continue

        pdfs_to_test.append(full_path)

    print(f"Testing {len(pdfs_to_test)} PDF files...")
    print()

    results = {}
    for i, pdf_path in enumerate(pdfs_to_test):
        pin_data = test_single_pdf(pdf_path, api_key)
        results[pdf_path] = pin_data
        print("\n")

        # Show progress
        if i < len(pdfs_to_test) - 1:
            print(f"Progress: {i+1}/{len(pdfs_to_test)} PDFs tested")

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    print(f"{'Status':<10} {'PDF':<40} {'Component':<20} {'Package':<15} {'Pins':<6}")
    print("-" * 100)

    for pdf_path, pin_data in results.items():
        filename = os.path.basename(pdf_path)
        status = "✅" if pin_data else "❌"
        if pin_data:
            pkg_type = pin_data.package.type if pin_data.package.type else "Unknown"
            pkg_count = pin_data.package.pin_count if pin_data.package.pin_count is not None else "N/A"
            print(f"{status:<10} {filename:<40} {pin_data.component_name:<20} {pkg_type:<15} {pkg_count:<6}")
        else:
            print(f"{status:<10} {filename:<40} {'ERROR':<20} {'N/A':<15} {'N/A':<6}")


if __name__ == "__main__":
    main()
