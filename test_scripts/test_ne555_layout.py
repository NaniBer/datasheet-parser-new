#!/usr/bin/env python3
"""Test layout extraction from NE555 datasheet using Vision API."""

import io
import json
import requests
from PIL import Image
import fitz  # PyMuPDF

pdf_path = "pdfs/NE555.PDF"
api_url = "https://qwen.ideeza.com/describe_image/"

# Role-based prompt
system_prompt = """You are an expert electronics engineer specializing in reading and interpreting electronic component pinout diagrams from datasheets.

You have deep knowledge of:
- Component package types (DIP, SOIC, TQFP, LQFP, QFN, BGA)
- Pin numbering conventions for each package type
- Visual interpretation of physical component layouts
- Datasheet diagram conventions and standards

Your task is to analyze pinout diagrams and extract accurate physical pin layout information."""

user_prompt = """Analyze this pinout diagram. Tell me which side each pin is on.

## Instructions

1. Identify which pins are located on each side of the component (LEFT, RIGHT, TOP, BOTTOM)
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

# Get image from page 1 (index 0)
with fitz.open(pdf_path) as pdf:
    page = pdf[0]
    zoom = 3.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_data = pix.tobytes("png")

# Test 0 degree rotation only
results = []

print("=" * 80)
print("Testing Vision API with NE555 page 1 (0° rotation)")
print("=" * 80)

original_img = Image.open(io.BytesIO(img_data))
rotated_img = original_img.rotate(0, expand=True)

# Save to bytes
img_bytes = io.BytesIO()
rotated_img.save(img_bytes, format="PNG")
img_bytes.seek(0)
rotated_data = img_bytes.getvalue()

# Save for reference
rotated_img.save("ne555_page1_rotated_0.png")

print(f"Image size: {len(rotated_data)} bytes")

files = {"file": ("ne555_page1_rotated_0.png", rotated_data, "image/png")}
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
                "rotation": 0,
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
print("RESULT")
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

# Expected for 8-pin DIP:
# Left: 1, 2, 3, 4 (top to bottom)
# Right: 8, 7, 6, 5 (top to bottom)
