#!/usr/bin/env python3
"""
Test: Use Vision API for pages with pinout diagrams ONLY.

Instead of sending all confusing text to LLM,
send ONLY the images from pages that have pinout diagrams.
"""

import sys
import os
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector
from src.llm.image_ocr_client import ImageOCRClient

def test_vision_only(pinout_pages: list[int]):
    """
    Use Vision API to extract pinout ONLY from specified pages.

    Args:
        pinout_pages: List of page numbers that contain pinout diagrams
    """
    pdf_path = "pdfs/test.pdf"

    print("=" * 80)
    print("STEP 1: Convert Pinout Pages to Images")
    print("=" * 80)

    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        # Convert target pages to images
        extracted_images = []

        for page_num in pinout_pages:
            if page_num < 1 or page_num > len(pdf.pages):
                print(f"Warning: Page {page_num} does not exist")
                continue

            page = pdf.pages[page_num - 1]
            print(f"\nProcessing Page {page_num}...")

            # Convert entire page to image (includes diagrams/drawings)
            # This is different from extracting embedded images!
            pil_image = page.to_image()

            # Save to bytes
            img_bytes = io.BytesIO()
            pil_image.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            img_data = img_bytes.getvalue()

            extracted_images.append((page_num, img_data))
            print(f"  ✓ Converted to image: {len(img_data)} bytes")

        print(f"\n\nTotal images extracted: {len(extracted_images)}")

    print("\n" + "=" * 80)
    print("STEP 2: Send Images to Vision API")
    print("=" * 80)

    # Create Vision client
    vision_client = ImageOCRClient(
        api_url="https://qwen.ideeza.com/describe_image/",
        output_token=4096,
        timeout=120
    )

    # Send to Vision API
    result = vision_client.extract_pinout_from_images(
        images=extracted_images,
        part_number="ATmega164A"
    )

    print("\n--- VISION API RESULT ---")
    print(f"Component:    {result.component_name}")
    print(f"Package:      {result.package_type}")
    print(f"Pin count:   {result.pin_count}")
    print(f"Confidence:   {result.confidence:.2f}")
    print(f"Notes:        {result.notes}")

    if result.pins:
        print(f"\nExtracted {len(result.pins)} pins:")
        print(f"{'Pin':<5} {'Name':<15} {'Function'}")
        print("-" * 50)
        for pin in result.pins:
            func = pin.get('function', 'N/A')
            num = pin.get('number', '?')
            name = pin.get('name', '?')
            print(f"{num:<5} {name:<15} {func}")
    else:
        print("\nNo pins extracted!")


if __name__ == "__main__":
    # Page 11 contains the PDIP/TQFP pinout diagram
    pinout_pages = [11]

    print("=" * 80)
    print("Vision-Only Extraction Test")
    print("=" * 80)
    print(f"\nTarget pages: {pinout_pages}")
    print("These pages contain actual pinout diagrams.")
    print()

    test_vision_only(pinout_pages)
