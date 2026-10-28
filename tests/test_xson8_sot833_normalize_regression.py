"""Regression: XSON8 (SOT833-1) footprint must not regress to a bare 'SON'.

The 74LVC1G99 ships in SOT833-1 (XSON8): a tiny 1.0 x 1.95 mm, 8-pin leadless
outline with NO thermal pad. PackageDetector.normalize_package_name('XSON8')
used to collapse to bare 'SON', which (a) made the builder's XSON/SOT833 epad
suppression miss it -> a spurious exposed pad "9", and (b) made
get_footprint_defaults fall back to the generic ~3 mm SON body -> oversized.

The outline identity (SOT833/XSON) must survive normalization so the builder and
footprint defaults keep the no-epad, tiny-body behavior, WITHOUT losing the
SON-family grid (_family) and WITHOUT over-suppressing a genuine SON-8 that has a
real thermal pad.
"""
import pytest

from src.utils.package_detector import PackageDetector
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
from src.package_types.footprint_defaults import get_footprint_defaults, _family


# A SOT833-1 datasheet-style dim set WITH a bogus D2/E2 (extraction noise). A
# real SOT833-1 has no exposed pad; D2/E2 here must be ignored, not turned into
# a centre pad.
_XSON8_DIMS_WITH_BOGUS_EPAD = {
    "e": 0.5, "E": 1.0, "E1": 1.0, "D": 1.95, "D1": 1.95,
    "b": 0.25, "L": 0.4, "D2": 1.2, "E2": 0.6,
}


@pytest.mark.parametrize("raw", ["XSON8", "XSON-8", "xson8"])
def test_normalize_xson8_keeps_sot833_identity(raw):
    norm = PackageDetector().normalize_package_name(raw)
    # Must NOT collapse to the bare SON family label...
    assert norm != "SON", f"{raw} regressed to bare 'SON'"
    # ...and must keep a token the builder regex + defaults can recognize.
    assert "SOT833" in norm.upper() or "XSON" in norm.upper(), norm


def test_sot833_identity_still_resolves_to_son_grid():
    # The pad GRID must stay SON-family for both the normalized XSON8 and the
    # already-correct SOT833-1 spelling.
    norm = PackageDetector().normalize_package_name("XSON8")
    assert _family(norm) == "SON"
    assert _family("SOT833-1") == "SON"


def test_package_family_loose_matching_preserved():
    # Regression guard: before the fix XSON8 collapsed to bare 'SON' whose loose-
    # matching family is 'QFN'. Keep that family for the SOT833/XSON identity so
    # an ordered 'XSON' still matches an extracted 'SOT833-1' variant (no false
    # "wrong package shape" refusal).
    d = PackageDetector()
    assert d.package_family("XSON8") == "QFN"
    assert d.package_family("SOT833-1") == "QFN"
    assert d.package_family("XSON") == "QFN"


def test_xson8_build_has_no_epad_and_tiny_body():
    # Simulate the real pipeline: name is normalized BEFORE reaching the builder.
    norm = PackageDetector().normalize_package_name("XSON8")

    b = PcbFootprintBuilder(norm, 8, "X", extracted_dims=_XSON8_DIMS_WITH_BOGUS_EPAD)
    assert b._has_exposed_pad is False, "bogus D2/E2 produced a spurious pad 9"

    # Tiny-body defaults (no extracted body dims -> falls back to defaults).
    d = get_footprint_defaults(norm, 8)
    assert (d["E1"], d["D1"]) == (1.0, 1.95), d


def test_genuine_son8_with_thermal_pad_still_gets_epad():
    # Regression guard against over-suppression: a real SON-8 that DOES carry a
    # thermal pad must still get its exposed pad.
    norm = PackageDetector().normalize_package_name("SON8")
    assert norm == "SON"
    b = PcbFootprintBuilder(norm, 8, "U", extracted_dims=_XSON8_DIMS_WITH_BOGUS_EPAD)
    assert b._has_exposed_pad is True, "genuine SON-8 lost its thermal pad"


@pytest.mark.parametrize("raw,family", [
    ("PFB-48", "TQFP"), ("PFB", "TQFP"), ("RHB-32", "QFN"), ("DW-16", "SOIC"),
    ("PW-20", "TSSOP"), ("N-16", "DIP"), ("DGK-8", "MSOP"),
])
def test_bare_ti_package_designator_names_its_family(raw, family):
    # Deployed run 28 Oct: TL16C2550PFBR came back as "PFB-48", which fell
    # through to the generic SON-48 fallback (2-row leadless pads, phantom EPAD).
    from src.utils.package_detector import PackageDetector

    assert PackageDetector().normalize_package_name(raw) == family


@pytest.mark.parametrize("raw", ["FN-44", "TQFP-48", "SOIC-8", "SOT833-1"])
def test_non_designator_names_are_unchanged_by_the_designator_rule(raw):
    from src.utils.package_detector import PackageDetector

    assert PackageDetector().normalize_package_name(raw) == {
        "FN-44": "FN-44", "TQFP-48": "TQFP", "SOIC-8": "SOIC", "SOT833-1": "SOT833-1"}[raw]
