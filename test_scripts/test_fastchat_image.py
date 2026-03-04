#!/usr/bin/env python3
"""Test using FastChat API to process pinout diagram images."""

import sys
import os
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chat_bot import get_completion_from_messages

# Use pinout image
image_path = "output/page11_300dpi.png"

print("=" * 70)
print("FastChat API Image Processing Test")
print("=" * 70)
print()
print(f"Image: {image_path}")
print()

# Check if image exists
if not os.path.exists(image_path):
    print(f"Error: Image not found: {image_path}")
    print("Make sure you've extracted pinout images first")
    sys.exit(1)

# Read and encode image
with open(image_path, 'rb') as f:
    image_data = f.read()
    base64_image = base64.b64encode(image_data).decode('utf-8')

# Build prompt for image-based extraction
prompt = f"""
You are an expert at reading electronic component pinout diagrams from datasheet images.

Analyze the image at the end of this message and extract pinout information.

The image shows a pinout diagram for an electronic component.

## Your Task:

1. **Identify the component** (e.g., ATmega164A, NE555, STM32F103)

2. **Determine the package type** (e.g., PDIP-40, DIP-8, TQFP-44)

3. **Extract ALL pins** with their numbers and names:
   - For DIP packages: Pin 1 is top-left, numbering goes DOWN left side, then UP right side
   - For SOIC/TQFP/QFN: Pin 1 is top-left, numbering is counter-clockwise
   - Include ALL pins (not just a sample)

4. **Key pins to verify:**
   - Power pins: VCC/VDD, GND/VSS, AVCC, AREF
   - Crystal pins: XTAL1, XTAL2
   - Control pins: RESET, CS, EN

5. **Port pins pattern:** Look for PA0-PA7, PB0-PB7, PC0-PC7, PD0-PD7

## Output Format:

Return ONLY valid JSON (no markdown code blocks, no additional text):

```json
{{
  "component_name": "Component Name",
  "package_type": "Package Type",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "PB0"},
    {"number": 2, "name": "PB1"},
    {"number": 3, "name": "PB2"},
    ...
  ],
  "extraction_confidence": 0.95,
  "notes": "All pins extracted from diagram"
}}
```

## Important Rules:

- Extract ALL pins for the package shown
- Verify pin count matches package type (e.g., PDIP-40 must have exactly 40 pins)
- If you can't read a pin number clearly, use the layout to infer it
- Return ONLY JSON - no explanations or additional text
"""

# Build messages - add image as a separate message
# Note: This assumes FastChat supports multimodal images
messages = [
    {
        "role": "user",
        "content": prompt
    }
]

# Try to send image as well (if FastChat supports it)
# This depends on whether FastChat API accepts images in messages
try:
    response = get_completion_from_messages(messages, model="llama-3", temperature=0)

    print("Response from FastChat:")
    print("-" * 70)
    print(response)
    print("-" * 70)
    print()

    # Try to parse JSON from response
    import json
    import re

    # Look for JSON in the response
    # Handle markdown code blocks: ```json\n{...}\n```
    json_match = re.search(r'```json\s*\n?({.*?})\n?```', response, re.DOTALL)

    if json_match:
        json_str = json_match.group(1)
        try:
            data = json.loads(json_str)
            print("Parsed JSON:")
            print("-" * 70)
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
    else:
        print("Note: Response doesn't contain JSON code block")
        print("The raw response is shown above")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print()
print("Note: This test uses the existing FastChat API.")
print("If the API doesn't support images, we'll need to:")
print("  1. Parse the extracted OCR text from the image")
print("  2. Send that text to FastChat API")
print()
