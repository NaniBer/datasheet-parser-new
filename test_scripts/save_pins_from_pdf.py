#!/usr/bin/env python3
"""
Extract pins from PDF and save to JSON for fast schematic testing.

This script runs the full extraction pipeline (page detection, content extraction,
LLM) and saves the extracted pins to a JSON file for fast testing.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm.client import LLMClient
from src.chat_bot import build_pin_extraction_prompt
from src.models import PinData
from src.utils import PackageDetector


def save_pins_from_pdf(pdf_path: str, output_json: str):
    """
    Extract pins from PDF and save to JSON file.

    Args:
        pdf_path: Path to PDF file
        output_json: Path to save extracted pins (JSON)
    """
    print("=" * 60)
    print("Extracting pins from PDF...")
    print("=" * 60)
    print(f"PDF: {pdf_path}")
    print(f"Output: {output_json}")
    print()

    # Step 1: Detect relevant pages
    print("Step 1: Detecting relevant pages...")
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=5)

    print(f"Found {len(candidates)} relevant page(s)")
    for i, candidate in enumerate(candidates[:5]):
        print(f"  {i+1}. Page {candidate.page_number}: confidence={candidate.confidence_score:.1f}")
    if len(candidates) > 5:
        print(f"  ... and {len(candidates) - 5} more")
    print()

    # Step 2: Extract content from relevant pages
    print("Step 2: Extracting content...")
    extractor = ContentExtractor(pdf_path)
    content = extractor.extract_content(candidates)
    print()

    # Step 3: Extract pins using LLM
    print("Step 3: Extracting pins with LLM...")
    client = LLMClient()
    prompt = build_pin_extraction_prompt(content, pdf_path)
    pin_data = client.extract_pin_data(prompt)

    # Step 4: Package detection
    print("Step 4: Detecting package type...")
    detector = PackageDetector()
    package_type = detector.detect_package_type(pin_data)
    print(f"Package: {package_type}")
    print()

    # Step 5: Save pins to JSON
    print("Step 5: Saving pins to JSON...")

    output = {
        "component_name": pin_data.component_name,
        "package_type": package_type,
        "pin_count": pin_data.package.pin_count,
        "pins": [
            {
                "number": pin.number,
                "name": pin.name,
                "function": pin.function
            }
            for pin in pin_data.pins
        ]
    }

    with open(output_json, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✅ Saved {len(pin_data.pins)} pins to {output_json}")
    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Component: {pin_data.component_name}")
    print(f"  Package: {package_type}")
    print(f"  Pins: {len(pin_data.pins)}")
    print(f"  Output: {output_json}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python save_pins_from_pdf.py <pdf_path> [output_json]")
        print()
        print("Example:")
        print("  python save_pins_from_pdf.py pdfs/NE555.PDF pins/NE555_pins.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else "pins/extracted_pins.json"

    save_pins_from_pdf(pdf_path, output_json)
