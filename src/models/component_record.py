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
from .pin_classifier import classify_pin_name

# --- controlled OUTPUT VOCABULARIES (the extraction output contract) ----------
# Finalized in docs/extraction-output-contract.md. Every enum has an explicit
# "unknown" member so the extractor is NEVER forced to guess: an unstated field
# resolves to unspecified / other / False, and required-but-missing dimensions
# BLOCK the record (F-01) rather than being invented.

# ERC electrical types (IEEE-315 / SnapMagic / spec SYM-07). Closed set — drives
# electrical-rule checking, so no free-form values.
ELECTRICAL_TYPES = {
    "input", "output", "bidirectional", "tri_state", "passive",
    "power_in", "power_out", "open_collector", "open_emitter",
    "no_connect", "unspecified",
}
# Non-canonical spellings normalized into the set. open_drain == open_collector
# for ERC (a pin that only sinks); tri-state/3state == tri_state; etc.
ELECTRICAL_TYPE_ALIASES = {
    "open_drain": "open_collector", "opendrain": "open_collector",
    "tristate": "tri_state", "tri-state": "tri_state", "3state": "tri_state",
    "nc": "no_connect", "no-connect": "no_connect", "noconnect": "no_connect",
    "power": "power_in", "power_input": "power_in", "power_output": "power_out",
    "analog": "passive", "": "unspecified", "unknown": "unspecified", "free": "unspecified",
}

# Functional roles -> symbol side (spec SYM-04). Roles are for LAYOUT/grouping;
# electrical_type is for ERC. A pin carries both (VCC = power_in + supply).
PIN_ROLES = {
    "supply", "ground", "input", "output", "io", "clock", "reset",
    "enable", "control", "address", "data", "analog", "oscillator",
    "thermal", "nc", "other",
}
ROLE_ALIASES = {
    "vcc": "supply", "vdd": "supply", "power": "supply",
    "gnd": "ground", "vss": "ground", "analog_io": "analog",
    "no_connect": "nc", "dnc": "nc", "reserved": "nc", "": "other",
}
# SnapEDA convention (QC S1): everything is LEFT or RIGHT (no top/bottom). The
# RIGHT column carries power/outputs/ground/thermal (VCC upper, outputs middle,
# GND lower); the LEFT column carries control, inputs, I/O, data/analog, other.
ROLE_SIDE = {
    "supply": "right", "ground": "right", "thermal": "right", "output": "right",
    "input": "left", "io": "left", "data": "left", "analog": "left",
    "clock": "left", "reset": "left", "enable": "left", "control": "left",
    "address": "left", "oscillator": "left",
    "nc": "unplaced", "other": "left",
}

# Device classes -> reference-designator prefix (spec SYM-10). device_class holds
# the semantic class; the prefix is derived via REFDES_PREFIX (fixes the old
# stub that conflated class "IC"/"LED" with prefixes).
DEVICE_CLASSES = {
    "resistor", "capacitor", "inductor", "ferrite_bead", "diode", "led",
    "transistor", "ic", "connector", "plug", "switch", "crystal",
    "oscillator", "fuse", "test_point", "other",
}
REFDES_PREFIX = {
    "resistor": "R", "capacitor": "C", "inductor": "L", "ferrite_bead": "FB",
    "diode": "D", "led": "D", "transistor": "Q", "ic": "U", "connector": "J",
    "plug": "P", "switch": "SW", "crystal": "Y", "oscillator": "Y",
    "fuse": "F", "test_point": "TP", "other": "U",
}

LAND_PATTERN_SOURCES = {"mfr_recommended", "ipc7351b", "dfm", "generic"}


# --- contract validation helpers (non-raising; used by a future validator) ----
def _norm(value) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def normalize_electrical_type(value) -> Optional[str]:
    """Canonical electrical_type, applying aliases; None if not in the contract."""
    if value is None:
        return None
    v = _norm(value)
    v = ELECTRICAL_TYPE_ALIASES.get(v, v)
    return v if v in ELECTRICAL_TYPES else None


def normalize_role(value) -> Optional[str]:
    """Canonical role, applying aliases; None if not in the contract."""
    if value is None:
        return None
    v = _norm(value)
    v = ROLE_ALIASES.get(v, v)
    return v if v in PIN_ROLES else None


def role_side(role: Optional[str]) -> str:
    """Symbol side a role places on (SYM-04); defaults left for unknown roles."""
    return ROLE_SIDE.get(role or "other", "left")


def classify_device_class(pin_data: "PinData") -> Optional[str]:
    """Best-effort device class for the reference-designator prefix (SYM-10).

    Prefers an explicit/extracted ``pin_data.device_class`` (normalised to the
    contract). Otherwise a conservative deterministic fallback: a multi-pin part
    that exposes both power and ground reads as an ``ic`` (prefix ``U``).
    Geometry cannot distinguish R/C/D/etc., so those are never guessed — the
    class stays None and ``refdes_prefix`` yields the safe default ``U``.
    """
    explicit = _norm(getattr(pin_data, "device_class", None))
    if explicit in DEVICE_CLASSES:
        return explicit
    pins = pin_data.pins or []
    names = " ".join((p.name or "").upper() for p in pins)
    has_supply = any(tok in names for tok in ("VCC", "VDD", "VS", "V+"))
    has_ground = any(tok in names for tok in ("GND", "VSS", "VEE"))
    if len(pins) >= 6 and has_supply and has_ground:
        return "ic"
    return None


# A "concrete" role is one that carries functional-grouping information. The
# catch-all ``other`` and any unknown/None are NOT concrete — they tell us
# nothing about which side a pin belongs on.
def role_coverage(roles: List[Optional[str]]) -> float:
    """Fraction of pins that carry a concrete (non-``other``) functional role."""
    if not roles:
        return 0.0
    concrete = sum(1 for r in roles if normalize_role(r) not in (None, "other"))
    return concrete / len(roles)


def functional_layout_applicable(roles: List[Optional[str]]) -> bool:
    """SYM-04 gate: enable functional (role-based) layout for this part.

    Conservative by design (see docs/extraction-output-contract.md and the
    Sub-step 4 decision doc): grouping is only meaningful when the highest-value
    anchors — power and ground — are both concretely identified AND at least half
    the pins carry a concrete role. Below the gate, callers fall back to the
    legacy physical layout, so partially/unclassified parts stay byte-identical.

    Single source of truth: the 4b generator uses this to decide layout, and the
    SYM-04 conformance check uses it to decide whether to grade grouping — so the
    check never penalises a part the generator legitimately left physical.
    """
    normalized = [normalize_role(r) for r in roles]
    has_supply = "supply" in normalized
    has_ground = "ground" in normalized
    return has_supply and has_ground and role_coverage(roles) >= 0.5


def refdes_prefix(device_class: Optional[str]) -> str:
    """Reference-designator prefix for a device class (SYM-10); 'U' if unknown."""
    return REFDES_PREFIX.get(_norm(device_class), "U")


def validate_pin_semantics(pin: "RecordPin") -> List[str]:
    """Return contract violations for a pin's enum fields (empty == valid).

    Non-raising: unknown/None values are allowed at the model level (the
    extractor may legitimately not know), but off-contract *concrete* values are
    reported so a future validation gate can catch them.
    """
    issues: List[str] = []
    if pin.electrical_type is not None and pin.electrical_type not in ELECTRICAL_TYPES:
        issues.append(f"pin {pin.number}: electrical_type {pin.electrical_type!r} off-contract")
    if pin.role is not None and pin.role not in PIN_ROLES:
        issues.append(f"pin {pin.number}: role {pin.role!r} off-contract")
    return issues

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
    # Phase-2 lossless passthrough: the exact flat extracted_dims dict this
    # Mechanical was built from, so to_flat_dims() reproduces it byte-for-byte
    # (incl. keys the structured fields don't yet model: dims_source, c, D1, ...).
    # None once dims are populated structurally (Phase 3+), where to_flat_dims
    # derives from the structured fields instead.
    raw_flat: Optional[Dict[str, float]] = None

    # Flat-dict keys used by the current pipeline (extracted_dims contract).
    _FLAT_MAP = {
        "e": "lead_pitch_e", "E": "lead_span_E", "D": "body_length_D",
        "E1": "body_width_E1", "b": "lead_width_b", "L": "lead_length_L",
        "A": "body_height_A", "A1": "standoff_A1",
    }

    @classmethod
    def from_flat_dims(cls, dims: Optional[Dict], provenance: Optional[Provenance] = None) -> "Mechanical":
        """Build from the flat extracted_dims dict.

        Slice B: preserves per-field min/nom/max tolerances (was b/L only) and a
        record-level Provenance from the extractor's reserved keys (``_page`` /
        ``dims_source``). Purely additive to the model; the flat dict — and thus
        what the builders read — is unchanged (``raw_flat`` passthrough)."""
        m = cls()
        if not dims:
            return m
        m.raw_flat = dict(dims)          # exact passthrough for lossless round-trip

        # Record-level provenance from the reserved keys, unless one was passed.
        prov = provenance
        if prov is None and (dims.get("_page") is not None or dims.get("dims_source") or dims.get("_table")):
            prov = Provenance(
                page=int(dims["_page"]) if dims.get("_page") is not None else None,
                table=dims.get("_table"),
                method=dims.get("dims_source"),
            )

        for key, attr in cls._FLAT_MAP.items():
            if dims.get(key) is not None:
                setattr(m, attr, Dimension(nom=float(dims[key]), provenance=prov))

        # Slice B: attach min/max tolerances for every mapped field.
        for key, attr in cls._FLAT_MAP.items():
            lo, hi = dims.get(f"{key}_min"), dims.get(f"{key}_max")
            if lo is None and hi is None:
                continue
            d = getattr(m, attr)
            if d is None:
                d = Dimension(provenance=prov)
                setattr(m, attr, d)
            if lo is not None:
                d.min = float(lo)
            if hi is not None:
                d.max = float(hi)

        # Thermal pad (nominal + tolerances when present).
        for tk in ("D2", "E2"):
            if any(dims.get(f"{tk}{sfx}") is not None for sfx in ("", "_min", "_max")):
                m.thermal_pad = m.thermal_pad or {}
                d = Dimension(provenance=prov)
                if dims.get(tk) is not None:
                    d.nom = float(dims[tk])
                if dims.get(f"{tk}_min") is not None:
                    d.min = float(dims[f"{tk}_min"])
                if dims.get(f"{tk}_max") is not None:
                    d.max = float(dims[f"{tk}_max"])
                m.thermal_pad[tk] = d
        return m

    def to_flat_dims(self) -> Dict[str, float]:
        """Reproduce the legacy extracted_dims flat dict for existing consumers.

        Phase 2: when built from a flat dict, return that exact dict (lossless,
        including keys the structured fields don't model). Otherwise derive from
        the structured Dimensions."""
        if self.raw_flat is not None:
            return dict(self.raw_flat)
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
    # Legacy pipeline flags carried through so the compat layer is lossless for
    # what the builders + watermark read (not new information — mirrors PinData).
    validation_errors: Optional[List[str]] = None
    footprint_unsupported_reason: Optional[str] = None

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
                device_class=classify_device_class(pin_data),
            ),
            provenance=provenance,
            ordered_pin_count=pin_data.ordered_pin_count,
            ordered_package_type=pin_data.ordered_package_type,
            validation_errors=list(pin_data.validation_errors) if pin_data.validation_errors else None,
            footprint_unsupported_reason=pin_data.footprint_unsupported_reason,
        )

        def _mk_pins(pins) -> List[RecordPin]:
            out = []
            for p in pins or []:
                is_dict = isinstance(p, dict)

                def g(key):
                    return p.get(key) if is_dict else getattr(p, key, None)

                # Slice A: carry the contract fields onto the record, normalizing
                # to the canonical vocab. role falls back to the legacy function.
                name = g("name") or ""
                etype = normalize_electrical_type(g("electrical_type"))
                role = normalize_role(g("role")) or normalize_role(g("function"))
                active_low = bool(g("active_low"))

                # Slice A.2: fill-only name classifier. Only fills fields the
                # extractor left empty; never overrides an existing value, and
                # only ever ADDS active_low (name-marker based). Ambiguous names
                # resolve to None -> stay unspecified/other (no guessing).
                c_type, c_role, c_active = classify_pin_name(name)
                etype = etype or c_type
                role = role or c_role
                active_low = active_low or c_active
                # fill-only: a no-connect name/role sets the nc flag (never unsets).
                nc = bool(g("nc")) or c_role == "nc" or c_type == "no_connect"

                out.append(RecordPin(
                    number=str(g("number")),
                    name=name,
                    electrical_type=etype,
                    role=role,
                    active_low=active_low,
                    nc=nc,
                    nc_instruction=g("nc_instruction"),
                ))
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

    def update_from_pin_data(
        self,
        pin_data: PinData,
        extracted_dims: Optional[Dict] = None,
    ) -> "ComponentRecord":
        """Refresh the geometry/flags from an enriched legacy PinData in place.

        The pipeline mutates the legacy ``pin_data`` after the extraction seam
        (ordering ground truth, module flag, package-type substitution) and
        computes dims late. This re-derives the variants/pins/mechanical/ordered
        fields + legacy flags from that final state while preserving the record's
        identity/provenance/links/version established at the seam. No new
        information is invented — it mirrors the legacy object.
        """
        fresh = ComponentRecord.from_pin_data(
            pin_data, part_number=self.identity.mpn, extracted_dims=extracted_dims,
        )
        self.variants = fresh.variants
        self.selected_variant = fresh.selected_variant
        self.ordered_pin_count = fresh.ordered_pin_count
        self.ordered_package_type = fresh.ordered_package_type
        self.validation_errors = fresh.validation_errors
        self.footprint_unsupported_reason = fresh.footprint_unsupported_reason
        self.status = fresh.status
        self.blocking = fresh.blocking
        return self

    def to_pin_data(self) -> PinData:
        """Reconstruct a legacy PinData so existing generation runs unchanged."""
        def _legacy_pins(pins: List[RecordPin]) -> List[dict]:
            return [{"number": p.number, "name": p.name, "function": p.role} for p in pins]

        # Restore the ORIGINAL extracted component_name (stored in description by
        # from_pin_data), not the part number in mpn — component_name becomes the
        # symbol/footprint label, so it must round-trip exactly.
        component_name = self.identity.description or self.identity.mpn or (self.component_id or "Unknown")

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
                validation_errors=list(self.validation_errors) if self.validation_errors else None,
                footprint_unsupported_reason=self.footprint_unsupported_reason,
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
            validation_errors=list(self.validation_errors) if self.validation_errors else None,
            footprint_unsupported_reason=self.footprint_unsupported_reason,
        )


def re_int(value) -> int:
    """Best-effort int from a pin-number string ("A1" -> 1, "12" -> 12, else 0)."""
    import re
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else 0
