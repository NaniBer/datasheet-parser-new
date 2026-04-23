#!/usr/bin/env python3
"""Test full end-to-end workflow: PDF extraction → 3D model generation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm.client import LLMClient
from src.schematic_generator.adapter import build_schematic_from_pin_data

def has_package_definition(package_type_str: str) -> tuple[bool, str]:
    """
    Check if we have a package definition for the returned package type.

    Args:
        package_type_str: Package type string from LLM (e.g., "SOIC-16", "LCCC-20")

    Returns:
        (has_definition, standardized_name) where:
        - has_definition: True if we have parameters for this package
        - standardized_name: The standardized package type name
    """
    # Clean up the package string
    pkg_str = package_type_str.upper().strip()

    # Remove pin count from package type (e.g., "SOIC-16" -> "SOIC")
    # Split on numbers/dashes
    import re
    pkg_base = re.sub(r'[-_].*\d+', '', pkg_str).strip()

    # Supported package types
    supported_types = {
        "DIP", "PDIP", "CDIP",
        "SOIC", "SOP", "SSOP", "TSOP",
        "TQFP", "LQFP", "QFP",
        "QFN", "DFN",
        "BGA", "LGA", "LCCC",
    }

    # Map aliases to standard types
    for alias, std_type in [
        ("LCCC", "LCCC"),
        ("LGA", "LCCC"),
        ("CDIP", "CDIP"),
    ]:
        if pkg_base == alias or pkg_str.startswith(alias):
            return (True, std_type)

    # Try direct match
    for supported_type in supported_types:
        if pkg_base == supported_type or pkg_str.startswith(supported_type):
            return (True, pkg_base)

    # Not found in supported list
    return (False, pkg_str)

def test_full_workflow(pdf_path: str, output_path: str):
    """Test complete workflow from PDF to 3D model."""

    print("=" * 80)
    print("Full End-to-End Workflow Test")
    print(f"PDF: {os.path.basename(pdf_path)}")
    print(f"Output: {output_path}")
    print("=" * 80)

    # Step 1: Detect relevant pages
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
        print(f"Images found: {len(content.images)}")

        # Step 3: Format for LLM
        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_content = ContentExtractor.format_for_llm(
            content,
            tables_only=tables_only_mode
        )

        print(f"Table-only mode: {tables_only_mode}")

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

        # Step 5: Validate packages
        print("\nStep 4: Validating package types...")
        if pin_data.packages:
            packages_list = pin_data.packages
            print(f"Number of packages: {len(packages_list)}")

            for pkg_data in packages_list:
                pkg_type = pkg_data['type']
                has_def, std_name = has_package_definition(pkg_type)

                status = "✅" if has_def else "⚠️"
                print(f"  {pkg_type}: {status} ({std_name})")

        # Step 6: Generate 3D model
        print("\nStep 5: Generating 3D schematic...")
        success = build_schematic_from_pin_data(
            pin_data,
            output_path
        )

        if success:
            print(f"\n✅ 3D model generated successfully!")
            print(f"Output saved to: {output_path}")
        else:
            print(f"\n❌ Failed to generate 3D model")

        # Step 7: Summary
        print("\n" + "=" * 80)
        print("WORKFLOW SUMMARY")
        print("=" * 80)

        if pin_data.packages:
            for i, pkg_data in enumerate(pin_data.packages, 1):
                print(f"\nPackage {i}: {pkg_data['type']}")
                print(f"  Pin count: {pkg_data['pin_count']}")
                print(f"  Pins extracted: {len(pkg_data['pins'])}")
        else:
            print(f"\nPackage: {pin_data.package.type}")
            print(f"Pin count: {pin_data.package.pin_count}")
            print(f"Pins extracted: {len(pin_data.pins)}")

        print(f"\nExtraction method: {pin_data.extraction_method}")
        print(f"Success: {'✅' if success else '❌'}")

    finally:
        extractor.close()

if __name__ == "__main__":
    # Test with 74HC595 PDF
    test_pdf = "pdfs/74HC595_TI.pdf"
    output_file = "output/test_74hc595_full_workflow.glb"

    if os.path.exists(test_pdf):
        test_full_workflow(test_pdf, output_file)
    else:
        print(f"❌ PDF not found: {test_pdf}")
        print(f"\nAvailable PDFs:")
        import glob
        for pdf in glob.glob("pdfs/*.pdf"):
            print(f"  - {pdf}")
