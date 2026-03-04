#!/usr/bin/env python3
"""Test layout extraction from page 10 text using our own LLM."""

import json
import sys
sys.path.insert(0, 'src')

from chat_bot import get_completion_from_messages
import pdfplumber

pdf_path = "pdfs/pages.pdf"

# Extract text from page 10
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[9]  # Page 10 (index 9)
    text = page.extract_text()

print("=" * 80)
print("EXTRACTED TEXT FROM PAGE 10")
print("=" * 80)
print(text[:2000])
print("...\n")

# Build prompt for LLM
system_prompt = """You are an expert at reading electronic component pinout diagrams from datasheets.

You understand that in datasheets, pin layouts are often displayed as:
- Rows of pin numbers with corresponding pin names below them
- Different rows represent different sides of the component
- Pin numbering follows standard conventions (counter-clockwise around the component)"""

user_prompt = f"""This text contains a pinout diagram layout. Identify which pins are on each side.

Text:
{text}

Task: Group the pin numbers by their physical side (LEFT, RIGHT, TOP, BOTTOM).

Return ONLY this JSON:

{{
  "left_side": [],
  "right_side": [],
  "bottom_edge": [],
  "top_edge": []
}}

Look for:
- Groups of sequential pin numbers
- Visual arrangement (rows, columns)
- Text labels that indicate sides"""

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
]

print("=" * 80)
print("CALLING LLM FOR LAYOUT EXTRACTION")
print("=" * 80)

try:
    response = get_completion_from_messages(messages, model="llama-3", temperature=0.1)
    print(f"\nLLM Response:\n{response}\n")

    # Try to extract JSON
    import re
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        json_str = json_match.group()
        try:
            layout = json.loads(json_str)

            print("=" * 80)
            print("EXTRACTED LAYOUT:")
            print("=" * 80)

            for side, pins in layout.items():
                if pins:
                    print(f"{side:20s}: {len(pins):2d} pins - {pins}")
                else:
                    print(f"{side:20s}:  0 pins")

            total = sum(len(pins) for pins in layout.values())
            print(f"\n{'Total':20s}: {total:2d} pins")

            # Validate
            expected_layout = {
                "left_side": list(range(1, 15)),  # 1-14
                "right_side": list(range(25, 39)),  # 25-38
                "bottom_edge": list(range(15, 25)),  # 15-24
                "top_edge": []
            }

            if total == 38:
                print("\n✓ Correct pin count!")

            if layout.get("left_side") == expected_layout["left_side"]:
                print("✓ Left side correct!")
            if layout.get("right_side") == sorted(layout.get("right_side", [])):
                print("✓ Right side correct!")
            if layout.get("bottom_edge") == expected_layout["bottom_edge"]:
                print("✓ Bottom edge correct!")

        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error: {e}")
    else:
        print("✗ No JSON found in response")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
