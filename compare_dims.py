"""
Batch comparison: extracted PDF dims vs hardcoded defaults.
Uses already-detected page candidates as hints to skip the slow full-page scan.
Usage: python3 -u compare_dims.py
"""
import os
import sys

sys.path.insert(0, ".")

from src.pdf_extractor.dimension_extractor import DimensionExtractor
from src.pdf_extractor.page_detector import PageDetector
from src.package_types import get_schematic_parameters

PDFS = [
    ("pdfs/74HC595_TI.pdf",  "SOIC-16", 16),
    ("pdfs/FT232R.pdf",      "SSOP-28", 28),
]

extractor = DimensionExtractor()

header = "{:<22} {:<12} {:<10} {:<10} {:<10} {:<10} {:<10}  {}".format(
    "PDF", "Package", "e(pitch)", "E(body_w)", "D(body_h)", "b(pad_w)", "L(pad_l)", "Notes"
)
print(header)
print("-" * len(header))
sys.stdout.flush()

for pdf_path, pkg, pins in PDFS:
    name = os.path.basename(pdf_path)
    try:
        params = get_schematic_parameters(pkg, pins)
        he = params.pin_pitch
        hE = params.body_width
        hD = params.body_height
        hb = params.pin_geometry.leg_width
        hL = params.pin_geometry.leg_length

        # Use page detector to find candidates (fast, text-based — no API calls)
        with PageDetector(pdf_path) as detector:
            candidates = detector.detect_relevant_pages(min_confidence=2)
        print(f"  {name}: {len(candidates)} candidate page(s) found by detector")
        sys.stdout.flush()

        dims = extractor.extract(pdf_path, target_package_type=pkg, hint_pages=candidates)

        if dims:
            ee = dims.get("e", he)
            eE = dims.get("E", hE)
            eD = dims.get("D", hD)
            eb = dims.get("b", hb)
            eL = dims.get("L", hL)

            changed = []
            if abs(ee - he) > 0.01: changed.append("e")
            if abs(eE - hE) > 0.1:  changed.append("E")
            if abs(eD - hD) > 0.1:  changed.append("D")
            if abs(eb - hb) > 0.01: changed.append("b")
            if abs(eL - hL) > 0.01: changed.append("L")

            note = ("DIFF: " + ",".join(changed)) if changed else "matches hardcoded"
            row = "{:<22} {:<12} {:<10.3f} {:<10.3f} {:<10.3f} {:<10.3f} {:<10.3f}  {}".format(
                name, pkg, ee, eE, eD, eb, eL, note
            )
            print(row)
            if changed:
                hard = "  hardcoded:          {:<10.3f} {:<10.3f} {:<10.3f} {:<10.3f} {:<10.3f}".format(
                    he, hE, hD, hb, hL
                )
                print(hard)
        else:
            note = "no match — hardcoded: e={:.3f} E={:.3f} D={:.3f} b={:.3f} L={:.3f}".format(
                he, hE, hD, hb, hL
            )
            print("{:<22} {:<12} {}".format(name, pkg, note))

        sys.stdout.flush()

    except Exception as ex:
        print("{:<22} {:<12} ERROR: {}".format(name, pkg, ex))
        sys.stdout.flush()
