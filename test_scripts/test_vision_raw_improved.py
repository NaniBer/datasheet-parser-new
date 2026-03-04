#!/usr/bin/env python3
"""Debug raw Vision API response with improved prompt."""

import io
import requests

pdf_path = "pdfs/pages.pdf"
api_url = "https://qwen.ideeza.com/describe_image/"
system_prompt = """You are an expert electronics engineer specializing in reading and interpreting electronic component pinout diagrams from datasheets.

You have deep knowledge of:
- Component package types (DIP, SOIC, TQFP, LQFP, QFN, BGA)
- Pin numbering conventions for each package type
- Visual interpretation of physical component layouts
- Datasheet diagram conventions and standards

Your task is to analyze pinout diagrams and extract accurate physical pin layout information."""

user_prompt = """Find and tell me where each of these pins is located in the diagram:

Pin 1, Pin 5, Pin 10, Pin 14: Which side?
Pin 15, Pin 20, Pin 24: Which side?
Pin 25, Pin 30, Pin 35, Pin 38: Which side?

For each pin, tell me: LEFT, RIGHT, BOTTOM, or TOP edge of the component.

Then return JSON:

{
  "left_side": [all pins on left edge],
  "right_side": [all pins on right edge],
  "bottom_edge": [all pins on bottom edge],
  "top_edge": [all pins on top edge]
}"""

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
