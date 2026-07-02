#!/usr/bin/env python3
"""Simple test to check if LLM API is working."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chat_bot import build_table_extraction_prompt, get_completion_from_messages
import time

# Simple table data for 74HC595
table_data = """
[
  ["PIN", "I/O(1)", "DESCRIPTION"],
  ["NAME", "SOIC, PDIP, SO, CDIP, SSOP, or TSSOP", "LCCC"],
  ["GND", "8", "10", "\u2014", "Ground Pin"],
  ["QA", "15", "19", "O", "QA Output"],
  ["QB", "1", "2", "O", "QB Output"]
]
"""

print("=" * 80)
print("Simple LLM API Test")
print("=" * 80)

# Build prompt
messages = build_table_extraction_prompt(table_data.strip())
print(f"Prompt length: {len(str(messages))} characters")

print("\nCalling LLM API with timeout...")

start_time = time.time()

try:
    response = get_completion_from_messages(messages)
    end_time = time.time()

    print(f"\n✅ LLM responded in {end_time - start_time:.1f} seconds")

    # Parse response
    import json
    clean_response = response.strip()
    if clean_response.startswith("```json"):
        clean_response = clean_response[7:]
    if clean_response.startswith("```"):
        clean_response = clean_response[3:]
    if clean_response.endswith("```"):
        clean_response = clean_response[:-3]
    clean_response = clean_response.strip()

    data = json.loads(clean_response)

    print(f"\nParsed successfully!")
    print(f"Component: {data.get('component_name', 'Unknown')}")
    print(f"Packages: {len(data.get('packages', []))}")

    # Show first package
    if 'packages' in data and len(data['packages']) > 0:
        pkg = data['packages'][0]
        print(f"\nPackage: {pkg['type']}")
        print(f"Pin count: {pkg['pin_count']}")
        print(f"Number of pins: {len(pkg.get('pins', []))}")

except Exception as e:
    elapsed = time.time() - start_time
    print(f"\n❌ Error after {elapsed:.1f} seconds: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
