"""Fix 11 intake-validation tests (tooling only; no parser dependency).

Covers the two heuristics added to ``tools/run_full_flow_eval.py``:
  * MD5 byte-duplicate grouping.
  * Conservative non-datasheet document flagging.

Uses tiny synthetic strings / temp files -- never the real corpus.
"""

import importlib.util
from pathlib import Path

import pytest

# Load the harness module directly by path (``tools`` is not a package).
_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_full_flow_eval.py"
_spec = importlib.util.spec_from_file_location("run_full_flow_eval", _MODULE_PATH)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


# --------------------------------------------------------------------------
# MD5 byte-duplicate grouping
# --------------------------------------------------------------------------

def test_md5_groups_identical_files_together(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    c = tmp_path / "c.pdf"
    a.write_bytes(b"%PDF-1.4 identical bytes")
    b.write_bytes(b"%PDF-1.4 identical bytes")  # byte-for-byte copy of a
    c.write_bytes(b"%PDF-1.4 something else entirely")

    groups = harness.group_by_md5([a, b, c])

    # a and b share one md5; c is alone.
    assert len(groups) == 2
    sizes = sorted(len(names) for names in groups.values())
    assert sizes == [1, 2]
    # The duplicate group contains exactly a.pdf and b.pdf.
    dup_group = next(names for names in groups.values() if len(names) == 2)
    assert dup_group == ["a.pdf", "b.pdf"]


def test_build_intake_marks_duplicates_and_keeps_canonical(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"same")
    b.write_bytes(b"same")

    intake = harness.build_intake([a, b])

    assert len(intake["duplicate_groups"]) == 1
    grp = intake["duplicate_groups"][0]
    assert grp["canonical"] == "a.pdf"           # sorted-first is kept
    assert grp["files"] == ["a.pdf", "b.pdf"]
    # The redundant copy is skipped from scoring, the canonical is not.
    assert intake["skip"]["b.pdf"]["status"] == "DUP_SKIPPED"
    assert intake["skip"]["b.pdf"]["duplicate_of"] == "a.pdf"
    assert "a.pdf" not in intake["skip"]


def test_file_md5_matches_hashlib(tmp_path):
    import hashlib
    p = tmp_path / "x.pdf"
    payload = b"arbitrary content \x00\x01\x02"
    p.write_bytes(payload)
    assert harness.file_md5(p) == hashlib.md5(payload).hexdigest()


# --------------------------------------------------------------------------
# Non-datasheet document flagging
# --------------------------------------------------------------------------

def test_getting_started_guide_is_flagged():
    text = (
        "Getting Started Guide\n"
        "Widget Development Kit\n"
        "This guide walks you through setting up your board step by step.\n"
    )
    flag = harness.classify_non_datasheet(text)
    assert flag is not None
    assert flag["doc_type"] == "getting-started"


def test_tutorial_is_flagged():
    text = "Tutorial: Building your first blinky project on the dev board.\n"
    flag = harness.classify_non_datasheet(text)
    assert flag is not None
    assert flag["doc_type"] == "tutorial"


def test_design_guide_is_flagged():
    text = "ACME1234 Design Guide\nHow to lay out the power stage\n"
    flag = harness.classify_non_datasheet(text)
    assert flag is not None
    assert flag["doc_type"] == "reference-design"


def test_reference_design_header_chrome_is_not_flagged():
    # TI stamps "Reference Design" as a boilerplate nav link on real datasheets.
    # It must NOT trigger a non-datasheet exclusion (regression: 4 real TI
    # datasheets were wrongly dropped by this exact signal).
    text = ("Product Folder Order Now Technical Documents Tools & Software "
            "Support & Community Reference Design\nTPS2514 USB Charging Port "
            "Controller\n")
    assert harness.classify_non_datasheet(text) is None


def test_demo_board_user_guide_is_flagged():
    text = "EVM User's Guide\nDemonstration Board for the ACME1234\n"
    flag = harness.classify_non_datasheet(text)
    assert flag is not None
    assert flag["doc_type"] in {"user-guide", "demo-board"}


def test_normal_datasheet_is_not_flagged():
    text = (
        "LM358\n"
        "Low-Power, Dual Operational Amplifiers\n"
        "Features ... Pin Configuration ... Absolute Maximum Ratings\n"
        "Electrical Characteristics\n"
    )
    assert harness.classify_non_datasheet(text) is None


def test_datasheet_markers_veto_a_body_mention_of_eval_board():
    # A real datasheet whose *body* mentions an evaluation board but whose
    # title block is a normal part heading, with strong datasheet structure.
    text = (
        "TPS62840\n"
        "750-mA Step-Down Converter\n"
        "Absolute Maximum Ratings\n"
        "Electrical Characteristics\n"
        "Pin Configuration\n"
        + ("x " * 500)
        + "An evaluation board is available for this device.\n"
    )
    assert harness.classify_non_datasheet(text) is None


def test_empty_text_is_not_flagged():
    assert harness.classify_non_datasheet("") is None
    assert harness.classify_non_datasheet("   \n  ") is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-p", "no:warnings"]))
