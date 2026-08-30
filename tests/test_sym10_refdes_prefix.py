"""SYM-10: reference-designator prefix correct for device class (build-time verdict).

device_class is populated deterministically (explicit/contract value, else an
'ic' fallback for a powered multi-pin part) and the prefix is stamped on the
symbol designator; the verdict compares them. All deterministic — no LLM.
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord, classify_device_class
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import refdes_prefix_verdict
from src.conformance.fixtures import FIXTURES
from src.conformance.runner import discover_artifacts, evaluate_part
from src.conformance.model import CheckStatus


def _pd(dc=None, pkg="SOT-23-3", n=3, names=None) -> PinData:
    names = names or [f"P{i}" for i in range(1, n + 1)]
    return PinData(component_name="X", device_class=dc,
                   package=PackageInfo(type=pkg, pin_count=n, width=0, height=0),
                   pins=[Pin(i, nm) for i, nm in enumerate(names, 1)])


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _designator(glb: str) -> str:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    dn = next(c for c in g.nodes[root].children if g.nodes[c].name == "DesignatorName")
    return (g.nodes[dn].extras or {}).get("value")


_IC8 = dict(pkg="SOIC-8", n=8, names=["VCC"] + [f"IO{i}" for i in range(2, 8)] + ["GND"])


# --- device_class classifier -------------------------------------------------
def test_classify_device_class():
    assert classify_device_class(_pd(dc="transistor")) == "transistor"
    assert classify_device_class(_pd(dc="RESISTOR")) == "resistor"   # normalised
    assert classify_device_class(_pd(dc="widget")) is None           # off-contract
    assert classify_device_class(_pd(**_IC8)) == "ic"                # powered multi-pin
    assert classify_device_class(_pd(n=3)) is None                   # can't guess R/C/D


# --- prefix stamped on the symbol designator from the class ------------------
def test_designator_stamped_from_class():
    assert _designator(_build(_pd(dc="transistor"))) == "Q"
    assert _designator(_build(_pd(dc="resistor", pkg="SOIC-8", n=2, names=["A", "B"]))) == "R"
    assert _designator(_build(_pd(**_IC8))) == "U"                   # ic -> U


# --- verdict passes on match, fails on mismatch ------------------------------
def test_sym10_verdict_pass_and_fail():
    glb = _build(_pd(dc="transistor"))
    ok, _ = refdes_prefix_verdict(glb, "transistor")
    assert ok is True
    bad, _ = refdes_prefix_verdict(glb, "resistor")   # same 'Q' symbol, wrong class
    assert bad is False


# --- LLM parse path carries device_class (mocked response, no network) -------
def test_llm_parse_reads_device_class():
    from src.llm.client import LLMClient
    from src.models import refdes_prefix
    resp = ('{"component_name":"BC847","device_class":"transistor",'
            '"package":{"type":"SOT-23-3","pin_count":3},'
            '"pins":[{"number":1,"name":"B"},{"number":2,"name":"E"},{"number":3,"name":"C"}]}')
    pd = LLMClient()._parse_llm_response(resp)
    assert pd.device_class == "transistor"
    rec = ComponentRecord.from_pin_data(pd)
    assert refdes_prefix(rec.identity.device_class) == "Q"   # class -> prefix


# --- end-to-end through the driver + runner ----------------------------------
def test_sym10_graded_pass_through_driver():
    import tools.gen_conformance as gc
    fx = next(f for f in FIXTURES if f.key == "sot23q")
    part_dir = Path(tempfile.mkdtemp()) / fx.key
    _, build_results = gc.generate_family(fx, part_dir)
    assert "SYM-10" in build_results
    report = evaluate_part(fx.key, discover_artifacts(part_dir, base=fx.key),
                           extra_results=build_results)
    by_id = {r.rule_id: r for r in report.results}
    assert by_id["SYM-10"].status is CheckStatus.PASS, by_id["SYM-10"].message
