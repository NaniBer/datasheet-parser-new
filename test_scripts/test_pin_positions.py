#!/usr/bin/env python3
"""Test pin position calculation with real PDF extraction."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm.client import LLMClient
from src.schematic_generator.adapter import pin_data_to_builder_format
from src.schematic_generator.package_geometry import get_schematic_parameters, calculate_pin_position

def test_pin_positions(pdf_path: str):
    """Test pin position calculation with extracted data."""

    print("=" * 80)
    print(f"Testing Pin Position Calculation: {os.path.basename(pdf_path)}")
    print("=" * 80)

    # Step 1: Detect pages with pinout tables
    print("\nStep 1: Detecting relevant pages...")
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=3)

    table_pages = [c for c in candidates if c.has_table]
    print(f"Pages with tables: {[c.page_number for c in table_pages]}")

    # Step 2: Extract content
    print("\nStep 2: Extracting content...")
    extractor = ContentExtractor(pdf_path)

    try:
        content = extractor.extract_content(candidates)

        print(f"Pages extracted: {content.pages}")
        print(f"Tables found: {len(content.tables)}")

        # Step 3: Format for LLM
        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_content = ContentExtractor.format_for_llm(
            content,
            tables_only=tables_only_mode
        )

        print(f"Table-only mode: {tables_only_mode}")
        print(f"Content length: {len(formatted_content)} chars")

        # Step 4: Extract pin data with LLM
        print("\nStep 3: Extracting pin data with LLM...")
        llm_client = LLMClient()

        pin_data = llm_client.extract_pin_data(
            formatted_content,
            tables_only_mode=tables_only_mode
        )

        print(f"\n✅ Extraction successful!")
        print(f"Component: {pin_data.component_name}")
        print(f"Extraction method: {pin_data.extraction_method}")

        # Handle both single-package and multi-package formats
        if pin_data.packages:
            packages_list = pin_data.packages
            print(f"Number of packages: {len(packages_list)}")

            for i, pkg_data in enumerate(packages_list, 1):
                print(f"\n{'=' * 80}")
                print(f"Package {i}: {pkg_data['type']}")
                print("=" * 80)

                pkg_type = pkg_data['type']
                pin_count = pkg_data['pin_count']
                pins = pkg_data['pins']

                print(f"Pin count: {pin_count}")
                print(f"Pins extracted: {len(pins)}")

                # Get package geometry parameters
                try:
                    params = get_schematic_parameters(pkg_type, pin_count)
                    print(f"\n✅ Package parameters found:")
                    print(f"  Package type: {params.package_type}")
                    print(f"  Body width: {params.body_width} mm")
                    print(f"  Body height: {params.body_height} mm")
                    print(f"  Pin pitch: {params.pin_pitch} mm")
                    print(f"  Pins per side: {params.pins_per_side}")
                    print(f"  Counter-clockwise: {params.counter_clockwise}")

                    # Calculate positions for all pins
                    print(f"\n📍 Calculating pin positions:")

                    # Sort pins by pin number to get correct indices
                    sorted_pins = sorted(pins, key=lambda p: p['number'])

                    for j, pin in enumerate(sorted_pins[:10], 1):  # Show first 10
                        pin_number = pin['number']
                        pin_index = j - 1  # 0-based index in sorted list

                        # Calculate position
                        x, y, side = calculate_pin_position(pin_index, params)

                        print(f"  Pin {pin_number:2d}: ({x:6.2f}, {y:6.2f}) {side:6s} - {pin['name']:8s}")

                    if len(sorted_pins) > 10:
                        print(f"  ... and {len(sorted_pins) - 10} more pins")

                except Exception as e:
                    print(f"\n❌ Error calculating positions: {e}")

        elif pin_data.package:
            # Legacy single-package format
            print(f"\nPackage: {pin_data.package.type}")
            print(f"Pin count: {pin_data.package.pin_count}")

            params = get_schematic_parameters(pin_data.package.type, pin_data.package.pin_count)

            print(f"\n📍 Calculating pin positions:")
            for i, pin in enumerate(pin_data.pins[:10], 1):
                x, y, side = calculate_pin_position(pin.number - 1, params)
                print(f"  Pin {pin.number:2d}: ({x:6.2f}, {y:6.2f}) {side:6s} - {pin.name}")

        # Test conversion to builder format
        print(f"\n{'=' * 80}")
        print("TESTING: Conversion to Builder Format")
        print("=" * 80)

        try:
            pkg_type, pin_count, component_name, pins_for_builder = pin_data_to_builder_format(pin_data)
            print(f"✅ Conversion successful!")
            print(f"Package type: {pkg_type}")
            print(f"Pin count: {pin_count}")
            print(f"Component name: {component_name}")
            print(f"Pins for builder: {len(pins_for_builder)}")

            print(f"\nFirst 5 pins for builder:")
            for pin in pins_for_builder[:5]:
                print(f"  {pin}")

        except Exception as e:
            print(f"❌ Conversion error: {e}")
            import traceback
            traceback.print_exc()

    finally:
        extractor.close()

if __name__ == "__main__":
    # Test with 74HC595 PDF
    test_pdf = "pdfs/74HC595_TI.pdf"

    if os.path.exists(test_pdf):
        test_pin_positions(test_pdf)
    else:
        print(f"❌ PDF not found: {test_pdf}")
        print(f"Available PDFs:")
        import glob
        for pdf in glob.glob("pdfs/*.pdf"):
            print(f"  - {pdf}")
