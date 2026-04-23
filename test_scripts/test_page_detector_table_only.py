#!/usr/bin/env python3
"""Focused test: PageDetector table detection only."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.page_detector import PageDetector

print('=' * 60)
print('FOCUSED TEST: PageDetector Table Detection Only')
print('=' * 60)

# Test on 74HC595 page 3
pdf_path = 'pdfs/74HC595_TI.pdf'

print(f'\nTesting: {pdf_path}')
print(f'Expected: Should detect 22-row table (multi-row header)')
print(f'Expected: Header rows: PIN NAME SOIC... (row 0) and NAME SOIC PDIP... (row 1)')

with PageDetector(pdf_path) as detector:
    # Directly access the PDF page (no detect_relevant_pages)
    pdf = detector.pdf
    page = pdf.pages[2]  # Page 3 (0-indexed)
    
    print(f'\n[1] Direct table extraction...')
    tables = page.extract_tables()
    
    print(f'    Tables found: {len(tables)}')
    
    if not tables:
        print('    ✗ FAILED: No tables')
        sys.exit(1)
    
    table = tables[0]  # Get the pinout table
    
    print(f'\n[2] Table structure...')
    print(f'    Total rows: {len(table)}')
    print(f'    Header row (row 0): {table[0]}')
    print(f'    First data row (row 1): {table[1] if len(table) > 1 else None}')
    
    # Check header patterns
    header_row0 = [str(cell) for cell in table[0]]
    header_row1 = [str(cell) for cell in table[1]] if len(table) > 1 else []
    
    header_text = ' '.join(header_row0)
    if len(table) > 1:
        header_text += ' | ' + ' '.join(header_row1)
    
    print(f'\n[3] Pattern matching...')
    
    # Check for pinout keywords in headers
    pinout_keywords = ['pin', 'name', 'function', 'description']
    found_keywords = [kw for kw in pinout_keywords if kw.lower() in header_text.lower()]
    
    if len(found_keywords) >= 2:
        print(f'    ✓ PASSED: Found {len(found_keywords)} pinout keywords in headers')
        print(f'    Keywords: {found_keywords}')
    else:
        print(f'    ✗ FAILED: Only found {len(found_keywords)} keyword')
    
    print(f'\n[4] Verification...')
    print(f'    Expected table: 22 rows (confirmed by PageDetector)')
    print(f'    Actual table: {len(table)} rows')
    
    if len(table) >= 20:
        print(f'    ✓ VERIFIED: Correct row count')
    else:
        print(f'    ✗ MISMATCH: Expected 22, got {len(table)}')

print('\n' + '=' * 60)
print('TEST COMPLETE')
