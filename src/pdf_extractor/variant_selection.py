"""Helpers for choosing one package variant from extracted pin data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from ..models.pin_data import PinData
    from ..utils.package_detector import PackageDetector
except ImportError:  # pragma: no cover - compatibility for top-level imports in legacy scripts
    from src.models.pin_data import PinData
    from src.utils.package_detector import PackageDetector


def _normalize_label(value: str) -> str:
    """Normalize a label for loose matching."""
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


# ST's STM32 order code encodes the pin count in the letter after the
# device number: STM32F103[R]BT7 -> R -> 64 pins. Only letters with a
# documented meaning are mapped; anything else (including the lowercase
# 'x' wildcard used in datasheet filenames) decodes to None — fail closed.
_STM32_PIN_COUNT_LETTERS = {
    "F": 20, "G": 28, "K": 32, "T": 36, "C": 48,
    "R": 64, "V": 100, "Z": 144, "I": 176,
}
_STM32_ORDER_CODE = re.compile(r"STM32[A-Z]\d{3}([A-Z])")


def expected_pin_count_from_part_number(part_number: Optional[str]) -> Optional[int]:
    """
    Pin count implied by an ST order code, or None.

    "STM32F103RBT7" -> 64, "STM32F103C6" -> 48. Returns None for
    non-STM32 parts and for wildcard family names ("STM32F103X6" —
    the datasheet's 'x' placeholder is not a real pin-count letter),
    so callers never receive a guessed constraint.
    """
    if not part_number:
        return None
    match = _STM32_ORDER_CODE.search(part_number.upper().replace(" ", ""))
    if not match:
        return None
    return _STM32_PIN_COUNT_LETTERS.get(match.group(1))


def _coerce_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _package_records(pin_data: PinData) -> List[Dict[str, Any]]:
    """Return the package entries available for selection."""
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


@dataclass
class PackageVariantSelection:
    """Resolved package variant chosen for downstream geometry generation."""

    index: int
    package: Dict[str, Any]
    reason: str
    ambiguous: bool = False


def _matches_package_type(
    candidate_type: str,
    target_type: str,
    detector: PackageDetector,
) -> bool:
    """Return True when two package type strings describe the same family."""
    candidate_norm = _normalize_label(candidate_type)
    target_norm = _normalize_label(target_type)
    if candidate_norm and candidate_norm == target_norm:
        return True

    candidate_family = detector.package_family(candidate_type)
    target_family = detector.package_family(target_type)
    return candidate_family == target_family and bool(candidate_family)


def select_package_variant(
    pin_data: PinData,
    part_number: Optional[str] = None,
    package_index: Optional[int] = None,
) -> PackageVariantSelection:
    """
    Choose one package variant from the extracted PinData.

    Selection priority:
    1. Explicit package_index override
    2. LLM-provided selected_package_index
    3. LLM-provided selected_package_type
    4. Single available package
    5. Otherwise raise an error instead of guessing
    """
    packages = _package_records(pin_data)
    if not packages:
        raise ValueError("PinData does not contain any package variants")

    detector = PackageDetector()

    def _result(index: int, reason: str, ambiguous: bool = False) -> PackageVariantSelection:
        return PackageVariantSelection(
            index=index,
            package=packages[index],
            reason=reason,
            ambiguous=ambiguous,
        )

    if package_index is not None:
        if 0 <= package_index < len(packages):
            return _result(
                package_index,
                f"Explicit package_index override selected package {package_index + 1}",
            )
        raise IndexError(
            f"Requested package_index {package_index} is out of range for {len(packages)} package variants"
        )

    # A pin count decoded from the order code is ground truth: it outranks
    # the LLM's own selection (STM32F103RBT7 is a 64-pin part regardless of
    # which variant the model preferred).
    implied_pins = expected_pin_count_from_part_number(part_number)
    if implied_pins:
        matches = [
            index for index, package in enumerate(packages)
            if _coerce_count(package.get("pin_count")) == implied_pins
        ]
        if len(matches) == 1:
            return _result(
                matches[0],
                f"Part number {part_number!r} implies {implied_pins} pins; "
                f"selected matching variant {packages[matches[0]].get('type')!r}",
            )

    if pin_data.selected_package_index is not None:
        if 0 <= pin_data.selected_package_index < len(packages):
            reason = (
                f"LLM selected package index {pin_data.selected_package_index + 1}"
            )
            if pin_data.selection_reason:
                reason += f": {pin_data.selection_reason}"
            return _result(pin_data.selected_package_index, reason)

    if pin_data.selected_package_type:
        target_type = pin_data.selected_package_type
        exact_matches: List[int] = []
        family_matches: List[int] = []

        for index, package in enumerate(packages):
            candidate_type = str(package.get("type", "") or "")
            if not candidate_type:
                continue
            if _normalize_label(candidate_type) == _normalize_label(target_type):
                exact_matches.append(index)
            elif _matches_package_type(candidate_type, target_type, detector):
                family_matches.append(index)

        if exact_matches:
            return _result(
                exact_matches[0],
                f"Matched selected_package_type {target_type!r} to extracted package type {packages[exact_matches[0]].get('type')!r}",
            )

        if family_matches:
            return _result(
                family_matches[0],
                f"Matched selected_package_type {target_type!r} to package family {packages[family_matches[0]].get('type')!r}",
            )

    if len(packages) == 1:
        return _result(0, "Only one package variant was extracted")

    message = (
        "Multiple package variants were extracted but no explicit variant selection was provided"
    )
    if part_number:
        message += f" for target part number {part_number!r}"
    message += ". Pass --part-number or ensure the extractor returns selected_package_index/selected_package_type."
    raise ValueError(message)


def pin_data_to_selected_package(
    pin_data: PinData,
    part_number: Optional[str] = None,
    package_index: Optional[int] = None,
) -> Dict[str, Any]:
    """Return the selected package entry for downstream geometry generation."""
    selection = select_package_variant(
        pin_data,
        part_number=part_number,
        package_index=package_index,
    )
    return selection.package
