"""Test script: PageDetector → OpenDataLoader → LLM flow."""

import sys
from pathlib import Path

# Add src to path
src_path = str(Path(__file__).parent.parent / "src")
sys.path.insert(0, src_path)

# Import modules directly to avoid __init__.py issues
import importlib.util

# Load modules using importlib
spec = importlib.util.spec_from_file_location("page_detector", f"{src_path}/pdf_extractor/page_detector.py")
page_detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(page_detector)
PageDetector = page_detector.PageDetector

spec = importlib.util.spec_from_file_location("content_extractor", f"{src_path}/pdf_extractor/content_extractor.py")
content_extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(content_extractor)
ContentExtractor = content_extractor.ContentExtractor

spec = importlib.util.spec_from_file_location("llm_client", f"{src_path}/llm/client.py")
llm_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(llm_client)
LLMClient = llm_client.LLMClient

spec = importlib.util.spec_from_file_location("pin_data", f"{src_path}/models/pin_data.py")
pin_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin_data)
PinData = pin_data.PinData

def test_table_extraction_flow():
    """Test complete flow: PageDetector → OpenDataLoader → LLM."""

    pdf_path = "pdfs/74HC595_TI.pdf"
    api_key = None  # Will use env var FASTCHAT_API_KEY

    print("=" * 70)
    print("TEST: PageDetector → OpenDataLoader → LLM Flow")
    print("=" * 70)

    # Step 1: PageDetector - Find pages with tables
    print("\n[STEP 1] PageDetector - Finding pages with tables...")
    print("-" * 70)

    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=5)

    print(f"Found {len(candidates)} candidate pages:")
    for c in candidates:
        print(f"  Page {c.page_number}: confidence={c.confidence_score}, "
              f"has_table={c.has_table}, has_diagram={c.has_diagram}")

    # Filter to pages with tables only
    table_pages = [c for c in candidates if c.has_table]
    print(f"\nPages with tables: {[c.page_number for c in table_pages]}")

    if not table_pages:
        print("❌ No tables found!")
        return

    # Step 2: ContentExtractor - Extract tables using OpenDataLoader
    print("\n[STEP 2] ContentExtractor - Extracting tables with OpenDataLoader...")
    print("-" * 70)

    extractor = ContentExtractor(pdf_path)
    content = extractor.extract_content(candidates)

    print(f"Extraction results:")
    print(f"  Pages: {content.pages}")
    print(f"  Text length: {len(content.text_content)} chars")
    print(f"  Tables found: {len(content.tables)}")
    print(f"  Images found: {len(content.images)}")

    # Show table structure
    if content.tables:
        page_num, table = content.tables[0]
        print(f"\nFirst table (page {page_num}):")
        print(f"  Rows: {len(table)}")
        if table:
            print(f"  Columns: {len(table[0])}")
            print(f"\n  Header row: {table[0]}")
            print(f"  Second row: {table[1]}")
            print(f"  First data row: {table[2]}")

    # Step 3: Format for LLM (table-only mode)
    print("\n[STEP 3] Formatting for LLM (table-only mode)...")
    print("-" * 70)

    tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
    formatted_content = ContentExtractor.format_for_llm(
        content,
        tables_only=tables_only_mode
    )

    print(f"Table-only mode: {tables_only_mode}")
    print(f"Content length sent to LLM: {len(formatted_content)} characters")

    print("\n" + "=" * 70)
    print("CONTENT SENT TO LLM:")
    print("=" * 70)
    print(formatted_content)
    print("=" * 70)

    # Step 4: LLM - Extract pin data
    print("\n[STEP 4] LLM - Extracting pin data...")
    print("-" * 70)

    try:
        llm_client = LLMClient(api_key=api_key, model="llama-3")

        print(f"Calling LLM with table-only mode={tables_only_mode}...")
        pin_data = llm_client.extract_pin_data(
            content=formatted_content,
            tables_only_mode=tables_only_mode
        )

        print(f"\n✅ LLM extraction successful!")
        print(f"\nExtracted PinData:")
        print(f"  Component: {pin_data.component_name}")
        print(f"  Package: {pin_data.package.type}-{pin_data.package.pin_count}")
        print(f"  Pin count: {len(pin_data.pins)}")
        print(f"  Extraction method: {pin_data.extraction_method}")

        print(f"\n  Pins extracted:")
        for pin in pin_data.pins:
            func = f" ({pin.function})" if pin.function else ""
            print(f"    Pin {pin.number:2d}: {pin.name:10s}{func}")

        # Check for correct pin names
        correct_names = ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH", "QH'"]
        extracted_names = [p.name for p in pin_data.pins]

        print(f"\n" + "=" * 70)
        print("VALIDATION:")
        print("=" * 70)

        found_correct = [name for name in correct_names if name in extracted_names]
        missing_correct = [name for name in correct_names if name not in extracted_names]

        print(f"Correct pin names found: {found_correct}")
        print(f"Correct pin names missing: {missing_correct}")

        # Check for hallucinations
        hallucinated = [name for name in extracted_names if name.startswith("Q") and name not in correct_names and name.isdigit()]
        if hallucinated:
            print(f"❌ Hallucinated pin names: {hallucinated}")
        else:
            print(f"✅ No hallucinated pin names detected")

        # Overall result
        print(f"\n" + "=" * 70)
        print("RESULT:")
        print("=" * 70)

        if not missing_correct and not hallucinated:
            print("✅ SUCCESS: All correct pin names extracted, no hallucinations!")
        elif missing_correct:
            print(f"⚠️  PARTIAL: Missing {len(missing_correct)} correct pin names")
        elif hallucinated:
            print(f"❌ FAILURE: Found {len(hallucinated)} hallucinated pin names")

    except Exception as e:
        print(f"❌ LLM extraction failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        extractor.close()

if __name__ == "__main__":
    test_table_extraction_flow()
