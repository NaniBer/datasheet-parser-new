#!/usr/bin/env python3
"""Combined pipeline: PageDetector + ContentExtractor"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.page_detector import PageDetector
from src.pdf_extractor.content_extractor import ContentExtractor

def extract_from_pdf(pdf_path, min_confidence=3):
    """
    Extract content from PDF: detect pages, then extract content.
    
    Args:
        pdf_path: Path to PDF file
        min_confidence: Minimum confidence score for page detection (default: 3)
    
    Returns:
        ExtractedContent object with text, tables, images
    """
    # Step 1: Detect relevant pages
    print(f"[1/2] Detecting relevant pages from {pdf_path}...")
    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=min_confidence)
    
    if not candidates:
        print(f"  ERROR: No relevant pages found")
        return None
    
    print(f"  Found {len(candidates)} relevant page(s)")
    
    # Step 2: Extract content
    print(f"[2/2] Extracting content...")
    with ContentExtractor(pdf_path) as extractor:
        content = extractor.extract_content(candidates)
    
    print(f"  Extracted {len(content.pages)} pages")
    print(f"  Found {len(content.tables)} table(s)")
    print(f"  Text content length: {len(content.text_content)} chars")
    
    return content

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 combined_extractor.py <pdf_path> [min_confidence]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    min_confidence = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    content = extract_from_pdf(pdf_path, min_confidence)
    
    if not content:
        print("ERROR: Failed to extract content")
        sys.exit(1)
    
    print(f"SUCCESS: Extracted content")
    print(f"  Text: {len(content.text_content)} chars")
    print(f"  Tables: {len(content.tables)}")
    print(f" Images: {len(content.images)}")
