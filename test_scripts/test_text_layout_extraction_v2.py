#!/usr/bin/env python3
"""Test layout extraction using our content_extractor for better text quality."""

import json
import sys
sys.path.insert(0, 'src')

from chat_bot import get_completion_from_messages
from pdf_extractor.content_extractor import ContentExtractor

pdf_path = "pdfs/pages.pdf"

# Use our ContentExtractor for better quality text
extractor = ContentExtractor(pdf_path)

# Extract from page 10 - need PageCandidate objects
from pdf_extractor.page_detector import PageCandidate
candidates = [PageCandidate(page_number=10, confidence_score=10)]
content = extractor.extract_content(candidates)

print("=" * 80)
print("EXTRACTED TEXT FROM PAGE 10 (using ContentExtractor)")
print("=" * 80)
print(f"Text length: {len(content.text_content)} chars")
print("\nFirst 2000 chars:")
print(content.text_content[:2000])
print("\n" + "=" * 80)

# Simple prompt
user_prompt = f"""This text contains a pinout diagram layout. Extract which pins are on each side.

Text:
{content.text_content}

Return ONLY this JSON:

{{
  "left_side": [],
  "right_side": [],
  "bottom_edge": [],
  "top_edge": []
}}

Group pin numbers by their physical side based on how they appear in the layout."""

messages = [
    {"role": "system", "content": "You are an expert at reading electronic datasheets."},
    {"role": "user", "content": user_prompt}
]

print("CALLING LLM...")
print("=" * 80)

try:
    response = get_completion_from_messages(messages, model="llama-3", temperature=0.1)
    print(f"\nLLM Response:\n{response}\n")

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

        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error: {e}")
    else:
        print("✗ No JSON found in response")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
