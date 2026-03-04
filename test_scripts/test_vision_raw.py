#!/usr/bin/env python3
"""
Show raw output from Vision API for debugging.

This will show exactly what the Vision API returns before any parsing.
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.image_ocr_client import ImageOCRClient

def show_raw_vision_output(page_num: int):
    """
    Get raw Vision API output for a specific page.

    Args:
        page_num: Page number to process
    """
    pdf_path = "pdfs/test.pdf"

    print("=" * 80)
    print(f"Vision API Raw Output for Page {page_num}")
    print("=" * 80)

    # Open PDF and convert page to image
    import pdfplumber
    import io

    with pdfplumber.open(pdf_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"Error: Page {page_num} does not exist")
            return

        page = pdf.pages[page_num - 1]

        # Convert page to image
        pil_image = page.to_image()

        # Save to bytes
        img_bytes = io.BytesIO()
        pil_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_data = img_bytes.getvalue()

        print(f"\nImage converted: {len(img_data)} bytes")

    # Create Vision client
    vision_client = ImageOCRClient(
        api_url="https://qwen.ideeza.com/describe_image/",
        output_token=4096,
        timeout=120
    )

    # Build prompt
    prompt = """You are an expert at reading electronic component pinout diagrams from datasheet images.

IMPORTANT: Extract COMPLETE pinout information including:
1. ALL Power pins: VCC, GND, AVCC, AREF, XTAL1, XTAL2
2. ALL Control pins: RESET, XTAL1, XTAL2
3. ALL Port pins: PB0-PB39, PA0-PA7, PC0-PC7, PD0-PD7
4. Pin numbers 1-40 for TQFP package

Format:
{
  "component_name": "Component Name",
  "package_type": "Package Type (e.g., TQFP/MLF-44)",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "Pin Name", "function": "Function"},
    ...
  ],
  "extraction_confidence": 0.95,
  "notes": "Notes about extraction quality"
}

Return ONLY valid JSON - no markdown, no additional text."""

    # Prepare request
    files = {
        "file": (f"page_{page_num}.png", img_data, "image/png")
    }
    data = {
        "text": prompt,
        "output_token": str(4096)
    }

    print(f"\nSending request to API...")
    print(f"API URL: {vision_client.api_url}")
    print(f"Prompt length: {len(prompt)} chars")

    # Send to API
    import requests
    try:
        response = requests.post(
            vision_client.api_url,
            headers={"accept": "application/json"},
            files=files,
            data=data,
            timeout=120
        )

        print(f"\n{'='*80}")
        print("RESPONSE STATUS:")
        print(f"  Status Code: {response.status_code}")
        print(f"  Headers: {dict(response.headers)}")

        # Try to get JSON
        try:
            json_response = response.json()
            print(f"\n{'='*80}")
            print("RAW JSON RESPONSE:")
            print(json.dumps(json_response, indent=2, ensure_ascii=False))
        except ValueError:
            print(f"\n{'='*80}")
            print("RAW TEXT RESPONSE (Not JSON):")
            print(response.text[:5000])

        # If response is too large, show preview
        response_text = response.text
        if len(response_text) > 10000:
            print(f"\n{'='*80}")
            print("FULL RESPONSE (first 10000 chars):")
            print(response_text[:10000])
            print(f"\n... (response is {len(response_text)} total chars)")
        else:
            print(f"\n{'='*80}")
            print("FULL RESPONSE:")
            print(response_text)

    except requests.exceptions.RequestException as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    show_raw_vision_output(11)
