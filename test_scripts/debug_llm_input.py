#!/usr/bin/env python3
"""
Debug script to see exactly what content is sent to the LLM.

This helps identify if the issue is in:
1. Page detection (wrong pages selected)
2. Content extraction (misaligned tables, truncated content)
3. LLM interpretation (reading content wrong)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.chat_bot import build_pin_extraction_prompt

def debug_llm_input(pdf_path: str):
    """
    Show exactly what content is sent to the LLM.

    Args:
        pdf_path: Path to the PDF file
    """
    print("=" * 80)
    print("STEP 1: Page Detection")
    print("=" * 80)

    with PageDetector(pdf_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=5)

        print(f"\nTotal PDF pages: {detector.total_pages}")
        print(f"Relevant pages found: {len(candidates)}")
        print()

        for i, c in enumerate(candidates, 1):
            print(f"Candidate {i}:")
            print(f"  Page: {c.page_number}")
            print(f"  Confidence: {c.confidence_score}")
            print(f"  Reasons: {', '.join(c.reasons)}")
            print(f"  Has table: {c.has_table}")
            print(f"  Has diagram: {c.has_diagram}")
            print()

    if not candidates:
        print("No relevant pages found!")
        return

    print("=" * 80)
    print("STEP 2: Content Extraction")
    print("=" * 80)

    with ContentExtractor(pdf_path) as extractor:
        content = extractor.extract_content(candidates)

        print(f"\nExtracted from {len(content.pages)} pages: {content.pages}")
        print(f"Number of tables: {len(content.tables)}")
        print(f"Number of images: {len(content.images)}")

    print("=" * 80)
    print("STEP 3: Content Sent to LLM (Raw)")
    print("=" * 80)
    print("\nThis is the EXACT text content that gets passed to the LLM:")
    print("-" * 80)
    print(content.text_content[:5000])  # First 5000 chars to avoid overwhelming
    print("... (truncated for display)")
    print("-" * 80)

    print("\n" + "=" * 80)
    print("STEP 4: Tables Extracted")
    print("=" * 80)

    for i, (page_num, table) in enumerate(content.tables, 1):
        print(f"\nTable {i} (Page {page_num}):")
        print("-" * 40)
        for row_idx, row in enumerate(table[:15]):  # Show first 15 rows
            print(f"Row {row_idx}: {row}")
        if len(table) > 15:
            print(f"... ({len(table)} total rows)")

    print("\n" + "=" * 80)
    print("STEP 5: LLM Prompt Preview")
    print("=" * 80)

    messages = build_pin_extraction_prompt(content.text_content)
    print("\nSystem Prompt (truncated):")
    print("-" * 40)
    print(messages[0]['content'][:1000] + "...")
    print("-" * 40)

    print("\nUser Prompt (truncated):")
    print("-" * 40)
    print(messages[1]['content'][:2000] + "...")
    print("-" * 40)

    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)

    # Check for potential issues
    issues = []

    # Issue 1: Too many pages selected
    if len(candidates) > 5:
        issues.append(f"⚠️  Too many pages selected ({len(candidates)}), may confuse LLM")

    # Issue 2: Content too long
    if len(content.text_content) > 10000:
        issues.append(f"⚠️  Content is very long ({len(content.text_content)} chars)")

    # Issue 3: No tables found
    if not content.tables:
        issues.append("⚠️  No tables extracted - LLM has to parse from plain text")

    # Issue 4: Tables with inconsistent rows
    if content.tables:
        for page_num, table in content.tables:
            row_lengths = [len(row) for row in table if row]
            if len(set(row_lengths)) > 1:
                issues.append(f"⚠️  Table on page {page_num} has inconsistent row lengths: {set(row_lengths)}")

    # Issue 5: Check for empty or None cells in tables
    empty_count = sum(
        sum(1 for cell in row if cell is None or str(cell).strip() == "")
        for _, table in content.tables
        for row in table
    )
    if empty_count > 10:
        issues.append(f"⚠️  Tables have many empty/None cells ({empty_count})")

    if issues:
        print("\nPotential Issues Found:")
        for issue in issues:
            print(issue)
    else:
        print("\n✓ No obvious structural issues detected")


if __name__ == "__main__":
    pdf_path = "pdfs/test.pdf"

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    debug_llm_input(pdf_path)
