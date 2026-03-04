#!/usr/bin/env python3
"""Test text-based layout extraction from NE555 datasheet."""

import json
import sys
sys.path.insert(0, 'src')

from chat_bot import get_completion_from_messages
import pdfplumber

pdf_path = "pdfs/NE555.PDF"

# Extract text from page 1
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    text = page.extract_text()

print("=" * 80)
print("EXTRACTED TEXT FROM NE555 PAGE 1")
print("=" * 80)
print(text[:1500])
print("...\n")

# Build prompt for LLM
system_prompt = """You are an expert at reading electronic component pinout diagrams from datasheets.

You understand that in datasheets, pin layouts are often displayed as:
- Rows of pin numbers with corresponding pin names beside them
- Different rows represent different sides of the component
- Pin numbering follows standard conventions (counter-clockwise around the component)"""

user_prompt = f"""Extract physical pin layout from the following datasheet text for NE555 timer IC.

The text shows pinout diagrams with pin numbers arranged in visual rows or columns.

Here is the text:
{text}

CRITICAL: Read pin numbers in the ORDER they appear visually in the diagram, NOT sorted numerically.

For example:
- If diagram shows "1" then "2" then "3" on the left side, list them as [1, 2, 3]
- If diagram shows "8" then "7" then "6" then "5" on the right side, list them as [8, 7, 6, 5]
- Maintain the VISUAL ORDER as shown in the diagram

Analyze this and tell me:
1. Which pins are on the LEFT side? List them in order from TOP to BOTTOM
2. Which pins are on the RIGHT side? List them in order from TOP to BOTTOM
3. Which pins are on the TOP edge (if any)?
4. Which pins are on the BOTTOM edge (if any)?

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

            # Expected for 8-pin DIP:
            # Left: 1, 2, 3, 4 (top to bottom)
            # Right: 8, 7, 6, 5 (top to bottom)
            expected_8pin = {
                "left_side": [1, 2, 3, 4],
                "right_side": [8, 7, 6, 5],
                "bottom_edge": [],
                "top_edge": []
            }

            if layout == expected_8pin:
                print("\n✓✓✓ PERFECT MATCH for 8-pin DIP! ✓✓✓")
            elif total == 8:
                print("\n✓ Correct pin count!")
            else:
                print(f"\n⚠️ Expected 8 pins, got {total}")

        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error: {e}")
    else:
        print("✗ No JSON found in response")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
