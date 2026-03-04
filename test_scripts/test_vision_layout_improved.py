#!/usr/bin/env python3
"""Test Vision API with improved prompt for layout extraction."""

import io
import requests
import json
import re

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Improved prompt that asks for JSON in the exact format pin_layout.py expects
prompt = """You are analyzing an electronic component pin layout diagram.

## YOUR TASK
Extract the pin LAYOUT structure from this QFN package pinout diagram.

## CRITICAL INSTRUCTIONS
1. Look at the ENTIRE image - count ALL pins visible (this component has 38 pins)
2. Identify which pins are on each side: LEFT, BOTTOM, RIGHT, TOP
3. Note the ORDER of pins on each side (top-to-bottom or left-to-right)
4. Return ONLY valid JSON

## HOW TO IDENTIFY PINS
- Left side: Pins running vertically on the left edge of the package
- Bottom side: Pins running horizontally along the bottom edge
- Right side: Pins running vertically on the right edge
- Top side: Pins running horizontally along the top edge (if present)

## OUTPUT FORMAT (STRICT JSON ONLY)
Return ONLY valid JSON - no markdown, no explanation:

```json
{
  "left_side": [1, 2, 3, ...],
  "bottom_edge": [15, 16, ...],
  "right_side": [25, 26, ...],
  "top_edge": []
}
```

IMPORTANT:
- Use EXACTLY these keys: "left_side", "bottom_edge", "right_side", "top_edge"
- List pin numbers IN THE ORDER they appear (top-to-bottom for sides, left-to-right for edges)
- List ALL pin numbers - no gaps, no missing pins
- Total pin count must equal the sum of all pins in all sections
- Return ONLY the JSON object - no text before or after"""

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

files = {
    "file": ("page_11.png", img_data, "image/png")
}
data = {
    "text": prompt,
    "output_token": "4096"
}

print("=" * 80)
print("Sending request to Vision API...")
print("=" * 80)

response = requests.post(
    api_url,
    headers={"accept": "application/json"},
    files=files,
    data=data,
    timeout=120
)

print(f"\nStatus: {response.status_code}")
print(f"Response length: {len(response.text)} chars")

# Parse response
try:
    resp_json = json.loads(response.text)
    description = resp_json.get("description", response.text)

    # Clean up markdown code blocks
    clean_json = description.strip()
    if clean_json.startswith("```json"):
        clean_json = clean_json[7:]
    if clean_json.startswith("```"):
        clean_json = clean_json[3:]
    if clean_json.endswith("```"):
        clean_json = clean_json[:-3]
    clean_json = clean_json.strip()

    print("\n" + "=" * 80)
    print("PARSED LAYOUT DATA:")
    print("=" * 80)
    print(clean_json)

    # Parse the JSON
    layout_data = json.loads(clean_json)

    print("\n" + "=" * 80)
    print("LAYOUT SUMMARY:")
    print("=" * 80)

    for section, pins in layout_data.items():
        count = len(pins)
        print(f"{section:20s}: {count:2d} pins - {pins}")

    # Validate
    total_pins = sum(len(pins) for pins in layout_data.values())
    print(f"\n{'Total':20s}: {total_pins:2d} pins")

    if total_pins == 38:
        print("\n✓ CORRECT: 38 pins detected")
    else:
        print(f"\n⚠️ INCORRECT: Expected 38 pins, got {total_pins}")

    # Check for gaps
    all_pins = []
    for pins in layout_data.values():
        all_pins.extend(pins)
    all_pins_sorted = sorted(all_pins)
    expected = list(range(1, total_pins + 1))

    if all_pins_sorted == expected:
        print("✓ Pin numbers are consecutive with no gaps")
    else:
        print("⚠️ Pin numbers have gaps or duplicates")
        missing = set(expected) - set(all_pins_sorted)
        if missing:
            print(f"   Missing pins: {sorted(missing)}")
        duplicates = [p for p in all_pins if all_pins.count(p) > 1]
        if duplicates:
            print(f"   Duplicate pins: {set(duplicates)}")

except json.JSONDecodeError as e:
    print(f"\nJSON Parse Error: {e}")
    print("\nRaw response:")
    print(response.text)
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
