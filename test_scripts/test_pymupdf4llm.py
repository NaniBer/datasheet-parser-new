#!/usr/bin/env python3
"""Test PyMuPDF4LLM on ESP32 datasheet."""

import pymupdf4llm
import sys

pdf_path = "pdfs/pages.pdf"

print("=" * 80)
print("Testing PyMuPDF4LLM on ESP32 page 10")
print("=" * 80)

# Convert PDF to Markdown
try:
    md_text = pymupdf4llm.to_markdown(pdf_path)

    # Find page 10 content
    lines = md_text.split('\n')
    page10_lines = []
    found_page10 = False
    for i, line in enumerate(lines):
        if 'Page 10' in line or found_page10:
            found_page10 = True
            page10_lines.append(line)
            if i < len(lines) - 1 and 'Page 11' in lines[i+1]:
                break

    print("\n--- MARKDOWN OUTPUT FOR PAGE 10 ---")
    print('\n'.join(page10_lines[:100]))  # First 100 lines

    print("\n" + "=" * 80)
    print(f"Total Markdown length: {len(md_text)} chars")
    print(f"Page 10 section length: {len(''.join(page10_lines))} chars")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
