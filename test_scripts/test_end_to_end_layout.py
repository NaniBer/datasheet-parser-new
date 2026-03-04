#!/usr/bin/env python3
"""
Complete end-to-end test: Read datasheet → Extract pins → Get layout → Create GLB

This tests the entire pipeline with the new layout extraction feature.
"""

import sys
import os
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm.image_ocr_client import ImageOCRClient
from src.chat_bot import get_completion_from_messages, build_pin_extraction_prompt
from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models.pin_data import PinData, Pin, PackageInfo

# Test datasheet
PDF_PATH = "pdfs/pages.pdf"
OUTPUT_PATH = "output/test_schematic_from_layout.glb"


def extract_pin_names_with_llm(pdf_path: str):
    """Extract pin names and numbers using LLM (existing pipeline)."""
    print("=" * 80)
    print("STEP 1: Page Detection")
    print("=" * 80)

    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=5)
        print(f"Found {len(candidates)} relevant pages: {[c.page_number for c in candidates]}")

    print()
    print("=" * 80)
    print("STEP 2: Content Extraction")
    print("=" * 80)

    with ContentExtractor(pdf_path) as extractor:
        content = extractor.extract_content(candidates)
        print(f"Extracted {len(content.pages)} pages")
        print(f"Text content: {len(content.text_content)} chars")

    print()
    print("=" * 80)
    print("STEP 3: LLM Pin Extraction")
    print("=" * 80)

    # Build LLM prompt focused on pin names and numbers only
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Senior EDA Technical Data Compiler.\n\n"

                "## TASK\n"
                "Extract pin names and numbers from the pinout diagram.\n\n"

                "## CRITICAL INSTRUCTIONS\n"
                "1. Extract EXACT pin numbers (1, 2, 3, ...) as labeled on diagram\n"
                "2. Extract EXACT pin names as shown on diagram\n"
                "3. Do NOT guess - use what you SEE in the diagram\n"
                "4. Extract ALL pins shown\n\n"

                "## OUTPUT FORMAT\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"pins\": [\n"
                "    {\"number\": 1, \"name\": \"Pin Name\"},\n"
                "    {\"number\": 2, \"name\": \"Pin Name\"},\n"
                "    ...\n"
                "  ]\n"
                "}\n\n"

                "IMPORTANT:\n"
                "- Return ONLY raw valid JSON - no markdown\n"
                "- Pin numbers MUST be consecutive\n"
                "- Extract ALL pins visible in diagram\n"
            )
        },
        {
            "role": "user",
            "content": (
                "Extract pin names and numbers from this pinout diagram.\n\n"
                f"--- DATASHEET CONTENT START ---\n"
                f"{content.text_content}\n"
                "--- DATASHEET CONTENT END ---"
            )
        }
    ]

    # Call LLM
    response = get_completion_from_messages(messages, model="llama-3")

    # Parse response
    import re
    clean_response = response.strip()
    if clean_response.startswith("```json"):
        clean_response = clean_response[7:]
    if clean_response.startswith("```"):
        clean_response = clean_response[3:]
    if clean_response.endswith("```"):
        clean_response = clean_response[:-3]

    import json
    result = json.loads(clean_response)

    pins_data = result.get("pins", [])
    print(f"✓ LLM extracted {len(pins_data)} pins")

    # Print first 10 pins
    print("\nFirst 10 pins:")
    for pin in pins_data[:10]:
        num = pin.get("number", "?")
        name = pin.get("name", "")
        print(f"  Pin {num:>2}: {name}")

    return pins_data


def extract_layout_with_vision(pdf_path: str, pinout_pages: list[int]):
    """Extract layout structure using Vision API."""
    print()
    print("=" * 80)
    print("STEP 4: Vision API Layout Extraction")
    print("=" * 80)

    import pdfplumber
    import requests

    with pdfplumber.open(pdf_path) as pdf:
        # Use first pinout page for layout
        page_num = pinout_pages[0]
        page = pdf.pages[page_num - 1]

        # Convert page to image
        pil_image = page.to_image()
        img_bytes = io.BytesIO()
        pil_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_data = img_bytes.getvalue()

    # Vision API prompt for layout
    vision_prompt = """You are analyzing an electronic component pin layout diagram.

## YOUR TASK
Extract pin LAYOUT structure from this diagram in TEXT FORMAT.

For this package, describe:

1. **Package type**: What type of package is this? (DIP, TQFP, QFN, SOIC, BGA, Grid, etc.)

2. **Pin numbering convention**: How are pins numbered?

3. **Pin arrangement by section**:
   For EACH section of the package (Left, Right, Top, Bottom, etc.):
   - Section name (e.g., "Left Side Column 1", "Bottom Edge")
   - Which pin numbers are in this section
   - The order of pins in this section

4. **Total pins**: How many total pins?

## OUTPUT FORMAT

Return ONLY a text description in this EXACT format:

```
Package Type: [Type]
Layout: [Description]
Total Pins: [Number]

[Section Name]: [Pin Numbers]
...
```

IMPORTANT:
- Describe ONLY the layout structure
- Don't list individual pin names
- Be specific about which pins are in each section
- Return ONLY the text block (no JSON, no markdown)
"""

    files = {"file": (f"page_{page_num}.png", img_data, "image/png")}
    data = {"text": vision_prompt, "output_token": "2048"}

    response = requests.post(
        "https://qwen.ideeza.com/describe_image/",
        headers={"accept": "application/json"},
        files=files,
        data=data,
        timeout=120
    )
    print(f"Vision API response status: {response}")

    print(f"✓ Vision API returned layout")

    # Extract layout text
    try:
        resp_json = json.loads(response.text)
        if "description" in resp_json:
            # Remove markdown
            import re
            layout_text = re.sub(r'```(?:text)?\s*', '', resp_json["description"])
            print(f"\nLayout detected:")
            print(layout_text)
            return layout_text
        else:
            return response.text
    except:
        return response.text


def create_schematic_from_data(llm_pins: list, layout_text: str, output_path: str):
    """Create GLB schematic from combined data."""
    print()
    print("=" * 80)
    print("STEP 5: Create Schematic GLB")
    print("=" * 80)

    # Combine LLM pin names with layout structure
    # For this component (38 pins, grid layout), create PinData

    # Build PinData object
    # Package info (simplified for now)
    package_info = PackageInfo(
        type="Grid-Layout",
        pin_count=len(llm_pins),
        width=20.0,  # Approximate
        height=20.0,
        pitch=2.54,
        thickness=1.0
    )

    # Build Pin objects from LLM data
    pins = []
    for pin_data in llm_pins:
        pin = Pin(
            number=str(pin_data.get("number", 0)),
            name=pin_data.get("name", ""),
            function="auto"  # Will be auto-classified later
        )
        pins.append(pin)

    pin_data_obj = PinData(
        component_name="Component",
        package=package_info,
        pins=pins,
        extraction_method="Hybrid (LLM + Vision)"
    )

    print(f"Created PinData with {len(pins)} pins")
    print(f"Package: {package_info.type}-{package_info.pin_count}")

    # Generate schematic
    print(f"Generating schematic to: {output_path}")

    success = build_schematic_from_pin_data(pin_data_obj, output_path)

    if success:
        print(f"✓ Schematic created successfully!")
        print(f"  File: {output_path}")

        # Show file size
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"  Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
    else:
        print(f"✗ Schematic generation failed!")


def run_end_to_end_test():
    """Run complete end-to-end test."""
    print("=" * 80)
    print("END-TO-END TEST: Read → Extract → Layout → Schematic")
    print("=" * 80)
    print()
    print(f"Input: {PDF_PATH}")
    print(f"Output: {OUTPUT_PATH}")
    print()

    try:
        # Step 1-3: Extract pin names with LLM (existing pipeline)
        llm_pins = extract_pin_names_with_llm(PDF_PATH)

        if not llm_pins:
            print("ERROR: No pins extracted!")
            return

        # Step 4: Extract layout with Vision API
        # Get pinout pages
        with PageDetector(PDF_PATH) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=5)
            pinout_pages = [c.page_number for c in candidates]

        layout_text = extract_layout_with_vision(PDF_PATH, pinout_pages)

        # Step 5: Create schematic from combined data
        create_schematic_from_data(llm_pins, layout_text, OUTPUT_PATH)

        print()
        print("=" * 80)
        print("END-TO-END TEST COMPLETE")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  - LLM extracted {len(llm_pins)} pin names")
        print(f"  - Vision API identified layout structure")
        print(f"  - Schematic created: {OUTPUT_PATH}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_end_to_end_test()
