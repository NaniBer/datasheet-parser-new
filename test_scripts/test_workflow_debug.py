#!/usr/bin/env python3
"""Debug full workflow to find where it gets stuck."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm.client import LLMClient
from src.schematic_generator.adapter import build_schematic_from_pin_data

def debug_workflow(pdf_path: str):
    """Debug workflow step by step with timing."""

    print("=" * 80)
    print("Debug Full Workflow - Step by Step")
    print("=" * 80)

    import time

    # Step 1: Detect relevant pages
    print("\n[1] Detecting relevant pages...")
    start = time.time()
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=3)
    elapsed = time.time() - start
    print(f"✅ Completed in {elapsed:.2f}s - {len(candidates)} pages")

    table_pages = [c for c in candidates if c.has_table]
    print(f"   Pages with tables: {[c.page_number for c in table_pages]}")

    # Step 2: Extract content
    print("\n[2] Extracting content...")
    start = time.time()
    extractor = ContentExtractor(pdf_path)

    try:
        content = extractor.extract_content(candidates)
        elapsed = time.time() - start
        print(f"✅ Completed in {elapsed:.2f}s")
        print(f"   Pages extracted: {content.pages}")
        print(f"   Tables found: {len(content.tables)}")
        print(f"   Images found: {len(content.images)}")

        # Step 3: Format for LLM
        print("\n[3] Formatting for LLM...")
        start = time.time()
        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_content = ContentExtractor.format_for_llm(
            content,
            tables_only=tables_only_mode
        )
        elapsed = time.time() - start
        print(f"✅ Completed in {elapsed:.2f}s")
        print(f"   Content length: {len(formatted_content)} chars")
        print(f"   Table-only mode: {tables_only_mode}")

        # Step 4: Extract pin data with LLM
        print("\n[4] Extracting pin data with LLM...")
        print(f"   Calling API...")
        start = time.time()
        llm_client = LLMClient()

        pin_data = llm_client.extract_pin_data(
            formatted_content,
            tables_only_mode=tables_only_mode
        )
        elapsed = time.time() - start
        print(f"✅ Completed in {elapsed:.2f}s")

        print(f"\n   Component: {pin_data.component_name}")
        print(f"   Extraction method: {pin_data.extraction_method}")

        # Step 5: Generate 3D model
        print("\n[5] Generating 3D schematic...")
        print(f"   Calling build_schematic_from_pin_data...")
        start = time.time()
        success = build_schematic_from_pin_data(
            pin_data,
            "output/debug_workflow.glb"
        )
        elapsed = time.time() - start
        print(f"✅ Completed in {elapsed:.2f}s")
        print(f"   Success: {success}")

        print(f"\n" + "=" * 80)
        print("WORKFLOW COMPLETED SUCCESSFULLY! ✅")

    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ ERROR in {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print(f"\nClosing extractor...")
        extractor.close()

if __name__ == "__main__":
    # Test with 74HC595 PDF
    test_pdf = "pdfs/74HC595_TI.pdf"

    if os.path.exists(test_pdf):
        debug_workflow(test_pdf)
    else:
        print(f"❌ PDF not found: {test_pdf}")
