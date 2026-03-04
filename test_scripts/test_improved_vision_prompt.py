#!/usr/bin/env python3
"""
Test improved Vision API prompt for complete pinout extraction.
"""

import io
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.image_ocr_client import ImageOCRClient

IMPROVED_PROMPT = """You are an expert at reading electronic component pinout diagrams from datasheet images. Your task is to extract COMPLETE pinout information.

## IMPORTANT: This is a TQFP/MLF package pinout diagram showing a 44-pin microcontroller.

## EXTRACTION REQUIREMENTS

### 1. Read the diagram systematically, side by side:

The diagram shows pins arranged in a grid. You MUST extract ALL pins from ALL FOUR sides:

**TOP SIDE (usually has 8-10 pins):**
- Look for pins along the top edge of the chip package
- These are typically PA0-PA7 or control pins

**RIGHT SIDE (usually has 11-12 pins):**
- Look for pins along the right edge
- These are typically PB0-PB12 or similar

**BOTTOM SIDE (usually has 8-10 pins):**
- Look for pins along the bottom edge
- These are typically PC0-PC7 or similar

**LEFT SIDE (usually has 8-10 pins):**
- Look for pins along the left edge
- These are typically PD0-PD7 or similar

### 2. Pin numbering convention for TQFP/MLF:

- Pin 1 is at TOP-LEFT corner
- Numbering goes COUNTER-CLOCKWISE around the package
- So pins go: Top (left to right) → Right (top to bottom) → Bottom (right to left) → Left (bottom to top)

### 3. Common pin categories you should identify:

**Power Pins:** VCC, VDD, AVCC, AGND, VSS
**Ground Pins:** GND, VSS
**Reset/Control:** RESET, XTAL1, XTAL2
**Port A Pins:** PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7
**Port B Pins:** PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7, PB8, PB9, PB10, PB11, PB12
**Port C Pins:** PC0, PC1, PC2, PC3, PC4, PC5, PC6, PC7
**Port D Pins:** PD0, PD1, PD2, PD3, PD4, PD5, PD6, PD7

### 4. Extraction steps:

1. **Start at Pin 1 (TOP-LEFT corner)**
2. **Move counter-clockwise** reading each pin name/number
3. **Count all pins** - there should be exactly 40 pins
4. **Identify pin functions** (power, ground, input/output, reset, etc.)

### 5. Critical verification:

After extraction, verify:
- ✅ Pin 1 is at top-left corner
- ✅ Pin numbers go 1, 2, 3, ... 40 (consecutive, counter-clockwise)
- ✅ ALL 4 port groups are present (PA, PB, PC, PD)
- ✅ Power pins (VCC, GND, AVCC) are identified
- ✅ Control pins (RESET, XTAL1, XTAL2) are identified
- ✅ Total count is exactly 40 pins

## OUTPUT FORMAT

Return ONLY valid JSON (no markdown, no additional text):

{
  "component_name": "Component Name",
  "package_type": "Package Type",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "Pin Name", "function": "Function Description"},
    {"number": 2, "name": "Pin Name", "function": "Function Description"},
    ...
  ],
  "extraction_confidence": 0.95,
  "notes": "Any issues or observations"
}

## CRITICAL REMINDERS

- Do NOT stop after reading one section - extract ALL pins from ALL sides
- Do NOT skip pins that seem less visible - extract what you can see
- If some text is unclear, still make your best attempt based on context
- Return EXACTLY 40 pins numbered 1-40

Now extract the complete pinout from this image.
"""


def test_improved_prompt():
    """Test improved Vision API prompt."""
    pdf_path = "pdfs/test.pdf"

    print("=" * 80)
    print("Testing Improved Vision API Prompt")
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

        print(f"\nPage 11 image converted: {len(img_data)} bytes")

    # Send to Vision API with improved prompt
    print("\n" + "=" * 80)
    print("STEP 2: Send to Vision API with IMPROVED PROMPT")
    print("=" * 80)

    vision_client = ImageOCRClient(
        api_url="https://qwen.ideeza.com/describe_image/",
        output_token=4096,
        timeout=120
    )

    files = {
        "file": (f"page_11.png", img_data, "image/png")
    }
    data = {
        "text": IMPROVED_PROMPT,
        "output_token": str(4096)
    }

    import requests
    try:
        response = requests.post(
            vision_client.api_url,
            headers={"accept": "application/json"},
            files=files,
            data=data,
            timeout=120
        )
        response.raise_for_status()

        print("\n" + "=" * 80)
        print("STEP 3: Parse Vision API Response")
        print("=" * 80)

        # Parse response
        import re
        raw_response = response.text

        # Extract JSON from response (may be wrapped in markdown)
        json_match = re.search(r'\{[\s\S]*\}', raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # Try to extract from description field
            try:
                resp_json = json.loads(raw_response)
                if "description" in resp_json:
                    desc = resp_json["description"]
                    # Remove markdown code blocks if present
                    desc = re.sub(r'```(?:json)?\s*', '', desc)
                    json_str = desc
                else:
                    json_str = raw_response
            except:
                json_str = raw_response

        # Parse JSON
        result = json.loads(json_str)

        print("\n--- EXTRACTED DATA ---")
        print(f"Component:  {result.get('component_name', 'Unknown')}")
        print(f"Package:      {result.get('package_type', 'Unknown')}")
        print(f"Pin count:   {result.get('pin_count', 0)}")

        pins = result.get('pins', [])
        print(f"\nExtracted {len(pins)} pins:")

        # Group pins by type
        power_pins = [p for p in pins if 'power' in str(p.get('function', '')).lower()]
        ground_pins = [p for p in pins if 'ground' in str(p.get('function', '')).lower()]
        pa_pins = [p for p in pins if p.get('name', '').startswith('PA')]
        pb_pins = [p for p in pins if p.get('name', '').startswith('PB')]
        pc_pins = [p for p in pins if p.get('name', '').startswith('PC')]
        pd_pins = [p for p in pins if p.get('name', '').startswith('PD')]
        reset_xtal_pins = [p for p in pins if p.get('name', '') in ['RESET', 'XTAL1', 'XTAL2', 'AREF']]

        print(f"\nPin Type Breakdown:")
        print(f"  Power pins:       {len(power_pins)}")
        print(f"  Ground pins:       {len(ground_pins)}")
        print(f"  Reset/XTAL pins:  {len(reset_xtal_pins)}")
        print(f"  Port A pins (PA): {len(pa_pins)}")
        print(f"  Port B pins (PB): {len(pb_pins)}")
        print(f"  Port C pins (PC): {len(pc_pins)}")
        print(f"  Port D pins (PD): {len(pd_pins)}")

        print("\n" + "-" * 80)
        print("All pins (sorted by number):")
        print("-" * 80)

        # Sort pins by number
        sorted_pins = sorted(pins, key=lambda x: x.get('number', 999))

        for pin in sorted_pins:
            num = pin.get('number', '?')
            name = pin.get('name', '?')
            func = pin.get('function', 'N/A')
            print(f"  Pin {num:>2}: {name:<15}  {func}")

        print("\n" + "=" * 80)
        print("VERIFICATION:")
        print("-" * 80)

        # Verify consecutive pin numbers
        pin_numbers = [p.get('number') for p in pins if p.get('number')]
        if sorted(pin_numbers) == list(range(1, len(pin_numbers) + 1)):
            print("✅ Pin numbers are consecutive (1 to 40)")
        else:
            print(f"❌ Pin numbers are NOT consecutive!")
            print(f"   Got: {sorted(pin_numbers)}")

        # Verify 4 port groups
        total = len(power_pins) + len(ground_pins) + len(reset_xtal_pins) + len(pa_pins) + len(pb_pins) + len(pc_pins) + len(pd_pins)
        print(f"\nTotal pins extracted: {total}")
        if total == 40:
            print("✅ Exactly 40 pins extracted!")
        else:
            print(f"❌ Expected 40 pins, got {total}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_improved_prompt()
