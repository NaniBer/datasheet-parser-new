#!/usr/bin/env python3
"""
Datasheet Parser CLI - Integrated with Layout Mode

Extract pin data from electronic component datasheets and generate schematic symbols.
NEW: Supports --layout-mode for Vision API layout extraction.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# Import project modules
from .pdf_extractor import PageDetector, ContentExtractor
from .llm import LLMClient
from .llm.image_ocr_client import ImageOCRClient
from .schematic_generator import build_schematic_from_pin_data
from .utils import PackageDetector
from .models import PinData, Pin, PackageInfo
import io
import pdfplumber
import requests
import re


def parse_layout_text(layout_text: str) -> dict:
    """
    Parse Vision API layout text response into structured format.

    Args:
        layout_text: Text response from Vision API

    Returns:
        Dict with structured layout information
    """
    result = {
        "package_type": "Unknown",
        "pin_count": 0,
        "sections": {}
    }

    # Extract package type
    pkg_patterns = {
        r"DIP": ["DIP", "Dual Inline"],
        r"QFN": ["QFN", "Quad Flat"],
        r"TQFP": ["TQFP", "Thin Quad Flat"],
        r"LQFP": ["LQFP", "Low-profile Quad Flat"],
        r"BGA": ["BGA", "Ball Grid Array"],
        r"SOIC": ["SOIC", "Small Outline"],
        r"Grid": ["Grid", "Column", "Layout"]
    }

    layout_lower = layout_text.lower()

    for pkg_type, keywords in pkg_patterns.items():
        for keyword in keywords:
            if keyword in layout_lower:
                result["package_type"] = pkg_type
                break
        if result["package_type"] != "Unknown":
            break

    # Extract pin count
    pin_count_match = re.search(r'pin count(?:\s+)?(?:\s+)?(\d+)', layout_lower)
    if pin_count_match:
        try:
            result["pin_count"] = int(pin_count_match.group(1))
        except:
            pass

    # Extract sections
    section_pattern = r'([A-Z][A-Za-z\s]*\s*\d+(?:\s+)?\d+\s*])'
    section_pattern2 = r'([A-Za-z]+\s*[A-Za-z]+\s*\d+(?:\s+)?\d+\s*:)'

    all_sections = re.findall(section_pattern, layout_text)

    # Try alternate pattern for sections
    if not all_sections:
        all_sections = re.findall(section_pattern2, layout_text)

    for section_str in all_sections:
        # Extract section name and pin numbers
        # Pattern: "Left Side: 1,2,3" or "Top: 1-10"
        if ":" in section_str:
            parts = section_str.split(":", 1)
            if len(parts) == 2:
                section_name = parts[0].strip()
                pins_str = parts[1].strip()

                # Extract pin numbers
                # Handle various formats: "1,2,3" or "1-10" or "Pin 1, Pin 2"
                numbers = []

                # Try to extract numbers
                num_matches = re.findall(r'\d+', pins_str)
                for num_str in num_matches:
                    try:
                        num = int(num_str.strip())
                        if num not in numbers:
                            numbers.append(num)
                    except:
                        pass

                if numbers:
                    result["sections"][section_name] = {
                        "pins": numbers,
                        "count": len(numbers)
                    }

    return result


def extract_layout_with_vision(pdf_path: str, page_num: int, verbose: bool = False) -> Optional[str]:
    """
    Extract layout structure using Vision API.

    Args:
        pdf_path: Path to PDF
        page_num: Page number with pinout diagram
        verbose: Enable verbose output

    Returns:
        Layout text description or None if failed
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num < 1 or page_num > len(pdf.pages):
                print(f"Error: Page {page_num} does not exist")
                return None

            page = pdf.pages[page_num - 1]

            # Convert page to image
            pil_image = page.to_image()
            img_bytes = io.BytesIO()
            pil_image.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            img_data = img_bytes.getvalue()

        # Vision API prompt for layout - FORCE it to find pin positions
        vision_prompt = """You are analyzing an electronic component pinout diagram image.

## CRITICAL TASK
Extract the COMPLETE PIN LAYOUT from this image. Look CAREFULLY at the diagram.

## WHAT TO EXTRACT

1. **Package Type**: What type of package is this? (DIP, TQFP, QFN, BGA, QFN, Grid, Module, etc.)

2. **Pin Count**: How many total pins does this package have?

3. **Pin Arrangement by Section**:
   For EACH visible section of the diagram (Top, Bottom, Left, Right, Center, or Columns):
   - Section name (e.g., "Top Side", "Bottom Side", "Left Column 1", "Right Side", "Center")
   - Pin numbers in this section (e.g., "1,2,3,4,5,6,7,8" or "1,2,3" etc.)
   - Direction/pattern (e.g., "left to right", "top to bottom", "clockwise", "counter-clockwise")

4. **Pin 1 Location**: Where is Pin 1 located? (top-left corner, other corner, etc.)

## EXACTION INSTRUCTIONS

1. Look for PIN NUMBERS labeled on the diagram (e.g., "1", "2", "3", or "A1", "B1", "1", "2")
2. List ALL pins by section in the order they appear
3. Don't miss any pins - count them carefully
4. Be specific about which section each pin belongs to

## OUTPUT FORMAT

Return ONLY a text description:

```
Package Type: [Type]
Pin Count: [Total]
Pin 1 Location: [Location]

[Section Name]: [Pin Numbers]
[Section Name]: [Pin Numbers]
...
```

EXAMPLE for 3-side grid layout:
```
Package Type: Grid
Pin Count: 38
Pin 1 Location: Top-left corner

Left Side Column 1: 1,2,3,4,5,6,7,8,9,10,11,12,13,14
Bottom Edge: 15,16,17,18,20,21,22,23
Right Side Column 2: 25,26,27,28,29,31,32,34,35,37
```

CRITICAL:
- Extract ALL pins visible in the diagram
- List pins by section
- Don't skip any pins
- Return ONLY text (no JSON, no markdown)
"""

        if verbose:
            print(f"  Sending page {page_num} to Vision API for layout extraction...")

        vision_client = ImageOCRClient(
            api_url="https://qwen.ideeza.com/describe_image/",
            output_token=2048,
            timeout=120
        )

        files = {"file": (f"page_{page_num}.png", img_data, "image/png")}
        data = {"text": vision_prompt, "output_token": "2048"}

        response = requests.post(
            vision_client.api_url,
            headers={"accept": "application/json"},
            files=files,
            data=data,
            timeout=120
        )

        if verbose:
            print(f"  Vision API returned (status: {response.status_code})")

        # Extract layout text
        import json
        try:
            resp_json = json.loads(response.text)
            if "description" in resp_json:
                # Remove markdown if present
                import re
                layout_text = re.sub(r'```(?:text)?\s*', '', resp_json["description"])
                if verbose:
                    print(f"  Layout extracted successfully")
                return layout_text
            else:
                return response.text
        except Exception as e:
            if verbose:
                print(f"  Error parsing Vision API response: {e}")
            return response.text

    except Exception as e:
        if verbose:
            print(f"  Error in layout extraction: {e}")
        return None


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract pin data from datasheets and generate schematic symbols",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python -m src.main_layout datasheet.pdf output.glb

  # With LLM API key
  python -m src.main_layout datasheet.pdf output.glb --api-key YOUR_API_KEY

  # With layout mode (separated flow)
  python -m src.main_layout datasheet.pdf output.glb --layout-mode

  # Verbose output
  python -m src.main_layout datasheet.pdf output.glb --verbose
        """
    )

    parser.add_argument(
        "input",
        help="Input PDF datasheet file"
    )

    parser.add_argument(
        "output",
        help="Output schematic GLB file (e.g., output.glb)"
    )

    parser.add_argument(
        "--api-key",
        help="LLM API key (or set FASTCHAT_API_KEY env var)"
    )

    parser.add_argument(
        "--model",
        default="llama-3",
        help="LLM model to use (default: %(default)s)"
    )

    parser.add_argument(
        "--min-confidence",
        type=int,
        default=5,
        help="Minimum confidence score for page detection (default: %(default)s)"
    )

    parser.add_argument(
        "--layout-mode",
        action="store_true",
        help="Use Vision API to extract layout structure (separated flow: LLM for pins, Vision for layout)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    return parser.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_arguments()

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() != ".pdf":
        print("Error: Input file must be a PDF")
        sys.exit(1)

    # Get API key - check DATASHEET_PARSER_API_KEY first, then FASTCHAT_API_KEY
    import os
    api_key = args.api_key or os.environ.get("DATASHEET_PARSER_API_KEY") or os.environ.get("FASTCHAT_API_KEY")

    # Set FASTCHAT_API_KEY if provided via argument
    if args.api_key:
        os.environ["FASTCHAT_API_KEY"] = args.api_key

    # Validate output path
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        print(f"Processing: {input_path}")
        print(f"Output: {output_path}")

    try:
        # Step 1: Detect relevant pages
        if args.verbose:
            print("\n[1/4] Detecting relevant pages...")
        with PageDetector(str(input_path)) as detector:
            candidates = detector.detect_relevant_pages(
                min_confidence=args.min_confidence
            )

            if args.verbose:
                print(f"Found {len(candidates)} relevant pages:")
                for c in candidates:
                    print(f" - Page {c.page_number} (confidence: {c.confidence_score}): {', '.join(c.reasons)}")

        if not candidates:
            print("Error: No relevant pages found in datasheet")
            print("Try lowering --min-confidence")
            sys.exit(1)

        # Step 2: Extract content from relevant pages
        if args.verbose:
            print("\n[2/4] Extracting content from relevant pages...")
        with ContentExtractor(str(input_path)) as extractor:
            content = extractor.extract_content(candidates)

            if args.verbose:
                print(f"Extracted content from {len(content.pages)} pages")
                print(f"Found {len(content.tables)} table(s)")
                print(f"Found {len(content.images)} image(s)")

        # Step 3: Extract pin data with LLM (for pin names and numbers)
        if args.verbose:
            print("\n[3/4] Extracting pin names and numbers with LLM...")
        if not api_key:
            print("Error: API key required for pin data extraction")
            print("Set --api-key or FASTCHAT_API_KEY environment variable")
            sys.exit(1)

        llm_client = LLMClient(api_key=api_key, model=args.model)
        pin_data = llm_client.extract_pin_data(
            content=content.text_content,
            images=[img_data for _, img_data in content.images] if content.images else None
        )

        if args.verbose:
            print(f"Extracted pin data:")
            print(f"  Component: {pin_data.component_name}")
            print(f"  Package: {pin_data.package.type}-{pin_data.package.pin_count}")
            if pin_data.package.width > 0:
                print(f"  Dimensions: {pin_data.package.width}mm x {pin_data.package.height}mm")
            else:
                print(f"  Dimensions: N/A (will be estimated from package type)")
            print(f"  Pin count: {len(pin_data.pins)}")
            print(f"  Extraction method: {pin_data.extraction_method}")

        # Step 4: Extract layout structure with Vision API (if layout mode enabled)
        layout_text = None
        if args.layout_mode:
            if args.verbose:
                print("\n[4/4] Extracting layout structure with Vision API...")

            # Get pinout pages
            pinout_pages = [c.page_number for c in candidates]

            # Use first pinout page for layout
            layout_page = pinout_pages[0] if pinout_pages else None

            if layout_page:
                layout_text = extract_layout_with_vision(str(input_path), layout_page, args.verbose)

                if args.verbose:
                    print(f"Layout text extracted:")
                    print(layout_text)
                    print()

                # Parse layout text into structured format
                layout_data = parse_layout_text(layout_text) if layout_text else {}

                if args.verbose:
                    print(f"Parsed layout data:")
                    print(f"  Package type: {layout_data.get('package_type', 'Unknown')}")
                    print(f"  Pin count: {layout_data.get('pin_count', 0)}")
                    print(f"  Sections found: {len(layout_data.get('sections', {}))}")

                    for section_name, section_info in layout_data.get('sections', {}).items():
                        print(f"  Section: {section_name}")
                        print(f"    Pins: {section_info.get('pins', [])}")
                        print(f"    Count: {section_info.get('count', 0)}")

            else:
                if args.verbose:
                    print("Warning: No pinout pages found for layout extraction")

        # Step 5: Validate and normalize package
        if args.verbose:
            print("\n[5/4] Validating and normalizing package...")

        detector = PackageDetector()
        normalized_pkg = detector.normalize_package_name(pin_data.package.type)
        pin_data.package.type = normalized_pkg

        if args.verbose:
            print(f"Normalized package type: {normalized_pkg}")

        # Step 6: Generate schematic symbol
        if args.verbose:
            print("\n[6/4] Generating schematic symbol...")

        # Prepare custom layout if available
        custom_layout = None
        if args.layout_mode and layout_text and layout_data.get('sections'):
            # Convert layout sections to format expected by PinLayout
            # layout_data["sections"] = {"section_name": {"pins": [...], "count": ...}, ...}
            # custom_layout = {"left_side": [1,2,3], "bottom_edge": [4,5,6], ...}
            custom_layout = {}
            for section_name, section_info in layout_data['sections'].items():
                custom_layout[section_name] = section_info.get('pins', [])

            if args.verbose:
                print(f"Custom layout prepared:")
                for section_name, pins in custom_layout.items():
                    print(f"  {section_name}: {pins}")

            print("Note: Using hybrid flow (LLM pins + Vision layout)")
        else:
            print("Note: Using standard flow (LLM only)")

        result = build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=str(output_path),
            custom_layout=custom_layout
        )

        if not result:
            print("Error: Failed to generate schematic")
            sys.exit(1)

        print(f"\nSuccess! Schematic generated: {output_path}")

        # Show file size
        if output_path.exists():
            import os
            file_size = os.path.getsize(str(output_path))
            print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install required packages: pip install -r requirements.txt")
        sys.exit(1)
    except NotImplementedError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
