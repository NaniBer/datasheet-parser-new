#!/usr/bin/env python3
"""Test PyMuPDF4LLM full output on ESP32 datasheet."""

import pymupdf4llm
import sys

pdf_path = "pdfs/pages.pdf"

print("=" * 80)
print("Testing PyMuPDF4LLM - Full output")
print("=" * 80)

# Convert PDF to Markdown
md_text = pymupdf4llm.to_markdown(pdf_path)

# Look for page 10 or pinout section
print("\n--- FIRST 200 LINES ---")
for i, line in enumerate(md_text.split('\n')[:200]):
    print(f"{i:3d}: {line}")

# Search for pin layout
print("\n" + "=" * 80)
print("SEARCHING FOR PIN LAYOUT...")
print("=" * 80)

for i, line in enumerate(md_text.split('\n')):
    if 'pin layout' in line.lower() or 'pinout' in line.lower():
        # Show 20 lines before and after
        lines = md_text.split('\n')
        start = max(0, i-5)
        end = min(len(lines), i+50)
        print(f"Found at line {i}: {line}")
        print("\nContext:")
        for j in range(start, end):
            print(lines[j])
        break
