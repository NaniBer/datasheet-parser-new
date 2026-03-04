#!/usr/bin/env python3
"""Test two-step Vision API approach."""

import io
import requests
import json

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Step 1: Describe the diagram structure
step1_prompt = """You are analyzing a pinout diagram from an electronic datasheet.

## YOUR TASK
Describe the STRUCTURE of this diagram. DO NOT list individual pins.

Answer these questions:

1. What type of diagram is this? (table, grid, physical representation, etc.)
2. How are pins arranged? (rows, columns, around edges, etc.)
3. How many distinct groups of pins do you see?
4. Where is each group positioned relative to the center/label?
5. What is the approximate shape? (L-shaped, U-shaped, rectangular, etc.)

Keep your answer brief and focused on STRUCTURE only."""

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[10]
    pil_image = page.to_image()
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    img_data = img_bytes.getvalue()

files = {"file": ("page_11.png", img_data, "image/png")}

print("=" * 80)
print("STEP 1: Describe diagram structure")
print("=" * 80)

data = {"text": step1_prompt, "output_token": "1024"}
response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
structure_desc = resp_json.get('description', response.text)
print(f"\n{structure_desc}\n")

# Step 2: Extract layout based on structure
step2_prompt = f"""You are analyzing a pinout diagram.

## DIAGRAM STRUCTURE
{structure_desc}

## YOUR TASK
Based on the structure above, extract which pin numbers belong to each side/section of the physical component.

Look for these visual cues:
- PINS ON LEFT: Vertical list on the left side of the diagram
- PINS ON BOTTOM: Horizontal row along the bottom edge
- PINS ON RIGHT: Vertical list on the right side
- PINS ON TOP: Horizontal row along the top edge

Count ALL pins shown - make sure you don't miss any!

## OUTPUT FORMAT (JSON ONLY)
```json
{{
  "left_side": [1, 2, 3, ...],
  "bottom_edge": [...],
  "right_side": [...],
  "top_edge": [...]
}}
```

Return ONLY valid JSON - no markdown, no explanation."""

print("=" * 80)
print("STEP 2: Extract layout based on structure")
print("=" * 80)

data = {"text": step2_prompt, "output_token": "4096"}
response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=120)
resp_json = json.loads(response.text)
layout_desc = resp_json.get('description', response.text)

print(f"\nRaw response:\n{layout_desc}\n")

# Clean and parse
clean_json = layout_desc.strip()
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

    if total == 38:
        print("\n✓ Correct pin count!")
    else:
        print(f"\n⚠️ Expected 38 pins, got {total}")

except json.JSONDecodeError as e:
    print(f"⚠️ Could not parse JSON: {e}")
