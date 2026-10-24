"""The GLB pipeline runs the repair layer's deterministic steps (no LLM).

QC re-check ADV SCH-01/02: /jobs builds the symbol from the CLI pipeline, which
never ran the repair layer, so grouped labels ("GPO0 to GPO3") stayed grouped or
were spread in printed order. The deterministic repairs (ordered variant's pin
table, group expansion, pin-drawing read) cost nothing and now run there too.
"""
import json
from pathlib import Path

import pytest

PDF_BYTES = b"%PDF-1.4\n%fake datasheet\n"


def test_repair_without_llm_makes_no_calls_and_keeps_usage(tmp_path, monkeypatch):
    import src.agentic.repair as R
    import src.chat_bot as chat_bot

    def _no_llm(*a, **k):
        raise AssertionError("LLM called in deterministic-only repair")

    monkeypatch.setattr(chat_bot, "get_completion_from_messages", _no_llm)
    monkeypatch.setattr(R, "_page_texts", lambda p: [(1, "PIN CONFIGURATION\n5, 6, 41, 42 GPO0 to GPO3\n")])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(PDF_BYTES)
    reset = {"n": 0}
    monkeypatch.setattr(chat_bot, "reset_usage", lambda: reset.__setitem__("n", reset["n"] + 1))

    pins = [{"number": n, "name": "GPO0 to GPO3"} for n in (5, 6, 41, 42)]
    pins += [{"number": n, "name": f"P{n}"} for n in (1, 2, 3, 4)]
    rep = R.repair_pins(pins, pdf, "X", use_llm=False)

    names = {p["number"]: p["name"] for p in rep["pins"]}
    assert all(names[n] == "GPO0 to GPO3" for n in (5, 6, 41, 42))  # fail closed
    assert reset["n"] == 0  # the pipeline's LLM usage counter is left alone


ADV7180 = Path.home() / "Downloads/datasheets/ADV7180KST48Z.pdf"
TRUTH = Path.home() / "Downloads/datasheets/truth_table.json"


@pytest.mark.skipif(not (ADV7180.exists() and TRUTH.exists()), reason="ADV7180 datasheet not available")
def test_pipeline_repair_fixes_adv7180_gpo_order():
    from src.main import _apply_deterministic_repair
    from src.models.pin_data import PackageInfo, Pin, PinData

    truth = next(p for p in json.load(open(TRUTH))["parts"] if p["part_number"] == "ADV7180KST48Z")
    gt = {int(k): v for k, v in truth["pinout"].items()}
    extracted = dict(gt)
    for n in (5, 6, 41, 42):
        extracted[n] = "GPO0 to GPO3"  # what the LLM extraction leaves behind
    extracted[24] = "AGND"            # QC run: pin 24 mis-read
    pd = PinData(
        component_name="ADV7180KST48Z",
        package=PackageInfo(type="LQFP-48", pin_count=48, width=0.0, height=0.0),
        pins=[Pin(number=n, name=v) for n, v in sorted(extracted.items())],
    )
    _apply_deterministic_repair(pd, ADV7180, "ADV7180KST48Z")
    got = {p.number: p.name for p in pd.pins}
    norm = lambda s: s.replace("_", "").upper()
    assert {n: norm(got[n]) for n in gt} == {n: norm(v) for n, v in gt.items()}
