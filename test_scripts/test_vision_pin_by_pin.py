#!/usr/bin/env python3
"""Test Vision API with role-based prompt format."""

import io
import requests
import json
import fitz  # PyMuPDF

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Role-based prompt format (combined into single text)
system_prompt = """You are an expert electronics engineer specializing in reading and interpreting electronic component pinout diagrams from datasheets.

You have deep knowledge of:
- Component package types (DIP, SOIC, TQFP, LQFP, QFN, BGA)
- Pin numbering conventions for each package type
- Visual interpretation of physical component layouts
- Datasheet diagram conventions and standards

Your task is to analyze pinout diagrams and extract accurate physical pin layout information."""

user_prompt = """Analyze the provided pinout diagram and extract the physical pin layout for this component.

## Instructions

1. Identify which pins are located on each side of the component (LEFT, RIGHT, TOP, BOTTOM)
2. List ALL pin numbers for each side
3. Maintain the ORDER of pins as they appear on each side

## Output Format

Return ONLY valid JSON:

{
  "left_side": [1, 2, 3, ...],
  "right_side": [...],
  "bottom_edge": [...],
  "top_edge": []
}

IMPORTANT:
- Do NOT repeat pin numbers - each pin belongs to only one side
- Return ONLY JSON - no markdown code blocks, no explanation"""

# Combine into single prompt
prompt = f"""SYSTEM: {system_prompt}

USER: {user_prompt}"""

print("=" * 80)
print("prompt ", prompt)
print("=" * 80)

print("Opening PDF...")
# Using PyMuPDF (fitz) for better image quality
with fitz.open(pdf_path) as pdf:
    print(f"PDF opened, {len(pdf)} pages")
    page = pdf[36]  # Page index 10 (page 11)
    print(f"Page 36 loaded")

    # Set higher zoom factor for better quality
    zoom = 3.0  # 3x zoom for sharper image
    mat = fitz.Matrix(zoom, zoom)

    # Render page to image
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_data = pix.tobytes("png")

files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt, "output_token": "4096"}
with open("page_37.png", "wb") as f:
    f.write(img_data)
print("image saved as page_11.png for reference")

print("=" * 80)
print("Testing Vision API with role-based prompt format")
print("=" * 80)

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=600)
resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nFull response:\n{description}\n")

# Try to extract JSON
import re
json_match = re.search(r'\{[\s\S]*\}', description)

if json_match:
    json_str = json_match.group()
    try:
        layout_data = json.loads(json_str)

        print("=" * 80)
        print("EXTRACTED LAYOUT:")
        print("=" * 80)

        for section, pins in layout_data.items():
            count = len(pins) if pins else 0
            if count > 0:
                print(f"{section:20s}: {count:2d} pins - {pins}")
            else:
                print(f"{section:20s}: {count:2d} pins")

        total = sum(len(pins) for pins in layout_data.values() if pins)
        print(f"\n{'Total':20s}: {total:2d} pins")

        if total == 38:
            print("\n✓ Correct pin count!")
        else:
            print(f"\n⚠️ Expected 38 pins, got {total}")

    except json.JSONDecodeError as e:
        print(f"⚠️ Could not parse JSON: {e}")
else:
    print("⚠️ No JSON found in response")
