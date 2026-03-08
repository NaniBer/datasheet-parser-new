#!/usr/bin/env python3
"""Debug raw Vision API response with improved prompt."""

import io
import requests

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"
system_prompt = """You are an expert electronics engineer and JSON Generator specializing in reading and interpreting electronic component pinout diagrams from datasheets.

You have deep knowledge of:
- Component package types (DIP, SOIC, TQFP, LQFP, QFN, BGA)
- Pin numbering conventions for each package type
- Visual interpretation of physical component layouts
- Datasheet diagram conventions and standards

Your task is to analyze pinout diagrams and extract accurate physical pin layout information.
## Output Format

Return ONLY valid JSON:

{
  "package_type": "",
  "left_side": [1, 2, 3, ...],
  "right_side": [...],
  "bottom_edge": [...],
  "top_edge": []
}"""

user_prompt = """Analyze the provided pinout diagram and extract the physical pin layout for this component.

## Instructions

1. Identify which pins are located on each side of the component (LEFT, RIGHT, TOP, BOTTOM)
2. List ALL pin numbers for each side
3. Maintain the ORDER of pins as they appear on each side
4. Figure out what kind of package type it is


IMPORTANT:
- Do NOT repeat pin numbers - each pin belongs to only one side
- Return ONLY JSON - no markdown code blocks, no explanation"""

# Combine into single prompt
prompt = f"""SYSTEM: {system_prompt}

USER: {user_prompt}"""


import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[9]  # Page 11
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
    "output_token": "4096"  # Increased to avoid truncation
}

print("Sending request...")
response = requests.post(
    api_url,
    headers={"accept": "application/json"},
    files=files,
    data=data,
    timeout=120
)

print(f"Status: {response.status_code}")
print(f"Response length: {len(response.text)}")
print("\n--- RAW RESPONSE (first 3000 chars) ---")
print(response.text)
print("\n--- FULL RESPONSE LENGTH ---")
print(f"Total: {len(response.text)} chars")
