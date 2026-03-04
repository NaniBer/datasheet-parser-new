#!/usr/bin/env python3
"""Test improved text-based layout extraction on ESP32 page 10."""

import json
import sys
sys.path.insert(0, 'src')

from chat_bot import get_completion_from_messages
import pdfplumber

pdf_path = "pdfs/pages.pdf"

# Extract text from page 10
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[9]
    text = page.extract_text()

print("=" * 80)
print("EXTRACTED TEXT FROM ESP32 PAGE 10")
print("=" * 80)
print(text[:2000])
print("...\n")

# Improved prompt (same as NE555)
system_prompt = """You are an expert at reading electronic component pinout diagrams from datasheets.

You understand that in datasheets, pin layouts are often displayed as:
- Rows of pin numbers with corresponding pin names beside them
- Different rows represent different sides of the component
- Pin numbering follows standard conventions (counter-clockwise around the component)"""

user_prompt = f"""Extract physical pin layout from the following datasheet text for ESP32-WROOM-32E module.

The text shows pinout diagrams with pin numbers arranged in visual rows or columns.

Here is the text:
{text}

CRITICAL: Read pin numbers in the ORDER they appear visually in the diagram, NOT sorted numerically.

For example:
- If diagram shows "1" then "2" then "3" on the left side, list them as [1, 2, 3]
- If diagram shows "38" then "37" then "36" on the right side, list them as [38, 37, 36]
- Maintain the VISUAL ORDER as shown in the diagram

Analyze this and tell me:
1. Which pins are on the LEFT side? List them in order from TOP to BOTTOM
2. Which pins are on the RIGHT side? List them in order from TOP to BOTTOM
3. Which pins are on the BOTTOM edge (if any)? List them in order from LEFT to RIGHT
4. Which pins are on the TOP edge (if any)? List them in order from LEFT to RIGHT

Return ONLY valid JSON:

{{
  "left_side": [pin numbers as integers, TOP to BOTTOM order],
  "right_side": [pin numbers as integers, TOP to BOTTOM order],
  "bottom_edge": [pin numbers as integers, LEFT to RIGHT order],
  "top_edge": [pin numbers as integers, LEFT to RIGHT order]
}}

IMPORTANT:
- Each pin belongs to exactly ONE side - NO duplicates
- Maintain VISUAL ORDER from diagram, not sorted order
- Return ONLY JSON - no markdown code blocks
- Use integers for pin numbers (not strings)"""

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
]

print("=" * 80)
print("CALLING LLM FOR ESP32 LAYOUT EXTRACTION")
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

            # Expected for ESP32-WROOM-32E QFN-38:
            expected = {
                "left_side": list(range(1, 15)),  # 1-14
                "bottom_edge": list(range(15, 25)),  # 15-24
                "right_side": list(range(25, 39)),  # 25-38
                "top_edge": []
            }

            if layout == expected:
                print("\n✓✓✓ PERFECT MATCH for ESP32-WROOM-32E QFN-38! ✓✓✓")
            elif total == 38:
                print("\n✓ Correct pin count!")
                if layout.get("left_side") == expected["left_side"]:
                    print("✓ Left side correct!")
                if layout.get("bottom_edge") == expected["bottom_edge"]:
                    print("✓ Bottom edge correct!")
                if layout.get("right_side") == expected["right_side"]:
                    print("✓ Right side correct!")
                if layout.get("top_edge") == expected["top_edge"]:
                    print("✓ Top edge correct!")
            else:
                print(f"\n⚠️ Expected 38 pins, got {total}")

        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error: {e}")
    else:
        print("✗ No JSON found in response")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
