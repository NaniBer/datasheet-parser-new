#!/usr/bin/env python3
"""Slice A live check: print the ComponentRecord pin semantics extracted from a PDF.

    python tools/inspect_extraction.py pdfs/lm358.pdf

Runs the real extraction (LLM) and reports each pin's electrical_type / role /
active_low / nc, plus a contract-validity tally. Read-only; writes no artifacts.
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

from src.main import (
    detect_relevant_pages, extract_content, extract_pin_data,
    get_dynamic_min_confidence, normalize_package, _grounding_source_text,
)
from src.pdf_extractor import infer_part_number_hint
from src.pdf_extractor.deterministic_table_parser import parse_pin_data_from_tables
from src.pdf_extractor.extraction_validator import validate_pin_data_extraction
from src.models import ComponentRecord, validate_pin_semantics


def _detect_path(content, part_number: str) -> str:
    """Mirror extract_pin_data: deterministic table parser wins if it validates,
    otherwise the LLM fallback runs."""
    det = parse_pin_data_from_tables(content, part_number=part_number)
    if det is None:
        return "llm"
    det = normalize_package(det, verbose=False)
    val = validate_pin_data_extraction(
        det, part_number=part_number, source_text=_grounding_source_text(content)
    )
    return "deterministic" if val.is_valid else "llm"


def main() -> int:
    pdf = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "llama-3"
    p = Path(pdf)

    min_conf = get_dynamic_min_confidence(p, 5, False)
    candidates = detect_relevant_pages(str(p), min_conf, False, model=model)
    content = extract_content(str(p), candidates, False)
    part_number = infer_part_number_hint(content.text_content, source_name=p.name)
    path = _detect_path(content, part_number)
    pin_data = extract_pin_data(content, model, False, part_number=part_number,
                                force_best_effort=True)

    rec = ComponentRecord.from_pin_data(pin_data, part_number=part_number)
    v = rec.selected()
    pins = v.pins if v else []
    print(f"PART: {rec.identity.description}  part_number={part_number}  "
          f"variant={v.package_type if v else '-'}  pins={len(pins)}")
    print(f"PATH: {path}")
    rows = [{"n": p.number, "name": p.name, "type": p.electrical_type,
             "role": p.role, "active_low": p.active_low, "nc": p.nc} for p in pins]
    print(json.dumps(rows, indent=1))

    issues = [i for pin in pins for i in validate_pin_semantics(pin)]
    typed = sum(1 for pin in pins if pin.electrical_type)
    roled = sum(1 for pin in pins if pin.role)
    al = sum(1 for pin in pins if pin.active_low)
    nc = sum(1 for pin in pins if pin.nc)
    print(f"SUMMARY: typed={typed}/{len(pins)} roled={roled}/{len(pins)} "
          f"active_low={al} nc={nc} contract_issues={len(issues)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
