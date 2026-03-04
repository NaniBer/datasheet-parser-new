#!/usr/bin/env python3
"""Check if page 11 has images according to pdfplumber."""

import pdfplumber

pdf = pdfplumber.open('pdfs/test.pdf')
page = pdf.pages[10]  # Page 11

print(f'Page 11 dimensions: {page.width} x {page.height}')
print()

print('=== IMAGES detected by pdfplumber ===')
images = page.images
print(f'Number of images: {len(images)}')
print()

for i, img in enumerate(images):
    print(f'Image {i+1}:')
    print(f'  Width: {img.get("width", 0)}')
    print(f'  Height: {img.get("height", 0)}')
    print(f'  Area: {img.get("width", 0) * img.get("height", 0)}')
    print()

print()
print('=== Trying to convert page to image ===')
try:
    pil_image = page.to_image()
    print(f'Success! PIL image created')
    print(f'Image dimensions: {pil_image.width} x {pil_image.height}')
except Exception as e:
    print(f'Error converting to image: {e}')
