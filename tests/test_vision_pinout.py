"""Deterministic tests for the vision pinout plumbing (no network).

The endpoint call itself is exercised manually; here we lock in the parts that
must be robust regardless of the model: response parsing, variant splitting,
variant selection, and page rendering.
"""

import pytest

from src.llm.vision_pinout import (
    parse_pins_from_text,
    split_variant_groups,
    select_variant,
)
from src.pdf_extractor.page_render import render_page_png


def test_parse_pins_from_markdown_and_multi_array():
    # Two package variants, code-fenced — the shape that broke strict json.loads.
    raw = """```json
    { "pins": [ {"number": 1, "name": "EN1"}, {"number": 2, "name": "VCC"} ] },
    { "pins": [ {"number": "1", "name": "A"}, {"number": "2", "name": "B"} ] }
    ```"""
    pins = parse_pins_from_text(raw)
    assert [(p["number"], p["name"]) for p in pins] == [
        (1, "EN1"), (2, "VCC"), (1, "A"), (2, "B")
    ]


def test_parse_pins_empty_on_junk():
    assert parse_pins_from_text("no pins here") == []
    assert parse_pins_from_text("") == []


def test_split_variant_groups_at_number_resets():
    pins = [{"number": n, "name": str(n)} for n in [1, 2, 3, 4, 1, 2]]
    groups = split_variant_groups(pins)
    assert [len(g) for g in groups] == [4, 2]


def test_select_variant_prefers_exact_count_then_largest():
    g14 = [{"number": i, "name": "x"} for i in range(1, 15)]
    g20 = [{"number": i, "name": "y"} for i in range(1, 21)]
    # exact match wins
    assert select_variant([g14, g20], expected_pin_count=14) is g14
    # no exact match -> largest
    assert select_variant([g14, g20], expected_pin_count=8) is g20
    # no expectation -> largest
    assert select_variant([g14, g20]) is g20
    assert select_variant([]) == []


def test_render_page_png_produces_png_bytes():
    png = render_page_png("pdfs/foo.pdf", 1, dpi=100)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    assert len(png) > 1000


def test_render_page_out_of_range_raises():
    with pytest.raises(IndexError):
        render_page_png("pdfs/foo.pdf", 9999)


# --------------------------- vision fallback trigger ---------------------------

class _Content:
    def __init__(self, text, pages=(1,), tables=None):
        self.text_content = text
        self.tables = tables or []
        self.pages = list(pages)


def test_vision_fallback_replaces_pins_when_text_ungrounded(monkeypatch):
    import src.main as m
    import src.llm.vision_pinout as vp
    from src.models.pin_data import PinData, Pin

    # Text names appear nowhere in the source -> low grounding -> vision fires.
    content = _Content("--- Page 1 ---\nunrelated prose with no pin names")
    pd = PinData(component_name="X", pins=[Pin(1, "FOO"), Pin(2, "BAR"), Pin(3, "BAZ")])
    monkeypatch.setattr(
        vp, "extract_pinout_best_page",
        lambda *a, **k: [{"number": 1, "name": "Base"},
                         {"number": 2, "name": "Collector"},
                         {"number": 3, "name": "Emitter"}],
    )
    m._apply_vision_fallback(pd, content, "x.pdf", "X")
    assert [p.name for p in pd.pins] == ["Base", "Collector", "Emitter"]
    assert pd.extraction_method == "Vision"
    assert pd.validation_errors and any("vision" in e for e in pd.validation_errors)


def test_vision_fallback_skips_when_well_grounded(monkeypatch):
    import src.main as m
    import src.llm.vision_pinout as vp
    from src.models.pin_data import PinData, Pin

    # Text pins are grounded in the source -> vision is not consulted (gated).
    content = _Content("--- Page 1 ---\n1 VCC\n2 GND\n3 OUT")
    pd = PinData(component_name="X", pins=[Pin(1, "VCC"), Pin(2, "GND"), Pin(3, "OUT")])
    calls = {"n": 0}

    def _spy(*a, **k):
        calls["n"] += 1
        return []
    monkeypatch.setattr(vp, "extract_pinout_best_page", _spy)
    m._apply_vision_fallback(pd, content, "x.pdf", "X")
    assert calls["n"] == 0                                     # vision never called
    assert [p.name for p in pd.pins] == ["VCC", "GND", "OUT"]  # unchanged


def test_vision_fallback_keeps_text_when_vision_empty(monkeypatch):
    import src.main as m
    import src.llm.vision_pinout as vp
    from src.models.pin_data import PinData, Pin

    content = _Content("--- Page 1 ---\nunrelated prose")
    pd = PinData(component_name="X", pins=[Pin(1, "FOO"), Pin(2, "BAR")])
    monkeypatch.setattr(vp, "extract_pinout_best_page", lambda *a, **k: [])
    m._apply_vision_fallback(pd, content, "x.pdf", "X")
    assert [p.name for p in pd.pins] == ["FOO", "BAR"]  # no confident vision -> keep text
