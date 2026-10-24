"""Deterministic pin-drawing read for non-contiguous numeric groups.

ADV7180: "GPO0 to GPO3" sits on pins 5, 6, 41, 42 and the pin table's printed
order is NOT the pin order (pin 5 is GPO1). Only the pin drawing says which
label sits on which pin; it is read from word positions before any vision call.
"""
from pathlib import Path

import pytest

from src.agentic.repair import read_series_from_drawing

SERIES = ["GPO0", "GPO1", "GPO2", "GPO3"]
PINS = [5, 6, 41, 42]


def _drawing_pdf(tmp_path: Path, labels: dict) -> Path:
    """A page laid out like the ADV7180 48-LQFP drawing plus a pin-table row."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    fs = 8
    page.insert_text((200, 300), "TOP VIEW", fontsize=fs)
    # Left side: label, then the numbered pin box on the same row.
    for row, (pin, name) in enumerate([(5, labels.get(5)), (6, labels.get(6))]):
        y = 200 + row * 11
        if name:
            page.insert_text((100, y), name, fontsize=fs)
        page.insert_text((128, y), str(pin), fontsize=fs)
    # Top side: rotated label above the numbered pin box in the same column.
    for col, (pin, name) in enumerate([(42, labels.get(42)), (41, labels.get(41))]):
        x = 300 + col * 11
        if name:
            page.insert_text((x + 6, 140), name, fontsize=fs, rotate=90)
        page.insert_text((x, 152), str(pin), fontsize=fs)
    # Pin-table row elsewhere on the page: "5, 6, 41, 42   GPO0 to GPO3".
    page.insert_text((60, 500), "5, 6, 41, 42", fontsize=fs)
    page.insert_text((140, 500), "GPO0 to GPO3", fontsize=fs)
    path = tmp_path / "drawing.pdf"
    doc.save(str(path))
    return path


def test_reads_label_next_to_each_pin(tmp_path):
    pdf = _drawing_pdf(tmp_path, {5: "GPO1", 6: "GPO0", 42: "GPO2", 41: "GPO3"})
    assert read_series_from_drawing(pdf, PINS, SERIES) == {
        5: "GPO1", 6: "GPO0", 41: "GPO3", 42: "GPO2"}


def test_ignores_pages_that_are_not_pin_drawings(tmp_path):
    import fitz

    pdf = _drawing_pdf(tmp_path, {5: "GPO1", 6: "GPO0", 42: "GPO2", 41: "GPO3"})
    doc = fitz.open(str(pdf))
    # An application circuit that labels the pins the other way round.
    app = doc.new_page()
    app.insert_text((100, 200), "GPO0", fontsize=8)
    app.insert_text((128, 200), "5", fontsize=8)
    app.insert_text((100, 211), "GPO1", fontsize=8)
    app.insert_text((128, 211), "6", fontsize=8)
    app.insert_text((100, 222), "GPO3", fontsize=8)
    app.insert_text((128, 222), "41", fontsize=8)
    app.insert_text((100, 233), "GPO2", fontsize=8)
    app.insert_text((128, 233), "42", fontsize=8)
    out = tmp_path / "with_app_circuit.pdf"
    doc.save(str(out))
    assert read_series_from_drawing(out, PINS, SERIES) == {
        5: "GPO1", 6: "GPO0", 41: "GPO3", 42: "GPO2"}


def test_fails_closed_when_a_pin_has_no_label(tmp_path):
    pdf = _drawing_pdf(tmp_path, {5: "GPO1", 6: "GPO0", 42: "GPO2"})
    assert read_series_from_drawing(pdf, PINS, SERIES) == {}


ADV7180 = Path.home() / "Downloads/datasheets/ADV7180KST48Z.pdf"


@pytest.mark.skipif(not ADV7180.exists(), reason="ADV7180 datasheet not available")
def test_adv7180_48_lead_drawing():
    # The 64-lead drawing (same labels on pins 12, 13, 55, 56) must not interfere.
    assert read_series_from_drawing(ADV7180, PINS, SERIES) == {
        5: "GPO1", 6: "GPO0", 41: "GPO3", 42: "GPO2"}
