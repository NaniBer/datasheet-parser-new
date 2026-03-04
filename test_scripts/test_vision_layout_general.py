#!/usr/bin/env python3
"""Test Vision API with a general prompt for any datasheet."""

import io
import requests
import json

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# General prompt that teaches the Vision API about datasheet conventions
prompt = """You are analyzing an electronic component pinout diagram from a datasheet.

## DATASHEET DIAGRAM CONVENTIONS

In datasheets, pinout diagrams use visual cues to show physical layout:

1. **LEFT SIDE**: When pins are shown in a vertical column on the LEFT of the diagram body, those pins are on the LEFT side of the physical component.

2. **BOTTOM SIDE**: When pins are shown in a horizontal row at the BOTTOM of the diagram body, those pins are on the BOTTOM edge of the physical component.

3. **RIGHT SIDE**: When pins are shown in a vertical column on the RIGHT of the diagram body, those pins are on the RIGHT side of the physical component.

4. **TOP SIDE**: When pins are shown in a horizontal row at the TOP of the diagram body, those pins are on the TOP edge of the physical component.

## YOUR TASK

1. Look at the ENTIRE image - identify which sides (left, bottom, right, top) have pins
2. For each side, list ALL pin numbers shown
3. Note the ORDER of pins (top-to-bottom for sides, left-to-right for edges)
4. Output the layout as JSON

## OUTPUT FORMAT (JSON ONLY)

```json
{
  "left_side": [1, 2, 3, ...],
  "bottom_edge": [...],
  "right_side": [...],
  "top_edge": [...]
}
```

Use EXACTLY these keys: "left_side", "bottom_edge", "right_side", "top_edge"

Return ONLY valid JSON - no markdown, no explanation.

IMPORTANT:
- List ALL pin numbers from each visible side
- Make sure pin numbers are in the ORDER they appear
- Return ONLY the JSON object"""

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[10]
    pil_image = page.to_image()
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    img_data = img_bytes.getvalue()

files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt, "output_token": "4096"}

print("=" * 80)
print("Testing GENERAL approach for any datasheet")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nRaw response:\n{description}\n")

# Clean and parse
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

    print("=" * 80)
    print("EXTRACTED LAYOUT:")
    print("=" * 80)

    for section, pins in layout_data.items():
        if pins:
            print(f"{section:20s}: {len(pins):2d} pins - {pins}")
        else:
            print(f"{section:20s}: {len(pins):2d} pins")

    total = sum(len(pins) for pins in layout_data.values())
    print(f"\n{'Total':20s}: {total:2d} pins")

    # Validation
    all_pins = []
    for pins in layout_data.values():
        all_pins.extend(pins)
    all_sorted = sorted(all_pins)
    expected = list(range(1, total + 1))

    if all_sorted == expected:
        print("✓ Pin numbers are consecutive with no gaps")
    else:
        missing = set(expected) - set(all_sorted)
        if missing:
            print(f"⚠️ Missing pins: {sorted(missing)}")

except json.JSONDecodeError as e:
    print(f"⚠️ Could not parse JSON: {e}")
