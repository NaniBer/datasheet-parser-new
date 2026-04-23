#!/usr/bin/env python3
"""Test PageDetector on all PDFs."""

import sys
import os
import glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_pdf(pdf_path):
    """Test a single PDF for table detection."""
    from src.pdf_extractor import PageDetector
    
    filename = os.path.basename(pdf_path)
    print(f'Testing: {filename}')
    print('-' * 60)
    
    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=3)
        
        # Find any pages with tables
        table_pages = [c for c in candidates if c.has_table]
        
        print(f'  Total candidates: {len(candidates)}')
        print(f'  Pages with tables: {len(table_pages)}')
        
        if table_pages:
            print('  Table pages:')
            for c in table_pages:
                print(f'    Page {c.page_number}: confidence={c.confidence_score}')
                print(f'      has_table={c.has_table}')
                
                # Verify table extraction
                pdf_page = detector.pdf.pages[c.page_number - 1]
                tables = pdf_page.extract_tables()
                
                if tables:
                    table = tables[0]
                    print(f'    ✓ Page {c.page_number} has {len(table)}-row table')
                    print(f'      Header: {table[0][:4]}')
                    print(f'      First data row: {table[1][:4]}')
        else:
            print(f'  ✗ Page {c.page_number}: has_table={c.has_table} but no tables extracted')
    
    return True

def main():
    # Get all PDFs
    pdfs = sorted(glob.glob('pdfs/*.pdf'))
    
    print('-' * 60)
    print('PAGE DETECTOR TEST FOR ALL PDFS')
    print('-' * 60)
    
    results = {
        'found': [],
        'not_found': [],
        'failed': []
    }
    
    for pdf_path in pdfs:
        try:
            success = test_pdf(pdf_path)
            if success:
                results['found'].append(pdf_path)
            else:
                results['failed'].append(pdf_path)
        except Exception as e:
            print(f'  ERROR testing {pdf_path}: {e}')
            results['failed'].append(pdf_path)
    
    print('-' * 60)
    print('SUMMARY')
    print('-' * 60)
    print(f'✓ Successfully tested: {len(results["found"])} PDFs')
    print(f'✗ Failed to test: {len(results["failed"])} PDFs')
    
    print('PDFs with table detection:')
    for pdf in results['found']:
        print(f'  ✓ {os.path.basename(pdf)}')
    
    print('PDFs without table detection:')
    for pdf in results['failed']:
        print(f'  ✗ {os.path.basename(pdf)}')

if __name__ == '__main__':
    main()
