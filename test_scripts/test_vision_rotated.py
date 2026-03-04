#!/usr/bin/env python3
"""Test Vision API with rotated images to get better layout detection."""

import io
import json
import requests
from PIL import Image
import fitz  # PyMuPDF

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"

# Role-based prompt format (system + user)
system_prompt = """You are an expert electronics engineer specializing in reading and interpreting electronic component pinout diagrams from datasheets.

You have deep knowledge of:
- Component package types (DIP, SOIC, TQFP, LQFP, QFN, BGA)
- Pin numbering conventions for each package type
- Visual interpretation of physical component layouts
- Datasheet diagram conventions and standards

Your task is to analyze pinout diagrams and extract accurate physical pin layout information."""

user_prompt = """Analyze this pinout diagram. Tell me which side each pin is on.

## Instructions

1. Look at the diagram and identify which pins are on each side of the component
2. List ALL pin numbers for each side
3. Each pin belongs to exactly ONE side - no duplicates

## Output Format

Return ONLY valid JSON (no markdown code blocks):

{
  "left_side": [pin numbers],
  "right_side": [pin numbers],
  "bottom_edge": [pin numbers],
  "top_edge": [pin numbers]
}"""

# Combine into single prompt
prompt = f"""SYSTEM: {system_prompt}

USER: {user_prompt}"""

# Get the image from PDF
with fitz.open(pdf_path) as pdf:
    page = pdf[9]
    zoom = 3.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_data = pix.tobytes("png")

# Load with PIL for rotation
original_img = Image.open(io.BytesIO(img_data))

# Test all rotations
results = []
rotations = [0]

print("=" * 80)
print("Testing Vision API with all rotations (page 10)")
print("=" * 80)

for angle in rotations:
    # Rotate image
    rotated_img = original_img.rotate(angle, expand=True)

    # Save to bytes
    img_bytes = io.BytesIO()
    rotated_img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    rotated_data = img_bytes.getvalue()

    # Save for reference
    rotated_img.save(f"page_37_rotated_{angle}.png")

    print(f"\n--- Testing {angle}° rotation ---")
    print(f"Image size: {len(rotated_data)} bytes")

    files = {"file": (f"page_37_rotated_{angle}.png", rotated_data, "image/png")}
    data = {"text": prompt, "output_token": "4096"}

    try:
        response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=60)
        response_data = response.json()
        description = response_data.get('description', response.text)

        print(f"Response: {description[:200]}...")

        # Try to extract JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', description)
        if json_match:
            json_str = json_match.group()
            try:
                layout = json.loads(json_str)
                results.append({
                    "rotation": angle,
                    "layout": layout
                })
                print(f"✓ Parsed JSON: {layout}")
            except json.JSONDecodeError as e:
                print(f"✗ JSON parse error: {e}")
        else:
            print(f"✗ No JSON found in response")

    except Exception as e:
        print(f"✗ Error: {e}")

# Print summary
print("\n" + "=" * 80)
print("SUMMARY OF ALL ROTATIONS")
print("=" * 80)

for result in results:
    print(f"\nRotation: {result['rotation']}°")
    layout = result['layout']
    for side, pins in layout.items():
        if pins:
            print(f"  {side:20s}: {len(pins):2d} pins - {pins}")
        else:
            print(f"  {side:20s}:  0 pins")

print("\n" + "=" * 80)
