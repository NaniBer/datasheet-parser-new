#!/usr/bin/env python3
"""Test end-to-end: PDF → Pin extraction → Schematic generation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor.page_detector import PageDetector
from src.pdf_extractor.content_extractor import ContentExtractor
from src.llm.client import LLMClient
from src.schematic_generator import build_schematic_from_pin_data
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')


def extract_part_number(filename: str) -> str:
    """Extract part number from filename (e.g., 'STM32F103RBT7.PDF' -> 'STM32F103RBT7')."""
    import re
    # Try to match part number pattern (letters and numbers)
    match = re.match(r'([A-Za-z]+[0-9A-Za-z-]*)', filename)
    if match:
        return match.group(1)
    return None


def test_pdf_to_schematic(pdf_path: str, output_path: str) -> bool:
    """Test full pipeline: PDF → Pin extraction → Schematic → GLB."""
    print(f"\n{'='*60}")
    print(f"Testing: {os.path.basename(pdf_path)}")
    print(f"{'='*60}")
    
    # 1. Extract part number from filename
    part_number = extract_part_number(pdf_path)
    print(f"Part number: {part_number}")
    print()
    
    # 2. Detect relevant pages
    print("Step 1: Detecting relevant pages...")
    detector = PageDetector(pdf_path)
    candidates = detector.detect_relevant_pages(min_confidence=5)
    print(f"  Found {len(candidates)} relevant page(s)")
    for i, candidate in enumerate(candidates):
        print(f"    Page {i+1}: p.{candidate.page_number} (confidence: {candidate.confidence_score:.1f})")
    
    if not candidates:
        print("  No relevant pages found!")
        return False
    
    print()
    
    # 3. Extract content from relevant pages
    print("Step 2: Extracting content...")
    extractor = ContentExtractor(pdf_path)
    extracted = extractor.extract_content(candidates)

    print(f"  Extracted {len(extracted.pages)} pages")
    print(f"  Extracted {len(extracted.tables)} tables")
    print(f"  Extracted {len(extracted.images)} images")
    print()

    # 4. Extract pin data using LLM
    print("Step 3: Extracting pin data using LLM...")
    client = LLMClient()

    # Build prompt with content
    prompt_content = ""
    if extracted.text_content:
        # Limit text content to avoid overwhelming the LLM
        prompt_content = extracted.text_content[:5000] if len(extracted.text_content) > 5000 else extracted.text_content
        prompt_content += f"\n\nExtracted from pages: {extracted.pages}\n\n"
    
    if extracted.tables:
        for i, (page_num, table_data) in enumerate(extracted.tables[:5]):  # Limit tables
            # table_data is a list of rows, where each row is a list of cells
            if table_data and len(table_data) > 0:
                header = " | ".join(str(cell) for cell in table_data[0])
                table_str = f"| {header} |"
                for row in table_data[1:6]:  # Show up to 5 data rows
                    table_str += "\n| " + " | ".join(str(cell) for cell in row) + " |"
                prompt_content += f"--- Table {i+1} (Page {page_num}) ---\n{table_str}\n\n"
    
    if not prompt_content:
        prompt_content = "No text or tables extracted from PDF."
    
    # Add part number context
    if part_number:
        prompt_content += f"\nPart number: {part_number}"
    
    pin_data = client.extract_pin_data(
        content=prompt_content,
        images=extracted.images,
        part_number=part_number
    )
    
    if not pin_data:
        print("  Failed to extract pin data!")
        return False
    
    print(f"  Extracted: {pin_data.component_name}")
    print(f"  Package: {pin_data.package.type} ({pin_data.package.pin_count} pins)")
    print(f"  Pins: {len(pin_data.pins)} pins extracted")
    
    # Show first few pins
    print()
    print("First few pins:")
    for i, pin in enumerate(pin_data.pins[:8]):
        print(f"  Pin {i+1}: {pin.number} - {pin.name}")
    print()
    
    # 5. Build and save schematic using adapter
    print("Step 4: Building and saving schematic...")

    result = build_schematic_from_pin_data(
        pin_data=pin_data,
        output_path=output_path,
    )
    
    if result:
        size = os.path.getsize(output_path)
        print(f"  Success! Saved to: {output_path}")
        print(f"  GLB file size: {size} bytes")
        print()
        return True
    else:
        print("  Failed to generate schematic!")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("End-to-End Schematic Generation Test")
    print("=" * 60)
    
    # Test PDFs
    test_pdfs = [
        "pdfs/STM32F103RBT7.PDF",
        # "pdfs/NE555.PDF",
        # "pdfs/test.pdf",  # ATmega164A
        # "pdfs/pages.pdf",  # Multiple diagrams
    ]
    
    results = []
    for pdf_path in test_pdfs:
        if os.path.exists(pdf_path):
            # Create output path
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            output_path = f"output/{base_name}_schematic.glb"
            
            # Create output directory if needed
            os.makedirs("output", exist_ok=True)
            
            # Run test
            result = test_pdf_to_schematic(pdf_path, output_path)
            results.append(result)
        else:
            print(f"\n  Warning: PDF not found: {pdf_path}")
            results.append(False)
    
    print()
    print("=" * 60)
    print(f"Summary: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
