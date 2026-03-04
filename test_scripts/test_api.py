#!/usr/bin/env python3
"""
Call: POST https://qwen.ideeza.com/describe_image/
multipart/form-data fields:
  - file: image file upload
  - text: prompt
  - output_token: integer (e.g., 1024)

Usage:
  python describe_image.py --file car_image.jpg
  python describe_image.py --file car_image.jpg --text "Describe the object in the image." --output-token 1024
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from typing import Any, Dict

import requests


API_URL = "https://qwen.ideeza.com/describe_image/"


def guess_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def call_api(
    file_path: str,
    text: str,
    output_token: int,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    mime_type = guess_mime_type(file_path)

    # multipart/form-data: use `files` for uploads, `data` for normal fields
    with open(file_path, "rb") as f:
        files = {
            "file": (os.path.basename(file_path), f, mime_type),
        }
        data = {
            "text": text,
            "output_token": str(output_token),  # safe for form fields
        }

        resp = requests.post(
            API_URL,
            headers={"accept": "application/json"},
            files=files,
            data=data,
            timeout=timeout_seconds,
        )

    # Raise a helpful error on non-2xx
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        body_preview = resp.text[:2000] if resp.text else ""
        raise requests.HTTPError(
            f"{e}\n--- Response body (first 2000 chars) ---\n{body_preview}"
        ) from None

    # Parse JSON (if the server returns JSON)
    try:
        return resp.json()
    except ValueError:
        # If the response isn't JSON, return raw text in a JSON-like wrapper
        return {"raw_text": resp.text}


def main() -> int:
    parser = argparse.ArgumentParser(description="Describe an image via qwen.ideeza.com API")
    parser.add_argument("--file", "-f", required=True, help="Path to the image file (e.g., car_image.jpg)")
    parser.add_argument("--text", "-t", default="""You are an expert at reading electronic component pinout diagrams from datasheet images. Analyze the provided image and extract complete pinout information.

  1. **Identify the component** (e.g., ATmega164A, NE555, STM32F103, ESP32-WROOM-32)

  2. **Determine the package type** (e.g., PDIP-40, DIP-8, TQFP-44, LQFP-64, SOIC-16, QFN-38)

  3. **Extract ALL pins** with their numbers and names:
     - For DIP packages: Pin 1 is top-left, numbering goes DOWN left side, then UP right side
     - For SOIC/TQFP/LQFP: Pin 1 is top-left, numbering is counter-clockwise
     - For QFN: Pin 1 is top-left, numbering is counter-clockwise on all 4 sides
     - Include ALL pins (not just a sample)

  4. **Verify key pins:**
     - Power pins: VCC/VDD, GND/VSS, AVCC, AREF, VBAT
     - Crystal pins: XTAL1, XTAL2, OSC_IN, OSC_OUT
     - Control pins: RESET, CS, EN, BOOT0
     - Communication pins: SCK, MISO, MOSI, TX, RX, SDA, SCL

  5. **Port pin patterns:** Look for PA0-PA7, PB0-PB7, PC0-PC7, PD0-PD7, or IO0-IO39

  ## Output Format:

  Return ONLY valid JSON (no markdown code blocks, no additional text):

  {
    "component_name": "Component Name",
    "package_type": "Package Type",
    "pin_count": 40,
    "pins": [
      {"number": 1, "name": "PB0", "function": "Port B bit 0"},
      {"number": 2, "name": "PB1", "function": "Port B bit 1"},
      ...
    ],
    "extraction_confidence": 0.95,
    "notes": "Optional notes about extraction quality"""
  , help="Prompt text")
    parser.add_argument("--output-token", "-o", type=int, default=1024, help="Max output tokens (e.g., 1024)")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    args = parser.parse_args()

    try:
        result = call_api(
            file_path=args.file,
            text=args.text,
            output_token=args.output_token,
            timeout_seconds=args.timeout,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())