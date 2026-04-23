#!/usr/bin/env python3
"""Test ContentExtractor with JSON formatting."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor

pdf_path = 'pdfs/74HC595_TI.pdf'

print('=' * 60)
print('CONTENT EXTRACTOR TEST')
print('=' * 60)

# Test 1: Check table extraction
print(f'\n[1] Page detection...')
with PageDetector(pdf_path) as detector:
    candidates = detector.detect_relevant_pages(min_confidence=3)
    
# Find page 3
page3 = next((c for c in candidates if c.page_number == 3), None)
if not page3:
    print('ERROR: Page 3 not found')
    sys.exit(1)

print(f'Page 3 has_table: {page3.has_table}')
print(f'Page 3 has_diagram: {page3.has_diagram}')

# Test 2: Check ContentExtractor
print(f'\n[2] ContentExtractor...')
with ContentExtractor(pdf_path) as extractor:
    content = extractor.extract_content([page3])
    
print(f'Extracted {len(content.pages)} pages')
print(f'Extracted {len(content.tables)} table(s)')
print(f'Text_content length: {len(content.text_content)} chars')

# Test 3: Check for JSON marker
has_json_marker = 'Pinout Tables (JSON)' in content.text_content
has_table_keyword = 'table' in content.text_content.lower()

print(f'\n[3] Content checking...')
print(f'Has JSON marker: {has_json_marker}')
print(f'Has table keyword: {has_table_keyword}')

if has_json_marker:
    print('✓ JSON formatting IS being applied')
elif has_table_keyword:
    print('⚠ Has table keyword but NO JSON marker')
else:
    print('✗ No table markers at all')

print(f'\n[4] Text preview (first 200 chars)...')
print(content.text_content[:200])

print('\n' + '=' * 60)
print('TEST COMPLETE')
