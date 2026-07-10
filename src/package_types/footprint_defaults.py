"""
Real JEDEC package dimensions for PCB footprint generation.

The SchematicParameters returned by get_*_parameters() use exaggerated
"display" proportions tuned for readable schematic symbols (e.g. DIP is
rendered 20mm wide with 2.5mm pitch). Footprints are manufacturing
artifacts and must instead default to real package dimensions; values
extracted from the datasheet PDF override these defaults.

Dimension keys mirror the extracted-dims dict consumed by
PcbFootprintBuilder._apply_extracted_dims():
    e  — lead pitch (mm)
    E  — lead span / through-hole row spacing (mm); drives pad x positions
    E1 — plastic body width (mm); drives the drawn fab outline
    D  — body length (mm)
    D1 — plastic body size on the second axis (quad packages)
    b  — lead width (mm)
    L  — lead foot length (mm)

Sources: JEDEC MS-001 (PDIP), MS-012/MS-013 (SOIC), MO-153 (TSSOP),
MO-150 (SSOP), MO-187 (MSOP), MO-220 (QFN), MS-026 (LQFP/TQFP).
"""

import re
from typing import Dict, Optional

from .package_geometry import PACKAGE_TYPE_ALIASES

# Per-family body lengths by pin count; fall back to a pitch-derived
# estimate when the count is not tabulated.
_SOIC_NARROW_D = {8: 4.9, 14: 8.65, 16: 9.9}
_SOIC_WIDE_D = {16: 10.3, 18: 11.5, 20: 12.8, 24: 15.4, 28: 17.9}
_TSSOP_D = {8: 3.0, 14: 5.0, 16: 5.0, 20: 6.5, 24: 7.8, 28: 9.7}
_SSOP_D = {16: 6.2, 20: 7.2, 24: 8.2, 28: 10.2}
_QFN_BODY = {12: 3.0, 16: 3.0, 20: 4.0, 24: 4.0, 28: 5.0, 32: 5.0, 40: 6.0, 48: 7.0, 64: 9.0}
_QFP_PITCH = {32: 0.8, 44: 0.8, 48: 0.5, 52: 0.65, 64: 0.5, 80: 0.5, 100: 0.5, 144: 0.5}
_DFN_PITCH = {6: 0.65, 8: 0.65, 10: 0.5, 12: 0.5}


def _family(package_type: str) -> Optional[str]:
    """
    Resolve the package *family string* (e.g. "SSOP"), not the PackageType
    enum: the enum collapses families with distinct physical dimensions
    (SSOP/MSOP/SOP all resolve to PackageType.SOIC).
    """
    normalized = re.sub(r"[^A-Z0-9]", "", (package_type or "").upper().split("-")[0])
    # Longest alias prefix wins so "TSSOP16" matches TSSOP, not SSOP/SOP.
    matches = [a for a in PACKAGE_TYPE_ALIASES if normalized.startswith(a)]
    return max(matches, key=len) if matches else None


def _dual_row_body_length(pin_count: int, pitch: float, margin: float = 0.5) -> float:
    """Estimate body length: pin row span plus end margins."""
    return round((pin_count // 2 - 1) * pitch + 2 * margin, 2)


def get_footprint_defaults(package_type: str, pin_count: int) -> Optional[Dict[str, float]]:
    """
    Return real JEDEC dimensions for a package, or None when the family
    has no tabulated footprint data (caller keeps existing parameters).
    """
    family = _family(package_type)

    if family in ("DIP", "PDIP", "CDIP"):
        # 300mil row spacing up to 28 pins, 600mil for wider packages.
        return {
            "e": 2.54,
            "E": 7.62 if pin_count <= 28 else 15.24,
            "E1": 6.35 if pin_count <= 28 else 13.7,
            "D": _dual_row_body_length(pin_count, 2.54, margin=1.3),
        }

    if family in ("SOIC", "SOP"):
        wide = family == "SOP" or pin_count >= 18
        return {
            "e": 1.27,
            "E": 10.3 if wide else 6.0,
            "E1": 7.5 if wide else 3.9,
            "D": (_SOIC_WIDE_D if wide else _SOIC_NARROW_D).get(
                pin_count, _dual_row_body_length(pin_count, 1.27, margin=1.0)
            ),
            "b": 0.41,
            "L": 0.84,
        }

    if family == "TSSOP":
        return {
            "e": 0.65,
            "E": 6.4,
            "E1": 4.4,
            "D": _TSSOP_D.get(pin_count, _dual_row_body_length(pin_count, 0.65)),
            "b": 0.25,
            "L": 0.6,
        }

    if family == "SSOP":
        return {
            "e": 0.65,
            "E": 7.8,
            "E1": 5.3,
            "D": _SSOP_D.get(pin_count, _dual_row_body_length(pin_count, 0.65)),
            "b": 0.3,
            "L": 0.75,
        }

    if family == "MSOP":
        return {
            "e": 0.5 if pin_count >= 10 else 0.65,
            "E": 4.9,
            "E1": 3.0,
            "D": 3.0,
            "b": 0.33,
            "L": 0.53,
        }

    if family == "QFN":
        body = _QFN_BODY.get(pin_count, round((pin_count // 4 - 1) * 0.5 + 1.5, 2))
        return {"e": 0.5, "E": body, "D": body, "b": 0.25, "L": 0.4}

    if family in ("DFN", "WSON", "SON"):
        pitch = _DFN_PITCH.get(pin_count, 0.5)
        return {
            "e": pitch,
            "E": 3.0,
            "D": max(3.0, _dual_row_body_length(pin_count, pitch, margin=0.7)),
            "b": 0.3,
            "L": 0.4,
        }

    if family in ("QFP", "LQFP", "TQFP"):
        pitch = _QFP_PITCH.get(pin_count, 0.5)
        # Lead span: pin row span + shoulders + lead feet on both sides.
        span = round((pin_count // 4 - 1) * pitch + 4.0, 2)
        body = round(span - 2.0, 2)  # MS-026: span = body + 2x (shoulder + foot)
        return {"e": pitch, "E": span, "E1": body, "D": span, "D1": body,
                "b": round(pitch * 0.45, 2), "L": 0.6}

    # BGA, LGA, LCCC, TSOP: no tabulated defaults yet.
    return None
