#!/usr/bin/env python3
"""First ask Vision API to describe what it sees."""

import io
import requests
import json

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Step 1: Just ask to describe the diagram
prompt = """You are analyzing an electronic component pinout diagram.

Please describe what you see in this image. Focus on:
1. What is in the center of the image?
2. What is arranged around the center?
3. How many items/pins do you see?
4. How are they arranged (vertically, horizontally, in a grid)?

Be specific and detailed in your description."""

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[10]
    pil_image = page.to_image()
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    img_data = img_bytes.getvalue()

files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt, "output_token": "1024"}

print("=" * 80)
print("STEP 1: Ask Vision API to describe what it sees")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nDescription:\n{description}\n")

# Step 2: Based on that, give more specific instructions
prompt2 = f"""Based on the ESP32-WROOM-32E QFN-38 component pinout diagram you just described:

You need to identify which pins are on each side of the component body.

The component has 38 pins arranged around a rectangular body:
- LEFT SIDE: Pins 1-14 (14 pins total)
- BOTTOM SIDE: Pins 15-24 (10 pins total)
- RIGHT SIDE: Pins 25-38 (14 pins total)
- TOP SIDE: No pins

Return the layout in this JSON format:

```json
{{
  "left_side": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
  "right_side": [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
  "bottom_edge": [15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
  "top_edge": []
}}
```

Return ONLY the JSON - no markdown, no explanation."""

data = {"text": prompt2, "output_token": "2048"}

print("=" * 80)
print("STEP 2: Ask for specific layout with expected format")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
description2 = resp_json.get('description', response.text)

print(f"\nResponse:\n{description2}\n")

# Parse if JSON
clean_json = description2.strip()
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
except:
    pass
