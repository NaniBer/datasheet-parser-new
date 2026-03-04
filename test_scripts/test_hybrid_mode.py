#!/usr/bin/env python3
"""
Test hybrid mode: Vision API for pin positions + LLM for functions.

This combines:
1. Vision API accuracy - Direct visual pin extraction
2. LLM intelligence - Function classification, validation, completeness
3. Robustness - If Vision misses something, LLM fills it in
"""

import sys
import os
import io
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.image_ocr_client import ImageOCRClient
from src.chat_bot import get_completion_from_messages, build_pin_extraction_prompt

# Pages 10 and 11 contain actual pinout diagrams in pages.pdf
PINOUT_PAGES = [10, 11]

def extract_with_vision(page_num: int, pdf_path: str):
    """
    Extract pin information using Vision API (direct visual).

    Args:
        page_num: Page number to process
        pdf_path: Path to PDF

    Returns:
        List of pins with number, name from Vision API
    """
    import pdfplumber

    # Open PDF and convert page to image
    with pdfplumber.open(pdf_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"Error: Page {page_num} does not exist")
            return []

        page = pdf.pages[page_num - 1]

        # Convert page to image
        pil_image = page.to_image()

        # Save to bytes
        img_bytes = io.BytesIO()
        pil_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_data = img_bytes.getvalue()

    # Send to Vision API
    vision_client = ImageOCRClient(
        api_url="https://qwen.ideeza.com/describe_image/",
        output_token=4096,  # Higher limit for detailed extraction
        timeout=120
    )

    files = {
        "file": (f"page_{page_num}.png", img_data, "image/png")
    }

    # Vision-specific prompt focused on visual pin extraction
    vision_prompt = """You are an expert at reading electronic component pinout diagrams from datasheet images.

## CRITICAL TASK
Extract COMPLETE pinout information from this TQFP pinout diagram. Read the diagram VERY CAREFULLY.

## PIN NUMBERING
- Pin 1 is at the top-left corner (with dot indicator)
- Numbers go in sequence: 1, 2, 3, 4, ... 40
- Follow the diagram layout EXACTLY as shown

## PIN EXTRACTION
For EACH pin number (1-40):
1. Identify where that pin number is located on the diagram
2. Read the pin name label exactly as shown (e.g., "PB0", "PD7", "VCC", "GND")
3. Extract function if shown

## PACKAGE IDENTIFICATION
- This is a TQFP/MLF package (44 pins)
- Count all pins and verify there are exactly 40

## OUTPUT FORMAT
Return ONLY valid JSON with this exact structure:

{
  "component_name": "ATmega164A",
  "package_type": "TQFP/MLF",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "EXACT pin name as shown on diagram"},
    {"number": 2, "name": "EXACT pin name as shown on diagram"},
    ...
  ],
  "extraction_confidence": 0.95,
  "notes": "Describe if any unclear or ambiguous pin numbers"
}

CRITICAL:
- Extract ALL 40 pins - no more, no less
- Pin numbers MUST be consecutive from 1 to 40
- Don't miss power pins (VCC, GND, AVCC, etc.)
- Don't miss control pins (RESET, XTAL1, XTAL2)
- Read the diagram in order around the perimeter, not randomly

Now extract the complete pinout from this image."""

    data = {
        "text": vision_prompt,
        "output_token": str(4096)
    }

    import requests
    response = requests.post(
        vision_client.api_url,
        headers={"accept": "application/json"},
        files=files,
        data=data,
        timeout=120
    )

    print(f"Vision API Status: {response.status_code}")
    print(f"Response length: {len(response.text)}")

    # Parse Vision API response
    try:
        # Extract JSON from description field
        resp_json = json.loads(response.text)

        if "description" in resp_json:
            desc = resp_json["description"]
            # Remove markdown if present
            import re
            desc = re.sub(r'```(?:json)?\s*', '', desc)

            # Parse JSON
            result = json.loads(desc)

            pins = result.get("pins", [])
            print(f"\nVision extracted {len(pins)} pins")

            return pins

        elif "pins" in resp_json:
            pins = resp_json.get("pins", [])
            print(f"\nVision extracted {len(pins)} pins")
            return pins

        else:
            print(f"Vision API response format: {json.dumps(resp_json, indent=2)}")
            return []

    except Exception as e:
        print(f"Vision API Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def verify_and_enhance_with_llm(vision_pins: list, pdf_path: str):
    """
    Use LLM to verify, enhance, and complete Vision API extraction.

    Args:
        vision_pins: List of pins from Vision API
        pdf_path: Path to PDF (for getting additional context)

    Returns:
        Enhanced pin data with numbers, names, functions
    """
    import pdfplumber

    # Build summary of Vision API extraction
    vision_summary = "Vision API extracted these pins:\n"
    vision_summary += "\n".join([f"Pin {p.get('number', '?')}: {p.get('name', '')}" for p in vision_pins])
    vision_summary += f"\n\nTotal: {len(vision_pins)} pins"

    # Send to LLM with context
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Senior EDA Technical Data Compiler. Your task is to verify and enhance pin extraction results.\n\n"

                "## VISION API EXTRACTION RESULTS\n"
                f"{vision_summary}\n\n"

                "## YOUR TASK\n"
                "Review the Vision API extraction above and:\n"
                "1. VERIFY pin numbers are correct (1-40 consecutive)\n"
                "2. VERIFY all critical pins are present (VCC, GND, AVCC, AREF, RESET, XTAL1, XTAL2)\n"
                "3. Classify each pin's PRIMARY function:\n"
                "   - 'power': VCC, VDD, AVCC\n"
                "   - 'ground': GND, VSS\n"
                "   - 'reset': RESET\n"
                "   - 'clock': XTAL1, XTAL2\n"
                "   - 'analog': AREF\n"
                "   - 'gpio': PAx, PBx, PCx, PDx pins\n"
                "4. For ambiguous cases, use your best judgment\n\n"

                "5. ADD any MISSING pins if Vision API missed any\n"
                "6. For each pin, ADD a function classification based on pin name pattern\n\n"

                "## OUTPUT FORMAT\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"component_name\": \"Component Name\",\n"
                "  \"package_type\": \"Package Type\",\n"
                "  \"pin_count\": number,\n"
                "  \"pins\": [\n"
                "    {\"number\": 1, \"name\": \"Pin Name\", \"function\": \"Function\"},\n"
                "    ...\n"
                "  ],\n"
                "  \"extraction_method\": \"Hybrid\"\n"
                "}\n\n"

                "IMPORTANT:\n"
                "- Return ONLY raw valid JSON - no markdown, no explanations\n"
                "- Total pin count MUST be 40\n"
                "- Pin numbers MUST be consecutive from 1 to 40\n"
                "- If Vision API is missing pins, YOU MUST ADD them\n"
                "- Use the Vision API pin names as the primary source\n"
            )
        }
    ]

    # Call LLM
    response = get_completion_from_messages(messages, model="llama-3")

    # Parse LLM response
    try:
        import re
        clean_response = response.strip()

        # Remove markdown code blocks
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]

        # Parse JSON
        result = json.loads(clean_response)

        return result

    except json.JSONDecodeError as e:
        print(f"\nLLM JSON Decode Error: {e}")
        print(f"Response preview: {response[:500]}")
        return None

    except Exception as e:
        print(f"\nLLM Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_hybrid_mode():
    """Test hybrid mode: Vision API + LLM."""
    pdf_path = "pdfs/pages.pdf"

    print("=" * 80)
    print("HYBRID MODE TEST")
    print("=" * 80)
    print()
    print("This test combines:")
    print("1. Vision API - Direct visual pin extraction")
    print("2. LLM - Verification, function classification, completeness")
    print()

    # Step 1: Extract with Vision API from all pinout pages
    print("-" * 80)
    print("STEP 1: Extract pins with Vision API")
    print("-" * 80)

    all_vision_pins = []
    for page_num in PINOUT_PAGES:
        print(f"\nProcessing Page {page_num}...")
        page_pins = extract_with_vision(page_num, pdf_path)
        if page_pins:
            print(f"  ✓ Extracted {len(page_pins)} pins from Page {page_num}")
            all_vision_pins.extend(page_pins)
        else:
            print(f"  ✗ No pins extracted from Page {page_num}")

    vision_pins = all_vision_pins

    if not vision_pins:
        print("ERROR: Vision API returned no pins!")
        return

    print(f"✓ Vision API extracted {len(vision_pins)} pins")

    # Step 2: Verify and enhance with LLM
    print()
    print("-" * 80)
    print("STEP 2: Verify and enhance with LLM")
    print("-" * 80)

    enhanced_data = verify_and_enhance_with_llm(vision_pins, pdf_path)

    if not enhanced_data:
        print("ERROR: LLM verification failed!")
        return

    # Step 3: Show final result
    print()
    print("=" * 80)
    print("FINAL HYBRID RESULT")
    print("=" * 80)
    print()

    print(f"Component: {enhanced_data.get('component_name', 'Unknown')}")
    print(f"Package: {enhanced_data.get('package_type', 'Unknown')}")
    print(f"Pin count: {len(enhanced_data.get('pins', []))}")

    pins = enhanced_data.get('pins', [])

    if pins:
        print(f"\n{'Pin':<5} {'Name':<20} {'Function'}")
        print("-" * 80)

        # Sort by pin number
        sorted_pins = sorted(pins, key=lambda x: x.get('number', 999))

        for pin in sorted_pins[:20]:  # Show first 20
            num = pin.get('number', '?')
            name = pin.get('name', '')
            func = pin.get('function', 'N/A')
            print(f"  {num:>2}  {name:<20}  {func}")

        if len(pins) > 20:
            print(f"  ... and {len(pins) - 20} more pins")

        # Verify completeness
        pin_numbers = [p.get('number') for p in pins if p.get('number')]
        if sorted(pin_numbers) == list(range(1, len(pin_numbers) + 1)):
            print("\n✅ Pin numbers are consecutive 1-40")
        else:
            print(f"\n❌ Pin numbers: {sorted(pin_numbers)}")

        # Check for critical pins
        pin_names = [p.get('name', '') for p in pins]
        has_vcc = any('VCC' in name for name in pin_names)
        has_gnd = any('GND' in name for name in pin_names)
        has_reset = any('RESET' in name for name in pin_names)

        print(f"\nCritical pins check:")
        print(f"  VCC: {'✓' if has_vcc else '✗'}")
        print(f"  GND: {'✓' if has_gnd else '✗'}")
        print(f"  RESET: {'✓' if has_reset else '✗'}")

    else:
        print("\nERROR: No pins extracted!")


if __name__ == "__main__":
    test_hybrid_mode()
