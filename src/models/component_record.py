"""Component Record v1 — the canonical extraction output schema.

One structured, versioned record that unifies pins + mechanical dimensions +
identity + provenance, replacing the split ``PinData`` + loose ``extracted_dims``
dict. See docs/requirements-matrix.json for the requirements each field
satisfies; the field-by-requirement map lives in the design notes.

PHASE 1 (this file): data model + a compatibility layer only. Nothing here
changes generation, LLM prompts, or extraction behaviour. The compat layer lets
the new record round-trip to/from the legacy ``PinData`` so the existing
pipeline keeps working unchanged:

    ComponentRecord.from_pin_data(pin_data, extracted_dims)   # legacy -> record
    record.to_pin_data()                                      # record -> legacy
    record.selected_mechanical().to_flat_dims()              # record -> extracted_dims

Schema note: the per-pin group is ``RecordPin`` here (the design doc calls it
"Pin"); it is intentionally distinct from the legacy ``models.pin_data.Pin``
(number:int, name, function) so the two can coexist during migration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .pin_data import PinData, PackageInfo, Pin as LegacyPin

# --- controlled vocabularies (documentation + optional validation) ------------
# Fields stay Optional[str] so the *current* extraction (which has none of this)
# is representable; the vocab is what a future extractor should populate.
ELECTRICAL_TYPES = {
    "input", "output", "bidirectional", "power_in", "power_out",
    "passive", "open_collector", "open_drain", "tristate", "analog", "no_connect",
}
PIN_ROLES = {
    "supply", "ground", "clock", "reset", "data", "address", "io",
    "control", "enable", "oscillator", "analog_io", "other",
}
LAND_PATTERN_SOURCES = {"mfr_recommended", "ipc7351b", "dfm", "generic"}
DEVICE_CLASSES = {"R", "C", "L", "D", "LED", "Q", "IC", "J", "P", "SW", "Y", "F", "TP", "FB"}

SCHEMA_VERSION = "1.0"
DEFAULT_UNIT = "mm"
DEFAULT_PERFORMANCE_CLASS = "IPC-2221 Class 2"


@dataclass
class Provenance:
    """Where a datum came from — attachable at record, dimension, or pin level [F-04]."""
    datasheet_url: Optional[str] = None
    revision: Optional[str] = None
    date: Optional[str] = None
    page: Optional[int] = None
    table: Optional[str] = None
    figure: Optional[str] = None
    method: Optional[str] = None            # "table" | "vision" | "text" | "llm"
    extracted_at: Optional[str] = None
    extractor_version: Optional[str] = None


@dataclass
class Dimension:
    """A mechanical value with tolerances [IN-03, F-03]. At least one of
    min/nom/max should be set; ``nominal()`` resolves a single value."""
    min: Optional[float] = None
    nom: Optional[float] = None
    max: Optional[float] = None
    unit: str = DEFAULT_UNIT
    source_value: Optional[str] = None      # as printed, e.g. "0.050 in" [F-02]
    source_unit: Optional[str] = None
    provenance: Optional[Provenance] = None

    def is_empty(self) -> bool:
        return self.min is None and self.nom is None and self.max is None

    def nominal(self) -> Optional[float]:
        """Single representative value: nom, else midpoint(min,max), else min|max."""
        if self.nom is not None:
            return self.nom
        if self.min is not None and self.max is not None:
            return (self.min + self.max) / 2.0
        return self.min if self.min is not None else self.max


@dataclass
class Identity:
    """Part identification + device class [IN-01, SYM-10, SYM-14]."""
    manufacturer: Optional[str] = None
    mpn: Optional[str] = None
    description: Optional[str] = None
    device_class: Optional[str] = None      # -> reference-designator prefix [SYM-10]
    category: Optional[str] = None
    datasheet_url: Optional[str] = None
    datasheet_revision: Optional[str] = None
    datasheet_date: Optional[str] = None
    distributor_refs: Dict[str, str] = field(default_factory=dict)


@dataclass
class ArtifactLinks:
    """Explicit artifact IDs — never filename matching [PL-02]."""
    symbol_id: Optional[str] = None
    footprint_id: Optional[str] = None
    model_id: Optional[str] = None


@dataclass
class Ratings:
    """Design-constraining ratings, when the device class requires them [SYM-16]."""
    voltage: Optional[Dimension] = None
    current: Optional[Dimension] = None
    power: Optional[Dimension] = None
    tolerance: Optional[str] = None
    dielectric: Optional[str] = None
    temperature: Optional[Dimension] = None


@dataclass
class RecordPin:
    """Per-pin electrical semantics [IN-02, SYM-07/04/08/11]. ``number`` is a
    string to support BGA grid refs (e.g. "A1")."""
    number: str
    name: str = ""
    electrical_type: Optional[str] = None   # ELECTRICAL_TYPES [SYM-07]
    role: Optional[str] = None              # PIN_ROLES [SYM-04]
    active_low: bool = False                # [SYM-08]
    nc: bool = False                        # [SYM-11]
    nc_instruction: Optional[str] = None    # "do not connect" vs "tie to GND" [SYM-11]
    hidden: bool = False                    # always false per SYM-05
    bank: Optional[str] = None              # multi-unit split (U1A/U1B) [SYM-06]
    description: Optional[str] = None
    provenance: Optional[Provenance] = None


@dataclass
class Mechanical:
    """Package mechanical dimensions, every field a Dimension [IN-03]."""
    body_length_D: Optional[Dimension] = None
    body_width_E1: Optional[Dimension] = None
    body_height_A: Optional[Dimension] = None      # -> footprint height field [FP-17]
    lead_pitch_e: Optional[Dimension] = None
    lead_width_b: Optional[Dimension] = None
    lead_length_L: Optional[Dimension] = None
    lead_span_E: Optional[Dimension] = None
    standoff_A1: Optional[Dimension] = None
    thermal_pad: Optional[Dict[str, Dimension]] = None   # {"D2":..., "E2":...}
    mounting_holes: List[Dict] = field(default_factory=list)
    max_envelope: Optional[Dict[str, Dimension]] = None  # {"x","y","z"} [3D-04]
    recommended_land_pattern: Optional[Dict] = None      # [PL-04]

    # Flat-dict keys used by the current pipeline (extracted_dims contract).
    _FLAT_MAP = {
        "e": "lead_pitch_e", "E": "lead_span_E", "D": "body_length_D",
        "E1": "body_width_E1", "b": "lead_width_b", "L": "lead_length_L",
        "A": "body_height_A", "A1": "standoff_A1",
    }

    @classmethod
    def from_flat_dims(cls, dims: Optional[Dict], provenance: Optional[Provenance] = None) -> "Mechanical":
        """Build from the legacy flat extracted_dims dict (nominal + b/L tolerances)."""
        m = cls()
        if not dims:
            return m
        for key, attr in cls._FLAT_MAP.items():
            if dims.get(key) is not None:
                d = Dimension(nom=float(dims[key]), provenance=provenance)
                setattr(m, attr, d)
        # tolerance carve-outs the current extractor keeps
        for base, attr in (("b", "lead_width_b"), ("L", "lead_length_L")):
            d = getattr(m, attr)
            lo, hi = dims.get(f"{base}_min"), dims.get(f"{base}_max")
            if lo is not None or hi is not None:
                if d is None:
                    d = Dimension(provenance=provenance)
                    setattr(m, attr, d)
                if lo is not None:
                    d.min = float(lo)
                if hi is not None:
                    d.max = float(hi)
        if dims.get("D2") is not None or dims.get("E2") is not None:
            m.thermal_pad = {}
            if dims.get("D2") is not None:
                m.thermal_pad["D2"] = Dimension(nom=float(dims["D2"]), provenance=provenance)
            if dims.get("E2") is not None:
                m.thermal_pad["E2"] = Dimension(nom=float(dims["E2"]), provenance=provenance)
        return m

    def to_flat_dims(self) -> Dict[str, float]:
        """Reproduce the legacy extracted_dims flat dict for existing consumers."""
        out: Dict[str, float] = {}
        for key, attr in self._FLAT_MAP.items():
            d = getattr(self, attr)
            if d is not None and d.nominal() is not None:
                out[key] = d.nominal()
        for base, attr in (("b", "lead_width_b"), ("L", "lead_length_L")):
            d = getattr(self, attr)
            if d is not None:
                if d.min is not None:
                    out[f"{base}_min"] = d.min
                if d.max is not None:
                    out[f"{base}_max"] = d.max
        if self.thermal_pad:
            for k, d in self.thermal_pad.items():
                if d.nominal() is not None:
                    out[k] = d.nominal()
        return out


@dataclass
class PackageVariant:
    """One package option (the multi-variant case) with its pins + mechanical."""
    variant_id: str
    package_type: str = ""
    package_family: str = ""
    pin_count: int = 0
    land_pattern_source: Optional[str] = None    # LAND_PATTERN_SOURCES [PL-04]
    ipc_name: Optional[str] = None               # [FP-05]
    zero_orientation_deg: int = 0                 # [FP-18]
    keepout_flags: List[str] = field(default_factory=list)   # [FP-19]
    test_point_required: bool = False            # [FP-20]
    mechanical: Mechanical = field(default_factory=Mechanical)
    pins: List[RecordPin] = field(default_factory=list)


@dataclass
class ComponentRecord:
    """The canonical extraction output — one record, all consumers [PL-01]."""
    schema_version: str = SCHEMA_VERSION
    component_id: Optional[str] = None           # stable identity [PL-02, F-07]
    version: int = 1                             # [F-07]
    changelog: List[Dict] = field(default_factory=list)
    status: str = "ok"                           # "ok" | "blocked" [F-01]
    blocking: List[str] = field(default_factory=list)   # missing required data [F-01]
    units: str = DEFAULT_UNIT                    # [F-02]
    performance_class: str = DEFAULT_PERFORMANCE_CLASS  # [F-08]
    identity: Identity = field(default_factory=Identity)
    provenance: Optional[Provenance] = None      # [F-04]
    links: ArtifactLinks = field(default_factory=ArtifactLinks)
    variants: List[PackageVariant] = field(default_factory=list)
    selected_variant: Optional[str] = None       # variant_id used for geometry
    ratings: Optional[Ratings] = None            # [SYM-16]
    # Preserved ordering-table ground truth (kept from legacy PinData).
    ordered_pin_count: Optional[int] = None
    ordered_package_type: Optional[str] = None

    # ---- lookups -------------------------------------------------------------
    def selected(self) -> Optional[PackageVariant]:
        if not self.variants:
            return None
        for v in self.variants:
            if v.variant_id == self.selected_variant:
                return v
        return self.variants[0]

    def selected_mechanical(self) -> Mechanical:
        v = self.selected()
        return v.mechanical if v else Mechanical()

    def is_blocked(self) -> bool:
        return self.status == "blocked"

    def block(self, *missing: str) -> "ComponentRecord":
        """Mark BLOCKED naming the missing required data [F-01]."""
        self.status = "blocked"
        for m in missing:
            if m not in self.blocking:
                self.blocking.append(m)
        return self

    # ---- compatibility layer -------------------------------------------------
    @classmethod
    def from_pin_data(
        cls,
        pin_data: PinData,
        extracted_dims: Optional[Dict] = None,
        part_number: Optional[str] = None,
        provenance: Optional[Provenance] = None,
    ) -> "ComponentRecord":
        """Represent the CURRENT extracted data as a ComponentRecord (lossless
        for what the pipeline captures today). No new information is invented:
        electrical_type stays None; the legacy free-text ``function`` maps to
        ``role``; dims (if any) attach to the selected variant's mechanical."""
        rec = cls(
            component_id=part_number or pin_data.component_name,
            identity=Identity(
                mpn=part_number or pin_data.component_name,
                description=pin_data.component_name,
            ),
            provenance=provenance,
            ordered_pin_count=pin_data.ordered_pin_count,
            ordered_package_type=pin_data.ordered_package_type,
        )

        def _mk_pins(pins) -> List[RecordPin]:
            out = []
            for p in pins or []:
                num = p.get("number") if isinstance(p, dict) else p.number
                name = p.get("name") if isinstance(p, dict) else p.name
                func = p.get("function") if isinstance(p, dict) else getattr(p, "function", None)
                out.append(RecordPin(number=str(num), name=name or "", role=func))
            return out

        variants: List[PackageVariant] = []
        if pin_data.packages:
            for i, pkg in enumerate(pin_data.packages):
                variants.append(PackageVariant(
                    variant_id=f"v{i}",
                    package_type=str(pkg.get("type", "") or ""),
                    pin_count=int(pkg.get("pin_count") or 0),
                    pins=_mk_pins(pkg.get("pins")),
                    # dims aren't per-variant today; attach to the selected one below
                    mechanical=Mechanical(),
                ))
            sel_idx = pin_data.selected_package_index or 0
        elif pin_data.package:
            variants.append(PackageVariant(
                variant_id="v0",
                package_type=pin_data.package.type,
                pin_count=pin_data.package.pin_count,
                pins=_mk_pins(pin_data.pins),
                mechanical=Mechanical(),
            ))
            sel_idx = 0
        else:
            sel_idx = 0

        rec.variants = variants
        if variants:
            sel_idx = sel_idx if 0 <= sel_idx < len(variants) else 0
            rec.selected_variant = variants[sel_idx].variant_id
            # Today's extracted_dims are a single dict for the chosen variant.
            variants[sel_idx].mechanical = Mechanical.from_flat_dims(extracted_dims, provenance)

        if not any(v.pins for v in variants):
            rec.block("pins")
        return rec

    def to_pin_data(self) -> PinData:
        """Reconstruct a legacy PinData so existing generation runs unchanged."""
        def _legacy_pins(pins: List[RecordPin]) -> List[dict]:
            return [{"number": p.number, "name": p.name, "function": p.role} for p in pins]

        component_name = self.identity.mpn or self.identity.description or (self.component_id or "Unknown")

        if len(self.variants) > 1:
            packages = [{
                "type": v.package_type,
                "pin_count": v.pin_count or len(v.pins),
                "width": 0, "height": 0, "pitch": None, "thickness": None,
                "pins": _legacy_pins(v.pins),
            } for v in self.variants]
            sel_idx = next((i for i, v in enumerate(self.variants)
                            if v.variant_id == self.selected_variant), 0)
            return PinData(
                component_name=component_name,
                packages=packages,
                selected_package_index=sel_idx,
                ordered_pin_count=self.ordered_pin_count,
                ordered_package_type=self.ordered_package_type,
            )

        v = self.selected()
        if v is None:
            return PinData(component_name=component_name)
        return PinData(
            component_name=component_name,
            package=PackageInfo(type=v.package_type, pin_count=v.pin_count or len(v.pins),
                                width=0.0, height=0.0),
            pins=[LegacyPin(number=int(re_int(p.number)), name=p.name, function=p.role)
                  for p in v.pins],
            ordered_pin_count=self.ordered_pin_count,
            ordered_package_type=self.ordered_package_type,
        )


def re_int(value) -> int:
    """Best-effort int from a pin-number string ("A1" -> 1, "12" -> 12, else 0)."""
    import re
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else 0
