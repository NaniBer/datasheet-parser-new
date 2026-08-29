"""Phase 0 — the rule inventory.

Every ``must`` rule from the IDEEZA Component Generation Spec that governs a
generated artifact, encoded as a checkable row. ``check`` names the function in
``checks.py`` that enforces it; ``None`` means the rule is inventoried but not
yet automated (it will report ``UNRUN``, honestly counted against coverage).

This table is the backbone: it is the single place that says what "correct"
means and how much of it we can currently prove. Growing coverage = turning
``check=None`` rows into real checks, one defect class at a time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Rule:
    id: str
    tier: str          # "must" | "should"
    artifact: str      # "symbol" | "footprint" | "body" | "cross" | "meta"
    title: str
    check: Optional[str] = None   # key in the checks registry, or None = UNRUN


# Ordered by artifact then rule id. `check` is wired to checks.REGISTRY.
RULES: List[Rule] = [
    # --- cross-artifact / validation batteries ---------------------------------
    Rule("V-01", "must", "cross", "Symbol pin set maps 1:1 to footprint pad set", "pin_pad_set_mapping"),
    Rule("V-02", "must", "cross", "Footprint dimensions match the datasheet", None),
    Rule("V-03", "must", "cross", "3D model aligns to footprint (origin, leads, height)", None),
    Rule("V-05", "must", "meta", "Machine-readable validation report emitted", "report_emitted"),

    # --- schematic symbol ------------------------------------------------------
    Rule("SYM-01", "must", "symbol", "Layout does not follow physical pin order", "layout_not_physical"),
    Rule("SYM-02", "must", "symbol", "Every pin endpoint on the 2.54 mm grid", "symbol_grid"),
    Rule("SYM-04", "must", "symbol", "Pins grouped by electrical function", "functional_grouping"),
    Rule("SYM-05", "must", "symbol", "Power and ground pins visible", "power_ground_visible"),
    Rule("SYM-07", "must", "symbol", "Electrical pin types assigned truthfully", "symbol_electrical_types"),
    Rule("SYM-08", "must", "symbol", "Active-low notation consistent", "active_low_notation"),
    Rule("SYM-10", "must", "symbol", "Reference designator prefix correct for class", None),
    Rule("SYM-11", "must", "symbol", "No-connect pins handled explicitly", "nc_pins_marked"),
    Rule("SYM-12", "must", "symbol", "No duplicated or skipped pin numbers", "symbol_pin_numbering"),

    # --- land pattern / footprint ----------------------------------------------
    Rule("FP-03", "must", "footprint", "Origin at body centroid", "origin_at_centroid"),
    Rule("FP-04", "must", "footprint", "Pads numbered CCW from pin 1", "pad_numbering_perimeter"),
    Rule("FP-06", "must", "footprint", "Courtyard / assembly / silk present and distinct", "footprint_layers_present"),
    Rule("FP-07", "must", "footprint", "Silkscreen clear of pads by >= 0.20 mm", "silk_pad_clearance"),
    Rule("FP-08", "must", "footprint", "Pin-1 / polarity marker present", "pin1_marker_present"),
    Rule("FP-10", "must", "footprint", "THT annular ring >= 0.05 mm after tolerance", "annular_ring"),
    Rule("FP-14", "must", "footprint", "Copper-to-copper pad clearance >= minimum", "pad_pad_clearance"),
    Rule("FP-15", "must", "footprint", "Mask/paste derived from copper", "mask_from_copper"),
    Rule("FP-17", "must", "footprint", "Component height recorded on footprint", "component_height_present"),
    Rule("FP-18", "must", "footprint", "Pick-and-place zero orientation set", "pnp_zero_orientation"),

    # --- layers ----------------------------------------------------------------
    Rule("LAY-01", "must", "footprint", "Full layer tree generated", "footprint_layers_present"),
    Rule("LAY-02", "must", "footprint", "Every object owns its layerId", "every_object_layer_id"),
    Rule("LAY-05", "must", "footprint", "THT pads are multi-layer with explicit drill", "tht_pad_multilayer"),
    Rule("LAY-06", "must", "footprint", "Silk-to-copper collision check ran", "silk_pad_clearance"),

    # --- 3D model --------------------------------------------------------------
    Rule("3D-01", "must", "body", "STEP emitted as primary format", "body_step_present"),
    Rule("3D-02", "must", "body", "Z=0 at seating plane, origin at centroid", "body_seating_plane"),
    # 3D-03 needs per-lead identity absent from the tessellated GLB; it is
    # supplied at build time (body Lead_<pin> vs footprint pad map) via the
    # generation driver's extra_results, so it stays check=None for static grading.
    Rule("3D-03", "must", "body", "Per-pin leads numbered to match pads", None),
    Rule("3D-06", "must", "body", "Clean, closed, watertight solids", "body_watertight"),
    Rule("3D-09", "must", "body", "Units declared as millimetres", "body_units_mm"),
    Rule("3D-11", "must", "body", "Model XY envelope inside courtyard", "body_within_courtyard"),

    # --- foundations -----------------------------------------------------------
    Rule("F-01", "must", "meta", "No dimension invented (flag and stop)", None),
    Rule("F-04", "must", "meta", "Datasheet provenance recorded on artifacts", None),
]


def implemented_rules() -> List[Rule]:
    return [r for r in RULES if r.check is not None]


def coverage() -> tuple:
    """(implemented_must, total_must) — how much of the MUST spec is automated."""
    must = [r for r in RULES if r.tier == "must"]
    impl = [r for r in must if r.check is not None]
    return len(impl), len(must)
