"""Test hybrid extraction with OpenDataLoader for tables."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pdf_extractor.page_detector import PageDetector
from pdf_extractor.content_extractor import ContentExtractor

def test_hybrid_extraction():
    """Test hybrid extraction on 74HC595 datasheet."""

    pdf_path = "pdfs/74HC595_TI.pdf"

    print("=" * 60)
    print("Testing Hybrid Extraction (pdfplumber + OpenDataLoader)")
    print("=" * 60)

    # Step 1: Detect pages with pinout tables
    print("\nStep 1: Detecting relevant pages...")
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=5)

    print(f"\nFound {len(candidates)} candidate pages:")
    for candidate in candidates:
        print(f"  Page {candidate.page_number}: confidence={candidate.confidence_score}, "
              f"table={candidate.has_table}, diagram={candidate.has_diagram}")

    # Filter to pages with tables only
    table_pages = [c for c in candidates if c.has_table]
    print(f"\nPages with tables: {[c.page_number for c in table_pages]}")

    # Step 2: Extract content using hybrid approach
    print("\nStep 2: Extracting content (hybrid mode)...")
    extractor = ContentExtractor(pdf_path)

    try:
        content = extractor.extract_content(candidates)

        print(f"\nExtraction results:")
        print(f"  Pages extracted: {content.pages}")
        print(f"  Text length: {len(content.text_content)} characters")
        print(f"  Number of tables: {len(content.tables)}")
        print(f"  Number of images: {len(content.images)}")

        # Show table details
        if content.tables:
            print(f"\nTable details:")
            for page_num, table in content.tables:
                print(f"\n  Table on page {page_num}:")
                print(f"    Rows: {len(table)}")
                if table:
                    print(f"    Columns: {len(table[0]) if table else 0}")
                    print(f"    Header row: {table[0]}")
                    if len(table) > 1:
                        print(f"    First data row: {table[1]}")
                    if len(table) > 2:
                        print(f"    Second data row: {table[2]}")

        # Step 3: Format for LLM
        print("\nStep 3: Formatting for LLM...")
        formatted = extractor.format_for_llm(content)

        print(f"\nFormatted content length: {len(formatted)} characters")
        print(f"\nFirst 500 characters of formatted content:")
        print("=" * 60)
        print(formatted[:500])
        print("=" * 60)

        # Check for specific pin names in formatted content
        print("\nStep 4: Checking for correct pin names...")
        pin_names = ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH", "QH'"]
        found_pins = []
        missing_pins = []

        for pin in pin_names:
            if pin in formatted:
                found_pins.append(pin)
            else:
                missing_pins.append(pin)

        print(f"\nFound pin names: {found_pins}")
        print(f"Missing pin names: {missing_pins}")

        # Check for hallucinated pin names
        print("\nStep 5: Checking for hallucinated pin names...")
        hallucinated_pins = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]
        found_hallucinated = []

        for pin in hallucinated_pins:
            if pin in formatted:
                found_hallucinated.append(pin)

        if found_hallucinated:
            print(f"WARNING: Found hallucinated pin names: {found_hallucinated}")
        else:
            print("✅ No hallucinated pin names detected")

        # Save formatted content for inspection
        output_file = "output/hybrid_extraction_test.txt"
        with open(output_file, "w") as f:
            f.write(formatted)

        print(f"\nFull formatted content saved to: {output_file}")

        # Step 5: Call LLM with table-only mode
        print("\nStep 6: Calling LLM with table-only mode...")
        print("=" * 60)

        from llm.client import LLMClient

        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_for_llm = ContentExtractor.format_for_llm(
            content,
            tables_only=tables_only_mode
        )

        print(f"Table-only mode: {tables_only_mode}")
        print(f"Content length: {len(formatted_for_llm)} characters")

        try:
            llm_client = LLMClient(model="llama-3")
            pin_data = llm_client.extract_pin_data(
                content=formatted_for_llm,
                tables_only_mode=tables_only_mode
            )

            print(f"\n✅ LLM extraction successful!")
            print(f"  Component: {pin_data.component_name}")
            print(f"  Package: {pin_data.package.type}-{pin_data.package.pin_count}")
            print(f"  Pin count: {len(pin_data.pins)}")
            print(f"  Extraction method: {pin_data.extraction_method}")

            print(f"\n  Pins extracted:")
            for pin in pin_data.pins:
                func = f" ({pin.function})" if pin.function else ""
                print(f"    Pin {pin.number:2d}: {pin.name:10s}{func}")

            # Validate pin names
            extracted_names = [p.name for p in pin_data.pins]
            found_correct = [name for name in pin_names if name in extracted_names]
            missing_correct = [name for name in pin_names if name not in extracted_names]
            hallucinated = [name for name in extracted_names if name.startswith("Q") and name not in pin_names and name.isdigit()]

            print(f"\n" + "=" * 60)
            print("LLM VALIDATION:")
            print("=" * 60)
            print(f"Correct names found: {found_correct}")
            print(f"Correct names missing: {missing_correct}")
            print(f"Hallucinated names: {hallucinated if hallucinated else 'None'}")

            if not missing_correct and not hallucinated:
                print("✅ PERFECT: All correct names, no hallucinations!")
            elif missing_correct:
                print(f"⚠️  Missing {len(missing_correct)} correct names")
            elif hallucinated:
                print(f"❌ Found {len(hallucinated)} hallucinations")

        except Exception as e:
            print(f"❌ LLM extraction failed: {e}")
            import traceback
            traceback.print_exc()

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if found_pins and not missing_pins:
            print("✅ All correct pin names found in formatted content")
        else:
            print(f"⚠️  Some pin names missing: {missing_pins}")

        if not found_hallucinated:
            print("✅ No hallucinated pin names detected")
        else:
            print(f"❌ Found hallucinated pin names: {found_hallucinated}")

        print(f"✅ Tables extracted: {len(content.tables)}")
        print(f"✅ Formatted content length: {len(formatted)} characters")

    finally:
        extractor.close()

if __name__ == "__main__":
    test_hybrid_extraction()
