#!/usr/bin/env python3
"""Test pin extraction prompt with datasheet content."""

import sys
sys.path.insert(0, '/Users/mac/Documents/Projects/datasheet-parser-new')

from src.chat_bot import get_completion_from_messages, build_pin_extraction_prompt
import json


def main():
    print("=" * 70)
    print("TEST: Pin Data Extraction with LLM")
    print("=" * 70)

    # Sample datasheet content from NE555
    sample_datasheet = """
NE555 Timer

8-Pin SOIC Package (8-Lead SOIC, 150 mil)
Pin Configuration:

Pin 1: GND - Ground
Pin 2: TRIGGER - Trigger input
Pin 3: OUTPUT - Output pin
Pin 4: RESET - Reset input
Pin 5: CONTROL VOLTAGE - Control voltage input
Pin 6: THRESHOLD - Threshold input
Pin 7: DISCHARGE - Discharge pin
Pin 8: VCC - Supply voltage (4.5V to 16V)

Dimensions:
Width: 3.9 mm
Height: 4.9 mm
Pitch: 1.27 mm
"""

    print("\n[1] Building messages for pin extraction...")
    messages = build_pin_extraction_prompt(sample_datasheet)
    print(f"  ✅ Messages built: {len(messages)} messages")

    print("\n[2] System prompt preview:")
    print(messages[0]["content"][:200] + "...")

    print("\n[3] Calling LLM (llama-3)...")
    try:
        result = get_completion_from_messages(messages, model="llama-3")
        print("\n--- LLM RESPONSE ---")
        print(result)
        print("\n--- END RESPONSE ---")

        # Try to parse as JSON
        print("\n[4] Parsing response as JSON...")
        try:
            # Remove markdown code blocks if present
            clean_result = result.strip()
            if clean_result.startswith("```json"):
                clean_result = clean_result[7:]
            if clean_result.startswith("```"):
                clean_result = clean_result[3:]
            if clean_result.endswith("```"):
                clean_result = clean_result[:-3]
            clean_result = clean_result.strip()

            pin_data = json.loads(clean_result)
            print(f"  ✅ Valid JSON parsed")
            print(f"  Component: {pin_data.get('component_name', 'Unknown')}")
            print(f"  Package: {pin_data.get('package', {}).get('type', 'Unknown')}-{pin_data.get('package', {}).get('pin_count', 0)}")
            print(f"  Pins extracted: {len(pin_data.get('pins', []))}")
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON parsing failed: {e}")
            print(f"  Raw response: {result[:200]}...")

    except Exception as e:
        print(f"  ❌ LLM call failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
