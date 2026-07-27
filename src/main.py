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
from typing import List, Optional

# Import project modules
from .pdf_extractor import PageDetector, ContentExtractor
from .pdf_extractor import infer_part_number_hint
from .pdf_extractor.deterministic_table_parser import parse_pin_data_from_tables
from .pdf_extractor.extraction_validator import validate_pin_data_extraction
from .llm import LLMClient
from .llm.image_ocr_client import ImageOCRClient
from .schematic_generator import (
    build_schematic_from_pin_data,
    build_pcb_2d_schematic,
    pin_data_to_builder_format,
)
from .utils import PackageDetector
from .models import PinData, Pin, PackageInfo
from .exceptions import (
    ValidationError, ErrorCodes, APICredentialsError, DatasheetParserError,
    LLMExtractionError, SchematicGenerationError,
)


# ============================================================================
# Validation Functions
# ============================================================================

# ---------------------------------------------------------------------------
# Exit-code contract (kept stable for callers and automation):
#   0 — all requested artifacts were produced and validated
#   1 — domain failure: unsupported/unvalidatable input, fail-closed refusal
#   2 — internal error: an unexpected exception (a bug), traceback printed
#   3 — degraded: artifacts were produced but are UNVALIDATED. Either
#       --force-best-effort accepted invalid data, or the output is
#       best-effort by construction (a lossy geometry approximation, or a
#       footprint built on display-proportion geometry with no real dims).
#       The GLB carries validated=false; this exit code lets callers that
#       only read the status distinguish a trusted result from a best-effort
#       one instead of seeing 0.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_DOMAIN_FAILURE = 1
EXIT_INTERNAL_ERROR = 2
EXIT_DEGRADED = 3


def _record_degraded(pin_data, reasons) -> None:
    """Merge best-effort/approximation reasons into pin_data.validation_errors.

    Reusing validation_errors means the existing watermark + exit-3 machinery
    fires automatically for auto-degraded output, not just --force-best-effort.
    """
    if pin_data is None or not reasons:
        return
    existing = list(pin_data.validation_errors or [])
    for reason in reasons:
        if reason not in existing:
            existing.append(reason)
    pin_data.validation_errors = existing


def _exit_if_degraded(pin_data) -> None:
    """Exit EXIT_DEGRADED when output was produced from unvalidated data.

    pin_data.validation_errors is set when invalid data was accepted via
    --force-best-effort, or when the output is best-effort by construction
    (lossy approximation / unverified geometry, recorded via _record_degraded).
    Both watermark the GLB; surfacing it in the exit code keeps degraded output
    from masquerading as a clean 0.
    """
    if pin_data is not None and getattr(pin_data, "validation_errors", None):
        sys.exit(EXIT_DEGRADED)


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


def setup_output_path(output_path: Path) -> None:
    """
    Ensure output directory exists.

    Args:
        output_path: Path to output file

    Raises:
        SystemExit: If directory cannot be created
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)


def _both_output_paths(output: str) -> tuple:
    """Derive schematic and footprint GLB paths from a base output argument.

    Examples:
        "NE555.glb"        -> ("NE555_schematic.glb", "NE555_footprint.glb")
        "output/NE555.glb" -> ("output/NE555_schematic.glb", "output/NE555_footprint.glb")
        "NE555"            -> ("NE555_schematic.glb", "NE555_footprint.glb")
    """
    p = Path(output)
    stem = p.stem
    parent = p.parent
    return (
        str(parent / f"{stem}_schematic.glb"),
        str(parent / f"{stem}_footprint.glb"),
    )


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
        sys.exit(EXIT_DOMAIN_FAILURE)

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


def _grounding_source_text(content) -> str:
    """
    Text the extraction must be grounded in: page text plus table cells.

    Table cells are included separately because in tables-only mode the pin
    names may exist only inside extracted tables, not in text_content.
    """
    parts = [content.text_content or ""]
    for _page_num, table_data in content.tables or []:
        for row in table_data or []:
            for cell in row or []:
                if cell:
                    parts.append(str(cell))
    return "\n".join(parts)


def extract_pin_data(
    content,
    model: str,
    verbose: bool = False,
    part_number: Optional[str] = None,
    max_attempts: int = 2,
    force_best_effort: bool = False,
) -> PinData:
    """
    Extract pin data using LLM.

    The LLM client reads FASTCHAT_API_KEY from the environment at call time.

    Args:
        content: ExtractedContent object
        model: Model name to use
        verbose: Enable verbose output

    Returns:
        PinData object with extracted information
    """
    if verbose:
        print("\n[3/5] Extracting pin data...")

    # Determine if we should use table-only mode
    # Use table-only mode when we have tables but no images (diagrams)
    tables_only_mode = len(content.tables) > 0 and len(content.images) == 0

    if not part_number:
        part_number = infer_part_number_hint(content.text_content)

    if verbose and part_number:
        print(f"  Target part number hint: {part_number}")

    # Check if we have sufficient content for extraction
    if not tables_only_mode and not content.text_content:
        print("Error: No tables or text content found for extraction")
        sys.exit(EXIT_DOMAIN_FAILURE)

    if verbose:
        if tables_only_mode:
            print(f"Using table-only mode (tables detected, no diagrams)")
        elif len(content.tables) == 0:
            print(f"Using text-based extraction (no tables found)")
        else:
            print(f"Using mixed mode (tables + diagrams)")

    grounding_text = _grounding_source_text(content)

    deterministic_pin_data = parse_pin_data_from_tables(content, part_number=part_number)
    if deterministic_pin_data is not None:
        deterministic_pin_data = normalize_package(deterministic_pin_data, verbose=False)
        deterministic_validation = validate_pin_data_extraction(
            deterministic_pin_data,
            part_number=part_number,
            source_text=grounding_text,
        )

        if deterministic_validation.is_valid:
            if verbose:
                print("Using deterministic table parser")
                _print_pin_data_summary(deterministic_pin_data, deterministic_validation)
            return deterministic_pin_data

        if verbose:
            print("Deterministic table parser candidate failed validation; falling back to LLM.")
            for error in deterministic_validation.errors:
                print(f"    - {error}")
            if deterministic_validation.warnings:
                print("  Validation warnings:")
                for warning in deterministic_validation.warnings:
                    print(f"    - {warning}")

    if verbose:
        print("Using LLM fallback for extraction")

    llm_client = LLMClient(model=model)

    # Format content for LLM using the appropriate mode
    from .pdf_extractor.content_extractor import ContentExtractor
    formatted_content = ContentExtractor.format_for_llm(content, tables_only=tables_only_mode)

    if verbose:
        print(f"Sending {len(formatted_content)} characters to LLM")

    validation_feedback = None
    last_validation = None
    last_pin_data = None
    last_llm_error = None

    for attempt in range(1, max_attempts + 1):
        if verbose and attempt > 1:
            print(f"Retrying pin extraction (attempt {attempt}/{max_attempts})...")

        try:
            pin_data = llm_client.extract_pin_data(
                content=formatted_content,
                part_number=part_number,
                tables_only_mode=tables_only_mode,
                validation_feedback=validation_feedback,
            )
        except LLMExtractionError as e:
            # The client fails closed on its own self-consistency checks; feed
            # its complaint into the next attempt instead of giving up early.
            last_llm_error = e
            issue = (e.details or {}).get("validation_issue")
            if issue:
                validation_feedback = issue
            if verbose:
                print(f"  LLM extraction failed: {e}")
            continue

        # Normalize before validation so the checks reflect what the rest of the
        # pipeline will actually use.
        pin_data = normalize_package(pin_data, verbose=False)
        last_pin_data = pin_data

        validation = validate_pin_data_extraction(
            pin_data,
            part_number=part_number,
            source_text=grounding_text,
        )
        last_validation = validation

        if validation.is_valid:
            if verbose:
                _print_pin_data_summary(pin_data, validation)

            return pin_data

        validation_feedback = validation.feedback

        if verbose:
            print("  Validation failed:")
            for error in validation.errors:
                print(f"    - {error}")
            if validation.warnings:
                print("  Validation warnings:")
                for warning in validation.warnings:
                    print(f"    - {warning}")
            if attempt < max_attempts:
                print("  Preparing a corrective retry...")

    # All attempts exhausted without a valid result — fail closed unless the
    # user explicitly asked for best-effort output (ARCH-005).
    if last_validation is not None and last_validation.errors:
        errors = list(last_validation.errors)
    elif last_llm_error is not None:
        errors = [str(last_llm_error)]
    else:
        errors = ["unknown validation failure"]

    if force_best_effort and last_pin_data is not None:
        print(
            f"Warning: Validation failed after {max_attempts} attempts. "
            f"Proceeding with UNVALIDATED best-effort result (--force-best-effort). "
            f"Issues: {'; '.join(errors)}"
        )
        last_pin_data.validation_errors = errors
        return last_pin_data

    raise ValidationError(
        f"Pin data failed validation after {max_attempts} attempts: "
        f"{'; '.join(errors)}. "
        "Re-run with --force-best-effort to emit unvalidated output.",
        error_code=ErrorCodes.EXTRACTION_VALIDATION_FAILED,
        details={"errors": errors},
    )


def extract_layout_with_vision(
    input_path: str,
    candidates: list,
    verbose: bool = False,
    part_number: Optional[str] = None,
) -> Optional[dict]:
    """
    Extract layout structure using Vision API.

    Args:
        input_path: Path to PDF file
        candidates: List of PageCandidate objects
        verbose: Enable verbose output

    Returns:
        Dict with side-based layout or None. Format: {"left_side": [1,2,3], ...}
    """
    from .pdf_extractor.content_extractor import ContentExtractor

    # Get pinout pages
    pinout_pages = [c.page_number for c in candidates]

    # Use first pinout page for layout
    layout_page = pinout_pages[0] if pinout_pages else None

    if not layout_page:
        if verbose:
            print("Warning: No pinout pages found for layout extraction")
        return None

    if verbose:
        print("\n[4/5] Extracting layout structure with Vision API...")

    try:
        # Extract image from the pinout page
        with ContentExtractor(input_path) as extractor:
            # Create a single page candidate for image extraction
            page_candidate = [c for c in candidates if c.page_number == layout_page][0]
            content = extractor.extract_content([page_candidate])

        if not content.images:
            if verbose:
                print("Warning: No images found on pinout page")
            return None

        # Use the first image for layout extraction
        image_data = content.images[0]

        # Initialize Vision API client
        vision_client = ImageOCRClient()

        # Extract layout with prompt for side-based layout
        layout_prompt = f"""Analyze this electronic component pinout diagram and extract the physical pin layout.

## Your Task:
Identify which pins are on each side of the component package.

{f"Target component: {part_number}" if part_number else ""}

## Expected Layout Types:
- **DIP/SOIC**: Pins on left and right sides only
- **QFP/LQFP**: Pins on all 4 sides (left, right, top, bottom)
- **QFN**: Pins on all 4 sides (some may have no pins on one side)
- **BGA**: Grid layout

## Output Format:
Return ONLY valid JSON (no markdown, no explanations):
{
  "component_name": "Component Name",
  "package_type": "Package Type",
  "pin_count": 38,
  "left_side": [1, 2, 3, ...],
  "bottom_edge": [15, 16, 17, ...],
  "right_side": [25, 26, 27, ...],
  "top_edge": [],
  "extraction_confidence": 0.95,
  "notes": "Description of layout quality"
}

Return ONLY the JSON object."""

        result = vision_client.extract_pinout_from_image(
            image_data=image_data,
            page_number=layout_page,
            prompt=layout_prompt
        )

        # Convert Vision API result to custom_layout format
        if result.confidence < 0.5:
            if verbose:
                print(f"Warning: Low confidence layout extraction ({result.confidence:.2f})")
            return None

        # Build custom_layout dict from Vision API result
        # Look for side information in the pins or extract from result.notes
        custom_layout = {}

        # First check if pins have 'side' field
        if result.pins and result.pins[0].get('side'):
            # Build layout from pin side information
            side_map = {"left": "left_side", "right": "right_side", "top": "top_edge", "bottom": "bottom_edge"}
            for pin in result.pins:
                side = pin.get('side', '')
                if side and side in side_map:
                    layout_side = side_map[side]
                    if layout_side not in custom_layout:
                        custom_layout[layout_side] = []
                    custom_layout[layout_side].append(pin.get('number'))

        else:
            # Try to parse from notes (for side-based layout format)
            import re
            notes = result.notes.lower()

            # Look for patterns like "left side has 14 pins (1-14)"
            left_match = re.search(r'left.*?(\d+)[\s-]*(\d+)', notes)
            bottom_match = re.search(r'bottom.*?(\d+)[\s-]*(\d+)', notes)
            right_match = re.search(r'right.*?(\d+)[\s-]*(\d+)', notes)
            top_match = re.search(r'top.*?(\d+)[\s-]*(\d+)', notes)

            if left_match:
                custom_layout['left_side'] = list(range(int(left_match.group(1)), int(left_match.group(2)) + 1))
            if bottom_match:
                custom_layout['bottom_edge'] = list(range(int(bottom_match.group(1)), int(bottom_match.group(2)) + 1))
            if right_match:
                custom_layout['right_side'] = list(range(int(right_match.group(1)), int(right_match.group(2)) + 1))
            if top_match:
                custom_layout['top_edge'] = list(range(int(top_match.group(1)), int(top_match.group(2)) + 1))

        if custom_layout:
            if verbose:
                print(f"Layout extracted from Vision API:")
                print(f"  Package: {result.package_type}")
                print(f"  Pin count: {result.pin_count}")
                print(f"  Confidence: {result.confidence:.2f}")
                for side, pins in custom_layout.items():
                    print(f"  {side}: {pins[:10]}{'...' if len(pins) > 10 else ''}")
            return custom_layout
        else:
            if verbose:
                print("Warning: Could not parse layout from Vision API response")
                print(f"  Notes: {result.notes[:100]}")
            return None

    except Exception as e:
        if verbose:
            print(f"Error extracting layout with Vision API: {e}")
        return None


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
    
    # Handle multi-package format
    if pin_data.packages and len(pin_data.packages) > 0:
        if verbose:
            print(f"Normalizing {len(pin_data.packages)} package types...")
        
        for pkg in pin_data.packages:
            pkg_type = pkg.get('type', '')
            if pkg_type:
                normalized = detector.normalize_package_name(pkg_type)
                pkg['type'] = normalized
                if verbose:
                    print(f"  {pkg_type} → {normalized}")
        
        if verbose:
            print(f"Normalized package types")
    
    # Handle legacy single-package format
    elif pin_data.package:
        normalized_pkg = detector.normalize_package_name(pin_data.package.type)
        pin_data.package.type = normalized_pkg
        
        if verbose:
            print(f"Normalized package type: {normalized_pkg}")

    return pin_data


def _print_pin_data_summary(pin_data: PinData, validation) -> None:
    """Print a concise summary of extracted pin data."""
    print(f"\nExtracted pin data:")
    print(f"  Component: {pin_data.component_name}")
    print(f"  Extraction method: {pin_data.extraction_method}")

    # Handle both multi-package and single-package formats
    if pin_data.packages and len(pin_data.packages) > 0:
        print(f"  Format: Multi-package ({len(pin_data.packages)} variants)")
        for i, pkg in enumerate(pin_data.packages, 1):
            print(f"  Package {i}: {pkg['type']}-{pkg['pin_count']} ({len(pkg['pins'])} pins)")
    elif pin_data.package:
        print(f"  Format: Single-package")
        print(f"  Package: {pin_data.package.type}-{pin_data.package.pin_count}")
        if pin_data.package.width > 0:
            print(f"  Dimensions: {pin_data.package.width}mm x {pin_data.package.height}mm")
        else:
            print(f"  Dimensions: N/A (will be estimated from package type)")
        print(f"  Pin count: {len(pin_data.pins)}")

    pins_list = []
    if pin_data.packages and len(pin_data.packages) > 0:
        pins_list = pin_data.packages[0]['pins'][:5]
    elif pin_data.pins:
        pins_list = pin_data.pins[:5]

    if pins_list:
        print(f"  Sample pins:")
        for pin in pins_list:
            pin_num = pin.get('number') if isinstance(pin, dict) else pin.number
            pin_name = pin.get('name') if isinstance(pin, dict) else pin.name
            pin_func = pin.get('function') if isinstance(pin, dict) else pin.function
            func = f" ({pin_func})" if pin_func else ""
            print(f"    Pin {pin_num}: {pin_name}{func}")

    if validation.warnings:
        print("  Validation warnings:")
        for warning in validation.warnings:
            print(f"    - {warning}")


# ============================================================================
# Main Orchestration
# ============================================================================

def get_dynamic_min_confidence(pdf_path: Path, user_min_confidence: int = 5, verbose: bool = False) -> int:
    """
    Dynamically adjust min_confidence based on PDF characteristics.

    - Small/simple PDFs (< 10 pages): Lower threshold (2) to catch simple components
    - Medium PDFs (10-50 pages): Standard threshold (3-4)
    - Large/complex PDFs (> 50 pages): Higher threshold (5+) to reduce false positives

    Args:
        pdf_path: Path to PDF file
        user_min_confidence: User-specified minimum confidence
        verbose: Enable verbose output

    Returns:
        Adjusted minimum confidence score
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            
            # Auto-adjust based on page count
            if page_count < 10:
                auto_min = 2  # Simple components (NE555, AMS1117)
            elif page_count < 50:
                auto_min = 3  # Medium complexity
            else:
                auto_min = 4  # Large datasheets
            
            # Use the minimum of user-specified and auto-adjusted value
            # (user can increase threshold if needed, but we won't force it higher)
            adjusted_min = min(user_min_confidence, auto_min)
            
            if verbose and adjusted_min != user_min_confidence:
                print(f"Auto-adjusted min_confidence: {user_min_confidence} → {adjusted_min} (PDF has {page_count} pages)")
            
            return adjusted_min
            
    except Exception as e:
        if verbose:
            print(f"Warning: Could not determine PDF page count, using default min_confidence: {e}")
        return user_min_confidence


def enforce_known_package_type(
    pin_data: PinData,
    part_number: Optional[str] = None,
    package_index: Optional[int] = None,
    force_best_effort: bool = False,
) -> None:
    """
    Fail closed on package types with no known geometry (ARCH-006).

    Unknown package types used to render silently as DIP. Now they raise
    SchematicGenerationError unless --force-best-effort is set, in which
    case the DIP substitution is made explicit: the selected package type
    is rewritten to "DIP-<pin_count>" and the substitution is recorded in
    pin_data.validation_errors (which triggers the GLB unvalidated
    watermark).
    """
    from .schematic_generator import parse_package_type

    package_type, pin_count, _, _ = pin_data_to_builder_format(
        pin_data,
        package_index=package_index,
        part_number=part_number,
    )

    try:
        parse_package_type(package_type)
        return
    except SchematicGenerationError as e:
        if not force_best_effort:
            raise SchematicGenerationError(
                f"{e} Re-run with --force-best-effort to substitute DIP "
                "geometry (output will be marked unvalidated).",
                error_code=ErrorCodes.PACKAGE_UNKNOWN,
                details=e.details,
            )

    substitute = f"DIP-{pin_count}"
    message = (
        f"Unknown package type '{package_type}'; substituted {substitute} "
        "geometry (--force-best-effort)"
    )
    print(f"Warning: {message}")

    if pin_data.packages:
        from .pdf_extractor.variant_selection import select_package_variant
        selection = select_package_variant(
            pin_data, part_number=part_number, package_index=package_index
        )
        selection.package["type"] = substitute
    elif pin_data.package:
        pin_data.package.type = substitute

    errors = list(pin_data.validation_errors or [])
    errors.append(message)
    pin_data.validation_errors = errors


# Canonical package families that PackageDetector.package_family() produces for
# real packages (it collapses SON/DFN/WSON->QFN, PDIP->DIP, etc.). Used to gate
# the family-mismatch check so unrecognized vendor strings can't force a refusal.
_KNOWN_PACKAGE_FAMILIES = {
    "SOIC", "SOP", "SSOP", "TSSOP", "MSOP", "VSSOP", "HVSSOP", "QSOP",
    "QFN", "DFN", "SON", "WSON", "VSON",
    "DIP", "PDIP", "CDIP", "SDIP",
    "PLCC", "LCCC", "LCC",
    "TQFP", "LQFP", "QFP", "BGA", "LGA",
    "SOT-23", "SOT-89", "SOT-223", "SOT-143",
    "TO-92", "TO-220", "TO-263", "TO-252", "TO-247", "TO-100",
}


def _extracted_pin_counts(pin_data: PinData) -> List[int]:
    """Pin counts of every extracted variant (declared count, or pin list length)."""
    counts: List[int] = []
    if pin_data.packages:
        for pkg in pin_data.packages:
            try:
                count = int(pkg.get("pin_count") or 0)
            except (TypeError, ValueError):
                count = 0
            count = count or len(pkg.get("pins") or [])
            if count:
                counts.append(count)
    elif pin_data.package:
        count = pin_data.package.pin_count or len(pin_data.pins or [])
        if count:
            counts.append(int(count))
    return counts


def _enforce_ordered_pin_count(
    pin_data: PinData,
    part_number: Optional[str],
    force_best_effort: bool,
) -> None:
    """Fail closed when the ordering table's grounded pin count matches no
    extracted variant — i.e. the LLM read the wrong variant/count and there is
    nothing for select_package_variant to correct it to.

    With --force-best-effort the conflict is recorded (watermark + exit 3)
    instead of refusing.
    """
    ordered = pin_data.ordered_pin_count
    if not ordered:
        return
    counts = _extracted_pin_counts(pin_data)
    if not counts or any(count == ordered for count in counts):
        return  # an extracted variant matches the grounded count

    message = (
        f"Ordering table lists {part_number!r} as a {ordered}-pin package, but the "
        f"extracted variant(s) have {counts} pins — the wrong variant was read."
    )
    if force_best_effort:
        pin_data.validation_errors = list(pin_data.validation_errors or []) + [message]
        print(f"Warning: {message} Proceeding UNVALIDATED (--force-best-effort).")
        return
    raise ValidationError(
        message + " Re-run with --force-best-effort to override.",
        error_code=ErrorCodes.EXTRACTION_VALIDATION_FAILED,
        details={"ordered_pin_count": ordered, "extracted_pin_counts": counts},
    )


def _enforce_ordered_package_family(
    pin_data: PinData,
    part_number: Optional[str],
    force_best_effort: bool,
) -> None:
    """Fail closed when the ordering table's grounded package family matches no
    extracted variant — the wrong *shape* was read even if the pin count agrees
    (e.g. SON-8 ordered but SOIC-8 extracted: same 8 pins, wrong 1.27mm grid).

    Conservative: only fires when the grounded family can be classified, so an
    unclassifiable vendor string never causes a false refusal.
    """
    ordered_type = pin_data.ordered_package_type
    if not ordered_type:
        return
    from .utils.package_detector import PackageDetector

    detector = PackageDetector()
    ordered_family = detector.package_family(ordered_type)
    # Only fire on a RECOGNIZED family. package_family() returns raw strings
    # unchanged for things it doesn't know (e.g. the LLM fallback's "SO20"),
    # which must NOT trigger a refusal against a real extracted family.
    if ordered_family not in _KNOWN_PACKAGE_FAMILIES:
        return

    families: List[str] = []
    if pin_data.packages:
        for pkg in pin_data.packages:
            fam = detector.package_family(str(pkg.get("type", "") or ""))
            if fam:
                families.append(fam)
    elif pin_data.package:
        fam = detector.package_family(pin_data.package.type)
        if fam:
            families.append(fam)

    if not families or any(fam == ordered_family for fam in families):
        return

    message = (
        f"Ordering table lists {part_number!r} as a {ordered_type} "
        f"({ordered_family}) package, but the extracted variant(s) are "
        f"{families} — the wrong package shape was read."
    )
    if force_best_effort:
        pin_data.validation_errors = list(pin_data.validation_errors or []) + [message]
        print(f"Warning: {message} Proceeding UNVALIDATED (--force-best-effort).")
        return
    raise ValidationError(
        message + " Re-run with --force-best-effort to override.",
        error_code=ErrorCodes.EXTRACTION_VALIDATION_FAILED,
        details={"ordered_package": ordered_type, "extracted_families": families},
    )


def apply_ordering_ground_truth(
    pin_data: PinData,
    input_path: Path,
    part_number: Optional[str],
    model: str,
    verbose: bool = False,
    force_best_effort: bool = False,
) -> None:
    """Ground the ordered variant in the datasheet's own ordering table.

    The order-code -> package mapping is printed in the sheet, so reading it is
    vendor-agnostic and outranks the LLM's variant choice. Sets
    pin_data.ordered_pin_count/type, then fails closed when that grounded count
    contradicts every extracted variant. A missing/unreadable table is safe:
    selection keeps its prior behaviour.
    """
    try:
        from .pdf_extractor.ordering_table import (
            find_ordering_match,
            find_ordering_match_llm,
            full_pdf_text,
        )

        doc_text = full_pdf_text(str(input_path))
        match = find_ordering_match(doc_text, part_number)
        # Deterministic parsing only covers layouts we hand-coded. When it
        # misses, fall back to the LLM reading the table (grounded against the
        # document text). This fires for single-variant extractions too, not
        # only multi-variant: most wrong-variant parts come out single-variant
        # from non-TI vendors, so without this they get no ground truth at all.
        if match is None and part_number and (pin_data.packages or pin_data.package):
            match = find_ordering_match_llm(
                doc_text, part_number, model=model, verbose=verbose
            )
    except Exception as exc:  # never let table parsing break the pipeline
        if verbose:
            print(f"  Ordering-table lookup skipped: {exc}")
        return

    if not match:
        return
    if match.pin_count:
        pin_data.ordered_pin_count = match.pin_count
    if match.package:
        pin_data.ordered_package_type = match.package
    if verbose:
        print(f"  Ordering table: {match.reason}")

    _enforce_ordered_pin_count(pin_data, part_number, force_best_effort)
    _enforce_ordered_package_family(pin_data, part_number, force_best_effort)


def process_datasheet(
    input_path: Path,
    output_path: Path,
    model: str,
    part_number: Optional[str] = None,
    layout_mode: bool = False,
    pcb_2d_mode: bool = False,
    min_confidence: int = 5,
    verbose: bool = False,
    package_index: Optional[int] = None,
    force_best_effort: bool = False,
) -> bool:
    """
    Main processing pipeline.

    Args:
        input_path: Path to input PDF
        output_path: Path to output GLB file
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
        # Step 1: Detect relevant pages with dynamic min_confidence
        adjusted_min_confidence = get_dynamic_min_confidence(input_path, min_confidence, verbose)
        candidates = detect_relevant_pages(str(input_path), adjusted_min_confidence, verbose)

        # Step 2: Extract content
        content = extract_content(str(input_path), candidates, verbose)

        resolved_part_number = part_number or infer_part_number_hint(
            content.text_content,
            source_name=input_path.name,
        )
        if verbose and resolved_part_number:
            print(f"Resolved part number hint: {resolved_part_number}")

        # Step 3: Extract pin data with LLM
        pin_data = extract_pin_data(
            content,
            model,
            verbose,
            part_number=resolved_part_number,
            force_best_effort=force_best_effort,
        )

        # Ground the ordered variant in the datasheet's own ordering table and
        # fail closed if the grounded pin count contradicts the extraction.
        apply_ordering_ground_truth(
            pin_data,
            input_path,
            resolved_part_number,
            model,
            verbose=verbose,
            force_best_effort=force_best_effort,
        )

        # Step 4: Extract layout with Vision API (if enabled)
        layout_data = None
        if layout_mode:
            layout_data = extract_layout_with_vision(
                str(input_path),
                candidates,
                verbose,
                part_number=resolved_part_number,
            )

        # Step 5: Use Vision layout if available
        custom_layout = layout_data  # Already in correct format {"left_side": [...], ...}
        if custom_layout:
            if verbose:
                print("Note: Using hybrid flow (LLM pins + Vision layout)")
        else:
            if verbose:
                print("Using standard layout based on package type")

        if verbose and pin_data.packages and len(pin_data.packages) > 1:
            from .pdf_extractor.variant_selection import select_package_variant

            selected_package = select_package_variant(
                pin_data,
                part_number=resolved_part_number,
                package_index=package_index,
            )
            selected_type = selected_package.package.get("type", "Unknown")
            print(
                "Selected package variant: %s (index %d)"
                % (selected_type, selected_package.index + 1)
            )
            print(f"  Selection reason: {selected_package.reason}")

        # Fail closed on unknown package geometry before any builder runs;
        # with --force-best-effort this substitutes explicit DIP geometry
        # and records it in validation_errors instead (ARCH-006).
        enforce_known_package_type(
            pin_data,
            part_number=resolved_part_number,
            package_index=package_index,
            force_best_effort=force_best_effort,
        )

        # Step 6: Generate schematic
        if verbose:
            if pcb_2d_mode:
                print(f"\n[5] Generating 2D PCB schematic...")
            else:
                print(f"\n[5] Generating 3D schematic...")

        # Choose schematic builder based on mode
        if pcb_2d_mode:
            # Use the shared package selector so 2D and 3D flows agree.
            package_type, pin_count, _, pin_data_list = pin_data_to_builder_format(
                pin_data,
                part_number=resolved_part_number,
                package_index=package_index,
            )

            # Extract real package dimensions from PDF (overrides hardcoded values)
            extracted_dims = None
            try:
                from .pdf_extractor.dimension_extractor import DimensionExtractor
                # package_type may be just "SOIC" for legacy format; append pin count
                target_pkg_type = (
                    package_type if any(c.isdigit() for c in package_type)
                    else f"{package_type}-{pin_count}"
                )
                extracted_dims = DimensionExtractor().extract(
                    str(input_path),
                    target_package_type=target_pkg_type,
                    hint_pages=candidates,
                    part_number=resolved_part_number,
                )
                if verbose and extracted_dims:
                    print(f"[DimensionExtractor] Extracted dims: {extracted_dims}")
            except Exception as e:
                if verbose:
                    print(f"[DimensionExtractor] Skipping: {e}")

            degraded: List[str] = []
            result = build_pcb_2d_schematic(
                package_type=package_type,
                pin_count=pin_count,
                component_name=pin_data.component_name,
                pin_data=pin_data_list,
                output_path=str(output_path),
                custom_layout=custom_layout,
                extracted_dims=extracted_dims,
                degraded_out=degraded,
            )
            _record_degraded(pin_data, degraded)
        else:
            # 3D mode - adapter handles both formats
            result = build_schematic_from_pin_data(
                pin_data=pin_data,
                output_path=str(output_path),
                custom_layout=custom_layout,
                part_number=resolved_part_number,
                package_index=package_index,
            )

        if not result:
            if pcb_2d_mode:
                print("Error: Failed to generate 2D PCB schematic")
            else:
                print("Error: Failed to generate 3D schematic")
            return False

        # Watermark output that is unvalidated (forced best-effort, or a
        # lossy/unverified footprint approximation recorded above).
        if pin_data.validation_errors and output_path.exists():
            from .core import mark_glb_unvalidated
            mark_glb_unvalidated(str(output_path), pin_data.validation_errors)
            print("Warning: Output is marked UNVALIDATED (validated=false in GLB extras).")

        print(f"\nSuccess! Schematic generated: {output_path}")

        # Show file size
        if output_path.exists():
            file_size = os.path.getsize(str(output_path))
            print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

        # Degraded (unvalidated) output exits 3, not 0.
        _exit_if_degraded(pin_data)
        return True

    except DatasheetParserError as e:
        # Expected domain failures (validation, credentials, fail-closed
        # refusals) — message only; the top-level handler owns exit codes.
        print(f"Error: {e}")
        if verbose:
            print(f"Error code: {e.error_code}")
            if e.details:
                print(f"Details: {e.details}")
        sys.exit(EXIT_DOMAIN_FAILURE)

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        sys.exit(EXIT_DOMAIN_FAILURE)
    # Anything else is a bug: it propagates to main()'s top-level handler,
    # which prints the traceback and exits EXIT_INTERNAL_ERROR.


def process_datasheet_both(pin_data: PinData, output_path: Path,
                            custom_layout=None, part_number: Optional[str] = None,
                            package_index: Optional[int] = None,
                            verbose: bool = False,
                            extracted_dims=None) -> bool:
    """Run both schematic and PCB footprint builders on already-extracted pin data.

    Args:
        pin_data: Extracted PinData (from extract_pin_data)
        output_path: Base output path — suffixes _schematic.glb / _footprint.glb are added
        custom_layout: Optional Vision API layout dict
        part_number: Optional part number for variant selection
        package_index: Optional zero-based package variant index
        verbose: Enable verbose output
        extracted_dims: Optional flat dict of real dimensions from PDF extraction.

    Returns:
        True if both outputs were generated successfully, False otherwise
    """
    schematic_str, footprint_str = _both_output_paths(str(output_path))
    schematic_path = Path(schematic_str)
    footprint_path = Path(footprint_str)

    setup_output_path(schematic_path)
    setup_output_path(footprint_path)

    # --- Schematic (3D pinout diagram) ---
    schematic_ok = False
    try:
        schematic_ok = bool(build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=schematic_str,
            custom_layout=custom_layout,
            part_number=part_number,
            package_index=package_index,
        ))
        if verbose:
            print(f"Schematic: {schematic_str}")
    except DatasheetParserError as e:
        print(f"Schematic refused: {e}")

    # --- PCB footprint (2D) ---
    footprint_ok = False
    try:
        package_type, pin_count, _, pin_data_list = pin_data_to_builder_format(
            pin_data,
            part_number=part_number,
            package_index=package_index,
        )
        degraded: List[str] = []
        footprint_ok = bool(build_pcb_2d_schematic(
            package_type=package_type,
            pin_count=pin_count,
            component_name=pin_data.component_name,
            pin_data=pin_data_list,
            output_path=footprint_str,
            custom_layout=custom_layout,
            extracted_dims=extracted_dims,
            degraded_out=degraded,
        ))
        if footprint_ok:
            _record_degraded(pin_data, degraded)
        if verbose:
            print(f"Footprint: {footprint_str}")
    except DatasheetParserError as e:
        # Fail-closed refusals (grid-array packages, unknown geometry)
        # are expected domain outcomes, not bugs.
        print(f"Failed to generate footprint: {e}")

    if not schematic_ok:
        print(f"Failed to generate schematic: {schematic_str}")
    if not footprint_ok:
        print(f"Failed to generate footprint: {footprint_str}")

    return schematic_ok and footprint_ok


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

  # With layout mode (Vision API for layout extraction)
  python -m src.main datasheet.pdf output.glb --layout-mode

Exit codes:
  0  all requested artifacts were produced
  1  domain failure (unsupported input, fail-closed refusal, validation)
  2  internal error (bug) — traceback printed

  # Verbose output
  python -m src.main datasheet.pdf output.glb --verbose

  # Specify confidence threshold
  python -m src.main datasheet.pdf output.glb --min-confidence 3 --verbose

  # Help the extractor choose the right variant
  python -m src.main datasheet.pdf output.glb --part-number SN74HC595DR

  # Generate both schematic and footprint in one run
  python -m src.main datasheet.pdf NE555.glb --both
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
        "--model",
        default="llama-3",
        help="LLM model to use (default: %(default)s)"
    )

    parser.add_argument(
        "--part-number",
        help="Optional target part number to guide variant selection (e.g., SN74HC595DR)"
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
        "--both",
        action="store_true",
        help="Generate both schematic and PCB footprint GLB files. "
             "Output argument is used as base name: "
             "NE555.glb -> NE555_schematic.glb + NE555_footprint.glb. "
             "Cannot be combined with --pcb-2d."
    )

    parser.add_argument(
        "--package-index",
        type=int,
        default=None,
        help="Zero-based index to force a specific package variant when multiple are extracted (e.g., 0 for first, 1 for second)"
    )

    parser.add_argument(
        "--force-best-effort",
        action="store_true",
        help="Emit output even when extracted pin data fails validation. "
             "The GLB is watermarked with validated=false and the validation "
             "errors in its scene extras. Without this flag, validation "
             "failures abort the run."
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    return parser.parse_args()


def main():
    """CLI entry point owning the exit-code contract (see EXIT_* above)."""
    try:
        _run_cli()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(EXIT_INTERNAL_ERROR)
    except DatasheetParserError as e:
        print(f"Error: {e}")
        sys.exit(EXIT_DOMAIN_FAILURE)
    except Exception:
        import traceback
        traceback.print_exc()
        print("Internal error — this is a bug in datasheet-parser, not a "
              "problem with your datasheet. Please report it with the "
              "traceback above.")
        sys.exit(EXIT_INTERNAL_ERROR)


def _run_cli():
    args = parse_arguments()

    # Mutual exclusion: --both and --pcb-2d cannot be used together
    if args.both and args.pcb_2d:
        print("Error: --both and --pcb-2d are mutually exclusive. "
              "Use --both to generate both outputs, or --pcb-2d for footprint only.")
        sys.exit(1)

    # Validate input file
    input_path = Path(args.input)
    validate_input_file(input_path)

    # Setup output path
    output_path = Path(args.output)
    setup_output_path(output_path)

    if args.both:
        # Run pipeline once, then call both builders
        adjusted_min_confidence = get_dynamic_min_confidence(input_path, args.min_confidence, args.verbose)
        candidates = detect_relevant_pages(str(input_path), adjusted_min_confidence, args.verbose)
        content = extract_content(str(input_path), candidates, args.verbose)

        resolved_part_number = args.part_number or infer_part_number_hint(
            content.text_content, source_name=input_path.name
        )

        try:
            pin_data = extract_pin_data(
                content, args.model, args.verbose,
                part_number=resolved_part_number,
                force_best_effort=args.force_best_effort,
            )
            # Ground the ordered variant in the datasheet's ordering table
            # (also applied in single-output mode via process_datasheet).
            apply_ordering_ground_truth(
                pin_data,
                input_path,
                resolved_part_number,
                args.model,
                verbose=args.verbose,
                force_best_effort=args.force_best_effort,
            )
        except DatasheetParserError as e:
            print(f"Error: {e}")
            sys.exit(EXIT_DOMAIN_FAILURE)

        # Fail closed on unknown package geometry (ARCH-006); with
        # --force-best-effort this substitutes explicit DIP geometry instead.
        try:
            enforce_known_package_type(
                pin_data,
                part_number=resolved_part_number,
                package_index=args.package_index,
                force_best_effort=args.force_best_effort,
            )
        except SchematicGenerationError as e:
            print(f"Error: {e}")
            sys.exit(EXIT_DOMAIN_FAILURE)

        # Extract real package dimensions from PDF for the footprint builder
        extracted_dims = None
        try:
            from .pdf_extractor.dimension_extractor import DimensionExtractor
            package_type_hint, pin_count_hint, _, _ = pin_data_to_builder_format(
                pin_data,
                part_number=resolved_part_number,
                package_index=args.package_index,
            )
            # pin_data_to_builder_format may return just "SOIC" for legacy format;
            # reconstruct full type string e.g. "SOIC-28" for accurate dim matching
            target_pkg_type = (
                package_type_hint if any(c.isdigit() for c in package_type_hint)
                else f"{package_type_hint}-{pin_count_hint}"
            )
            extracted_dims = DimensionExtractor().extract(
                str(input_path),
                target_package_type=target_pkg_type,
                hint_pages=candidates,
                part_number=resolved_part_number,
            )
            if args.verbose and extracted_dims:
                print(f"[DimensionExtractor] Extracted dims: {extracted_dims}")
        except Exception as e:
            print(f"Warning: dimension extraction skipped ({e}); "
                  "JEDEC family defaults will be used.")

        success = process_datasheet_both(
            pin_data=pin_data,
            output_path=output_path,
            part_number=resolved_part_number,
            package_index=args.package_index,
            verbose=args.verbose,
            extracted_dims=extracted_dims,
        )
        if not success:
            sys.exit(EXIT_DOMAIN_FAILURE)

        # Watermark both outputs when unvalidated (forced best-effort, or a
        # lossy/unverified footprint approximation recorded above).
        if pin_data.validation_errors:
            from .core import mark_glb_unvalidated
            for generated in _both_output_paths(str(output_path)):
                if Path(generated).exists():
                    mark_glb_unvalidated(generated, pin_data.validation_errors)
            print("Warning: Outputs are marked UNVALIDATED (validated=false in GLB extras).")

        # Degraded (unvalidated) output exits 3, not 0.
        _exit_if_degraded(pin_data)
    else:
        # Single output mode (existing behaviour)
        process_datasheet(
            input_path=input_path,
            output_path=output_path,
            model=args.model,
            part_number=args.part_number,
            layout_mode=args.layout_mode,
            pcb_2d_mode=args.pcb_2d,
            min_confidence=args.min_confidence,
            verbose=args.verbose,
            package_index=args.package_index,
            force_best_effort=args.force_best_effort,
        )


if __name__ == "__main__":
    main()
