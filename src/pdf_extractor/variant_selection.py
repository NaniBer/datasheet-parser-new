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
