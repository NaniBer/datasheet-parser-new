#!/usr/bin/env python3
"""Test the new all-variants table extraction on 74HC595 table data."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chat_bot import build_table_extraction_prompt, get_completion_from_messages

# Table data from 74HC595 datasheet (from hybrid_extraction_test.txt)
table_data = """
[
  [
    "PIN",
    "I/O(1)",
    "DESCRIPTION"
  ],
  [
    "NAME",
    "SOIC, PDIP, SO, CDIP, SSOP, or TSSOP",
    "LCCC"
  ],
  [
    "GND",
    "8",
    "10",
    "\u2014",
    "Ground Pin"
  ],
  [
    "OE",
    "13",
    "17",
    "I",
    "Output Enable"
  ],
  [
    "QA",
    "15",
    "19",
    "O",
    "QA Output"
  ],
  [
    "QB",
    "1",
    "2",
    "O",
    "QB Output"
  ],
  [
    "QC",
    "2",
    "3",
    "O",
    "QC Output"
  ],
  [
    "QD",
    "3",
    "4",
    "O",
    "QD Output"
  ],
  [
    "QE",
    "4",
    "5",
    "O",
    "QE Output"
  ],
  [
    "QF",
    "5",
    "7",
    "O",
    "QF Output"
  ],
  [
    "QG",
    "6",
    "8",
    "O",
    "QG Output"
  ],
  [
    "QH",
    "7",
    "9",
    "O",
    "QH Output"
  ],
  [
    "QH'",
    "9",
    "12",
    "O",
    "QH' Output"
  ],
  [
    "RCLK",
    "12",
    "14",
    "I",
    "RCLK Input"
  ],
  [
    "SER",
    "14",
    "18",
    "I",
    "SER Input"
  ],
  [
    "SRCLK",
    "11",
    "14",
    "I",
    "SRCLK Input"
  ],
  [
    "SRCLR",
    "10",
    "13",
    "I",
    "SRCLR Input"
  ],
  [
    "NC",
    "\u2014",
    "1",
    "\u2014",
    "No Connection"
  ],
  [
    "16"
  ],
  [
    "11"
  ],
  [
    "16"
  ],
  [
    "VCC",
    "\u2014",
    "20",
    "\u2014",
    "Power Pin"
  ]
]
"""

print("=" * 80)
print("Testing All-Variants Table Extraction on 74HC595")
print("=" * 80)

# Build the prompt
messages = build_table_extraction_prompt(table_data.strip())

print("\nSending to LLM...")
print(f"Prompt length: {len(str(messages))} characters")

try:
    # Call LLM
    response = get_completion_from_messages(messages)

    print("\n" + "=" * 80)
    print("LLM RESPONSE:")
    print("=" * 80)
    print(response)
    print("=" * 80)

    # Parse and analyze the response
    import json

    # Use same cleaning logic as LLM client
    clean_response = response.strip()
    if clean_response.startswith("```json"):
        clean_response = clean_response[7:]
    if clean_response.startswith("```"):
        clean_response = clean_response[3:]
    if clean_response.endswith("```"):
        clean_response = clean_response[:-3]
    clean_response = clean_response.strip()

    print(f"\nCleaned JSON (first 200 chars): {clean_response[:200]}")

    try:
        data = json.loads(clean_response)

        print("\nPARSED RESPONSE:")
        print(f"Component: {data.get('component_name', 'Unknown')}")
        print(f"Extraction Method: {data.get('extraction_method', 'Unknown')}")

        if 'packages' in data:
            packages = data['packages']
            print(f"\nNumber of packages extracted: {len(packages)}")

            for i, pkg in enumerate(packages):
                print(f"\n--- Package {i+1} ---")
                print(f"Type: {pkg.get('type', 'Unknown')}")
                print(f"Pin Count: {pkg.get('pin_count', 0)}")

                pins = pkg.get('pins', [])
                print(f"Number of pins: {len(pins)}")

                if len(pins) > 0:
                    print("\nFirst 5 pins:")
                    for pin in pins[:5]:
                        print(f"  Pin {pin.get('number')}: {pin.get('name')} ({pin.get('function')})")

                    if len(pins) > 5:
                        print(f"  ... and {len(pins) - 5} more pins")

            # Check for duplicates
            print("\nCHECKING FOR DUPLICATES:")
            for i, pkg in enumerate(packages):
                pin_numbers = [p['number'] for p in pkg.get('pins', [])]
                if len(pin_numbers) != len(set(pin_numbers)):
                    print(f"  ⚠️  Package {i+1} has duplicate pin numbers!")
                else:
                    print(f"  ✓ Package {i+1} has no duplicate pin numbers")

        elif 'package' in data:
            print("\n⚠️  Legacy single-package format returned (should be packages array)")
            pkg = data['package']
            print(f"Type: {pkg.get('type', 'Unknown')}")
            print(f"Pin Count: {pkg.get('pin_count', 0)}")

    except json.JSONDecodeError as e:
        print(f"\n❌ Failed to parse JSON: {e}")
        print("Response was not valid JSON")

except Exception as e:
    print(f"\n❌ Error calling LLM: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
