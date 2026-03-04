#!/usr/bin/env python3
"""Test Vision API with step-by-step layout extraction."""

import io
import requests
import json
import re

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Step-by-step approach: First ask Vision API to identify what it sees
prompt1 = """You are analyzing an electronic component pinout diagram.

## YOUR TASK
Look at this diagram and answer these questions:

1. How many distinct sides/edges of the component have pins?
2. For each side, which pin numbers are shown?
3. How many total pins are shown?

Be VERY thorough - look at the ENTIRE image. Count ALL pins you can see.

Return your answer as a simple text description.
"""

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[10]
    pil_image = page.to_image()
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    img_data = img_bytes.getvalue()

files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt1, "output_token": "2048"}

print("=" * 80)
print("STEP 1: Ask Vision API what it sees")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
print(f"\nVision API says:\n{resp_json.get('description', response.text)}")

# Now try a more specific prompt with the expected layout
prompt2 = """You are analyzing an ESP32-WROOM-32E QFN-38 pinout diagram.

## YOUR TASK
Extract the pin layout and tell me which pins are on each side.

This component has 38 pins arranged in a QFN (Quad Flat No-leads) package.


## YOUR JOB
Look at the diagram and CONFIRM or CORRECT this layout.

## OUTPUT FORMAT (JSON ONLY)
```json
{
  "left_side": [],
  "bottom_edge": [15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
  "right_side": [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
  "top_edge": []
}
```

Return ONLY the JSON - no markdown, no explanation."""

data = {"text": prompt2, "output_token": "4096"}

print("\n" + "=" * 80)
print("STEP 2: Ask with expected layout template")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nRaw response:\n{description}")

# Parse JSON
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
    print("LAYOUT SUMMARY:")
    print("=" * 80)

    for section, pins in layout_data.items():
        count = len(pins)
        print(f"{section:20s}: {count:2d} pins")

    total = sum(len(pins) for pins in layout_data.values())
    print(f"\n{'Total':20s}: {total:2d} pins")

    if total == 38:
        print("\n✓ CORRECT: 38 pins detected")
    else:
        print(f"\n⚠️ Got {total} pins instead of 38")

except json.JSONDecodeError:
    print("\n⚠️ Could not parse JSON from response")
