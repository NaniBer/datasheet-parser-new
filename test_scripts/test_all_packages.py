#!/usr/bin/env python3
"""
Test script for all valid PDFs - generates both 3D schematic and 2D PCB outputs.
Validates pin extraction and provides comprehensive results.
"""

import sys
import os
from pathlib import Path
import json
import pypdf

# Add src to path (need parent directory since we're in test_scripts)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.llm import LLMClient
from src.llm.image_ocr_client import ImageOCRClient
from src.schematic_generator import build_schematic_from_pin_data, build_pcb_2d_schematic
from src.utils import PackageDetector
from src.models import PinData, Pin, PackageInfo
from src.exceptions import ValidationError, APICredentialsError

# Test configuration
TEST_PDFS = [
    {
        'file': 'pdfs/74HC595_TI.pdf',
        'name': '74HC595',
        'expected_package': 'SOIC',
        'expected_pin_count': 16,
        'description': '74HC595 shift register',
        'key_pins': ['1', '8', '9', '16']  # VSS, GND, Q7S, VCC
    },
    {
        'file': 'pdfs/AMS1117.pdf',
        'name': 'AMS1117',
        'expected_package': 'SOT',
        'expected_pin_count': 3,
        'description': 'AMS1117 voltage regulator',
        'key_pins': ['1', '2', '3']  # GND, OUTPUT, INPUT
    },
    {
        'file': 'pdfs/DFN.pdf',
        'name': 'DFN-Various',
        'expected_package': 'DFN',
        'expected_pin_count': None,  # Unknown - will skip validation
        'description': 'Various DFN packages',
        'key_pins': []
    },
    {
        'file': 'pdfs/MAX1487-MAX491.pdf',
        'name': 'MAX1487/MAX491',
        'expected_package': None,  # Unknown
        'expected_pin_count': 8,  # Typical RS-485 transceiver
        'description': 'RS-485 transceivers',
        'key_pins': []
    },
    {
        'file': 'pdfs/MPU-6000-Datasheet1.pdf',
        'name': 'MPU-6000',
        'expected_package': 'QFN',
        'expected_pin_count': 24,
        'description': 'MPU-6000 6-axis motion tracking',
        'key_pins': ['1', '12', '18', '24']
    },
    {
        'file': 'pdfs/TSSOP.pdf',
        'name': 'TSSOP-Various',
        'expected_package': 'TSSOP',
        'expected_pin_count': None,
        'description': 'Various TSSOP packages',
        'key_pins': []
    },
    {
        'file': 'pdfs/TVS-Diode-SMBJ-Datasheet.pdf',
        'name': 'SMBJ-TVS',
        'expected_package': 'SMB',
        'expected_pin_count': 2,  # Diode
        'description': 'TVS diodes SMBJ series',
        'key_pins': []
    },
    {
        'file': 'pdfs/esp32-c3_datasheet_en.pdf',
        'name': 'ESP32-C3',
        'expected_package': 'QFN',
        'expected_pin_count': 32,
        'description': 'ESP32-C3 Wi-Fi/Bluetooth',
        'key_pins': ['1', '16', '17', '32']
    },
    {
        'file': 'pdfs/test.pdf',
        'name': 'ATmega164A',
        'expected_package': 'PDIP',
        'expected_pin_count': 40,
        'description': 'ATmega164A microcontroller (PDIP variant)',
        'key_pins': ['1', '20', '21', '40']
    },
]

# Expected results tracking
results = []

def print_header(text):
    print('\n' + '=' * 80)
    print(text)
    print('=' * 80)

def process_pdf(test_info, api_key, verbose=True):
    """Process a single PDF and generate both 3D and 2D schematics."""

    pdf_file = test_info['file']
    component_name = test_info['name']

    if verbose:
        print_header(f'Processing: {pdf_file}')
        print(f'Component: {component_name}')
        print(f'Description: {test_info["description"]}')
        print(f'Expected package: {test_info["expected_package"]}')
        print(f'Expected pin count: {test_info["expected_pin_count"]}')

    result = {
        'pdf': pdf_file,
        'component': component_name,
        'expected_package': test_info['expected_package'],
        'expected_pin_count': test_info['expected_pin_count'],
        'status': 'failed',
        'error': None,
        'extracted_package': None,
        'extracted_pin_count': 0,
        'pin_names': {},
        '3d_file': None,
        '2d_file': None,
        '3d_size': 0,
        '2d_size': 0,
        '3d_nodes': 0,
        '2d_nodes': 0
    }

    try:
        # Step 1: Detect relevant pages
        if verbose:
            print(f'\n[1/7] Detecting relevant pages...')

        with PageDetector(pdf_file) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=5)

        if not candidates:
            result['error'] = 'No relevant pages detected'
            return result

        if verbose:
            print(f'  Found {len(candidates)} relevant pages')

        # Step 2: Extract content
        if verbose:
            print(f'\n[2/7] Extracting content...')

        with ContentExtractor(pdf_file) as extractor:
            content = extractor.extract_content(candidates)

        # Step 3: Extract pin data with LLM
        if verbose:
            print(f'\n[3/7] Extracting pin data with LLM...')

        llm_client = LLMClient(api_key=api_key, model='llama-3')
        pin_data = llm_client.extract_pin_data(content=content.text_content)

        result['extracted_package'] = pin_data.package.type
        result['extracted_pin_count'] = len(pin_data.pins)

        # Record pin names for key pins
        for pin in pin_data.pins:
            if str(pin.number) in test_info['key_pins']:
                result['pin_names'][str(pin.number)] = pin.name

        if verbose:
            print(f'  Component: {pin_data.component_name}')
            print(f'  Package: {pin_data.package.type}')
            print(f'  Pin count: {len(pin_data.pins)}')

            # Show key pins
            if test_info['key_pins']:
                print(f'  Key pins:')
                for pin_num in test_info['key_pins']:
                    pin = next((p for p in pin_data.pins if str(p.number) == pin_num), None)
                    if pin:
                        print(f'    Pin {pin_num}: {pin.name}')

        # Validate pin count if expected is set
        if test_info['expected_pin_count']:
            if len(pin_data.pins) != test_info['expected_pin_count']:
                result['error'] = f'Pin count mismatch: expected {test_info["expected_pin_count"]}, got {len(pin_data.pins)}'
                if verbose:
                    print(f'  ⚠️  {result["error"]}')
            elif verbose:
                print(f'  ✓ Pin count matches expected')

        # Step 4: Validate and normalize package
        if verbose:
            print(f'\n[4/7] Validating package...')

        detector = PackageDetector()
        normalized_pkg = detector.normalize_package_name(pin_data.package.type)
        pin_data.package.type = normalized_pkg

        if verbose:
            print(f'  Normalized package: {normalized_pkg}')

        # Step 5: Generate 3D schematic
        if verbose:
            print(f'\n[5/7] Generating 3D schematic...')

        output_3d = f'output/{component_name}_3d.glb'

        success_3d = build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=output_3d
        )

        if success_3d and os.path.exists(output_3d):
            result['3d_file'] = output_3d
            result['3d_size'] = os.path.getsize(output_3d)
            result['status'] = 'partial'

            # Count nodes in 3D file
            try:
                import struct
                with open(output_3d, 'rb') as f:
                    f.read(12)  # Skip header
                    json_length = struct.unpack('<I', f.read(4))[0]
                    f.read(4)  # Skip json_type
                    json_data = f.read(json_length)
                    gltf_data = json.loads(json_data.decode('utf-8'))
                    result['3d_nodes'] = len(gltf_data.get('nodes', []))
            except:
                pass

            if verbose:
                print(f'  ✓ Generated: {output_3d}')
                print(f'  Size: {result["3d_size"]:,} bytes')
                print(f'  Nodes: {result["3d_nodes"]}')
        else:
            result['error'] = 'Failed to generate 3D schematic'
            if verbose:
                print(f'  ✗ Failed to generate 3D schematic')

        # Step 6: Generate 2D PCB schematic
        if verbose:
            print(f'\n[6/7] Generating 2D PCB schematic...')

        output_2d = f'output/{component_name}_2d.glb'

        success_2d = build_pcb_2d_schematic(
            package_type=pin_data.package.type,
            pin_count=pin_data.package.pin_count,
            component_name=pin_data.component_name,
            pin_data=[{"number": p.number, "name": p.name} for p in pin_data.pins],
            output_path=output_2d
        )

        if success_2d and os.path.exists(output_2d):
            result['2d_file'] = output_2d
            result['2d_size'] = os.path.getsize(output_2d)
            result['status'] = 'success'

            # Count nodes in 2D file
            try:
                import struct
                with open(output_2d, 'rb') as f:
                    f.read(12)  # Skip header
                    json_length = struct.unpack('<I', f.read(4))[0]
                    f.read(4)  # Skip json_type
                    json_data = f.read(json_length)
                    gltf_data = json.loads(json_data.decode('utf-8'))
                    result['2d_nodes'] = len(gltf_data.get('nodes', []))
            except:
                pass

            if verbose:
                print(f'  ✓ Generated: {output_2d}')
                print(f'  Size: {result["2d_size"]:,} bytes')
                print(f'  Nodes: {result["2d_nodes"]}')
        else:
            if verbose:
                print(f'  ✗ Failed to generate 2D PCB schematic')

        # Step 7: Final status
        if verbose:
            print(f'\n[7/7] Status: {result["status"].upper()}')

    except Exception as e:
        result['error'] = str(e)
        if verbose:
            print(f'\n✗ Error: {e}')
            import traceback
            traceback.print_exc()

    return result

def main():
    """Main test function."""

    print_header('COMPREHENSIVE PDF TEST - ALL PACKAGES')
    print(f'Testing {len(TEST_PDFS)} PDF files')
    print('Generating both 3D schematic and 2D PCB outputs')

    # Get API key
    api_key = os.environ.get('DATASHEET_PARSER_API_KEY') or os.environ.get('FASTCHAT_API_KEY')
    if not api_key:
        print('\n✗ API key required!')
        print('Set DATASHEET_PARSER_API_KEY or FASTCHAT_API_KEY environment variable')
        sys.exit(1)

    # Process each PDF
    for i, test_info in enumerate(TEST_PDFS, 1):
        print(f'\n\n{"=" * 80}')
        print(f'TEST {i}/{len(TEST_PDFS)}: {test_info["name"]}')
        print(f'{"=" * 80}')

        result = process_pdf(test_info, api_key, verbose=True)
        results.append(result)

        # Show intermediate summary
        print(f'\n--- INTERMEDIATE SUMMARY ---')
        successful = sum(1 for r in results if r['status'] == 'success')
        partial = sum(1 for r in results if r['status'] == 'partial')
        failed = sum(1 for r in results if r['status'] == 'failed')
        print(f'Success: {successful} | Partial: {partial} | Failed: {failed}')

    # Final summary
    print_header('FINAL SUMMARY')

    print('\nDetailed Results:')
    print('-' * 80)

    for result in results:
        status_icon = '✅' if result['status'] == 'success' else ('⚠️' if result['status'] == 'partial' else '❌')
        print(f'{status_icon} {result["component"]:20} | {result["extracted_package"] or "N/A":10} | {result["extracted_pin_count"]:3} pins | {result["status"]:10}')

    print('\nStatistics:')
    print('-' * 80)

    successful = [r for r in results if r['status'] == 'success']
    partial = [r for r in results if r['status'] == 'partial']
    failed = [r for r in results if r['status'] == 'failed']

    print(f'Total tests: {len(results)}')
    print(f'Successful: {len(successful)}')
    print(f'Partial (3D only): {len(partial)}')
    print(f'Failed: {len(failed)}')

    if successful:
        print(f'\nAverage file sizes:')
        avg_3d = sum(r['3d_size'] for r in successful) / len(successful)
        avg_2d = sum(r['2d_size'] for r in successful) / len(successful)
        avg_3d_nodes = sum(r['3d_nodes'] for r in successful) / len(successful)
        avg_2d_nodes = sum(r['2d_nodes'] for r in successful) / len(successful)

        print(f'  3D: {avg_3d:,.0f} bytes ({avg_3d_nodes:.0f} nodes)')
        print(f'  2D: {avg_2d:,.0f} bytes ({avg_2d_nodes:.0f} nodes)')

    # Pin extraction validation
    print('\nPin Extraction Validation:')
    print('-' * 80)

    for result in results:
        if result['expected_pin_count'] and result['extracted_pin_count']:
            match = '✅' if result['extracted_pin_count'] == result['expected_pin_count'] else '❌'
            print(f'{match} {result["component"]:20} | Expected: {result["expected_pin_count"]:3} | Got: {result["extracted_pin_count"]:3}')

    # Show errors for failed tests
    if failed:
        print('\nFailed Tests:')
        print('-' * 80)
        for result in failed:
            print(f'❌ {result["component"]}: {result["error"]}')

    print_header('TEST COMPLETE')
    print(f'Output files saved in: output/')

if __name__ == '__main__':
    main()
