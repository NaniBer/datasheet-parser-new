"""F-04: generated artifacts record dimension provenance (method-level)."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator import build_pcb_2d_schematic
from src.model3d import build_body_model
from src.conformance.checks import check_provenance_recorded, PartContext
from src.conformance.model import CheckStatus


def _footprint(d: Path) -> str:
    out = str(d / "x_footprint.glb")
    build_pcb_2d_schematic(package_type="SOIC-8", pin_count=8, component_name="X",
                           pin_data=[{"number": str(i), "name": f"P{i}"} for i in range(1, 9)],
                           output_path=out)
    return out


def _body(d: Path) -> str:
    result = build_body_model("SOIC-8", 8, "X", None, str(d / "x_body"))
    assert result.success and result.glb_path
    return result.glb_path


def test_f04_footprint_records_provenance():
    outcome = check_provenance_recorded(
        PartContext("x", {"footprint": _footprint(Path(tempfile.mkdtemp()))}))
    assert outcome.status is CheckStatus.PASS


def test_f04_body_records_provenance():
    outcome = check_provenance_recorded(
        PartContext("x", {"body": _body(Path(tempfile.mkdtemp()))}))
    assert outcome.status is CheckStatus.PASS


def test_f04_provenance_carries_a_method():
    g = GLTF2().load_binary(_footprint(Path(tempfile.mkdtemp())))
    root = g.scenes[g.scene or 0].nodes[0]
    prov = (g.nodes[root].extras or {}).get("provenance")
    assert isinstance(prov, dict) and prov.get("method")


def test_f04_skips_without_artifacts():
    assert check_provenance_recorded(PartContext("x", {})).status is CheckStatus.SKIP
