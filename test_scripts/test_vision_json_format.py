#!/usr/bin/env python3
"""Test Vision API with JSON format requirement."""

import io
import json
import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.image_ocr_client import ImageOCRClient

# Explicit JSON format prompt
JSON_FORMAT_PROMPT = """You are an expert at reading electronic component pinout diagrams from datasheet images.

EXACT TASK: Extract complete pinout information from this TQFP/MLF pinout diagram and return as JSON.

OUTPUT FORMAT MUST BE:

{
  "component_name": "Component Name",
  "package_type": "Package Type",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "Pin Name", "function": "Function Description"},
    {"number": 2, "name": "Pin Name", "function": "Function Description"},
    ...
  ]
}

REQUIREMENTS:
1. Extract ALL 40 pins numbered 1-40
2. Read diagram counter-clockwise starting from Pin 1 (top-left)
3. Identify pin names exactly as shown
4. Classify functions (power, ground, input/output, reset, etc.)

RETURN ONLY THE JSON OBJECT - no markdown, no additional text, no explanations."""

def test_json_format():
    """Test Vision API with JSON format requirement."""
    pdf_path = "pdfs/test.pdf"

    print("=" * 80)
    print("Testing Vision API with JSON Format Requirement")
    print("=" * 80)

    # Open PDF and convert page 11 to image
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[10]  # Page 11 (0-indexed)
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
        "text": JSON_FORMAT_PROMPT,
        "output_token": "4096"
    }

    print("\n" + "=" * 80)
    print("Sending request...")
    print(f"Prompt: {len(JSON_FORMAT_PROMPT)} chars")

    import requests
    response = requests.post(
        "https://qwen.ideeza.com/describe_image/",
        headers={"accept": "application/json"},
        files=files,
        data=data,
        timeout=120
    )

    print(f"\nStatus: {response.status_code}")
    print(f"Response length: {len(response.text)}")

    print("\n" + "-" * 80)
    print("RAW RESPONSE (first 2000 chars):")
    print(response.text[:2000])
    print("\n" + "-" * 80)

    # Try to parse as JSON
    try:
        # Check if response has "description" field
        resp_json = json.loads(response.text)

        if "description" in resp_json:
            desc = resp_json["description"]
            print("\n--- DESCRIPTION FIELD FOUND ---")
            print(f"Description length: {len(desc)}")
            print(f"Description: {desc[:500]}")

            # Try to extract JSON from description
            # Look for JSON pattern in description
            json_match = re.search(r'\{[\s\S]*\}', desc, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                print("\n--- JSON EXTRACTED FROM DESCRIPTION ---")
                print(f"JSON string length: {len(json_str)}")

                # Parse the extracted JSON
                try:
                    pin_data = json.loads(json_str)
                    print(f"\nComponent: {pin_data.get('component_name', 'Unknown')}")
                    print(f"Package: {pin_data.get('package_type', 'Unknown')}")
                    print(f"Pin count: {pin_data.get('pin_count', 0)}")

                    pins = pin_data.get('pins', [])
                    print(f"\nExtracted {len(pins)} pins:")

                    for pin in pins[:10]:  # First 10
                        num = pin.get('number', '?')
                        name = pin.get('name', '?')
                        func = pin.get('function', 'N/A')
                        print(f"  Pin {num:>2}: {name:<20} {func}")

                    if len(pins) > 10:
                        print(f"  ... and {len(pins) - 10} more pins")

                    print(f"\nTotal: {len(pins)} pins")

                except json.JSONDecodeError as e:
                    print(f"\nFailed to parse extracted JSON: {e}")
            else:
                print("\nNo JSON found in description")

        # Check if response is already a JSON object
        elif "component_name" in resp_json or "pins" in resp_json:
            print("\n--- DIRECT JSON RESPONSE ---")
            print(json.dumps(resp_json, indent=2, ensure_ascii=False))

            pin_data = resp_json
            print(f"\nComponent: {pin_data.get('component_name', 'Unknown')}")
            print(f"Package: {pin_data.get('package_type', 'Unknown')}")
            print(f"Pin count: {pin_data.get('pin_count', 0)}")

            pins = pin_data.get('pins', [])
            print(f"\nExtracted {len(pins)} pins:")

            for pin in pins[:10]:  # First 10
                num = pin.get('number', '?')
                name = pin.get('name', '?')
                func = pin.get('function', 'N/A')
                print(f"  Pin {num:>2}: {name:<20} {func}")

        except json.JSONDecodeError as e:
            print(f"\nFailed to parse response as JSON: {e}")
            print("\nTrying to extract from plain text...")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_json_format()
