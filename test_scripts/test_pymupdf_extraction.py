#!/usr/bin/env python3
"""Compare text extraction quality: pdfplumber vs PyMuPDF (fitz)."""

import fitz  # PyMuPDF
import pdfplumber

pdf_path = "pdfs/pages.pdf"
page_index = 9  # Page 10 (ESP32 pinout)

print("=" * 80)
print("COMPARING TEXT EXTRACTION QUALITY")
print("=" * 80)

# Extract with pdfplumber
print("\n--- PDFPLUMBER TEXT ---")
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[page_index]
    pdfplumber_text = page.extract_text()
    print(pdfplumber_text[:1500])

# Extract with PyMuPDF (fitz)
print("\n--- PYMUPDF (FITZ) TEXT ---")
with fitz.open(pdf_path) as pdf:
    page = pdf[page_index]
    pymupdf_text = page.get_text()
    print(pymupdf_text[:1500])

print("\n" + "=" * 80)
print("COMPARISON SUMMARY")
print("=" * 80)
print(f"pdfplumber: {len(pdfplumber_text)} chars")
print(f"PyMuPDF:    {len(pymupdf_text)} chars")

# Check for bottom row pins (15-24)
print("\n--- SEARCHING FOR PINS 15-24 (bottom edge) ---")
if "15" in pdfplumber_text or "16" in pdfplumber_text:
    print("pdfplumber: Found bottom row pins")
else:
    print("pdfplumber: Bottom row pins NOT found (garbled)")

if "15" in pymupdf_text or "16" in pymupdf_text:
    print("PyMuPDF:    Found bottom row pins")
else:
    print("PyMuPDF:    Bottom row pins NOT found (garbled)")

# Show sample of each method around the area where pins 15-24 should be
print("\n--- SAMPLE AROUND BOTTOM ROW AREA ---")
print("pdfplumber:")
pdfplumber_lines = pdfplumber_text.split('\n')
for i, line in enumerate(pdfplumber_lines):
    if 'Keepout' in line or 'GND 38' in line:
        # Show lines around this area
        for j in range(max(0, i-2), min(len(pdfplumber_lines), i+10)):
            print(f"  {pdfplumber_lines[j]}")
        break

print("\nPyMuPDF:")
pymupdf_lines = pymupdf_text.split('\n')
for i, line in enumerate(pymupdf_lines):
    if 'Keepout' in line or 'GND 38' in line:
        # Show lines around this area
        for j in range(max(0, i-2), min(len(pymupdf_lines), i+10)):
            print(f"  {pymupdf_lines[j]}")
        break
