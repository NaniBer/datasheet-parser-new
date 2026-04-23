#!/usr/bin/env python3
"""Test full pipeline pin extraction (no GLB generation)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.chat_bot import build_pin_extraction_prompt
from src.llm.client import LLMClient
import os

pdf_path = 'pdfs/74HC595_TI.pdf'
api_key = os.getenv('FASTCHAT_API_KEY')

if not api_key:
    print('ERROR: FASTCHAT_API_KEY not set')
    sys.exit(1)

print('=' * 60)
print('FULL PIPELINE PIN EXTRACTION TEST')
print('=' * 60)

try:
    # Step 1: Page detection
    print(f'\n[1/5] Page detection...')
    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=3)
    
    page3 = next((c for c in candidates if c.page_number == 3), None)
    if not page3:
        print('ERROR: Page 3 not found')
        sys.exit(1)
    
    print(f' Page 3 has_table: {page3.has_table}')
    print(f' Confidence: {page3.confidence_score}')
    
    # Step 2: Content extraction
    print(f'\n[2/5] Extracting content from relevant pages...')
    with ContentExtractor(pdf_path) as extractor:
        content = extractor.extract_content([page3])
        
        print(f' Extracted {len(content.pages)} pages')
        print(f' Found {len(content.tables)} table(s)')
        print(f' Text content length: {len(content.text_content)} chars')
    
    # Step 3: Pin extraction
    print(f'\n[3/5] Extracting pin data with LLM...')
    
    llm_client = LLMClient(api_key=api_key, model='llama-3')
    pin_data = llm_client.extract_pin_data(content=content.text_content)
    
    print(f'\n Pin extraction results:')
    print(f'  Component: {pin_data.component_name}')
    print(f'  Package: {pin_data.package.type}-{pin_data.package.pin_count}')
    print(f'  Pin count: {len(pin_data.pins)}')
    
    print(f'\n First 10 pins:')
    for i, pin in enumerate(pin_data.pins[:10]):
        print(f'  {i+1}. Pin {pin.number}: {pin.name} ({pin.function})')
    
    if len(pin_data.pins) > 10:
        print(f'  ... and {len(pin_data.pins) - 10} more pins')
    
    # Check for correct names (QA, QB, QC instead of Q1, Q2, Q3)
    pin_names = [p.name for p in pin_data.pins]
    has_qa = 'QA' in pin_names
    has_qb = 'QB' in pin_names
    has_qc = 'QC' in pin_names
    
    print(f'\n  Pin name verification:')
    print(f'  Has QA: {has_qa}')
    print(f' Has QB: {has_qb}')
    print(f' Has QC: {has_qc}')
    
    if has_qa and has_qb and has_qc:
        print('\nSUCCESS: Correct pin names extracted!')
    else:
        print('\nFAILURE: Hallucinating sequential names (Q1, Q2, Q3...)')
    
    print('\n' + '=' * 60)
    print('TEST COMPLETE')
    
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
