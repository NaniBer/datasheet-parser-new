"""LAY-02: every drawn footprint object owns a layerId (stamp + check)."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator import build_pcb_2d_schematic
from src.conformance.checks import check_every_object_layer_id, PartContext
from src.conformance.model import CheckStatus


def _build_footprint(package_type="SOIC-8", pin_count=8) -> str:
    out = str(Path(tempfile.mkdtemp()) / "x_footprint.glb")
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, pin_count + 1)]
    ok = build_pcb_2d_schematic(package_type=package_type, pin_count=pin_count,
                                component_name="X", pin_data=pins, output_path=out)
    assert ok and Path(out).is_file()
    return out


def test_lay02_smd_all_objects_have_layer_id():
    outcome = check_every_object_layer_id(PartContext("x", {"footprint": _build_footprint()}))
    assert outcome.status is CheckStatus.PASS


def test_lay02_through_hole_all_objects_have_layer_id():
    outcome = check_every_object_layer_id(
        PartContext("x", {"footprint": _build_footprint("DIP-8", 8)}))
    assert outcome.status is CheckStatus.PASS


def test_lay02_copper_and_silk_nodes_carry_expected_layers():
    g = GLTF2().load_binary(_build_footprint("DIP-8", 8))
    by_layer = {}
    for node in g.nodes:
        if node.mesh is None:
            continue
        lid = (node.extras or {}).get("layerId")
        by_layer.setdefault(node.name, set()).add(lid)
    assert by_layer["CopperCirclePad"] == {"F.Cu"}
    assert by_layer["SolderMask"] == {"F.Mask"}
    assert by_layer["HoleCylinderPin"] == {"drill"}
    assert by_layer["CopperCylinderPin"] == {"*.Cu"}
    # BoundingBox (UI helper) is intentionally exempt
    assert by_layer.get("BoundingBox") == {None}


def test_lay02_skips_without_footprint():
    outcome = check_every_object_layer_id(PartContext("x", {}))
    assert outcome.status is CheckStatus.SKIP
