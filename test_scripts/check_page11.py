#!/usr/bin/env python3
import pdfplumber
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.pdf_extractor.pinout_filter import PinoutFilter

pdf = pdfplumber.open('pdfs/pages.pdf')
page = pdf.pages[9]  # Page 11 (0-indexed)

print('=== PAGE 11 TEXT ===')
text = page.extract_text()
print(text)

print('\n=== PAGE 11 FILTER CHECK ===')

# Create filter and test with new logic
filter_obj = PinoutFilter()
is_pinout = filter_obj.is_pinout_section(text)

print(f'Will pass filter: {is_pinout}')
print(f'Reasoning:')
print(f'  - Text contains pinout keywords and is not filtered as non-pinout content')
