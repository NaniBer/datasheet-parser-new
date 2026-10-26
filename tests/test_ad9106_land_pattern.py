"""QC re-check 2026-10-23, AD9106 (LFCSP-32, CP-32-12) footprint.

FP-03 body 3.28 mm (pulled inside the pads), FP-08 mask openings merged
(0.102 mm margin at 0.5 mm pitch), FP-09 lands 1.10 mm reaching 1.75 mm from
centre and EP 3.25 mm, FP-10 corner pads drawn shorter than stored, FP-11 EP
paste one 100 % block. Target: the ADI / Ultra Librarian CP_32_12 pattern.
"""
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest
from pygltflib import GLTF2

from src.pdf_extractor.text_dimensions import page_package_name, parse_adi_outline
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder

# AD9106 datasheet p.58 as PyMuPDF reads it (stacked max / nom / min).
ADI_PAGE = """OUTLINE DIMENSIONS
0.50
0.40
0.30
0.50
BSC
EXPOSED
PAD
0.05 MAX
0.02 NOM
0.20 REF
0.30
0.25
0.18
5.10
5.00 SQ
4.90
0.80
0.75
0.70
0.25 MIN
3.75
3.60 SQ
3.55
Figure 61. 32-Lead Lead Frame Chip Scale Package [LFCSP]
"""

DIMS = {"e": 0.5, "D": 5.0, "E": 5.0, "D1": 5.0, "E1": 5.0, "D2": 3.6, "E2": 3.6,
        "D2_max": 3.75, "E2_max": 3.75, "b": 0.25, "b_max": 0.3, "L": 0.4,
        "L_max": 0.5, "A": 0.8}


def test_adi_outline_page_is_read_without_vision():
    assert parse_adi_outline(ADI_PAGE) == DIMS
    assert page_package_name(ADI_PAGE) == "LFCSP-32"


def test_adi_outline_needs_a_pitch_and_skips_ambiguous_leads():
    assert parse_adi_outline(ADI_PAGE.replace("BSC", "TYP")) == {}
    two_plain = ADI_PAGE.replace("0.80\n0.75\n0.70\n", "")
    assert "b" not in parse_adi_outline(two_plain)


@pytest.fixture(scope="module")
def ad9106():
    return PcbFootprintBuilder("LFCSP-32", 32, "AD9106", extracted_dims=dict(DIMS))


def test_lands_match_the_adi_pattern(ad9106):
    b = ad9106
    assert b.pad_spec["length"] == pytest.approx(0.80)
    assert not b._pad_length_override                  # corner pads not cut (FP-10)
    for p in b.pin_positions:
        x0, x1, y0, y1 = b._pad_bbox(p)
        inner, outer = sorted(map(abs, (x0, x1) if p.side in ("left", "right") else (y0, y1)))
        assert inner == pytest.approx(2.05) and outer == pytest.approx(2.85), p.pin_number
    assert (b._epad_w, b._epad_l) == (3.75, 3.75)       # EP max, not 3.25 (FP-09)
    fab_hw, fab_hh, *_ = b._layer_half_dims()
    assert (fab_hw, fab_hh) == (2.5, 2.5)               # real 5 x 5 body (FP-03)


def test_mask_keeps_a_web_between_every_opening(ad9106):
    b = ad9106
    m = b.mask_margin
    assert m == pytest.approx(0.05)
    assert b.params.pin_pitch - b.pad_spec["width"] - 2 * m >= b.MASK_MIN_DAM - 1e-9
    assert 2.05 - b._epad_w / 2 - 2 * m >= b.MASK_MIN_DAM - 1e-9


def test_glb_ep_paste_windows_and_pin_data(ad9106):
    out = str(Path(tempfile.mkdtemp()) / "fp.glb")
    assert ad9106.save_glb(out, [{"number": str(i), "name": f"P{i}"} for i in range(1, 33)])
    g = GLTF2().load_binary(out)
    ep = next(i for i, nd in enumerate(g.nodes) if nd.name == "33")
    kids = {g.nodes[c].name: g.nodes[c] for c in g.nodes[ep].children}
    paste = kids["PasteMask"]
    assert paste.extras["layerId"] == "F.Paste"
    prims = g.meshes[paste.mesh].primitives
    lo = np.min([g.accessors[p.attributes.POSITION].min for p in prims], axis=0)
    hi = np.max([g.accessors[p.attributes.POSITION].max for p in prims], axis=0)
    span = hi[0] - lo[0]
    assert span < 3.75                                  # windows, not the full pad
    windows = ad9106.ep_paste_windows()
    assert len(windows) == 4
    area = sum(w * h for *_, w, h in windows) / 3.75 ** 2
    assert 0.5 <= area <= 0.8                           # FP-11
    pd = next(nd for nd in g.nodes if nd.name == "1").extras["pinData"]
    assert (pd["length"], pd["solder_mask_margin"]) == (pytest.approx(0.8), 0.05)
