#!/usr/bin/env python3
"""
Datasheet Parser CLI

Extract pin data from electronic component datasheets and generate schematic symbols.
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


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract pin data from datasheets and generate schematic symbols",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python -m src.main datasheet.pdf output.glb

  # With LLM API key
  python -m src.main datasheet.pdf output.glb --api-key YOUR_API_KEY

  # Specify model
  python -m src.main datasheet.pdf output.glb --model gpt-4

  # Verbose output
  python -m src.main datasheet.pdf output.glb --verbose
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
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--layout-mode",
        action="store_true",
        help="Use Vision API to extract layout structure (separated flow: LLM for pins, Vision for layout)"
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
        print(f"Error: Input file must be a PDF")
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
            print("\n[1/3] Detecting relevant pages...")

        with PageDetector(str(input_path)) as detector:
            candidates = detector.detect_relevant_pages(
                min_confidence=args.min_confidence
            )

            if args.verbose:
                print(f"Found {len(candidates)} relevant pages:")
                for c in candidates:
                    print(f"  - Page {c.page_number} (confidence: {c.confidence_score}): {', '.join(c.reasons)}")

        if not candidates:
            print("Error: No relevant pages found in datasheet")
            print("Try lowering --min-confidence")
            sys.exit(1)

        # Step 2: Extract content from relevant pages
        if args.verbose:
            print("\n[2/3] Extracting content from relevant pages...")

        with ContentExtractor(str(input_path)) as extractor:
            content = extractor.extract_content(candidates)

            if args.verbose:
                print(f"Extracted content from {len(content.pages)} pages")
                print(f"Found {len(content.tables)} table(s)")
                print(f"Found {len(content.images)} image(s)")

        # Step 3: Extract pin data with LLM
        if args.verbose:
            print("\n[3/3] Extracting pin data with LLM...")

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

            if len(pin_data.pins) > 0:
                print(f"  Pins (all {len(pin_data.pins)} pins):")
                for i, pin in enumerate(pin_data.pins, 1):
                    func = f" ({pin.function})" if pin.function else ""
                    print(f"    {i:2d}. Pin {pin.number}: {pin.name}{func}")

        # Validate and normalize package
        detector = PackageDetector()
        normalized_pkg = detector.normalize_package_name(pin_data.package.type)
        pin_data.package.type = normalized_pkg

        # Step 4: Generate schematic symbol
        if args.verbose:
            print("\n[3/3] Generating schematic symbol...")

        result = build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=str(output_path)
        )
        if not result:
            print(f"Error: Failed to generate schematic")
            sys.exit(1)

        print(f"\nSuccess! Schematic generated: {output_path}")

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
