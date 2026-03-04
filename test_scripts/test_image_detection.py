#!/usr/bin/env python3
"""Test image detection and dummy OCR API integration."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.image_detector import ImageDetector
from src.llm.image_ocr_client import DummyImageOCRClient

pdf_path = "pdfs/test.pdf"
output_dir = "output/images"

print("=" * 70)
print("Image Detection Test for ATmega164A")
print("=" * 70)
print()

# 1. Find pages with images
print("Step 1: Finding pages with images...")
detector = ImageDetector(pdf_path)
candidates = detector.find_pages_with_images(
    min_confidence=0.3,
    require_large_image=True
)

print(f"\nFound {len(candidates)} page(s) with potential pinout images:\n")

for i, c in enumerate(candidates, 1):
    print(f"{i}. Page {c.page_number}: confidence={c.confidence:.2f}")
    print(f"   Images: {len(c.images)}")
    for j, img in enumerate(c.images):
        size_text = f"{img.width:.1f}x{img.height:.1f}"
        large_text = " [LARGE]" if img.is_large else ""
        print(f"     Image {j}: {size_text}{large_text}")
    print(f"   Reasons: {', '.join(c.reasons)}")
    print()

# 2. Save images to disk
print("=" * 70)
print("Step 2: Saving images to disk...")
print(f"Output directory: {output_dir}")
print()

detector.save_images_to_disk(output_dir, candidates)

print(f"Saved images to {output_dir}/")
print()

# 3. Test dummy OCR API
print("=" * 70)
print("Step 3: Testing Dummy OCR API...")
print()

ocr_client = DummyImageOCRClient()

# Get images from top 2 pages
top_pages = candidates[:2]
images_to_process = []

for c in top_pages:
    for img in c.images:
        if img.image_data:
            images_to_process.append((c.page_number, img.image_data))

print(f"Processing {len(images_to_process)} image(s) with dummy API...\n")

result = ocr_client.extract_pinout_from_images(
    images=images_to_process,
    part_number="ATmega164A"
)

print()
print("Result from Dummy API:")
print("-" * 70)
print(f"Component: {result.component_name}")
print(f"Package: {result.package_type}")
print(f"Pin count: {result.pin_count}")
print(f"Confidence: {result.confidence}")
print(f"Extraction method: {result.extraction_method}")
print()
print(f"Extracted {len(result.pins)} pins:")
for pin in result.pins:
    print(f"  Pin {pin.get('number')}: {pin.get('name')}")

print()
print("-" * 70)
print()
print("NOTE: This is using the DUMMY API client.")
print("Replace DummyImageOCRClient with actual AI API integration.")
print()

detector.close()
