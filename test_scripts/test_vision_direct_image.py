#!/usr/bin/env python3
"""Test Vision API by sending page_11.png directly."""

import requests
import json

api_url = "https://qwen.ideeza.com/describe_image/"
image_path = "page_11.png"

# Improved prompt with generalized instructions and reinforcement
prompt = """1. Examine the ENTIRE image before counting.
2. Identify all four physical edges of the component:
   - Left vertical edge
   - Right vertical edge
   - Top horizontal edge
   - Bottom horizontal edge
3. Count and list ALL visible pins located directly on each edge.
4. Do NOT skip partially visible pins.
5. Do NOT infer missing pins — only count what is visibly present.
6. Double-check your counting before producing the final answer.
7. Ensure that:
   - No pin appears in more than one side list.
   - All visible pins are accounted for.
   - The lists reflect physical position, not numbering order.

If you detect uncertainty, re-evaluate the image before finalizing your answer.

## OUTPUT FORMAT (STRICTLY FOLLOW THIS FORMAT)

First, return ONLY this JSON:

```json
{
  "left_side": [list of pin numbers],
  "right_side": [list of pin numbers],
  "bottom_edge": [list of pin numbers],
  "top_edge": [list of pin numbers]
}
"""

print("=" * 80)
print("Testing Vision API with direct image upload")
print("=" * 80)

# Read the image file
with open(image_path, "rb") as f:
    img_data = f.read()

# Send to Vision API
files = {"file": ("page_11.png", img_data, "image/png")}
data = {"text": prompt, "output_token": "4096"}

response = requests.post(api_url, headers={"accept": "application/json"}, files=files, data=data, timeout=600)

print(f"Status Code: {response.status_code}")

resp_json = json.loads(response.text)
description = resp_json.get('description', response.text)

print(f"\nFull response:\n{description}\n")

# Try to extract JSON
import re
json_match = re.search(r'\{[\s\S]*\}', description)

if json_match:
    json_str = json_match.group()
    try:
        layout_data = json.loads(json_str)

        print("=" * 80)
        print("EXTRACTED LAYOUT:")
        print("=" * 80)

        for side, pins in layout_data.items():
            count = len(pins) if pins else 0
            if count > 0:
                print(f"{side:10s}: {count:2d} pins - {pins[:20]}" + ("..." if len(pins) > 20 else ""))
            else:
                print(f"{side:10s}: {count:2d} pins")

        total = sum(len(pins) for pins in layout_data.values() if pins)
        print(f"\n{'Total':10s}: {total:2d} pins")

        if total == 38:
            print("\n✓ Correct pin count!")
        else:
            print(f"\n⚠️ Expected 38 pins, got {total}")

    except json.JSONDecodeError as e:
        print(f"⚠️ Could not parse JSON: {e}")
else:
    print("⚠️ No JSON found in response")
