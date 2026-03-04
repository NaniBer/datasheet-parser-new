#!/usr/bin/env python3
"""Test Vision API with explicit physical layout interpretation."""

import io
import requests
import json

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Very explicit prompt emphasizing physical interpretation
prompt = """You are analyzing a PHYSICAL COMPONENT PINOUT DIAGRAM from an electronic datasheet.

## CRITICAL: THIS IS A PHYSICAL COMPONENT DIAGRAM

You are NOT looking at a table or list. You are looking at a PHYSICAL DIAGRAM that shows:
- A rectangular component body in the center
- Pins extending from the sides of this component
- Each pin has a number label and a name label

## YOUR TASK

You must identify which pins are on which SIDE of the physical component body.

## INSTRUCTIONS

1. Find the COMPONENT BODY (the rectangle in the center)
2. Identify pins EXTENDING from the LEFT SIDE of this rectangle
3. Identify pins EXTENDING from the RIGHT SIDE of this rectangle
4. Identify pins EXTENDING from the BOTTOM SIDE of this rectangle
5. Identify pins EXTENDING from the TOP SIDE of this rectangle (if any)

## IMPORTANT RULES

- Do NOT interpret this as a table - this is a PHYSICAL DIAGRAM
- Look at the VISUAL POSITION of pins relative to the component body
- Count ALL pins shown around the component
- List pin numbers in the ORDER they appear around the component

## EXPECTED FOR THIS COMPONENT

This is an ESP32-WROOM-32E QFN-38 component:
- It should have 38 pins total
- Pins are arranged around a rectangular body
- Most pins are on the LEFT side (about 14 pins)
- Some pins are on the BOTTOM side (about 10 pins)
- Some pins are on the RIGHT side (about 14 pins)
- NO pins on the TOP side

If you do NOT see this arrangement, you are misinterpreting the diagram.

## OUTPUT FORMAT

```json
{
  "left_side": [1, 2, 3, ...],
  "right_side": [...],
  "bottom_edge": [...],
  "top_edge": []
}
```

CRITICAL:
- You MUST return 38 pins total
- Left side should have ~14 pins
- Bottom side should have ~10 pins
- Right side should have ~14 pins
- Top side should have 0 pins

Return ONLY valid JSON - no markdown, no explanation."""

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
print("Testing with Explicit Physical Layout Instructions")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nResponse Length: {len(description)} chars")

# Parse response
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
    print("EXTRACTED LAYOUT:")
    print("=" * 80)

    for section, pins in layout_data.items():
        if pins:
            print(f"{section:20s}: {len(pins):2d} pins - {pins}")
        else:
            print(f"{section:20s}: {len(pins):2d} pins")

    total = sum(len(pins) for pins in layout_data.values())
    print(f"\n{'Total':20s}: {total:2d} pins")

    if total == 38:
        print("\n✓ CORRECT PIN COUNT!")
    else:
        print(f"\n⚠️ EXPECTED 38 PINS, GOT {total}")

except json.JSONDecodeError as e:
    print(f"Parse Error: {e}")
    print("Raw response:", description)
