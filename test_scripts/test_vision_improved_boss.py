#!/usr/bin/env python3
"""Test Vision API with improved prompt based on boss's instructions."""

import io
import requests
import json
import re

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Improved prompt following boss's instructions
prompt = """You are analyzing a pinout diagram from an electronic component datasheet.

## IMPORTANT INSTRUCTIONS - YOU MUST FOLLOW THESE

1. Look at the ENTIRE image carefully
2. Identify which pins are on each side of the component (LEFT, RIGHT, TOP, BOTTOM)
3. Count ALL pins shown - do not miss any pins
4. Note the ORDER of pins on each side
5. Return your answer in JSON format as specified below

## ANALYSIS RULES

**To identify LEFT side pins:**
- Look for pins arranged vertically on the left edge of the component
- These pins are typically numbered starting from 1 or continue from bottom side
- Note the order: top-to-bottom or bottom-to-top

**To identify RIGHT side pins:**
- Look for pins arranged vertically on the right edge of the component
- These pins continue from where left side ended
- Note the order: top-to-bottom or bottom-to-top

**To identify BOTTOM side pins:**
- Look for pins arranged horizontally along the bottom edge
- These pins continue from where right side ended
- Note the order: left-to-right

**To identify TOP side pins:**
- Look for pins arranged horizontally along the top edge
- These pins continue from where bottom side ended
- Note the order: right-to-left

## CRITICAL REQUIREMENTS

- You MUST identify ALL pins visible in the diagram
- You MUST correctly determine which side each pin belongs to
- You MUST list pins in the correct order for each side
- If the diagram shows a table/list, you must interpret it as a physical component layout
- The total number of pins across all sides must equal the number of pins shown

## OUTPUT FORMAT

Return ONLY valid JSON with these exact keys:

```json
{
  "left_side": [list of pin numbers],
  "right_side": [list of pin numbers],
  "bottom_edge": [list of pin numbers],
  "top_edge": [list of pin numbers]
}
```

IMPORTANT:
- Return ONLY the JSON object - no markdown, no explanation
- Use ONLY these exact keys: "left_side", "right_side", "bottom_edge", "top_edge"
- Each key must contain a list of pin numbers (integers)
- The lists can be empty if no pins on that side
- Pin numbers must be in the order they appear on that side"""

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    # Page 11 contains the pinout diagram
    page = pdf.pages[10]
    pil_image = page.to_image()

    # Save to bytes
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    img_data = img_bytes.getvalue()

files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt, "output_token": "4096"}

print("=" * 80)
print("Testing Vision API with Improved Prompt (Boss Instructions)")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nVision API Response Status: {response.status_code}")
print(f"Response Length: {len(description)} chars")

# Parse the response
clean_json = description.strip()
if clean_json.startswith("```json"):
    clean_json = clean_json[7:]
if clean_json.startswith("```"):
    clean_json = clean_json[3:]
if clean_json.endswith("```"):
    clean_json = clean_json[:-3]
clean_json = clean_json.strip()

try:
    layout_data = json.loads(clean_json)

    print("\n" + "=" * 80)
    print("EXTRACTED LAYOUT DATA:")
    print("=" * 80)

    for section, pins in layout_data.items():
        if pins:
            print(f"{section:20s}: {len(pins):2d} pins - {pins}")
        else:
            print(f"{section:20s}: {len(pins):2d} pins")

    total_pins = sum(len(pins) for pins in layout_data.values())
    print(f"\n{'Total':20s}: {total_pins:2d} pins")

    # Validation
    all_pins = []
    for pins in layout_data.values():
        all_pins.extend(pins)
    all_sorted = sorted(all_pins)
    expected = list(range(1, total_pins + 1))

    print("\n" + "=" * 80)
    print("VALIDATION:")
    print("=" * 80)

    if all_sorted == expected:
        print("✓ Pin numbers are consecutive with no gaps")
    else:
        missing = set(expected) - set(all_sorted)
        if missing:
            print(f"⚠️ Missing pins: {sorted(missing)}")

    # Check for expected ESP32-WROOM-32E layout
    print("\n" + "=" * 80)
    print("EXPECTED ESP32-WROOM-32E LAYOUT:")
    print("=" * 80)
    print("  left_side:  14 pins (1-14)")
    print("  bottom_edge: 10 pins (15-24)")
    print("  right_side: 14 pins (25-38)")
    print("  top_edge: 0 pins")
    print(f"  Total: 38 pins\n")

    actual_left = len(layout_data.get('left_side', []))
    actual_bottom = len(layout_data.get('bottom_edge', []))
    actual_right = len(layout_data.get('right_side', []))
    actual_top = len(layout_data.get('top_edge', []))

    print("ACTUAL DETECTED LAYOUT:")
    print(f"  left_side: {actual_left} pins")
    print(f"  bottom_edge: {actual_bottom} pins")
    print(f"  right_side: {actual_right} pins")
    print(f"  top_edge: {actual_top} pins\n")

    if actual_left == 14 and actual_bottom == 10 and actual_right == 14 and actual_top == 0:
        print("✓ LAYOUT MATCHES ESP32-WROOM-32E!")
    else:
        print("⚠️ Layout does NOT match ESP32-WROOM-32E")
        print("  This component has a NON-STANDARD QFN layout")

except json.JSONDecodeError as e:
    print(f"\n⚠️ JSON Parse Error: {e}")
    print("\nRaw response:")
    print(description)

print("\n" + "=" * 80)
print("END OF TEST")
print("=" * 80)
