"""Structural validation helpers for extracted pin data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from ..models.pin_data import PinData
    from ..utils.package_detector import PackageDetector
    from .variant_selection import expected_pin_count_from_part_number
except ImportError:  # pragma: no cover - compatibility for top-level imports in legacy scripts
    from src.models.pin_data import PinData
    from src.utils.package_detector import PackageDetector
    from src.pdf_extractor.variant_selection import expected_pin_count_from_part_number
from .non_pin_features import is_non_pin_feature_name


@dataclass
class ExtractionValidationResult:
    """Outcome of validating extracted pin data."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def feedback(self) -> str:
        """Return a compact retry instruction string."""
        lines = ["The previous pin extraction failed validation."]
        if self.errors:
            lines.append("Fix these issues:")
            lines.extend(f"- {error}" for error in self.errors)
        if self.warnings:
            lines.append("Also note:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.append(
            "Return corrected JSON only. Ensure every package has unique pin numbers, "
            "a complete 1..N pin sequence, only numbered electrical pins are included, and a package type that matches the matched variant."
        )
        return "\n".join(lines)


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def _identifier_matches(left: str, right: str) -> bool:
    left_norm = _normalize_identifier(left)
    right_norm = _normalize_identifier(right)

    if not left_norm or not right_norm:
        return False

    return left_norm in right_norm or right_norm in left_norm


def _coerce_pin_number(pin: Any) -> Optional[int]:
    if pin is None:
        return None

    if isinstance(pin, dict):
        value = pin.get("number")
    else:
        value = getattr(pin, "number", None)

    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_pin_name(pin: Any) -> str:
    if pin is None:
        return ""

    if isinstance(pin, dict):
        value = pin.get("name", "")
    else:
        value = getattr(pin, "name", "")

    return str(value or "").strip()


def _iter_packages(pin_data: PinData) -> List[Dict[str, Any]]:
    if pin_data.packages:
        return list(pin_data.packages)

    if pin_data.package:
        return [
            {
                "type": pin_data.package.type,
                "pin_count": pin_data.package.pin_count,
                "pins": pin_data.pins or [],
            }
        ]

    return []


def _validate_package(
    package: Dict[str, Any],
    package_index: int,
    errors: List[str],
    warnings: List[str],
) -> None:
    label = f"package {package_index + 1}"
    package_type = str(package.get("type", "") or "").strip()
    pin_count = package.get("pin_count", 0)
    pins = package.get("pins") or []

    if not package_type or package_type.lower() == "unknown":
        errors.append(f"{label} has an unknown package type")

    try:
        pin_count = int(pin_count)
    except (TypeError, ValueError):
        pin_count = 0

    if pin_count <= 0:
        errors.append(f"{label} has an invalid pin count: {package.get('pin_count')!r}")

    if not pins:
        errors.append(f"{label} has no extracted pins")
        return

    pin_numbers: List[int] = []
    seen_numbers = set()

    for pin_index, pin in enumerate(pins, start=1):
        pin_number = _coerce_pin_number(pin)
        pin_name = _coerce_pin_name(pin)

        if is_non_pin_feature_name(pin_name):
            if pin_number is not None and pin_number > 0:
                # Thermal/exposed pad with an explicit pin number — valid connection.
                warnings.append(
                    f"{label} pin {pin_index} is a package feature ({pin_name!r}) with explicit number {pin_number}; treating as a real pin"
                )
                # fall through — validate it like any other pin
            else:
                errors.append(
                    f"{label} pin {pin_index} is a non-pin package feature ({pin_name!r}) and must not be included in pins"
                )
                continue

        if pin_number is None or pin_number <= 0:
            errors.append(f"{label} pin {pin_index} has an invalid pin number")
            continue

        pin_numbers.append(pin_number)
        if pin_number in seen_numbers:
            errors.append(f"{label} contains duplicate pin number {pin_number}")
        seen_numbers.add(pin_number)

        if not pin_name:
            warnings.append(f"{label} pin {pin_number} has an empty name")

    if pin_count > 0 and len(pins) != pin_count:
        errors.append(
            f"{label} pin count mismatch: package declares {pin_count} pins but {len(pins)} pins were extracted"
        )

    if pin_count > 0:
        expected_numbers = list(range(1, pin_count + 1))
        if sorted(pin_numbers) != expected_numbers:
            missing = [num for num in expected_numbers if num not in pin_numbers]
            extra = [num for num in pin_numbers if num not in expected_numbers]
            detail_parts = []
            if missing:
                detail_parts.append(f"missing {missing}")
            if extra:
                detail_parts.append(f"unexpected {extra}")
            errors.append(
                f"{label} pin numbering is not a complete 1..{pin_count} sequence ({', '.join(detail_parts)})"
            )


def validate_pin_data_extraction(
    pin_data: PinData,
    part_number: Optional[str] = None,
) -> ExtractionValidationResult:
    """
    Validate structural correctness of extracted pin data.

    This is intentionally strict about pin numbering and package consistency,
    because that is the main failure mode we want to catch before generating
    geometry.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if pin_data is None:
        return ExtractionValidationResult(
            is_valid=False,
            errors=["No pin data was returned by the LLM"],
            warnings=[],
        )

    if not pin_data.component_name or pin_data.component_name == "Unknown":
        warnings.append("component_name is missing or unknown")

    if part_number and pin_data.component_name and not _identifier_matches(
        pin_data.component_name,
        part_number,
    ):
        warnings.append(
            f"component_name {pin_data.component_name!r} does not closely match target part number {part_number!r}"
        )

    packages = _iter_packages(pin_data)
    if not packages:
        errors.append("PinData does not contain a package or packages payload")
    else:
        for package_index, package in enumerate(packages):
            _validate_package(package, package_index, errors, warnings)

        # An order-code pin count is ground truth (STM32F103[R]BT7 = 64
        # pins). Extractions that offer no variant with that count are
        # wrong-variant reads of a multi-variant table — the main silent
        # failure mode on STM32-style datasheets.
        implied_pins = expected_pin_count_from_part_number(part_number)
        if implied_pins:
            counts = []
            for package in packages:
                try:
                    counts.append(int(package.get("pin_count") or 0))
                except (TypeError, ValueError):
                    counts.append(0)
            if implied_pins not in counts:
                errors.append(
                    f"target part number {part_number!r} implies a {implied_pins}-pin "
                    f"package, but the extracted variants have {sorted(set(counts))} pins. "
                    f"Extract the {implied_pins}-pin variant's pin-number column."
                )

        if len(packages) > 1 and pin_data.selected_package_index is None and not pin_data.selected_package_type:
            errors.append(
                "multiple package variants were extracted but no selected_package_index or selected_package_type was provided"
            )

        if pin_data.selected_package_index is not None:
            if pin_data.selected_package_index < 0 or pin_data.selected_package_index >= len(packages):
                errors.append(
                    "selected_package_index %r is out of range for %d extracted package variants"
                    % (pin_data.selected_package_index, len(packages))
                )

        if pin_data.selected_package_type:
            detector = PackageDetector()
            selected_family = detector.package_family(pin_data.selected_package_type)
            if selected_family:
                matches = []
                for package in packages:
                    package_type = str(package.get("type", "") or "")
                    if detector.package_family(package_type) == selected_family:
                        matches.append(package_type)
                if not matches:
                    errors.append(
                        f"selected_package_type {pin_data.selected_package_type!r} did not match any extracted package types"
                    )

    return ExtractionValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
    )
