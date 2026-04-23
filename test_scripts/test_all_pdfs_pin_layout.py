#!/usr/bin/env python3
import sys
import os

# Set up Java environment (do this once at the start)
os.environ['JAVA_HOME'] = '/opt/homebrew/opt/openjdk@17'
new_path = '/opt/homebrew/opt/openjdk@17/bin:' + os.environ.get('PATH', '')
os.environ['PATH'] = new_path

# Add parent directory to path to import src
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm import LLMClient
from src.schematic_generator.pin_layout import PinLayout, layout_pins
from src.schematic_generator.schematic_builder import SchematicBuilder
from src.models import PinData

def test_pin_extraction_and_layout(pdf_path, model="llama-3"):
    """Test pin extraction and layout generation for a single PDF."""
    print(f"\n{'='*60}")
    print(f"Testing: {os.path.basename(pdf_path)}")
    print(f"{'='*60}")

    results = {
        'pdf_path': pdf_path,
        'pdf_name': os.path.basename(pdf_path),
        'success': False,
        'error': None,
        'packages_tested': [],
        'total_variants': 0,
        'successful_variants': 0,
        'failed_variants': 0,
        'extraction_time': None,
        'llm_time': None
    }

    import time
    start_time = time.time()

    try:
        # Step 1: Detect relevant pages
        print(f"Step 1: Detecting relevant pages...")
        page_detect_start = time.time()
        with PageDetector(pdf_path) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=2)  # Lower threshold for simple components
        page_detect_time = time.time() - page_detect_start

        if not candidates:
            print("  ❌ No relevant pages found")
            results['error'] = "No relevant pages found"
            return results

        print(f"  ✓ Found {len(candidates)} relevant page(s) in {page_detect_time:.1f}s")

        # Step 2: Extract content
        print(f"Step 2: Extracting content...")
        extract_start = time.time()
        with ContentExtractor(pdf_path) as extractor:
            content = extractor.extract_content(candidates)
        extract_time = time.time() - extract_start

        print(f"  ✓ Extracted {len(content.pages)} pages with {len(content.tables)} table(s) in {extract_time:.1f}s")

        # If no tables found, check if we have text content for LLM extraction
        if not content.tables:
            print("  ⚠️  No tables found, will try text-based extraction")
            if not content.text_content or len(content.text_content.strip()) < 100:
                print("  ❌ Insufficient text content for extraction")
                results['error'] = "No tables and insufficient text content"
                return results
            print("  ✓ Using text content for LLM extraction")

        # Step 3: Extract pin data with LLM
        print(f"Step 3: Extracting pin data with LLM...")
        llm_start = time.time()

        llm_client = LLMClient(model=model)

        # Use table-only mode if we have tables
        tables_only_mode = len(content.tables) > 0 and len(content.images) == 0
        formatted_content = ContentExtractor.format_for_llm(content, tables_only=tables_only_mode)

        print(f"  Sending {len(formatted_content)} chars to LLM...")
        pin_data = llm_client.extract_pin_data(
            content=formatted_content,
            tables_only_mode=tables_only_mode
        )

        llm_time = time.time() - llm_start
        results['llm_time'] = llm_time
        print(f"  ✓ LLM extraction completed in {llm_time:.1f}s")

        # Handle both multi-package format (new) and single-package format (legacy)
        packages_list = []
        if hasattr(pin_data, 'packages') and pin_data.packages:
            # Multi-package format (e.g., from table extraction)
            packages_list = pin_data.packages
            print(f"  ✓ Found {len(packages_list)} package variant(s) (multi-package format)")
        elif hasattr(pin_data, 'package') and pin_data.package:
            # Single-package format (legacy, e.g., from diagram extraction)
            pkg = pin_data.package
            packages_list = [{
                'type': pkg.type,
                'pin_count': pkg.pin_count,
                'width': pkg.width,
                'height': pkg.height,
                'pitch': pkg.pitch,
                'pins': [
                    {
                        'number': p.number,
                        'name': p.name,
                        'function': p.function
                    } for p in pin_data.pins
                ]
            }]
            print(f"  ✓ Found 1 package variant (single-package format)")
        else:
            print("  ❌ No packages found in extracted data")
            results['error'] = "No packages extracted"
            return results

        results['total_variants'] = len(packages_list)

        # Test each variant
        for i, package in enumerate(packages_list, 1):
            pkg_type = package.get('type', 'Unknown')
            pkg_pin_count = package.get('pin_count', 0)
            pkg_pins = package.get('pins', [])

            print(f"\n  Variant {i}/{len(packages_list)}: {pkg_type}")
            package_result = {
                'package_type': pkg_type,
                'pin_count': pkg_pin_count,
                'pins': len(pkg_pins) if pkg_pins else 0,
                'success': False,
                'error': None,
                'pin_layout_created': False,
                'schematic_builder_created': False
            }

            try:
                # Test pin count
                print(f"    Pin count: {pkg_pin_count}")
                print(f"    Extracted pins: {len(pkg_pins) if pkg_pins else 0}")
                
                # Show sample pins
                if pkg_pins and len(pkg_pins) > 0:
                    print(f"    Sample pins:")
                    for pin in pkg_pins[:5]:
                        pin_num = pin.get('number', pin.get('pin_num', '?'))
                        pin_name = pin.get('name', pin.get('pin_name', '?'))
                        pin_func = pin.get('function', '')
                        print(f"      Pin {pin_num}: {pin_name} ({pin_func})")

                # Test SchematicBuilder creation
                print(f"    Testing SchematicBuilder creation...")
                try:
                    builder = SchematicBuilder(pkg_type, pkg_pin_count)
                    print(f"      ✓ SchematicBuilder created successfully")
                    package_result['schematic_builder_created'] = True

                    # Test pin layout from builder
                    print(f"    Testing pin layout from SchematicBuilder...")
                    pin_layout = PinLayout(builder.params)
                    print(f"      ✓ PinLayout created successfully")
                    package_result['pin_layout_created'] = True

                    # Get pin positions
                    print(f"    Testing pin position calculation...")
                    positions = pin_layout.layout_all_pins()

                    if not positions:
                        print(f"      ⚠ No pin positions returned")
                        package_result['error'] = "No pin positions generated"
                    else:
                        print(f"      ✓ Generated {len(positions)} pin positions")

                        # Check a few positions
                        sample_pins = positions[:min(5, len(positions))]
                        print(f"      Sample pins:")
                        for pos in sample_pins:
                            print(f"        Pin {pos.pin_number}: ({pos.x:.2f}, {pos.y:.2f}) {pos.side}")

                except Exception as e:
                    print(f"      ⚠ SchematicBuilder failed: {e}")
                    package_result['error'] = f"SchematicBuilder error: {e}"

                package_result['success'] = True
                results['successful_variants'] += 1
                print(f"    ✓ All tests passed for this variant")

            except Exception as e:
                print(f"    ❌ Variant failed: {e}")
                package_result['error'] = str(e)
                results['failed_variants'] += 1

            results['packages_tested'].append(package_result)

        results['success'] = results['successful_variants'] > 0
        total_time = time.time() - start_time
        print(f"\n  ✓ Total processing time: {total_time:.1f}s")

    except Exception as e:
        print(f"  ❌ Failed to process PDF: {e}")
        import traceback
        traceback.print_exc()
        results['error'] = str(e)

    return results

def generate_report(results_list):
    """Generate a summary report from test results."""
    print(f"\n{'='*80}")
    print(f"PIN EXTRACTION AND LAYOUT TEST REPORT")
    print(f"{'='*80}\n")

    total_pdfs = len(results_list)
    successful_pdfs = sum(1 for r in results_list if r['success'])
    failed_pdfs = total_pdfs - successful_pdfs

    total_variants = sum(r['total_variants'] for r in results_list)
    total_successful_variants = sum(r['successful_variants'] for r in results_list)
    total_failed_variants = sum(r['failed_variants'] for r in results_list)

    print(f"SUMMARY")
    print(f"{'-'*80}")
    print(f"Total PDFs tested:        {total_pdfs}")
    print(f"Successful PDFs:          {successful_pdfs}")
    print(f"Failed PDFs:              {failed_pdfs}")
    print(f"")
    print(f"Total package variants:    {total_variants}")
    print(f"Successful variants:      {total_successful_variants}")
    print(f"Failed variants:          {total_failed_variants}")
    print(f"")

    if failed_pdfs > 0:
        print(f"FAILED PDFS:")
        print(f"{'-'*80}")
        for result in results_list:
            if not result['success']:
                print(f"  ❌ {result['pdf_name']}")
                print(f"     Error: {result['error']}")
        print(f"")

    if total_failed_variants > 0:
        print(f"FAILED VARIANTS:")
        print(f"{'-'*80}")
        for result in results_list:
            for pkg in result['packages_tested']:
                if not pkg['success']:
                    print(f"  ❌ {result['pdf_name']} - {pkg['package_type']}")
                    print(f"     Error: {pkg['error']}")
        print(f"")

    print(f"DETAILED RESULTS:")
    print(f"{'='*80}")
    for result in results_list:
        status = "✓" if result['success'] else "❌"
        print(f"\n{status} {result['pdf_name']}")
        print(f"  Total variants: {result['total_variants']}")
        print(f"  Successful: {result['successful_variants']}")
        print(f"  Failed: {result['failed_variants']}")

        for pkg in result['packages_tested']:
            pkg_status = "✓" if pkg['success'] else "❌"
            print(f"    {pkg_status} {pkg['package_type']} (pins: {pkg['pin_count']})")
            if pkg['error']:
                print(f"       Error: {pkg['error']}")

    print(f"\n{'='*80}")
    print(f"END OF REPORT")
    print(f"{'='*80}\n")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test pin extraction and layout on PDFs")
    parser.add_argument("--pdf-dir", default="pdfs", help="Directory containing PDF files")
    parser.add_argument("--model", default="llama-3", help="LLM model to use")
    parser.add_argument("--pdf", help="Specific PDF file to test (otherwise lists all PDFs)")
    parser.add_argument("--all", action="store_true", help="Test all PDFs in the directory")

    args = parser.parse_args()

    # Find all PDFs
    import glob
    pdf_files = sorted(glob.glob(os.path.join(args.pdf_dir, "*.pdf")))

    if not pdf_files:
        print(f"No PDF files found in {args.pdf_dir}")
        return

    # Handle specific PDF or list all
    if args.pdf:
        # Test specific PDF
        pdf_path = os.path.join(args.pdf_dir, args.pdf)
        if not os.path.exists(pdf_path):
            print(f"❌ PDF not found: {pdf_path}")
            return
        print(f"Testing single PDF: {args.pdf}")
        result = test_pin_extraction_and_layout(pdf_path, model=args.model)
        generate_report([result])
    elif args.all:
        # Test all PDFs
        print(f"Found {len(pdf_files)} PDF files to test")
        print(f"Testing pin extraction and layout generation for each PDF...")

        # Run tests on all PDFs
        all_results = []
        for i, pdf_path in enumerate(pdf_files, 1):
            print(f"\n\n[{i}/{len(pdf_files)}] Processing...")
            result = test_pin_extraction_and_layout(pdf_path, model=args.model)
            all_results.append(result)

        # Generate report
        generate_report(all_results)
    else:
        # List available PDFs and prompt
        print("Available PDF files:")
        for i, pdf_file in enumerate(pdf_files, 1):
            print(f"  {i}. {os.path.basename(pdf_file)}")
        print("\nTo test a specific PDF, run:")
        print(f"  python3 {sys.argv[0]} --pdf <filename>")
        print("\nTo test all PDFs, run:")
        print(f"  python3 {sys.argv[0]} --all")
        print("\nExample:")
        print(f"  python3 {sys.argv[0]} --pdf 74HC595_TI.pdf")

if __name__ == "__main__":
    main()
