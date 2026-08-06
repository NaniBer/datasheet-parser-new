"""Deterministic PDF -> 3D body end-to-end test.

Drives the real ``--both --body-3d`` pipeline (page detection, content
extraction, pin extraction, dimension extraction, footprint + body build, STEP
export) on a checked-in datasheet PDF and asserts the emitted body STEP
reimports with the expected package geometry.

Determinism: the network LLM/vision seams are patched to RAISE, so the test can
only pass through the deterministic table-parser + text-dimension paths. This
guards against the LLM backend's run-to-run noise (it ignores ``seed``) -- the
test is offline and reproducible in CI. lm358 (DIP-8) is a clean-table part that
the deterministic parser fully covers; MCP3208 (DIP-16) is a second case.

Note: with the vision endpoint blocked, package dimensions fall back to JEDEC
defaults, so the body is (correctly) watermarked ``unverified``. A ``verified``
body requires the vision path to supply standoff A1 (the text parser does not
extract A1); that is exercised separately when vision is available.
"""
from pathlib import Path

import pytest

import src.main as M


def _boom(*args, **kwargs):
    raise RuntimeError("network LLM/vision called -- test is meant to be offline")


def _solids_bbox(step_path: str):
    """Aggregate bounding box over a reimported STEP's solids.

    The compound BoundingBox() of an imported STEP comes back uninitialised
    (infinite) in this OCC build, so reduce over individual solids instead.
    """
    import cadquery as cq

    wp = cq.importers.importStep(step_path)
    solids = wp.solids().vals()
    assert solids, "reimported STEP has no solids"
    xs_min = [s.BoundingBox().xmin for s in solids]
    xs_max = [s.BoundingBox().xmax for s in solids]
    ys_min = [s.BoundingBox().ymin for s in solids]
    ys_max = [s.BoundingBox().ymax for s in solids]
    zs_min = [s.BoundingBox().zmin for s in solids]
    zs_max = [s.BoundingBox().zmax for s in solids]
    return {
        "xlen": max(xs_max) - min(xs_min),
        "ylen": max(ys_max) - min(ys_min),
        "zmin": min(zs_min),
        "zmax": max(zs_max),
    }


def _run_both_body3d(pdf: str, out: Path, monkeypatch):
    """Replicate the CLI --both --body-3d sequence (src/main.py:1697-1777)
    fully offline, and return the emitted body STEP path."""
    # Block every network seam so only deterministic paths can succeed.
    monkeypatch.setattr(M, "LLMClient", _boom)
    monkeypatch.setattr(M, "PageVerifier", _boom)
    monkeypatch.setattr(
        "src.pdf_extractor.dimension_extractor.requests.post", _boom
    )

    from src.pdf_extractor.dimension_extractor import DimensionExtractor

    ip = Path(pdf)
    mc = M.get_dynamic_min_confidence(ip, 5, False)
    candidates = M.detect_relevant_pages(str(ip), mc, False, model="llama-3")
    content = M.extract_content(str(ip), candidates, False)
    part = M.infer_part_number_hint(content.text_content, source_name=ip.name)

    pin_data = M.extract_pin_data(
        content, "llama-3", False, part_number=part, force_best_effort=True
    )
    M.apply_ordering_ground_truth(
        pin_data, ip, part, "llama-3", verbose=False, force_best_effort=True
    )
    M.flag_module_footprint(pin_data, ip, verbose=False)
    M.enforce_known_package_type(
        pin_data, part_number=part, package_index=None, force_best_effort=True
    )

    pkg_hint, pin_count_hint, _, _ = M.pin_data_to_builder_format(
        pin_data, part_number=part, package_index=None
    )
    target = (
        pkg_hint if any(c.isdigit() for c in pkg_hint)
        else f"{pkg_hint}-{pin_count_hint}"
    )
    dims = DimensionExtractor().extract(
        str(ip), target_package_type=target, hint_pages=candidates, part_number=part
    )

    ok = M.process_datasheet_both(
        pin_data=pin_data,
        output_path=out,
        part_number=part,
        package_index=None,
        verbose=False,
        extracted_dims=dims,
        emit_body_3d=True,
    )
    assert ok is True
    return Path(str(out).replace(".glb", "_body.step"))


class TestPdfToBodyEndToEnd:
    def test_lm358_dip8_pdf_to_body_step(self, tmp_path, monkeypatch):
        pdf = "pdfs/lm358.pdf"
        if not Path(pdf).exists():
            pytest.skip(f"{pdf} not checked in")

        out = tmp_path / "lm358.glb"
        step = _run_both_body3d(pdf, out, monkeypatch)

        # The whole chain emitted the body + its footprint/schematic siblings.
        assert step.exists() and step.stat().st_size > 0
        assert (tmp_path / "lm358_footprint.glb").exists()
        assert (tmp_path / "lm358_schematic.glb").exists()

        # DIP-8 geometry: leads run below the board (through-hole), ~300-mil row
        # span, height a couple mm. (JEDEC-default dims: vision blocked.)
        bb = _solids_bbox(str(step))
        assert bb["zmin"] < -1.0, "through-hole leads must protrude below Z=0"
        assert 6.0 < bb["xlen"] < 9.5, bb
        assert 8.0 < bb["ylen"] < 12.5, bb
        assert 1.0 < bb["zmax"] < 6.0, bb

    def test_mcp3208_dip16_pdf_to_body_step(self, tmp_path, monkeypatch):
        pdf = "pdfs/MCP3208.pdf"
        if not Path(pdf).exists():
            pytest.skip(f"{pdf} not checked in")

        out = tmp_path / "mcp3208.glb"
        step = _run_both_body3d(pdf, out, monkeypatch)

        assert step.exists() and step.stat().st_size > 0
        bb = _solids_bbox(str(step))
        # DIP-16: 8 pins/side at 100-mil -> longer body than DIP-8.
        assert bb["zmin"] < -1.0
        assert 6.0 < bb["xlen"] < 9.5, bb
        assert 16.0 < bb["ylen"] < 22.0, bb
