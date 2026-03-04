#!/usr/bin/env python3
"""
Deep debug script to see EXACTLY what pdfplumber extracts from tables.

This will help us understand why table extraction is failing.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber not installed")
    sys.exit(1)

def debug_page_tables(pdf_path: str, page_num: int):
    """
    Debug table extraction for a specific page.

    Args:
        pdf_path: Path to PDF
        page_num: Page number to debug
    """
    print("=" * 80)
    print(f"Debugging Page {page_num}")
    print("=" * 80)

    with pdfplumber.open(pdf_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"Error: Page {page_num} does not exist (PDF has {len(pdf.pages)} pages)")
            return

        page = pdf.pages[page_num - 1]

        print(f"\nPage Dimensions: {page.width} x {page.height}")
        print(f"Total text length: {len(page.extract_text() or '')} chars")

        # Extract text
        print("\n--- Raw Text (first 500 chars) ---")
        text = page.extract_text() or ""
        print(text[:500])
        print("...")

        # Extract tables
        print("\n--- Table Extraction ---")
        tables = page.extract_tables()

        print(f"\nTotal tables found: {len(tables)}")

        for i, table in enumerate(tables, 1):
            print(f"\n{'='*60}")
            print(f"Table {i}")
            print(f"{'='*60}")

            print(f"Number of rows: {len(table)}")

            if table:
                # Analyze row structure
                print("\nRow analysis:")
                for row_idx, row in enumerate(table[:10]):  # First 10 rows
                    row_str = " | ".join([str(cell)[:20] if cell else "None" for cell in row])
                    print(f"  Row {row_idx} ({len(row)} cells): {row_str}")

                if len(table) > 10:
                    print(f"  ... ({len(table) - 10} more rows)")

                # Check for empty cells
                total_cells = sum(len(row) for row in table)
                empty_cells = sum(1 for row in table for cell in row if not cell or str(cell).strip() == "")
                print(f"\nTotal cells: {total_cells}, Empty cells: {empty_cells} ({empty_cells/total_cells*100:.1f}%)")

        # Try different table extraction settings
        print("\n--- Alternative Table Extraction Methods ---")

        # Method 1: extract_tables() with tolerance
        print("\n1. extract_tables() - standard:")
        tables_standard = page.extract_tables()
        print(f"   Found {len(tables_standard)} tables")
        for i, tbl in enumerate(tables_standard[:1], 1):  # First table only
            print(f"   Table {i}: {len(tbl)} rows")

        # Method 2: find_tables() first
        print("\n2. find_tables() then extract:")
        table_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "explicit_vertical_lines": [],
            "explicit_horizontal_lines": [],
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 3,
            "min_words_vertical": 3,
            "min_words_horizontal": 1,
            "keep_blank_chars": "",
            "text_x_tolerance": 3,
            "text_y_tolerance": 3,
            "intersection_tolerance": 3,
        }
        tables_found = page.find_tables(table_settings=table_settings)
        print(f"   Found {len(tables_found)} tables using find_tables()")

        for i, tbl in enumerate(tables_found[:3], 1):  # First 3 tables
            print(f"\n   Table {i} (bbox: {tbl.bbox}):")
            print(f"   Rows: {len(tbl.extract())}")
            extracted = tbl.extract()
            for row_idx, row in enumerate(extracted[:5]):
                row_str = " | ".join([str(cell)[:25] for cell in row])
                print(f"     Row {row_idx}: {row_str}")

        # Check for images
        print("\n--- Images on Page ---")
        images = page.images
        print(f"Number of images: {len(images)}")
        for i, img in enumerate(images[:5]):
            print(f"  Image {i+1}: {img.get('width', 0)} x {img.get('height', 0)}")


def main():
    pdf_path = "pdfs/test.pdf"

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    # Debug the pages that should contain pinout tables
    # Based on the debug output: page 310 had the most confidence
    pages_to_debug = [10, 12, 13, 86, 300, 310]

    for page_num in pages_to_debug:
        print("\n\n")
        debug_page_tables(pdf_path, page_num)


if __name__ == "__main__":
    main()
