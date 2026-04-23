#!/usr/bin/env python3
"""Test all-variants table extraction on multiple PDFs."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chat_bot import build_table_extraction_prompt, get_completion_from_messages

# Test data from various PDFs (table data from actual extractions)
test_cases = [
    {
        "name": "MAX1487-MAX491",
        "pdf": "MAX1487-MAX491.pdf",
        "description": "RS-485 transceiver, likely multiple package variants",
        "table_data": """
[
  ["PIN", "NAME", "FUNCTION", "SO", "DIP"],
  [1, "RO", "Receiver Output", 1, 1],
  [2, "\\u2014", "No Connection", 2, 2],
  [3, "\\u2014", "No Connection", 3, 3],
  [4, "DI", "Driver Input", 4, 4],
  [5, "GND", "Ground", 5, 5],
  [6, "A", "Driver Output / Receiver Input", 6, 6],
  [7, "B", "Driver Output / Receiver Input", 7, 7],
  [8, "VCC", "Power Supply", 8, 8]
]
"""
    },
    {
        "name": "MPU-6000",
        "pdf": "MPU-6000-Datasheet1.pdf",
        "description": "IMU sensor, LGA-24 package",
        "table_data": """
[
  ["PIN", "NAME", "FUNCTION"],
  [1, "CLKIN", "External Clock Input"],
  [2, "VDDIO", "Digital I/O Supply Voltage"],
  [3, "GND", "Ground"],
  [4, "AD0", "I2C Slave Address LSB"],
  [5, "REGOUT", "Voltage Regulator Output"],
  [6, "GND", "Ground"],
  [7, "CPOUT", "Charge Pump Capacitor"],
  [8, "CLKOUT", "Clock Output"],
  [9, "AUX_DA", "I2C Master Data"],
  [10, "AUX_CL", "I2C Master Clock"],
  [11, "VSYNC", "Frame Synchronization"],
  [12, "FSYNC", "Frame Synchronization"],
  [13, "INT", "Interrupt"],
  [14, "GND", "Ground"],
  [15, "VDD", "Analog Supply Voltage"],
  [16, "NC", "No Connection"],
  [17, "NC", "No Connection"],
  [18, "GND", "Ground"],
  [19, "NC", "No Connection"],
  [20, "CPOUT", "Charge Pump Capacitor"],
  [21, "GND", "Ground"],
  [22, "RESV", "Reserved"],
  [23, "GND", "Ground"],
  [24, "VDD", "Analog Supply Voltage"]
]
"""
    },
    {
        "name": "NE555",
        "pdf": "NE555.pdf",
        "description": "Timer IC, DIP-8 package",
        "table_data": """
[
  ["PIN", "NAME", "FUNCTION"],
  [1, "GND", "Ground"],
  [2, "TRIG", "Trigger"],
  [3, "OUT", "Output"],
  [4, "RESET", "Reset"],
  [5, "CV", "Control Voltage"],
  [6, "THR", "Threshold"],
  [7, "DIS", "Discharge"],
  [8, "VCC", "Power Supply"]
]
"""
    }
]

print("=" * 80)
print("Testing All-Variants Table Extraction on Multiple PDFs")
print("=" * 80)

for i, test_case in enumerate(test_cases, 1):
    print(f"\n{'=' * 80}")
    print(f"TEST {i}: {test_case['name']}")
    print(f"PDF: {test_case['pdf']}")
    print(f"Description: {test_case['description']}")
    print("=" * 80)

    try:
        # Build the prompt
        messages = build_table_extraction_prompt(test_case['table_data'].strip())

        print(f"\nSending to LLM...")

        # Call LLM
        response = get_completion_from_messages(messages)

        # Parse the response
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()

        import json
        data = json.loads(clean_response)

        # Display results
        print(f"\n✅ SUCCESS")
        print(f"Component: {data.get('component_name', 'Unknown')}")
        print(f"Extraction Method: {data.get('extraction_method', 'Unknown')}")

        if 'packages' in data:
            packages = data['packages']
            print(f"Number of packages: {len(packages)}")

            for j, pkg in enumerate(packages, 1):
                print(f"\n--- Package {j} ---")
                print(f"Type: {pkg.get('type', 'Unknown')}")
                print(f"Pin Count: {pkg.get('pin_count', 0)}")

                pins = pkg.get('pins', [])
                print(f"Number of pins extracted: {len(pins)}")

                # Check for duplicates
                pin_numbers = [p['number'] for p in pins]
                has_duplicates = len(pin_numbers) != len(set(pin_numbers))

                print(f"Has duplicates: {'YES ❌' if has_duplicates else 'NO ✓'}")

                # Show first few pins
                if len(pins) > 0:
                    print(f"\nFirst 5 pins:")
                    for pin in pins[:5]:
                        print(f"  Pin {pin.get('number'):2d}: {pin.get('name'):12s} ({pin.get('function')})")

                    if len(pins) > 5:
                        print(f"  ... and {len(pins) - 5} more pins")

        elif 'package' in data:
            print("\n⚠️  Legacy single-package format (not packages array)")

        # Show issues
        print(f"\nIssues Found:")
        issues = []

        # Note: component_name is now optional, so "Unknown" is acceptable
        # Only flag as issue if it's missing entirely or empty
        if 'component_name' not in data or not data.get('component_name'):
            issues.append("Component name field missing (should be present, even if 'Unknown')")

        if 'packages' in data:
            for pkg in data['packages']:
                pins = pkg.get('pins', [])
                pin_numbers = [p['number'] for p in pins]
                if len(pin_numbers) != len(set(pin_numbers)):
                    issues.append(f"Package {pkg.get('type')} has duplicate pins")

                # Check for dashes instead of NC
                for pin in pins:
                    if pin.get('name') in ['—', '-', '']:
                        issues.append(f"Package {pkg.get('type')} pin {pin.get('number')} has '{pin.get('name')}' instead of 'NC'")

        if len(issues) == 0:
            print("  None ✓")
        else:
            for issue in issues:
                print(f"  ❌ {issue}")

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON PARSE ERROR: {e}")
        print(f"First 200 chars of response: {clean_response[:200]}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("Testing complete. Check results above for details on each PDF.")
