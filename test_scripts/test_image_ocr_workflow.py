#!/usr/bin/env python3
"""End-to-end test of image-based pinout extraction workflow."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.image_pinout_extractor import ImagePinoutExtractor
from src.llm.image_ocr_client import DummyImageOCRClient

pdf_path = "pdfs/test.pdf"
output_dir = "output/pinout_images"

print("=" * 70)
print("Image-Based Pinout Extraction Workflow Test")
print("=" * 70)
print()

# 1. Extract pinout images from PDF
print("Step 1: Extracting pinout diagrams as images...")
print()

extractor = ImagePinoutExtractor(pdf_path)
images = extractor.find_and_extract_pinout_images(
    save_to_disk=True,
    output_dir=output_dir
)

print(f"Extracted {len(images)} pinout image(s):")
for i, (page_num, _) in enumerate(images, 1):
    print(f"  {i}. Page {page_num}")

print()

# 2. Send to AI OCR API
print("=" * 70)
print("Step 2: Processing images with AI OCR API...")
print()

ocr_client = DummyImageOCRClient(api_key="your-api-key-here")

result = ocr_client.extract_pinout_from_images(
    images=images,
    part_number="ATmega164A"
)

print()
print("Extraction Result:")
print("-" * 70)
print(f"Component:  {result.component_name}")
print(f"Package:     {result.package_type}")
print(f"Pin count:   {result.pin_count}")
print(f"Confidence:  {result.confidence:.2f}")
print(f"Method:      {result.extraction_method}")
print()

if result.pins:
    print(f"Extracted {len(result.pins)} pins:")
    for i, pin in enumerate(result.pins[:10], 1):  # Show first 10
        print(f"  {i:2d}. Pin {pin.get('number'):3s}: {pin.get('name')}")
    if len(result.pins) > 10:
        print(f"  ... and {len(result.pins) - 10} more pins")
else:
    print("No pins extracted")

print()
print("-" * 70)
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()
print(f"Images extracted and saved to: {output_dir}/")
print(f"Number of pages processed: {len(images)}")
print()
print("NOTE: Currently using DummyImageOCRClient.")
print("To use real AI API:")
print("  1. Replace DummyImageOCRClient with your AI API implementation")
print("  2. Update API_URL and API_KEY in src/llm/image_ocr_client.py")
print("  3. Implement the extract_pinout_from_image() method with real API calls")
print()

extractor.close()
