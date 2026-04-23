#!/usr/bin/env python3
"""Test PageDetector only - verify table detection."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector

print('=' * 60)
print('TEST: PageDetector Table Detection Only')
print('=' * 60)

# Test PageDetector on 74HC595
with PageDetector('pdfs/74HC595_TI.pdf') as detector:
    print('\n[1] Running detect_relevant_pages()...')
    candidates = detector.detect_relevant_pages(min_confidence=3)
    
    print(f'Found {len(candidates)} candidate pages')
    
    # Find page 3
    page3 = next((c for c in candidates if c.page_number == 3), None)
    if not page3:
        print('ERROR: Page 3 not found in candidates')
        sys.exit(1)
    
    print(f'\n[2] Page 3 details:')
    print(f'  Page number: {page3.page_number}')
    print(f'  Confidence score: {page3.confidence_score}')
    print(f'  has_table: {page3.has_table}')
    print(f'  has_diagram: {page3.has_diagram}')
    print(f'  Reasons: {page3.reasons}')
    
    # Now verify the table directly using pdfplumber
    print(f'\n[3] Extracting tables from page 3 directly with pdfplumber...')
    
    pdf_page = detector.pdf.pages[page3.page_number - 1]
    tables = pdf_page.extract_tables()
    
    print(f'  Found {len(tables)} table(s) on page 3')
    
    if tables:
        table = tables[0]  # Get the pinout table
        print(f'\n[4] Pinout table structure:')
        print(f'  Number of rows: {len(table)}')
        print(f'  Header row: {table[0]}')
        print(f'  First 3 data rows:')
        for i in range(min(3, len(table))):
            print(f'  Row {i}: {table[i]}')
        
        # Check if this is a pinout table
        header_text = ' '.join(str(cell) for cell in table[0]).lower()
        pinout_keywords = ['pin', 'function', 'description', 'name']
        keyword_count = sum(1 for kw in pinout_keywords if kw in header_text)
        
        if keyword_count >= 2:
            print(f'\n[5] Pinout table check: PASSED (found {keyword_count} keywords)')
        else:
            print(f'\n[5] Pinout table check: FAILED (found only {keyword_count} keywords)')
    else:
        print(f'\n[5] No tables found')

print('\n' + '=' * 60)
print('TEST COMPLETE')
