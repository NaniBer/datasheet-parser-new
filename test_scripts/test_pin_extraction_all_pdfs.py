"""
Comprehensive Pin Extraction Test - All PDFs
Tests pin extraction on all PDFs and compares with expected results.
"""

import sys
import os
import dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.page_detector import PageDetector
from src.pdf_extractor.content_extractor import ContentExtractor
from src.llm.client import LLMClient


# Expected results for each PDF
EXPECTED_RESULTS = {
    "pdfs/NE555.PDF": {
        "component_name": "NE555",
        "package_type": "DIP",
        "pin_count": 8,
        "expected_pins": [
            {"number": 1, "name": "GND"},
            {"number": 2, "name": "TRIG"},
            {"number": 3, "name": "OUTPUT"},
            {"number": 4, "name": "RESET"},
            {"number": 5, "name": "CV"},
            {"number": 6, "name": "THR"},
            {"number": 7, "name": "DISCH"},
            {"number": 8, "name": "VCC"},
        ]
    },
    "pdfs/MC74HC595A.PDF": {
        "component_name": "MC74HC595A",
        "package_type": "DIP",
        "pin_count": 16,
        "expected_pins": [
            {"number": 1, "name": "QB"},
            {"number": 2, "name": "QC"},
            {"number": 3, "name": "QD"},
            {"number": 4, "name": "QE"},
            {"number": 5, "name": "QF"},
            {"number": 6, "name": "QG"},
            {"number": 7, "name": "QH"},
            {"number": 8, "name": "GND"},
            {"number": 9, "name": "QH'"},
            {"number": 10, "name": "VCC"},
            {"number": 11, "name": "SRCLK"},
            {"number": 12, "name": "RCLK"},
            {"number": 13, "name": "SER"},
            {"number": 14, "name": "OE"},
            {"number": 15, "name": "MR"},
            {"number": 16, "name": "QA"},
        ]
    },
    "pdfs/74HC595_TI.pdf": {
        "component_name": "SN74HC595",
        "package_type": "SOIC",
        "pin_count": 16,
    },
    "pdfs/74HC595_SOIC16_Nexperia.pdf": {
        "component_name": "74HC595",
        "package_type": "SOIC",
        "pin_count": 16,
    },
    "pdfs/74HC00_SOIC14.pdf": {
        "component_name": "74HC00",
        "package_type": "SOIC",
        "pin_count": 14,
    },
    "pdfs/STM32F103RBT7.PDF": {
        "component_name": "STM32F103RBT7",
        "package_type": "LQFP",
        "pin_count": 64,
    },
    "pdfs/ATmega328P_TQFP32.pdf": {
        "component_name": "ATmega328P",
        "package_type": "TQFP",
        "pin_count": 32,
    },
    "pdfs/BGA_example.pdf": {
        "component_name": "BGA example",
        "package_type": "BGA",
        "pin_count": None,
    },
    "pdfs/esp32-c3_datasheet_en.pdf": {
        "component_name": "ESP32-C3",
        "package_type": "QFN",
        "pin_count": None,
    },
    "pdfs/pages.pdf": {
        "component_name": "ESP32-WROOM-32E",
        "package_type": "QFN",
        "pin_count": 38,
    },
    "pdfs/AMS1117.pdf": {
        "component_name": "AMS1117",
        "package_type": "SOT-223",
        "pin_count": 3,
    },
}


def print_separator(char="=", length=80):
    print(char * length)


def test_single_pdf(pdf_path, expected, api_key=None):
    """Test pin extraction on a single PDF."""
    print_separator()
    print(f"Testing: {pdf_path}")
    print_separator()

    # Expected info
    print("EXPECTED RESULTS:")
    print(f"  Component: {expected.get('component_name', 'Unknown')}")
    print(f"  Package:   {expected.get('package_type', 'Unknown')}")
    print(f"  Pin Count: {expected.get('pin_count', 'Unknown')}")
    if 'expected_pins' in expected:
        print(f"  Expected Pins:")
        for pin in expected['expected_pins']:
            print(f"    Pin {pin['number']:2d}: {pin['name']}")
    print()

    # Run extraction
    try:
        print("RUNNING EXTRACTION...")

        # Step 1: Page Detection
        page_detector = PageDetector(pdf_path)
        candidates = page_detector.detect_relevant_pages(min_confidence=5)
        print(f"  Pages detected: {len(candidates)}")
        if candidates:
            for i, candidate in enumerate(candidates[:3]):
                print(f"    Page {candidate.page_number}: confidence={candidate.confidence_score:.1f}")

        # Step 2: Content Extraction
        content_extractor = ContentExtractor(pdf_path)
        extracted_content = content_extractor.extract_content(candidates)
        print(f"  Text extracted: {len(extracted_content.text_content)} chars")
        print(f"  Tables extracted: {len(extracted_content.tables)}")

        # Step 3: LLM Extraction
        llm_client = LLMClient(api_key=api_key)
        pin_data = llm_client.extract_pin_data(
            content=extracted_content,
            part_number=expected.get('component_name', 'Unknown'),
            hint=f"Package type: {expected.get('package_type', 'Unknown')}"
        )

        # Results
        print_separator()
        print("ACTUAL RESULTS:")
        print(f"  Component: {pin_data.component_name}")
        print(f"  Package:   {pin_data.package.type}")
        print(f"  Pin Count: {pin_data.package.pin_count}")
        print(f"  Dimensions: {pin_data.package.width} x {pin_data.package.height} mm")
        print()
        print(f"  Extracted Pins ({len(pin_data.pins)}):")
        for pin in pin_data.pins[:30]:
            function_str = f" - {pin.function}" if pin.function else ""
            print(f"    Pin {pin.number:3d}: {pin.name:15s}{function_str}")
        if len(pin_data.pins) > 30:
            print(f"    ... and {len(pin_data.pins) - 30} more")

        # Comparison
        print_separator()
        print("COMPARISON:")

        # Pin count comparison
        expected_count = expected.get('pin_count')
        if expected_count:
            if pin_data.package.pin_count == expected_count:
                print(f"  ✅ Pin count matches: {expected_count}")
            else:
                print(f"  ⚠️  Pin count: expected {expected_count}, got {pin_data.package.pin_count}")

        # Package type comparison
        expected_pkg = expected.get('package_type', '').upper()
        actual_pkg = pin_data.package.type.upper()
        if expected_pkg and actual_pkg:
            if expected_pkg in actual_pkg or actual_pkg in expected_pkg:
                print(f"  ✅ Package matches: {actual_pkg}")
            else:
                print(f"  ⚠️  Package type: expected {expected_pkg}, got {actual_pkg}")

        # Pin name comparison (if available)
        if 'expected_pins' in expected:
            expected_pins_dict = {p['number']: p['name'] for p in expected['expected_pins']}
            actual_pins_dict = {p.number: p.name for p in pin_data.pins}

            matched = 0
            mismatched = 0
            missing = 0

            for pin_num, expected_name in expected_pins_dict.items():
                if pin_num in actual_pins_dict:
                    actual_name = actual_pins_dict[pin_num]
                    # Normalize for comparison (case-insensitive, ignore special chars)
                    exp_normalized = expected_name.upper().replace('-', '').replace('_', '')
                    act_normalized = actual_name.upper().replace('-', '').replace('_', '')
                    if exp_normalized == act_normalized or exp_normalized in act_normalized or act_normalized in exp_normalized:
                        matched += 1
                    else:
                        mismatched += 1
                        print(f"  ⚠️  Pin {pin_num}: expected '{expected_name}', got '{actual_name}'")
                else:
                    missing += 1
                    print(f"  ⚠️  Pin {pin_num}: expected '{expected_name}' not found")

            total = len(expected_pins_dict)
            if matched == total:
                print(f"  ✅ All {total} pin names match!")
            elif mismatched == 0 and missing == 0:
                print(f"  ✅ All {total} pins found (some names may differ)")
            else:
                print(f"  ⚠️  Pin name accuracy: {matched}/{total} matched, {mismatched} mismatched, {missing} missing")

        return pin_data

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("COMPREHENSIVE PIN EXTRACTION TEST - ALL PDFs")
    print_separator()

    dotenv.load_dotenv()
    api_key = os.getenv("FASTCHAT_API_KEY")

    if not api_key:
        print("❌ FASTCHAT_API_KEY not found in environment")
        return

    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Test selected PDFs
    pdfs_to_test = [
        "pdfs/NE555.PDF",                    # Simple, well-known
        "pdfs/MC74HC595A.PDF",              # Medium complexity
        "pdfs/74HC595_TI.pdf",              # SOIC variant
        "pdfs/STM32F103RBT7.PDF",          # Complex, many pins
        # "pdfs/ATmega328P_TQFP32.pdf",   # TQFP package - FILE CORRUPTED (HTML access denied)
        "pdfs/esp32-c3_datasheet_en.pdf",     # QFN package
    ]

    results = {}
    for pdf_path in pdfs_to_test:
        if not os.path.exists(pdf_path):
            print(f"⚠️  Skipping {pdf_path} - file not found")
            continue

        if pdf_path not in EXPECTED_RESULTS:
            print(f"⚠️  Skipping {pdf_path} - no expected results defined")
            continue

        expected = EXPECTED_RESULTS[pdf_path]
        pin_data = test_single_pdf(pdf_path, expected, api_key)
        results[pdf_path] = pin_data
        print("\n\n")

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    for pdf_path, pin_data in results.items():
        expected = EXPECTED_RESULTS[pdf_path]
        status = "✅" if pin_data else "❌"
        print(f"{status} {pdf_path}")
        if pin_data:
            print(f"   Component: {pin_data.component_name}")
            print(f"   Package: {pin_data.package.type}")
            print(f"   Pins: {pin_data.package.pin_count}")


if __name__ == "__main__":
    main()
