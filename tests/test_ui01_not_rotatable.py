"""UI-01: symbol & footprint are flat top-view artifacts — root locks rotation.

Root-cause fix (rotation lock on the Package root of both artifacts) + the guard
that keeps it from silently regressing. From the QC review (issues S4 / F1).
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.schematic_generator import build_pcb_2d_schematic
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_transform_locked, PartContext
from src.conformance.model import CheckStatus


def _symbol() -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    pd = PinData(component_name="X", package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
                 pins=[Pin(i, f"P{i}") for i in range(1, 9)])
    build_schematic_from_pin_data(pin_data=pd, output_path=out, record=ComponentRecord.from_pin_data(pd))
    return out


def _footprint() -> str:
    out = str(Path(tempfile.mkdtemp()) / "f.glb")
    build_pcb_2d_schematic(package_type="SOIC-8", pin_count=8, component_name="X",
                           pin_data=[{"number": str(i), "name": f"P{i}"} for i in range(1, 9)],
                           output_path=out)
    return out


def _root_htc(glb: str):
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    return (g.nodes[root].extras or {}).get("hideTransformControls")


# --- fix: both roots lock rotation -------------------------------------------
def test_symbol_root_locks_rotation():
    assert _root_htc(_symbol()).get("rotate") == "xyz"


def test_footprint_root_locks_rotation():
    assert _root_htc(_footprint()).get("rotate") == "xyz"


# --- guard: PASS when locked, FAIL if a future change drops the lock ----------
def test_ui01_passes_on_built_artifacts():
    ctx = PartContext("x", {"symbol": _symbol(), "footprint": _footprint()})
    assert check_transform_locked(ctx).status is CheckStatus.PASS


def test_ui01_fails_when_lock_stripped():
    glb = _symbol()
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    ex = dict(g.nodes[root].extras or {})
    ex.pop("hideTransformControls", None)      # simulate a regression
    g.nodes[root].extras = ex
    g.save(glb)
    assert check_transform_locked(PartContext("x", {"symbol": glb})).status is CheckStatus.FAIL


def test_ui01_skips_without_artifacts():
    assert check_transform_locked(PartContext("x", {})).status is CheckStatus.SKIP
