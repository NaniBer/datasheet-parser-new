#!/usr/bin/env python3
"""
Test the full text-based pin extraction and show:
1. What content is sent to LLM
2. What LLM returns
3. How pins are mapped (number → name)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm import LLMClient
from src.chat_bot import build_pin_extraction_prompt

def test_full_extraction(pdf_path: str):
    """Run full extraction and show details."""
    import os

    print("=" * 80)
    print("STEP 1: Page Detection")
    print("=" * 80)

    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=5)

        print(f"\nRelevant pages: {[c.page_number for c in candidates]}")

        # Sort by page number
        candidates_sorted = sorted(candidates, key=lambda x: x.page_number)

    print("\n" + "=" * 80)
    print("STEP 2: Content Extraction")
    print("=" * 80)

    with ContentExtractor(pdf_path) as extractor:
        content = extractor.extract_content(candidates)

        print(f"\nPages: {content.pages}")
        print(f"Tables found: {len(content.tables)}")
        print(f"Images found: {len(content.images)}")
        print(f"Text content length: {len(content.text_content)} chars")

    print("\n" + "=" * 80)
    print("STEP 3: Full Text Content Sent to LLM")
    print("=" * 80)

    # Show full content
    print("\n--- COMPLETE TEXT CONTENT ---\n")
    print(content.text_content)
    print("\n--- END OF CONTENT ---\n")

    print("\n" + "=" * 80)
    print("STEP 4: LLM Extraction")
    print("=" * 80)

    api_key = os.environ.get("FASTCHAT_API_KEY") or os.environ.get("DATASHEET_PARSER_API_KEY")
    if not api_key:
        print("\nERROR: No API key found!")
        print("Set FASTCHAT_API_KEY or DATASHEET_PARSER_API_KEY environment variable")
        return

    llm_client = LLMClient(api_key=api_key, model="llama-3")

    try:
        pin_data = llm_client.extract_pin_data(
            content=content.text_content,
            part_number="ATmega164A"
        )

        print("\n--- LLM RESULT ---\n")
        print(f"Component Name: {pin_data.component_name}")
        print(f"Package: {pin_data.package.type}-{pin_data.package.pin_count}")
        print(f"Pin Count: {len(pin_data.pins)}")
        print(f"Extraction Method: {pin_data.extraction_method}")

        print("\n--- PIN MAPPING ---")
        print(f"{'Pin':<5} {'Name':<15} {'Function'}")
        print("-" * 50)

        for pin in pin_data.pins:
            func = pin.function or "N/A"
            print(f"{pin.number:<5} {pin.name:<15} {func}")

        # Check for issues
        print("\n--- VALIDATION ---")

        # Check if pin count matches package
        expected_pins = pin_data.package.pin_count
        actual_pins = len(pin_data.pins)
        if actual_pins != expected_pins:
            print(f"⚠️  PIN COUNT MISMATCH: Package says {expected_pins} pins, but extracted {actual_pins}")

        # Check for power pins
        power_pins = [p for p in pin_data.pins if p.function and 'power' in p.function.lower()]
        if not power_pins:
            print("⚠️  No power pins found (VCC/VDD)")

        # Check for ground pins
        ground_pins = [p for p in pin_data.pins if p.function and 'ground' in p.function.lower()]
        if not ground_pins:
            print("⚠️  No ground pins found (GND/VSS)")

        # Check for duplicate pin numbers
        pin_numbers = [p.number for p in pin_data.pins]
        if len(pin_numbers) != len(set(pin_numbers)):
            print("⚠️  DUPLICATE PIN NUMBERS FOUND!")
            from collections import Counter
            dupes = [num for num, count in Counter(pin_numbers).items() if count > 1]
            print(f"   Duplicates: {dupes}")

        # Check for consecutive pin numbers
        sorted_pins = sorted(pin_numbers)
        if sorted_pins == list(range(1, len(sorted_pins) + 1)):
            print("✓ Pin numbers are consecutive")
        else:
            print(f"⚠️  Pin numbers are NOT consecutive: {sorted_pins}")

    except Exception as e:
        print(f"\nERROR during LLM extraction: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    pdf_path = "pdfs/test.pdf"

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    test_full_extraction(pdf_path)
