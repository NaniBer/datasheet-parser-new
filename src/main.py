#!/usr/bin/env python3
"""
Datasheet Parser CLI - Refactored Version

Extract pin data from electronic component datasheets and generate schematic symbols.
Refactored into smaller, focused functions for better maintainability.
"""

import sys
import argparse
import os
from pathlib import Path
from typing import Optional

# Import project modules
from .pdf_extractor import PageDetector, ContentExtractor
from .llm import LLMClient
from .llm.image_ocr_client import ImageOCRClient
from .schematic_generator import build_schematic_from_pin_data, build_pcb_2d_schematic
from .utils import PackageDetector
from .models import PinData, Pin, PackageInfo
from .exceptions import ValidationError, ErrorCodes


# ============================================================================
# Validation Functions
# ============================================================================

def validate_input_file(input_path: Path) -> None:
    """
    Validate input file exists and has correct extension.

    Args:
        input_path: Path to input file

    Raises:
        ValidationError: If validation fails
    """
    if not input_path.exists():
        raise ValidationError(
            message=f"Input file not found: {input_path}",
            error_code=ErrorCodes.FILE_NOT_FOUND,
            details={"input_path": str(input_path)}
        )

    if input_path.suffix.lower() != ".pdf":
        raise ValidationError(
            message="Input file must be a PDF",
            error_code=ErrorCodes.INVALID_PDF_FILE,
            details={"actual_suffix": input_path.suffix}
        )


def get_api_key(args) -> str:
    """
    Get API key from args or environment variables.

    Args:
        args: Parsed command-line arguments

    Returns:
        API key string

    Raises:
        APICredentialsError: If API key not found
    """
    api_key = args.api_key or os.environ.get("DATASHEET_PARSER_API_KEY") or os.environ.get("FASTCHAT_API_KEY")

    if not api_key:
        raise APICredentialsError(
            message="API key required for pin data extraction",
            error_code=ErrorCodes.MISSING_API_KEY,
            details={
                "env_vars_checked": ["DATASHEET_PARSER_API_KEY", "FASTCHAT_API_KEY"],
                "cli_arg_provided": args.api_key is not None
            }
        )

    # Set FASTCHAT_API_KEY if provided via argument
    if args.api_key:
        os.environ["FASTCHAT_API_KEY"] = args.api_key

    return api_key


def setup_output_path(output_path: Path) -> None:
    """
    Ensure output directory exists.

    Args:
        output_path: Path to output file

    Raises:
        SystemExit: If directory cannot be created
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Pipeline Functions
# ============================================================================

def detect_relevant_pages(input_path: str, min_confidence: int, verbose: bool = False):
    """
    Detect pages in PDF that contain pinout information.

    Args:
        input_path: Path to PDF file
        min_confidence: Minimum confidence score
        verbose: Enable verbose output

    Returns:
        List of PageCandidate objects
    """
    if verbose:
        print("\n[1/5] Detecting relevant pages...")

    with PageDetector(input_path) as detector:
        candidates = detector.detect_relevant_pages(min_confidence=min_confidence)

    if verbose:
        print(f"Found {len(candidates)} relevant pages:")
        for c in candidates:
            print(f"  - Page {c.page_number} (confidence: {c.confidence_score}): {', '.join(c.reasons)}")

    if not candidates:
        print("Error: No relevant pages found in datasheet")
        print("Try lowering --min-confidence")
        sys.exit(1)

    return candidates


def extract_content(input_path: str, candidates: list, verbose: bool = False):
    """
    Extract text, tables, and images from relevant pages.

    Args:
        input_path: Path to PDF file
        candidates: List of PageCandidate objects
        verbose: Enable verbose output

    Returns:
        ExtractedContent object
    """
    if verbose:
        print("\n[2/5] Extracting content from relevant pages...")

    with ContentExtractor(input_path) as extractor:
        content = extractor.extract_content(candidates)

    if verbose:
        print(f"Extracted content from {len(content.pages)} pages")
        print(f"Found {len(content.tables)} table(s)")
        print(f"Found {len(content.images)} image(s)")

    return content


def extract_pin_data(content, api_key: str, model: str, verbose: bool = False) -> PinData:
    """
    Extract pin data using LLM.

    Args:
        content: ExtractedContent object
        api_key: API key for LLM service
        model: Model name to use
        verbose: Enable verbose output

    Returns:
        PinData object with extracted information

    Raises:
        SystemExit: If API key not found
    """
    if verbose:
        print("\n[3/5] Extracting pin data with LLM...")

    llm_client = LLMClient(api_key=api_key, model=model)
    pin_data = llm_client.extract_pin_data(content=content.text_content)

    if verbose:
        print(f"Extracted pin data:")
        print(f"  Component: {pin_data.component_name}")
        print(f"  Package: {pin_data.package.type}-{pin_data.package.pin_count}")
        if pin_data.package.width > 0:
            print(f"  Dimensions: {pin_data.package.width}mm x {pin_data.package.height}mm")
        else:
            print(f"  Dimensions: N/A (will be estimated from package type)")
        print(f"  Pin count: {len(pin_data.pins)}")
        print(f"  Extraction method: {pin_data.extraction_method}")

        if verbose and len(pin_data.pins) > 0:
            print(f"  Pins (all {len(pin_data.pins)} pins):")
            for i, pin in enumerate(pin_data.pins, 1):
                func = f" ({pin.function})" if pin.function else ""
                print(f"    {i:2d}. Pin {pin.number}: {pin.name}{func}")

    return pin_data


def extract_layout_with_vision(input_path: str, candidates: list, verbose: bool = False) -> Optional[dict]:
    """
    Extract layout structure using Vision API.

    Args:
        input_path: Path to PDF file
        candidates: List of PageCandidate objects
        verbose: Enable verbose output

    Returns:
        Dict with layout information or None
    """
    layout_text = None
    layout_data = {}

    # Get pinout pages
    pinout_pages = [c.page_number for c in candidates]

    # Use first pinout page for layout
    layout_page = pinout_pages[0] if pinout_pages else None

    if layout_page:
        if verbose:
            print("\n[4/5] Extracting layout structure with Vision API...")

        # Import Vision layout extraction function
        from .main import extract_layout_with_vision as extract_layout

        layout_text = extract_layout(input_path, layout_page, verbose)

        if verbose and layout_text:
            print(f"Layout text extracted:")
            print(layout_text)
            print()

            # Parse layout text
            from .main import parse_layout_text
            layout_data = parse_layout_text(layout_text)

            print(f"Parsed layout data:")
            print(f"  Package type: {layout_data.get('package_type', 'Unknown')}")
            print(f"  Pin count: {layout_data.get('pin_count', 0)}")
            print(f"  Sections found: {len(layout_data.get('sections', {}))}")
            for section_name, section_info in layout_data.get('sections', {}).items():
                print(f"  Section: {section_name}")
                print(f"    Pins: {section_info.get('pins', [])}")
                print(f"    Count: {section_info.get('count', 0)}")
    else:
        if verbose:
            print("Warning: No pinout pages found for layout extraction")

    return layout_data if layout_data and layout_data.get('sections') else None


def normalize_package(pin_data: PinData, verbose: bool = False):
    """
    Validate and normalize package type.

    Args:
        pin_data: PinData object
        verbose: Enable verbose output

    Returns:
        PinData with normalized package type
    """
    if verbose:
        print("\n[4] Validating package and generating schematic...")

    detector = PackageDetector()
    normalized_pkg = detector.normalize_package_name(pin_data.package.type)
    pin_data.package.type = normalized_pkg

    if verbose:
        print(f"Normalized package type: {normalized_pkg}")

    return pin_data


def prepare_custom_layout(layout_data: dict, verbose: bool = False) -> Optional[dict]:
    """
    Convert Vision API layout data to format expected by PinLayout.

    Args:
        layout_data: Parsed layout data from Vision API
        verbose: Enable verbose output

    Returns:
        Dict with section names mapped to pin numbers, or None
    """
    if not layout_data or not layout_data.get('sections'):
        return None

    custom_layout = {}
    for section_name, section_info in layout_data['sections'].items():
        custom_layout[section_name] = section_info.get('pins', [])

    if verbose:
        print(f"Custom layout prepared:")
        for section_name, pins in custom_layout.items():
            print(f"  {section_name}: {pins}")

    return custom_layout


# ============================================================================
# Main Orchestration
# ============================================================================

def process_datasheet(
    input_path: Path,
    output_path: Path,
    api_key: str,
    model: str,
    layout_mode: bool = False,
    pcb_2d_mode: bool = False,
    min_confidence: int = 5,
    verbose: bool = False
) -> bool:
    """
    Main processing pipeline.

    Args:
        input_path: Path to input PDF
        output_path: Path to output GLB file
        api_key: API key for LLM service
        model: Model name to use
        layout_mode: Enable Vision API layout extraction
        pcb_2d_mode: Enable 2D PCB schematic generation
        min_confidence: Minimum confidence score for page detection
        verbose: Enable verbose output

    Returns:
        True if successful

    Raises:
        SystemExit: On error
    """
    # Display processing info
    if verbose:
        print(f"Processing: {input_path}")
        print(f"Output: {output_path}")
        if pcb_2d_mode:
            mode = "2D PCB Mode (2D PCB schematic)"
        elif layout_mode:
            mode = "Layout Mode (LLM + Vision, 3D schematic)"
        else:
            mode = "Standard Mode (LLM only, 3D schematic)"
        print(f"Mode: {mode}")

    # Pipeline steps
    try:
        # Step 1: Detect relevant pages
        candidates = detect_relevant_pages(str(input_path), min_confidence, verbose)

        # Step 2: Extract content
        content = extract_content(str(input_path), candidates, verbose)

        # Step 3: Extract pin data with LLM
        pin_data = extract_pin_data(content, api_key, model, verbose)

        # Step 4: Extract layout with Vision API (if enabled)
        layout_data = None
        if layout_mode:
            layout_data = extract_layout_with_vision(str(input_path), candidates, verbose)

        # Step 5: Validate and normalize package
        pin_data = normalize_package(pin_data, verbose)

        # Step 6: Prepare custom layout if available
        custom_layout = None
        if layout_data:
            custom_layout = prepare_custom_layout(layout_data, verbose)
            if verbose:
                print("Note: Using hybrid flow (LLM pins + Vision layout)")
        else:
            if verbose:
                print("Using standard layout based on package type")

        # Step 7: Generate schematic
        if verbose:
            if pcb_2d_mode:
                print(f"\n[5] Generating 2D PCB schematic...")
            else:
                print(f"\n[5] Generating 3D schematic...")

        # Choose schematic builder based on mode
        if pcb_2d_mode:
            result = build_pcb_2d_schematic(
                package_type=pin_data.package.type,
                pin_count=pin_data.package.pin_count,
                component_name=pin_data.component_name,
                pin_data=[{"number": p.number, "name": p.name} for p in pin_data.pins],
                output_path=str(output_path),
                custom_layout=custom_layout
            )
        else:
            result = build_schematic_from_pin_data(
                pin_data=pin_data,
                output_path=str(output_path),
                custom_layout=custom_layout
            )

        if not result:
            if pcb_2d_mode:
                print("Error: Failed to generate 2D PCB schematic")
            else:
                print("Error: Failed to generate 3D schematic")
            return False

        print(f"\nSuccess! Schematic generated: {output_path}")

        # Show file size
        if output_path.exists():
            file_size = os.path.getsize(str(output_path))
            print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

        return True

    except ValidationError as e:
        print(f"Validation error: {e}")
        if verbose:
            print(f"Error code: {e.error_code}")
            if e.details:
                print(f"Details: {e.details}")
        sys.exit(1)

    except APICredentialsError as e:
        print(f"API credentials error: {e}")
        if verbose:
            print(f"Error code: {e.error_code}")
            if e.details:
                print(f"Details: {e.details}")
        sys.exit(1)

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

    except DatasheetParserError as e:
        print(f"Datasheet parser error: {e}")
        if verbose:
            print(f"Error code: {e.error_code}")
            if e.details:
                print(f"Details: {e.details}")
        sys.exit(1)

    except Exception as e:
        print(f"Unexpected error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ============================================================================
# CLI Entry Point
# ============================================================================

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract pin data from datasheets and generate schematic symbols",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (3D schematic)
  python -m src.main datasheet.pdf output.glb

  # 2D PCB schematic generation
  python -m src.main datasheet.pdf output.glb --pcb-2d

  # With LLM API key
  python -m src.main datasheet.pdf output.glb --api-key YOUR_API_KEY

  # With layout mode (Vision API for layout extraction)
  python -m src.main datasheet.pdf output.glb --layout-mode

  # Verbose output
  python -m src.main datasheet.pdf output.glb --verbose

  # Specify confidence threshold
  python -m src.main datasheet.pdf output.glb --min-confidence 3 --verbose
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
        help="LLM API key (or set DATASHEET_PARSER_API_KEY or FASTCHAT_API_KEY env var)"
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
        "--pcb-2d",
        action="store_true",
        help="Generate 2D PCB-style schematic (instead of 3D schematic)"
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
    validate_input_file(input_path)

    # Get API key
    api_key = get_api_key(args)

    # Setup output path
    output_path = Path(args.output)
    setup_output_path(output_path)

    # Process datasheet
    process_datasheet(
        input_path=input_path,
        output_path=output_path,
        api_key=api_key,
        model=args.model,
        layout_mode=args.layout_mode,
        pcb_2d_mode=args.pcb_2d,
        min_confidence=args.min_confidence,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
