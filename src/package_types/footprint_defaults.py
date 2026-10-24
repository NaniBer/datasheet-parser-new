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
_QSOP_D = {8: 3.0, 16: 4.9, 20: 5.2, 24: 6.15, 28: 7.06}  # JEDEC MO-137
_QFN_BODY = {12: 3.0, 16: 3.0, 20: 4.0, 24: 4.0, 28: 5.0, 32: 5.0, 40: 6.0, 48: 7.0, 64: 9.0}
_QFP_PITCH = {32: 0.8, 44: 0.8, 48: 0.5, 52: 0.65, 64: 0.5, 80: 0.5, 100: 0.5, 144: 0.5}
# JEDEC MS-026 nominal body size (E1 = D1, mm) for square LQFP/TQFP by pin
# count. The lead span (E = D) is body + 2.0 mm (1.0 mm lead protrusion per
# side, MS-026). Pin counts not listed fall back to a pitch-derived estimate.
_QFP_BODY = {32: 7.0, 44: 10.0, 48: 7.0, 52: 10.0, 64: 10.0, 80: 12.0, 100: 14.0, 128: 14.0, 144: 20.0}
_DFN_PITCH = {6: 0.65, 8: 0.65, 10: 0.5, 12: 0.5}

# Power-tab / through-hole tab families (TO-220, DPAK/TO-252, D2PAK/TO-263,
# TO-247). These are recognised for *classification only* so the upstream
# family detector no longer returns None and the 3D body layer can route them
# to its power-tab template. They deliberately have NO entry in
# get_footprint_defaults (it returns None for them) — a TO-220-style tab does
# not fit the SMD/DIP pad grids modelled here, so fabricating defaults would
# make the footprint builder emit a wrong pad layout.
#
# Keys are separator-stripped aliases; values are the canonical family token.
# TO-252 is the JEDEC name for DPAK and TO-263 for D2PAK, so they collapse to a
# single token each.
_POWER_TAB_ALIASES = {
    "TO220": "TO220",
    "TO247": "TO247",
    "TO252": "DPAK",
    "DPAK": "DPAK",
    "TO263": "D2PAK",
    "D2PAK": "D2PAK",
}

# Geometry aliases whose canonical family token differs from the alias itself,
# so they reuse an existing real pad grid: LFCSP is ADI's QFN (same leadless
# perimeter grid) and XSON is a leadless SON variant (e.g. SOT833-1).
_GEOMETRY_CANONICAL = {"LFCSP": "QFN", "XSON": "SON", "SOT833": "SON"}

# NXP/JEDEC SOT833-1 — the 8-pin XSON outline (e.g. 74LVC1G99). It is a *very*
# small leadless SON (body 1.0 x 1.95 mm, 0.5 mm pitch, 2 rows of 4), so it must
# NOT inherit the generic SON-8 grid (~3.0 x 3.35 mm, 0.65 mm pitch) which
# oversizes the body and courtyard ~3x. Values are the published SOT833-1
# outline; b/L reuse the 0.5 mm-pitch leadless lead dims shared with QFN/HVSSOP
# (not invented). Leadless => body edge is the terminal span (E = E1, D = D1).
# There is no exposed thermal pad on this logic package, so D2/E2 are omitted
# (a real EP would only ever come from the datasheet via extracted_dims).
_SOT833_1_XSON8 = {
    "e": 0.5,
    "E": 1.0,
    "E1": 1.0,
    "D": 1.95,
    "D1": 1.95,
    "b": 0.25,
    "L": 0.4,
}


def has_thermal_pad_outline(package_type: str) -> bool:
    """True when the package outline carries an exposed thermal pad.

    Leadless families (QFN/LFCSP/DFN/WSON/SON) do, except XSON / SOT833: these
    small-signal leadless outlines (74LVC1G99 in SOT833-1) have NO thermal pad,
    though they canonicalise to SON. The footprint and the symbol both use this
    so the symbol never carries an EPAD pin the footprint has no pad for.
    """
    if _family(package_type) not in ("QFN", "DFN", "WSON", "SON"):
        return False
    return not re.search(r"XSON|SOT\s*-?\s*833", package_type or "", re.I)


def _family(package_type: str) -> Optional[str]:
    """
    Resolve the package *family string* (e.g. "SSOP"), not the PackageType
    enum: the enum collapses families with distinct physical dimensions
    (SSOP/MSOP/SOP all resolve to PackageType.SOIC).
    """
    # Strip separators entirely ("SOT-23-8" -> "SOT238") so families whose
    # names contain digits still prefix-match their alias.
    def _strip(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", s.upper())

    normalized = _strip(package_type or "")
    # Longest alias prefix wins so "TSSOP16" matches TSSOP, not SSOP/SOP.
    # A letter right after the alias disqualifies it ("SOJ" is not "SO").
    # (stripped_alias, canonical_family_token) pairs; for the geometry aliases
    # the family token is the alias itself, for power-tab it is the mapped token.
    matches = []
    for alias in PACKAGE_TYPE_ALIASES:
        stripped = _strip(alias)
        if normalized.startswith(stripped) and not normalized[len(stripped):len(stripped) + 1].isalpha():
            matches.append((stripped, _GEOMETRY_CANONICAL.get(stripped, stripped)))
    for stripped, canonical in _POWER_TAB_ALIASES.items():
        if normalized.startswith(stripped) and not normalized[len(stripped):len(stripped) + 1].isalpha():
            matches.append((stripped, canonical))
    # Whole-word fallback for suffix forms like "32-LEAD LFCSP": the prefix
    # match above only catches a family token at the start of the string.
    if not matches:
        tokens = set(re.split(r"[^A-Z0-9]+", (package_type or "").upper()))
        for alias in PACKAGE_TYPE_ALIASES:
            stripped = _strip(alias)
            if stripped in tokens:
                matches.append((stripped, _GEOMETRY_CANONICAL.get(stripped, stripped)))
        for stripped, canonical in _POWER_TAB_ALIASES.items():
            if stripped in tokens:
                matches.append((stripped, canonical))
    return max(matches, key=lambda m: len(m[0]))[1] if matches else None


def _dual_row_body_length(pin_count: int, pitch: float, margin: float = 0.5) -> float:
    """Estimate body length: pin row span plus end margins."""
    return round((pin_count // 2 - 1) * pitch + 2 * margin, 2)


def get_footprint_defaults(package_type: str, pin_count: int) -> Optional[Dict[str, float]]:
    """
    Return real JEDEC dimensions for a package, or None when the family
    has no tabulated footprint data (caller keeps existing parameters).
    """
    family = _family(package_type)

    # SOT833-1 / XSON8: a tiny leadless SON variant that must not inherit the
    # generic SON-8 grid (which oversizes body + courtyard ~3x). Keyed off the
    # documented outline name (SOT833) or XSON with 8 pins — never a part
    # number. Other XSON pin counts map to different outlines (SOT886/SOT891…)
    # we do not tabulate, so they fall through to the generic SON branch.
    normalized = re.sub(r"[^A-Z0-9]", "", (package_type or "").upper())
    if "SOT833" in normalized or ("XSON" in normalized and pin_count == 8):
        return dict(_SOT833_1_XSON8)

    if family in ("DIP", "PDIP", "CDIP"):
        # 300mil row spacing up to 28 pins, 600mil for wider packages. The body
        # end margin is ~0.8 mm per side, matching the JEDEC MS-001 body length
        # (DIP-16 = 19.3 mm, DIP-8 = 9.27 mm); the old 1.3 mm margin over-ran the
        # body by ~1 mm (PGA2311P came out 20.38 mm long, #69).
        return {
            "e": 2.54,
            "E": 7.62 if pin_count <= 28 else 15.24,
            "E1": 6.35 if pin_count <= 28 else 13.7,
            "D": _dual_row_body_length(pin_count, 2.54, margin=0.8),
            # Lower-lead cross-section maxima (JEDEC MS-001: b 0.356-0.558,
            # c 0.203-0.381). Published as b_max/c_max — the keys the through-hole
            # drill derivation reads — so the hole = lead diagonal + clearance
            # sizes to the widest lead (~0.93 mm) instead of sticking at the
            # 0.83 mm floor (#71). Plain b/L are intentionally omitted so the
            # 3D leg geometry and symbol insets are left untouched.
            "b_max": 0.56,
            "c_max": 0.38,
        }

    if family == "SOT23":
        # JEDEC MO-178: 2.9 x 1.63 body, 2.8 lead span for all pin counts;
        # 3/5/6-pin variants sit on a 0.95 pitch, the 8-pin on 0.65.
        return {
            "e": 0.65 if pin_count >= 8 else 0.95,
            "E": 2.8,
            "E1": 1.63,
            "D": 2.9,
            "b": 0.30 if pin_count >= 8 else 0.40,
            "L": 0.45,
        }

    if family in ("SOIC", "SOP", "SO"):
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

    if family == "QSOP":
        # JEDEC MO-137: 0.635mm pitch, 3.9mm body, ~6.0mm lead span. Without
        # this it fell to SOIC's 1.27mm or SSOP's 0.65mm grid.
        return {
            "e": 0.635,
            "E": 6.0,
            "E1": 3.9,
            "D": _QSOP_D.get(pin_count, _dual_row_body_length(pin_count, 0.635, margin=0.6)),
            "b": 0.3,
            "L": 0.65,
        }

    if family in ("HVSSOP", "VSSOP"):
        # 0.5mm pitch, 3x3mm body class. HVSSOP used to normalize to SSOP and
        # land on 0.65mm; VSSOP/HVSSOP are 0.5mm.
        return {
            "e": 0.5,
            "E": 4.9,
            "E1": 3.0,
            "D": _dual_row_body_length(pin_count, 0.5, margin=0.65),
            "b": 0.25,
            "L": 0.5,
        }

    if family == "QFN":
        # Leadless: terminals sit on the underside at the body edge, so the
        # molded body IS the E/D span. Publish it as E1/D1 too, so the drawn
        # fab outline is sourced from a real body dimension (not a lead span).
        # D2/E2 is the exposed thermal pad: datasheet dims override, but when
        # absent ~0.65x body is a safe JEDEC-typical default (QFN EPs run
        # ~0.5-0.75 of body). Real datasheet D2/E2 flows in via extracted_dims.
        body = _QFN_BODY.get(pin_count, round((pin_count // 4 - 1) * 0.5 + 1.5, 2))
        ep = round(body * 0.65, 2)
        return {"e": 0.5, "E": body, "E1": body, "D": body, "D1": body,
                "b": 0.25, "L": 0.4, "D2": ep, "E2": ep}

    if family in ("DFN", "WSON", "SON"):
        # Leadless, like QFN: body edge = terminal span, so E1 = E and D1 = D.
        # Body-based E1/D1 lets the fab outline come from the real body; the
        # pad-clearance clamp only tightens it where the body would overlap pads.
        pitch = _DFN_PITCH.get(pin_count, 0.5)
        body_l = max(3.0, _dual_row_body_length(pin_count, pitch, margin=0.7))
        # Exposed pad ~0.6x body (datasheet D2/E2 overrides via extracted_dims).
        return {
            "e": pitch,
            "E": 3.0,
            "E1": 3.0,
            "D": body_l,
            "D1": body_l,
            "b": 0.3,
            "L": 0.4,
            "D2": round(body_l * 0.6, 2),
            "E2": round(3.0 * 0.6, 2),
        }

    if family in ("QFP", "LQFP", "TQFP"):
        pitch = _QFP_PITCH.get(pin_count, 0.5)
        # Body (E1/D1) is the JEDEC MS-026 standard size; the lead span (E/D) is
        # body + 2.0 mm (1.0 mm lead protrusion per side). The old
        # (pins/4 - 1) * pitch + 4.0 span over-stated 48-pin parts by ~0.5 mm,
        # so the body came out 7.5 (clamped to 7.38, #61) instead of the real
        # 7.0, and the SMD pads sat ~0.25 mm too far out with a short heel (#59).
        body = _QFP_BODY.get(pin_count, round((pin_count // 4 - 1) * pitch + 2.0, 2))
        span = round(body + 2.0, 2)
        # IPC-7351 sizes the pad from the longest foot (L_max); MS-026 gull-wing
        # L runs 0.45-0.75 mm, so L_max = 0.75 (the nominal 0.6 left the pad
        # ~0.15 mm short of the land pattern, #12).
        return {"e": pitch, "E": span, "E1": body, "D": span, "D1": body,
                "b": round(pitch * 0.45, 2), "L": 0.6, "L_max": 0.75}

    # BGA, LGA, LCCC, TSOP: no tabulated defaults yet.
    return None
