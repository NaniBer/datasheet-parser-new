#!/usr/bin/env python3
"""
Datasheet Parser CLI

Extract pin data from electronic component datasheets and generate 3D CAD models.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# Import project modules
from .pdf_extractor import PageDetector, ContentExtractor
from .llm import LLMClient, PageVerifier
from .model_generator import CadqueryBuilder, GLBExporter
from .utils import PackageDetector
from .models import PinData


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract pin data from datasheets and generate 3D CAD models",
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

  # Export to alternative format
  python -m src.main datasheet.pdf output.step --format step
        """
    )

    parser.add_argument(
        "input",
        help="Input PDF datasheet file"
    )

    parser.add_argument(
        "output",
        help="Output 3D model file (e.g., output.glb, output.step, output.stl)"
    )

    parser.add_argument(
        "--api-key",
        help="LLM API key (or set DATASHEET_PARSER_API_KEY env var)"
    )

    parser.add_argument(
        "--model",
        default="default",
        help="LLM model to use (default: %(default)s)"
    )

    parser.add_argument(
        "--format",
        choices=["glb", "step", "stl"],
        default="glb",
        help="Output format (default: %(default)s)"
    )

    parser.add_argument(
        "--min-confidence",
        type=int,
        default=5,
        help="Minimum confidence score for page detection (default: %(default)s)"
    )

    parser.add_argument(
        "--verify-ambiguity",
        action="store_true",
        help="Use LLM to verify ambiguous pages (requires API key)"
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
        print(f"Format: {args.format.upper()}")

    try:
        # Step 1: Detect relevant pages
        if args.verbose:
            print("\n[1/5] Detecting relevant pages...")

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
            print("Try lowering --min-confidence or using --verify-ambiguity")
            sys.exit(1)

        # Step 2: Extract content from relevant pages
        if args.verbose:
            print("\n[2/5] Extracting content from relevant pages...")

        with ContentExtractor(str(input_path)) as extractor:
            content = extractor.extract_content(candidates)

            if args.verbose:
                print(f"Extracted content from {len(content.pages)} pages")
                print(f"Found {len(content.tables)} table(s)")
                print(f"Found {len(content.images)} image(s)")

        # Step 3: Verify ambiguous pages (if requested)
        if args.verify_ambiguity and api_key:
            if args.verbose:
                print("\n[3/5] Verifying ambiguous pages with LLM...")

            llm_client = LLMClient(api_key=api_key, model=args.model)
            verifier = PageVerifier(llm_client)

            low_conf_pages = detector.get_low_confidence_pages(threshold=args.min_confidence)
            if low_conf_pages:
                candidates = verifier.verify_pages(low_conf_pages, extractor)
                if args.verbose:
                    print(f"Verified {len(low_conf_pages)} ambiguous pages")

        # Step 4: Extract pin data using LLM
        if args.verbose:
            print("\n[4/5] Extracting pin data with LLM...")

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
            print(f"  Dimensions: {pin_data.package.width}mm x {pin_data.package.height}mm")
            print(f"  Pin count: {len(pin_data.pins)}")
            print(f"  Extraction method: {pin_data.extraction_method}")

            if len(pin_data.pins) <= 10:
                print(f"  Pins:")
                for pin in pin_data.pins:
                    func = f" ({pin.function})" if pin.function else ""
                    print(f"    {pin.number}: {pin.name}{func}")

        # Validate and normalize package
        detector = PackageDetector()
        normalized_pkg = detector.normalize_package_name(pin_data.package.type)
        pin_data.package.type = normalized_pkg

        # Step 5: Generate 3D model
        if args.verbose:
            print("\n[5/5] Generating 3D model...")

        builder = CadqueryBuilder(pin_data)
        cadquery_code = builder.generate_model_code()

        if args.verbose:
            print(f"Generated cadquery code ({len(cadquery_code)} characters)")

        # Export model
        exporter = GLBExporter(cadquery_code)

        output_format = args.format
        if output_format == "glb":
            exporter.export_to_glb(str(output_path))
        elif output_format == "step":
            exporter.export_to_step(str(output_path))
        elif output_format == "stl":
            exporter.export_to_obj(str(output_path))  # Exports as STL

        print(f"\nSuccess! Model generated: {output_path}")

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
