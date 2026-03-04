#!/usr/bin/env python3
"""Test PyMuPDF4LLM pinout section."""

import pymupdf4llm
import sys

pdf_path = "pdfs/pages.pdf"

print("=" * 80)
print("Testing PyMuPDF4LLM - Pinout Section")
print("=" * 80)

# Convert PDF to Markdown
md_text = pymupdf4llm.to_markdown(pdf_path)

# Look for pin layout section (around line 373)
lines = md_text.split('\n')
start = max(0, 350)
end = min(len(lines), 450)

print("\n--- PIN LAYOUT SECTION (lines 350-450) ---\n")
for i in range(start, end):
    print(f"{i:3d}: {lines[i]}")

# Save to file
with open('pymupdf4llm_output.md', 'w') as f:
    f.write(md_text)

print(f"\nSaved full Markdown to pymupdf4llm_output.md ({len(md_text)} chars)")
