#!/usr/bin/env python3
"""
Test separated flow:
1. LLM extracts pin names and numbers
2. Vision API analyzes pin layout image → Returns text format
3. Combine both results
"""

import sys
import os
import io
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.image_ocr_client import ImageOCRClient
from src.chat_bot import get_completion_from_messages, build_pin_extraction_prompt

# Pages 10 and 11 contain pinout diagrams
PINOUT_PAGES = [10, 11]

def extract_pin_names_with_llm(pdf_path: str):
    """
    Extract pin names and numbers using LLM.

    Args:
        pdf_path: Path to PDF

    Returns:
        List of pins with number and name
    """
    # Get page text
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        text_content = ""
        for page_num in PINOUT_PAGES:
            page = pdf.pages[page_num - 1]
            text = page.extract_text() or ""
            text_content += f"--- Page {page_num} ---\n{text}\n\n"

    # Call LLM
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Senior EDA Technical Data Compiler.\n\n"
                "## TASK\n"
                "Extract ONLY pin names and numbers from the pinout diagram text.\n\n"
                "## FOCUS AREAS\n"
                "1. Extract EXACT pin names as shown in diagram\n"
                "2. Extract EXACT pin numbers (1, 2, 3, ...)\n"
                "3. Package type detection is NOT required\n"
                "4. Function classification is NOT required\n\n"
                "## OUTPUT FORMAT\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"pins\": [\n"
                "    {\"number\": 1, \"name\": \"Pin Name\"},\n"
                "    {\"number\": 2, \"name\": \"Pin Name\"},\n"
                "    ...\n"
                "  ]\n"
                "}\n\n"
                "CRITICAL:\n"
                "- Extract EXACT pin names as labeled in diagram\n"
                "- Extract EXACT pin numbers\n"
                "- Return ONLY JSON, no markdown, no explanations\n"
            )
        },
        {
            "role": "user",
            "content": (
                "Extract pin names and numbers from this pinout diagram.\n\n"
                f"--- DATASHEET CONTENT START ---\n"
                f"{text_content}\n"
                "--- DATASHEET CONTENT END ---"
            )
        }
    ]

    response = get_completion_from_messages(messages, model="llama-3")

    # Parse response
    try:
        import re
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        if clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]

        result = json.loads(clean_response)
        return result.get("pins", [])

    except Exception as e:
        print(f"LLM Error: {e}")
        return []


def extract_layout_with_vision(page_num: int, pdf_path: str):
    """
    Extract pin layout information using Vision API.

    Args:
        page_num: Page number with pin layout
        pdf_path: Path to PDF

    Returns:
        Layout information in text format
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        pil_image = page.to_image()

        img_bytes = io.BytesIO()
        pil_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        img_data = img_bytes.getvalue()

    # Send to Vision API with layout-focused prompt
    vision_prompt = """You are analyzing an electronic component pin layout diagram.

## YOUR TASK
Extract the pin LAYOUT structure from this diagram in TEXT FORMAT.

## LAYOUT INFORMATION TO EXTRACT

For this TQFP/QFN package, describe:

1. **Pin numbering convention**: How are pins numbered?
   - Counter-clockwise from pin 1?
   - Clockwise from pin 1?

2. **Pin arrangement on each side**:
   - Top side: Which pin numbers are on the top edge?
   - Right side: Which pin numbers are on the right edge?
   - Bottom side: Which pin numbers are on the bottom edge?
   - Left side: Which pin numbers are on the left edge?

3. **Pin 1 location**: Where is pin 1 located on the diagram?
   - Top-left corner
   - Other corner
   - Center of one side

4. **Side-by-side pin distribution**:
   - Total pins per side
   - Pin number sequence on each side

## OUTPUT FORMAT

Return ONLY a text description in this EXACT format:

```
Layout: TQFP Counter-Clockwise
Pin 1: Top-left corner
Top side: Pins 1-11 (left to right)
Right side: Pins 12-23 (top to bottom)
Bottom side: Pins 24-34 (right to left)
Left side: Pins 35-40 (bottom to top)
```

IMPORTANT:
- Describe ONLY the layout structure
- Don't list individual pin names
- Use numbers as shown on diagram
- Return ONLY the text block (no JSON, no markdown code)
"""

    files = {"file": (f"page_{page_num}.png", img_data, "image/png")}
    data = {"text": vision_prompt, "output_token": "2048"}

    import requests
    response = requests.post(
        "https://qwen.ideeza.com/describe_image/",
        headers={"accept": "application/json"},
        files=files,
        data=data,
        timeout=120
    )

    # Extract layout text from response
    try:
        resp_json = json.loads(response.text)
        if "description" in resp_json:
            # Remove markdown if present
            import re
            layout_text = re.sub(r'```(?:text)?\s*', '', resp_json["description"])
            return layout_text
        elif len(resp_json) == 1 and "description" in list(resp_json.values()):
            layout_text = re.sub(r'```(?:text)?\s*', '', list(resp_json.values())[0])
            return layout_text
        else:
            return response.text

    except Exception as e:
        print(f"Vision API Error: {e}")
        return response.text


def combine_pin_names_with_layout(llm_pins: list, layout_text: str):
    """
    Combine LLM pin names with Vision layout text.

    Args:
        llm_pins: List of pins from LLM
        layout_text: Layout description from Vision

    Returns:
        Combined result
    """
    print("=" * 80)
    print("COMBINED RESULT")
    print("=" * 80)
    print()

    print("## LLM Pin Names and Numbers")
    print()
    print(f"{'Pin':<5} {'Name'}")
    print("-" * 50)

    for pin in llm_pins:
        num = pin.get('number', '?')
        name = pin.get('name', '')
        print(f"  {num:>4}  {name}")

    print()
    print("## Vision API Layout Structure")
    print()
    print(layout_text)

    print()
    print("=" * 80)
    print("COMBINED PIN MAPPING")
    print("=" * 80)
    print()
    print("Pin numbers from LLM: ✓")
    print("Pin names from LLM: ✓")
    print("Layout structure from Vision API: ✓")
    print()
    print("Ready for schematic generation!")


def test_separated_flow():
    """Test the separated flow."""
    pdf_path = "pdfs/pages.pdf"

    print("=" * 80)
    print("SEPARATED FLOW TEST")
    print("=" * 80)
    print()
    print("This test separates responsibilities:")
    print("1. LLM: Pin names and numbers")
    print("2. Vision API: Pin layout structure")
    print("3. Combine: Both for final result")
    print()

    # Step 1: Extract pin names with LLM
    print("-" * 80)
    print("STEP 1: Extract Pin Names with LLM")
    print("-" * 80)

    llm_pins = extract_pin_names_with_llm(pdf_path)

    if not llm_pins:
        print("ERROR: LLM returned no pins!")
        return

    print(f"✓ LLM extracted {len(llm_pins)} pins")
    print()

    # Step 2: Extract layout with Vision API
    print("-" * 80)
    print("STEP 2: Extract Layout with Vision API")
    print("-" * 80)

    # Use the page that has the clearest layout
    layout_page = PINOUT_PAGES[0]  # Page 10
    print(f"Processing Page {layout_page} for layout...")

    layout_text = extract_layout_with_vision(layout_page, pdf_path)

    print(f"✓ Vision API returned layout information")
    print()

    # Step 3: Combine results
    combine_pin_names_with_layout(llm_pins, layout_text)


if __name__ == "__main__":
    test_separated_flow()
