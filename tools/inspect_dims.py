#!/usr/bin/env python3
"""Slice B live check: dimension tolerances + provenance for a PDF.

    python tools/inspect_dims.py pdfs/lm358.pdf SOIC-8 LM358

Runs the real DimensionExtractor (vision/text) and reports each mechanical
field's min/nom/max and provenance (page/method). Read-only; writes nothing.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from src.pdf_extractor.dimension_extractor import DimensionExtractor
from src.main import detect_relevant_pages, get_dynamic_min_confidence
from src.models import Mechanical

_FIELDS = [("e", "lead_pitch_e"), ("E", "lead_span_E"), ("D", "body_length_D"),
           ("E1", "body_width_E1"), ("b", "lead_width_b"), ("L", "lead_length_L"),
           ("A", "body_height_A"), ("A1", "standoff_A1")]


def main() -> int:
    pdf = sys.argv[1]
    pkg = sys.argv[2] if len(sys.argv) > 2 else None
    pn = sys.argv[3] if len(sys.argv) > 3 else None

    # Mirror the real pipeline: pass detected candidate pages so the extractor
    # skips the expensive full-page vision scan (one call PER PAGE).
    p = Path(pdf)
    min_conf = get_dynamic_min_confidence(p, 5, False)
    candidates = detect_relevant_pages(str(p), min_conf, False, model="llama-3")
    dims = DimensionExtractor().extract(pdf, target_package_type=pkg,
                                        hint_pages=candidates, part_number=pn)
    print("FLAT:", json.dumps(dims))
    if not dims:
        print("SUMMARY: no dimensions extracted")
        return 0

    m = Mechanical.from_flat_dims(dims)
    rows = []
    for name, attr in _FIELDS:
        d = getattr(m, attr)
        if d is not None:
            rows.append({"field": name, "min": d.min, "nom": d.nom, "max": d.max,
                         "page": d.provenance.page if d.provenance else None,
                         "method": d.provenance.method if d.provenance else None})
    print("MECHANICAL:", json.dumps(rows, indent=1))
    with_tol = sum(1 for r in rows if r["min"] is not None or r["max"] is not None)
    print(f"SUMMARY: fields={len(rows)} with_tolerance={with_tol} "
          f"source={dims.get('dims_source')} page={dims.get('_page')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
