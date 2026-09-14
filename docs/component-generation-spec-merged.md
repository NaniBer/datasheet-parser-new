# IDEEZA · Component Library Engineering

## Component generation spec: symbol, land pattern, and 3D model from a datasheet

The pipeline, the layer data model, and the complete ruleset for the AI engineer that turns a
datasheet into library artifacts. Every rule is a checkable condition with a numeric value, so it
can be enforced in code rather than eyeballed. It assumes no prior EDA knowledge — the
conventions an experienced librarian applies silently are written out.

### This document merges three inputs

1. **Component Generation & Footprint Architecture** — the pipeline, input-data contract, layer
   architecture, component linking, validation gates, and UI flow. Sections 1–5 and 8 derive from it.
2. **IPC standards review** — the numeric geometry rules, tolerance handling, and the two reported
   output defects. Sections 6–7 derive from it.
3. **IPC / SnapMagic standards reference & observed part issues** — the SnapEDA/SnapMagic practical
   CAD conventions (IEEE-315 + IPC-7351B as applied), the pad-dimension calculation methodology, and
   the concrete QC findings on real parts. **Section 9** (standards & pad math) and **Section 10**
   (observed issues) derive from it, and its SnapMagic pin conventions are folded into Section 6.

### Governing standards

| Domain | Standard |
|---|---|
| SMT land patterns | IPC-7351B |
| THT land patterns | IPC-7251 |
| Generic PCB design | IPC-2221B |
| Bottom-termination | IPC-7093 |
| Via protection | IPC-4761 |
| Schematic documentation | IPC-2612 |
| Graphic symbols | IEEE 315 |
| STEP 3D exchange | ISO 10303 STEP AP242 |
| Practical CAD symbol/footprint conventions | SnapMagic / SnapEDA internal rules |

**Contents:** [Defects](#defects) · [1 Pipeline](#section-1--generation-pipeline) ·
[2 Inputs](#section-2--input-data-contract) · [3 Foundations](#section-3--foundations) ·
[4 Layers](#section-4--layer-architecture--independence) ·
[5 Land pattern](#section-5--land-pattern--footprint-geometry) · [6 Symbol](#section-6--schematic-symbol) ·
[7 3D model](#section-7--3d-model) · [8 Validation](#section-8--validation-gates) ·
[9 Standards & pad math](#section-9--standards-reference--pad-dimension-methodology) ·
[10 Observed issues](#section-10--observed-part-issues-qc-findings) · [Checklist](#pre-flight-checklist)

**Tier meaning.** `must` blocks publication if unmet. `should` is the standing default; departures
need a recorded reason on the part.

---

## Defects

### The two defects reported in output

Both are deterministic failures a checker can catch before publication. The first has two independent
root causes — one geometric, one in the editor's data model.

#### FP-07 · LAY-02 — Copper layer is intersecting the silkscreen layer

**Geometric cause.** The generator is drawing the body outline as silkscreen. On most chip packages
the body is narrower than the land span, so the body's own edges land directly on the pads. Every pad
must be an exclusion zone: clip all silkscreen within 0.20 mm of any pad — see **FP-07**.

**Data-model cause.** If silkscreen and copper are not independent objects each owning its own
`layerId`, geometry at the same coordinates gets merged, co-selected, or co-edited — which produces
"intersecting layers" even when the clipping maths is right. See **LAY-01–LAY-04**.

#### SYM-02 · SYM-04 — Symbol pins are scattered: no grid, no grouping, no consistent spacing

Pins are being placed in datasheet pin-number order at arbitrary coordinates. They must snap to a
2.54 mm grid with no exceptions, and be grouped by electrical function — under the operative SnapMagic
convention (see Section 6): inputs left, outputs right, I/O middle-left, VCC/power upper-right, GND
lower-right, control upper-left — regardless of physical package order. See **SYM-04**.

> The concrete, per-part manifestations of these defects — on LM358P, SN74HC595D, and TPS63060DSCR —
> are catalogued in **[Section 10](#section-10--observed-part-issues-qc-findings)** and each is mapped
> back to the rule it violates.

---

## Section 1 · Generation pipeline

The three artifacts are siblings generated from one structured extraction — **not** a chain where the
footprint comes first and the rest are derived from it. Getting this order wrong is what makes symbol
and footprint drift apart.

```
Datasheet / mfr data
        │
        ▼
Extract structured data ──► Pin/logic data · Package data · Mechanical data
        │
        ├──────────────┬──────────────┐
        ▼              ▼              ▼
Schematic symbol   2D footprint    3D model
        └──────────────┴──────────────┘
                       │
                       ▼
              Component linking
                       │
                       ▼
              Validation / QA gate
                       │
                       ▼
              Library component
```

The three artifacts are generated in parallel from one extraction, then linked and validated together.
The footprint is not the parent of the other two.

- **PL-01 — Extract once, generate three times · must.** Parse the datasheet into a single structured
  component record (Section 2), then generate symbol, footprint, and model independently from it. Never
  derive the symbol from the footprint or vice versa — a shared source record is what keeps pin
  numbering consistent, and a derivation chain is what lets it drift.

- **PL-02 — Link the three artifacts by ID, not by name matching · must.** A component record holds
  explicit `symbolId`, `footprintId`, and `modelId` references. Never resolve the relationship by
  string-matching filenames at load time.

  ```
  Component STM32F103C8T6
    ├─ symbolId    → SYM_STM32F103_LQFP48
    ├─ footprintId → FP_LQFP48_7X7_P050
    └─ modelId     → 3D_LQFP48_7X7X140
  ```

  *Why it matters:* name matching silently attaches the wrong footprint when two packages share a
  naming stem, and breaks entirely when a file is renamed.

- **PL-03 — Do not save before validating · must.** Generation output goes to a staging state, runs the
  full validation battery (Section 8), and only persists to the library on a pass. A part that failed
  validation must never exist in the library in any state.

- **PL-04 — Follow the source-priority order; the datasheet always wins · must.** When more than one
  source could define the land pattern, use them in this order and record which one was used:

  | # | Source | Use when |
  |---|---|---|
  | 1 | Manufacturer's recommended land pattern | The datasheet gives one — always prefer it |
  | 2 | IPC-7351B calculation | No recommended pattern published |
  | 3 | Assembly-house DFM rules | Overlay on 1 or 2 where the house is stricter |
  | 4 | Generic package template | Last resort — flag for human review |

  The generator must never reason "this is QFN-24, therefore use the QFN-24 template." Even standardised
  package names carry manufacturer-specific dimensions. Always: identify package → extract *this
  datasheet's* actual dimensions → determine land pattern → apply manufacturing rules.

- **PL-05 — Expose the pipeline as a stepped wizard with previews · should.** Component info → symbol
  (with pin table + preview) → footprint (dimensions, IPC calculation, pad generation, layer generation,
  2D preview) → 3D (dimensions, generate, preview) → link → validate (electrical, mechanical, 3D, DRC,
  DFM) → save. Each step's output must be reviewable before the next runs; a single opaque "generate"
  button gives the reviewer nothing to check.

---

## Section 2 · Input data contract

Nothing is generated until these fields are collected. A missing field is a **blocked** part, not a
defaulted one.

- **IN-01 — Identification fields · must.**
  - Manufacturer, manufacturer part number, description
  - Component category, package name
  - Datasheet URL, datasheet revision/date, manufacturer URL
  - Distributor references (LCSC / DigiKey / Mouser) where available

- **IN-02 — Per-pin electrical fields; drives the symbol · must.** Every pin needs a complete row. The
  function field is what makes functional grouping (SYM-04) possible, so it cannot be left blank.

  | Field | Example | Drives |
  |---|---|---|
  | Pin number | 1 | Pad mapping (X-02) |
  | Pin name | GND | Symbol label |
  | Electrical type | Power Input | ERC (SYM-07) |
  | Pin function | Ground | Grouping (SYM-04) |
  | Side / position | Bottom | Placement |
  | Length & orientation | 2.54 mm, right | Geometry (SYM-02) |
  | Active low | No | Notation (SYM-08) |
  | Hidden | No — always | See SYM-05 |

- **IN-03 — Mechanical fields; drives footprint and model · must.** Capture every dimension with its
  tolerance. Nominal-only capture makes the tolerance rules in F-03 impossible to apply.
  - Package type, pin count, lead pitch
  - Body length / width / height — each with min, nominal, max
  - Lead length / width / span — each with min, nominal, max
  - Pin-to-pin spacing, standoff / seating height
  - Thermal pad dimensions, mounting hole positions and diameters
  - Manufacturer's recommended land pattern, if the datasheet publishes one (PL-04)

---

## Section 3 · Foundations

These apply to all three artifacts. They encode what an experienced librarian never states out loud —
which is exactly why an automated generator gets them wrong.

- **F-01 — Never invent a dimension. Flag and stop. · must.** If a dimension needed for a rule is
  absent, ambiguous, or unreadable, do not interpolate it, estimate it from a drawing, or borrow it from
  a similar part. Emit the part as **BLOCKED**, naming the specific missing dimension, and route to human
  review. *Why:* the highest-risk rule for an automated generator — a guessed dimension produces an
  artifact that passes every geometric check and is silently wrong, discovered only on assembled hardware.

- **F-02 — Work in millimetres throughout · must.** Millimetres are primary for all three artifacts.
  Convert inches/mils once at ingest, record both, carry mm forward. Never mix units inside one artifact.
  The schematic grid is the deliberate exception: defined in both (2.54 mm = 100 mil) because the imperial
  value is the historical convention.

- **F-03 — Apply tolerance extremes in the direction that is safe · must.**

  | Using it for | Take | Because |
  |---|---|---|
  | Pad size / fillet calculation | max lead span, min lead length | Worst case for joint formation |
  | Courtyard / keep-out | maximum body | Largest part must still fit |
  | Assembly outline & 3D body | nominal | Represents a typical part |
  | Hole diameter | maximum lead diameter | Largest lead must insert |
  | Clearance verification | maximum envelope | Collision check must be worst case |

- **F-04 — Record datasheet provenance on every artifact · must.** Each artifact carries manufacturer,
  MPN, datasheet URL, revision/date, the page and table the dimensions came from, and generation
  timestamp. All three artifacts for one part must cite the same revision. *Why:* package dimensions
  change between datasheet revisions without the part number changing — provenance is the only way to
  diff a library part against a newer datasheet.

- **F-05 — Pass through the IDEEZA review gate before publication · must.** Generated parts enter as
  **PENDING REVIEW**, never published. Sequence: manufacturer submits part data → IDEEZA engineering
  reviews → on approval the symbol, footprint, and 3D model are generated and verified → part is
  published and linked to the submitting manufacturer's inventory. Rejection returns a specific reason to
  the submitter. A part must never be orderable or RFQ-matchable while in PENDING REVIEW.

- **F-06 — Name all three artifacts from one canonical key · should.** Derive filenames from the same
  package identifier so they sort together and a missing member is obvious. Never name a footprint after
  the part number — many part numbers share one package, and the footprint should be reused, not
  duplicated.

- **F-07 — Version, never overwrite · must.** A published artifact is immutable. Corrections create a
  new version with a changelog entry; boards already referencing the old version keep referencing it
  until deliberately migrated. Silent in-place edits can invalidate a board that already passed review.

- **F-08 — Default to IPC-2221 Class 2 unless told otherwise · must.** Performance class sets minimum
  annular ring, conductor spacing, and acceptance criteria. Class 1 general electronic, Class 2 dedicated
  service (commercial default), Class 3 high-reliability. Record the class; never mix classes within one
  board's library.

---

## Section 4 · Layer architecture & independence

This is the data model behind the reported copper/silkscreen defect. Layers legitimately occupy the same
X/Y space — copper, mask, paste, and courtyard all sit on top of each other by design. What must never
happen is those coincident geometries behaving as one object.

- **LAY-01 — Generate the full layer tree, top and bottom · must.**

  ```
  FOOTPRINT
  ├─ TOP
  │   ├─ Top Copper          pads, plated features
  │   ├─ Top Solder Mask     derived from copper (FP-15)
  │   ├─ Top Paste           derived from copper (FP-15)
  │   ├─ Top Silkscreen      legend, clipped clear of copper (FP-07)
  │   ├─ Top Assembly        nominal body outline
  │   ├─ Top Fabrication     dimensions, centre mark, mechanical detail
  │   └─ Top Courtyard       placement keep-out (FP-01)
  ├─ BOTTOM
  │   └─ … same seven layers, mirrored
  └─ OTHER
      ├─ Mechanical
      ├─ Keepout
      ├─ Milling
      └─ Documentation
  ```

- **LAY-02 — Every object owns its `layerId`; never infer it from geometry · must.** Layer membership is
  a property of the object, not something computed from its shape, position, or line width at render time.
  Two objects at identical coordinates on different layers are two objects.

  ```
  Object {
    id          unique
    layerId     ← owned by the object, authoritative
    geometry    line | rect | arc | polygon | pad
    position    x, y
    rotation
    lineWidth
    fill
    visibility
    selectable
    locked
  }
  ```

  *Why:* inferring layer from geometry is the direct cause of "layers intersecting each other." Once two
  coincident objects are treated as one, editing the silkscreen edits the copper — and no amount of
  correct clipping maths will hold.

- **LAY-03 — Coincident geometry is legal; merged geometry is not · must.** Different layers may occupy
  the same X/Y coordinate space — that is normal and correct. They must remain independent geometry
  objects (Top Copper, Top Mask, Top Paste, Top Silk, Top Courtyard at the same X/Y — five independent
  objects, each carrying its own `layerId`, each selectable / hideable / editable / exportable in
  isolation). The requirement is logical independence: same coordinates, separate objects.

- **LAY-04 — Implement these layer interactions exactly · must.**

  | Action | Required behaviour |
  |---|---|
  | Hide Top Silk | Only Top Silk disappears |
  | Hide Top Copper | Only Top Copper disappears |
  | Select Top Silk | Only silk objects selected |
  | Delete Top Silk | Copper remains |
  | Move Top Silk | Copper remains in place |
  | Move Top Copper | Silk remains in place |
  | Lock Courtyard | Courtyard cannot be edited |
  | Lock Assembly | Assembly cannot be edited |
  | Single-layer mode | Only the selected layer visible |
  | Export Top Silk | Only Top Silk geometry exported |
  | Change object's layer | Layer changes, geometry unchanged |

- **LAY-05 — Associate through-hole pads with all layers they occupy · must.** A plated through-hole pad
  is a multi-layer object: top copper, bottom copper, and the plated barrel between them, plus mask on
  both sides. Emit it as one pad object with a multi-layer association and an explicit drill, not as two
  unrelated single-layer pads.

  ```
  Pad {
    layers = MultiLayer
    drill  = 1.00 mm      ← finished hole (FP-10)
    pad    = 1.80 mm      ← leaves ≥ 0.05 mm ring
  }
  ```

- **LAY-06 — Run a silkscreen-to-copper collision check as a pipeline stage · must.** Do not rely on the
  generator getting clipping right. After layer generation, run an explicit check: for every silkscreen
  object, test against every copper object on the same side; any violation of FP-07's 0.20 mm raises a
  blocking error naming both objects. This is the automated backstop for the reported defect.

- **LAY-07 — Keep courtyard and assembly out of the manufacturing output · must.** Courtyard, assembly,
  fabrication, and documentation layers are design-time only and must be excluded from Gerber/ODB++
  manufacturing exports. Only copper, mask, paste, silkscreen, and drill data reach the fabricator.

---

## Section 5 · Land pattern & footprint geometry

IPC-7351B for surface-mount, IPC-7251 for through-hole, clearances from IPC-2221B — applied only after
the source-priority check in PL-04. This is the artifact most likely to cause a physical manufacturing
failure. The IPC-7351B land-pattern methodology and pad-dimension math are detailed in
[Section 9](#section-9--standards-reference--pad-dimension-methodology).

- **FP-01 — Use IPC-7351B Density Level B by default · must.** Nominal (median) land protrusion unless
  the part is explicitly flagged.

  | Density level | IPC name | Courtyard excess | Use when |
  |---|---|---|---|
  | Level A | Most material | 0.50 mm | Hand soldering, rework, low density |
  | **Level B — default** | Nominal | 0.25 mm | General commercial assembly |
  | Level C | Least material | 0.10 mm | High density, verified fine-pitch process |

- **FP-02 — Compute the land from toe, heel, and side fillet goals · must.** Where no manufacturer land
  pattern exists (PL-04), derive pad size per IPC-7351B from the lead's maximum span and minimum length
  plus the fillet targets for the density level. Never copy from a "close enough" package. Conceptually:
  component dimensions + manufacturing tolerance + placement tolerance + solder joint requirement +
  density level → pad dimensions. Implement the formulas from the applicable IPC-7351 revision rather than
  inventing a universal one. The three fillet goals that size a land: **toe** past the lead tip, **heel**
  behind the bend, **side** along the lead edge.

- **FP-03 — Place the origin at the component centroid · must.** The origin sits at the body's geometric
  centre — the point a pick-and-place nozzle targets — not at pin 1, not at a corner. For asymmetric
  bodies use the centroid of the body outline. Must equal the 3D model origin (3D-02). An origin at pin 1
  offsets every placement by half the package, and nothing in the artwork looks wrong.

- **FP-04 — Number pads counter-clockwise from pin 1, viewed from the top · must.** Pin 1 at top-left,
  numbering counter-clockwise as seen from above the board. For BGAs use the row-letter / column-number
  grid, omitting I, O, Q, S, X, Z. Thermal pads take the next number after the last signal pin unless the
  datasheet assigns one. Pad numbering must match symbol pin numbering exactly (X-02). Viewing from the
  bottom reverses the direction — a common, silent way to mirror a footprint.

- **FP-05 — Name land patterns to the IPC-7351B convention · should.** Encode package type, body
  dimensions in hundredths of a millimetre, height, pin count, density level — `RESC1608X55N` (chip
  resistor, 1.60 × 0.80 mm, 0.55 mm high, Nominal) or `SOIC127P600X175-8N`. The name is the only place
  density level survives into the library. (See Section 9 §3.)

- **FP-06 — Courtyard, assembly, and silkscreen are three different things · must.** Using silkscreen as
  the courtyard makes placement DRC pass on parts that physically collide, because silkscreen has been
  trimmed away from the pads.

  | Layer | Represents | Geometry |
  |---|---|---|
  | Courtyard | Placement DRC keep-out | max body + lands + excess (FP-01) |
  | Assembly | True body for docs / 3D | nominal body dimensions |
  | Fabrication | Mechanical documentation | outline, centre, pin 1, dimensions |
  | Silkscreen | Printed legend | body outline, clipped per FP-07 |

  Place the pin-1 dot outside the courtyard so clipping can never erase it (FP-08).

- **FP-07 — Keep silkscreen clear of every solderable surface — 0.20 mm minimum · must.** This is the
  reported defect. Silkscreen must never overlap or approach within 0.20 mm of any SMD pad, through-hole
  annular ring, test point, or fiducial. Where an outline would cross a pad, clip it at the clearance
  boundary and leave a gap — a broken outline is correct output, not a flaw. Backed by the pipeline check
  in LAY-06. Root cause: on most chip packages the body outline is narrower than the land span, so drawing
  the body as silkscreen puts its edges directly on the pads.

  | Silkscreen parameter | Minimum | Note |
  |---|---|---|
  | Clearance to solderable copper | 0.20 mm | Auto-clip; never overlap |
  | Line width | 0.15 mm | Thinner may not print |
  | Text cap height | 0.80 mm | Below this, illegible after fab |
  | Silk-to-silk spacing | 0.15 mm | Prevents ink bridging |

- **FP-08 — Mark pin 1 and polarity outside the courtyard · must.** Every orientation-sensitive part
  needs a pin-1 or polarity indicator on both silkscreen and assembly layers. Place the silkscreen marker
  outside the courtyard so FP-07 clipping can never erase it. A chamfered corner or adjacent dot both
  work; a marker reduced to a stub by clipping does not.

- **FP-09 — Place the reference designator so it survives assembly · should.** Silkscreen designator:
  minimum 0.80 mm cap height, readable left-to-right or bottom-to-top only, outside the courtyard, never
  overlapping a pad, another designator, or a via. Keep a duplicate on the assembly layer at the component
  centre for documentation.

- **FP-10 — Size through-hole pads from lead diameter, respecting minimum annular ring · must.** Per
  IPC-7251: finished hole = maximum lead diameter + 0.25 mm at nominal density. Pad diameter must leave at
  least the minimum annular ring on every side — 0.05 mm external for IPC-2221 Class 2. For square or
  rectangular leads use the diagonal, not the edge. Drill registration tolerance eats into the ring, so
  the minimum must hold *after* tolerance, not before.

- **FP-11 — Make pin 1 visually distinct on through-hole parts · should.** Give pin 1 a rectangular or
  square pad while other pins are round or oval. This survives silkscreen loss and is readable on a bare
  board.

- **FP-12 — Segment thermal-pad paste for bottom-terminated parts · must.** For QFN, DFN, and any
  exposed-pad package, do not emit a single flood aperture. Specify paste coverage as a segmented array —
  typically 50–75% of pad area — plus any thermal via pattern, per IPC-7093. A full-area paste deposit
  outgasses during reflow and floats the part, tilting it and opening the perimeter joints.

- **FP-13 — Never place a via inside a pad unless explicitly specified · must.** Via-in-pad wicks solder
  away from the joint. Where thermal performance requires it, the via must be filled-and-capped per
  IPC-4761 and flagged on the part so the fabricator quotes the extra process.

- **FP-14 — Maintain minimum copper-to-copper clearance between adjacent pads · must.** Adjacent pads
  within one footprint must respect minimum copper spacing — commonly 0.15 mm for standard commercial
  fabrication, more where working voltage requires it per the IPC-2221B spacing tables. On fine-pitch
  parts, reduce pad width before violating spacing.

- **FP-15 — Derive mask and paste from copper, never hand-draw them · must.** Generate mask openings by
  expanding each pad by one configurable value, and paste apertures by contracting or segmenting it.

  ```
  Copper pad   0.60 × 0.80 mm
      ↓ mask expansion  +0.05 mm per side   ← configurable, not hard-coded
  Mask opening 0.70 × 0.90 mm

  Paste aperture = 1:1, or reduced / segmented per package (FP-12)
  ```

  *Why:* 0.05 mm per side is a common house value, not a universal PCB rule — fabrication capabilities
  vary, so it must be a configurable process parameter.

- **FP-16 — Mark plated vs non-plated holes distinctly · must.** Mechanical mounting holes are usually
  non-plated with no annular ring and no net; component leads are plated. Emit these as different object
  types — a non-plated hole rendered as a plated pad appears in the netlist and can short to a plane.

- **FP-17 — Record component height and body envelope on the footprint · must.** Maximum height above
  the board is a first-class field, not implied by the 3D model. Enclosure clearance and keep-out checks
  read it directly, and a board may be reviewed before models are attached.

- **FP-18 — Set the pick-and-place zero-rotation orientation per IPC-7351 · must.** IPC-7351B defines a
  zero-degree orientation per package family — for two-pin chip parts, pin 1 to the left; for most ICs,
  pin 1 at top-left. Store rotation as an explicit field. An inconsistent zero orientation rotates parts
  by 90° or 180° on the assembly line with nothing wrong in the artwork.

- **FP-19 — Flag parts needing board-edge or keep-out treatment · should.** Edge connectors, antennas,
  castellated modules, and press-fit parts have constraints beyond the courtyard — board-edge offset,
  ground keep-out, panel rail clearance. Record as named constraints on the part.

- **FP-20 — Provide test-point access for parts with no other probe point · should.** Where a net
  terminates only under a BGA or QFN thermal pad, flag it — the board will need a dedicated test pad. This
  is a property of the package, so it belongs on the part.

---

## Section 6 · Schematic symbol

IPC-2612 for diagram documentation, IEEE 315 for graphic symbols, and the SnapMagic/SnapEDA CAD
conventions for practical library rules (electrical pin types, pin arrangement, special-pin graphics —
see Section 9 §1). The symbol represents electrical behaviour, not physical appearance — it may be a
simple shape provided its pins correspond correctly to the footprint pads. A bad symbol won't scrap a
board; it will cause a design error that reaches one.

> **Pin-side convention — reconciliation.** Two conventions appear across the source documents. The
> operative one for this library is the **SnapMagic 2-column layout** (below), because the QC findings in
> Section 10 grade parts against it and the generator implements it. The alternative 4-side phrasing
> ("inputs left, outputs right, power top, ground bottom") from the original architecture doc is
> **superseded** by SnapMagic here and retained only as background. Whichever is chosen, it must be
> applied uniformly library-wide.
>
> **Operative SnapMagic pin arrangement:** Inputs → left · Outputs → right · I/O → middle-left ·
> VCC / power → upper-right · GND → lower-right · Control → upper-left.

- **SYM-01 — Never reproduce the physical pin order · must.** The package's pin sequence is an artifact
  of silicon layout and moulding, carrying no schematic meaning. Reading pins 1..N off the datasheet and
  placing them clockwise around a rectangle is the root cause of the scattered-pin defect. Group by
  function first (SYM-04), then attach whatever pin numbers those functions happen to have.

- **SYM-02 — Snap every pin to a 2.54 mm grid — no exceptions · must.** All pin endpoints land exactly
  on a 2.54 mm (100 mil) grid. Pin length uniform across the symbol: 2.54 mm or 5.08 mm, chosen once per
  library, never mixed within one symbol. Body outline edges on grid too. An off-grid pin cannot be
  connected by a wire drawn on grid — the wire appears to touch while the netlist records no connection.

  | Parameter | Value | Tolerance |
  |---|---|---|
  | Pin pitch / grid | 2.54 mm (100 mil) | exact — zero offset |
  | Pin length | 2.54 or 5.08 mm | uniform per symbol |
  | Pin name text | 1.27 mm | min cap height |
  | Text rotation | 0° or 90° CCW only | never 180° / 270° |

- **SYM-03 — Size the body to the pin count, with margin · should.** The body must be tall enough that
  every pin sits on its own grid step with at least one blank step between functional groups, and wide
  enough that the longest pin name plus the designator fits inside without touching the outline or another
  label. Never overlap text with text, text with outline, or pin with pin. *(The body outline line width
  must not exceed the pin line width — see Section 10, LM358P/SN74HC595D.)*

- **SYM-04 — Group pins by electrical function, in reading order · must.** Signal flows left to right.
  Within each side, order pins into contiguous functional blocks separated by one blank grid step — never
  interleave unrelated signals. Under the operative **SnapMagic convention**:

  | Region | Pin classes |
  |---|---|
  | Left | Inputs |
  | Middle-left | Bidirectional I/O |
  | Upper-left | Control |
  | Right | Outputs |
  | Upper-right | VCC / power rails |
  | Lower-right | GND / returns |

  Pin numbers become incidental annotations — function determines position, numbering follows. *(Retained
  background — original 4-side phrasing: inputs/control/clocks/address/reset left, outputs/status/IO right,
  power top highest-voltage-leftmost, grounds + thermal bottom. Superseded by the SnapMagic table above.)*

- **SYM-05 — Make power and ground pins visible · must.** Do not emit hidden or auto-connected power
  pins. Every supply and return appears on the symbol and is wired explicitly. Where a part has multiple
  internally-common supply pins, show each — the board still needs a decoupling capacitor at each. *Why:*
  hidden power pins connect by name silently; a part expecting 1.8 V on a pin named VCC attaches to a
  3.3 V net with no error and no visible wire.

- **SYM-06 — Split large parts into functional banks · should.** Above roughly 40 pins, or wherever a
  part contains independent blocks, emit a multi-unit symbol with suffixed units (U1A, U1B, …). Keep
  power/ground in their own unit or repeat per unit — choose one convention library-wide.

- **SYM-07 — Set electrical pin types truthfully · must.** Assign each pin its real type — input, output,
  bidirectional, power in, power out, passive, open collector, open emitter, tri-state, NC. Do not default
  everything to passive or bidirectional to silence warnings. *Why:* ERC only catches driver conflicts,
  unpowered inputs, and shorted outputs when pin types are honest. SnapMagic requires the pin type to
  reflect the true input type for correct ERC/DRC.

- **SYM-08 — Indicate active-low with one consistent notation · must.** Use an overbar where the renderer
  supports it, otherwise one chosen prefix (`~RESET` or `!RESET`) applied uniformly. Never mix `nRESET`,
  `RESET#`, `/RESET`, `RESET_N` in one library. Carry datasheet inversion bubbles through per IEEE 315.

- **SYM-09 — Use the conventional graphic form for standard devices · should.** Resistors, capacitors,
  inductors, diodes, transistors, op-amps, and logic gates all have established IEEE 315 shapes — use them.
  Clock pins use a triangle marker; active-low pins use a bar/overline (SnapMagic special-pin graphics).
  Reserve the plain rectangle for ICs with no conventional form.

- **SYM-10 — Assign the correct reference designator prefix · must.** Prefix comes from device class:
  R resistor, C capacitor, L inductor, D diode/LED, Q transistor, U IC, J jack, P plug, SW switch,
  Y crystal, F fuse, TP test point, FB ferrite bead. Never emit a bare `U` for everything.

- **SYM-11 — Handle no-connect pins explicitly · must.** Pins marked NC, DNC, or reserved must appear on
  the symbol with the correct type — and the datasheet's instruction preserved. "Do not connect" and
  "connect to ground" are different requirements that both get abbreviated to NC; carry the actual wording
  into the pin description.

- **SYM-12 — Never duplicate or skip a pin number · must.** Each pin number appears exactly once across
  all units, and the set matches the package exactly with no gaps. Where a package ties multiple pads to
  one function, emit each pad as its own pin — do not collapse them. One symbol pin represents one
  function, even where that function maps to different package pins.

- **SYM-13 — Place pin names inside the body, pin numbers outside · should.** The functional name sits
  inside the outline adjacent to its pin; the package pin number sits outside, above or beside the pin
  line. Swapping them mid-library makes every schematic ambiguous. *(Names overlapping the body line or
  sitting on the leg is a reported defect — see Section 10, SN74HC595D.)*

- **SYM-14 — Populate the symbol fields that outlive the symbol · must.** At minimum: reference, value,
  part number, description, datasheet, manufacturer, footprint link, and the datasheet revision generated
  from. SnapMagic places the MPN above the symbol and the reference/value below it. A symbol with no
  footprint association gets one assigned by hand later — which is how mismatched parts reach a board.

- **SYM-15 — Set the symbol anchor at a predictable point · should.** Place the symbol origin on grid at
  the body's top-left corner or centre — one convention library-wide. An arbitrary anchor makes symbols
  jump when placed and breaks alignment when arrayed.

- **SYM-16 — Carry ratings that constrain the design · should.** Voltage rating, current rating,
  tolerance, dielectric, power rating, and temperature range belong in symbol fields. These are design
  constraints a reviewer checks against the schematic, not just procurement data.

- **SYM-17 — The schematic symbol is a 2D top-view artifact only · must.** *(New — from the LM358P /
  SN74HC595D findings.)* The symbol must have no Z height and must not be rotatable in the editor: it is a
  flat top-view drawing, not a 3D object. A symbol carrying body height or free rotation is malformed.
  See Section 10.

---

## Section 7 · 3D model

Generated from mechanical package dimensions, never from the schematic. IPC does not specify 3D geometry;
the governing standard is ISO 10303 (STEP), with alignment inherited from the land pattern. The model's
job is mechanical verification, so dimensional truth beats visual fidelity.

- **3D-01 — Deliver STEP (AP242, or AP214) as the primary format · must.** Emit a neutral
  parametric-solid STEP file. Mesh formats (STL, OBJ, WRL, GLB) may be generated from the STEP as
  secondary renders but must never be the source of truth — they carry no units, no assembly structure,
  and no reliable origin.

- **3D-02 — Align the model origin to the footprint origin, Z=0 at the seating plane · must.** Model
  origin is the same centroid as FP-03. Z = 0 is the PCB surface the part sits on, body extending in +Z.
  Pin 1 falls on the same side as pin 1 in the land pattern, with no extra rotation baked in. Define the
  coordinate system once: X = width, Y = length, Z = height.

  | Axis / datum | Definition | Common failure |
  |---|---|---|
  | Origin XY | body centroid (= FP-03) | Origin at pin 1 or a corner |
  | Z = 0 | PCB seating plane | Z=0 at body centre → part sunk in board |
  | +Z direction | away from board | Model mirrored below the board |
  | Rotation | pin 1 matches footprint | 90° / 180° offset vs. land pattern |

- **3D-03 — Generate leads per-pin with numbering that matches the footprint · must.** Each physical lead
  is generated with its own number, X/Y/Z position, length, width, height, and rotation, and those numbers
  must correspond to the footprint pad numbering. The chain symbol pin 1 → footprint pad 1 → 3D lead 1 is
  a hard requirement, verified in X-03.

- **3D-04 — Model nominal dimensions; verify clearance against maximum · must.** Build the body at
  datasheet nominal so the model represents a typical part. Separately record the maximum envelope — max
  body, max height, max lead span — in metadata so collision and keep-out checks run worst case.

- **3D-05 — Model the standoff — do not rest the body on the board · must.** Where the datasheet
  specifies a standoff or seating height, the body sits at that height above Z=0, with only intended
  contact features touching the plane. *Why:* zero standoff hides real interference — an underfill gap or
  a low-profile trace routed beneath the part reads as clear when it isn't.

- **3D-06 — Emit clean, closed, watertight solids · must.** Every solid is a valid closed manifold: no
  self-intersecting faces, no zero-thickness sheets, no duplicate coincident bodies, no stray construction
  geometry. Validate before publishing — an invalid solid fails import in mechanical CAD, often without a
  clear error.

- **3D-07 — Simplify aggressively — model the envelope, not the part · should.** Omit internal structure,
  fine text, decorative fillets, and sub-0.1 mm surface detail. Keep what carries mechanical meaning:
  envelope, lead geometry, standoff, connector openings, mounting holes, pin-1 indicator.

- **3D-08 — Assign materials and colours by convention · should.** Dark grey/black moulding compound,
  tin-silver for leads and terminations, gold for plated contacts, appropriate body colours for LEDs and
  connectors. Colour is how a reviewer spots a lead modelled as body, or a connector modelled inside-out.

- **3D-09 — State units explicitly as millimetres · must.** Write the unit declaration into the STEP
  header rather than relying on importer defaults. A model silently arriving in inches is off by 25.4×.

- **3D-10 — Do not include the PCB, pads, or solder in the model · must.** The model is the component
  only. Board substrate, copper pads, solder fillets, and neighbouring parts belong to the board assembly.

- **3D-11 — Keep the model's footprint within the footprint's courtyard · must.** Project the model's
  maximum XY envelope onto the board plane and verify it fits inside the courtyard from FP-06. A mismatch
  means one artifact is wrong — this single test catches scaling errors, wrong-package substitutions, and
  rotation mistakes.

- **3D-12 — Model moving and mating features in their neutral state · should.** Connectors, sockets,
  switches, and hinged parts are modelled unmated and at rest, with mating clearance and travel recorded
  as metadata. Where insertion or actuation sweeps a volume, record that envelope.

- **3D-13 — Use one body per material, grouped as an assembly · should.** Merge coplanar faces and
  consolidate: one solid for the moulding, one for the lead frame, one per distinct material. Hundreds of
  tiny bodies slow every downstream operation and make material assignment unreliable.

- **3D-14 — Round coordinates to a sane precision · should.** Emit vertex coordinates at 0.001 mm
  resolution. Floating-point noise inflates file size, defeats deduplication, and produces spurious
  validation warnings.

---

## Section 8 · Validation gates

Four batteries run in sequence after generation and before save. These catch what per-artifact rules
cannot see, because they compare artifacts against each other.

- **V-01 — Electrical validation — symbol against footprint · must.**
  - Pin count equals pad count, thermal pads and shields included
  - Pin numbers map 1:1 as a *set*, not just by count — an off-by-one that swaps two numbers has a
    matching count and produces a board wired backwards
  - No duplicate pin numbers, no missing pin numbers
  - Every datasheet pin exists on the symbol
  - Pin names match the datasheet; electrical types assigned and plausible
  - All pin connection points on grid (SYM-02)

- **V-02 — Mechanical validation — footprint against datasheet · must.**
  - Body size and pad positions match the extracted dimensions
  - Pitch correct across every pad row
  - Package orientation and pin-1 position correct
  - Hole and annular-ring dimensions within FP-10
  - Courtyard present, sized per density level, on its own layer

- **V-03 — 3D validation — model against footprint · must.**
  - Body centred on the footprint origin; correct origin and rotation
  - Leads aligned to pads, lead numbering matching pad numbering
  - Pin 1 aligned across all three artifacts
  - Height matches the footprint's recorded height field (FP-17)
  - XY envelope inside the courtyard (3D-11)

- **V-04 — Manufacturing validation — DRC / DFM · must.**
  - Pad-to-pad clearance (FP-14)
  - Solder-mask clearance and paste dimensions (FP-15)
  - Silkscreen-to-pad clearance (FP-07, LAY-06) — the reported defect's automated backstop
  - Courtyard clearance
  - Hole and annular-ring requirements
  - House DFM rules from the assembly partner

- **V-05 — Emit a machine-readable validation report per part · must.** Every generated part carries a
  report listing each rule checked, its result, and the measured value where numeric. A part with unrun
  checks is not a passing part — it is an unverified one, and must not publish. All three artifacts must
  also cite the same datasheet revision (F-04).

---

## Section 9 · Standards reference & pad-dimension methodology

*Derived from the IPC / SnapMagic standards review. Provides the rationale and calculation detail behind
Sections 5 and 6.* For PCB part / CAD-library creation following the same standards SnapEDA/SnapMagic use:

| Part element | Standard to follow | What it covers |
|---|---|---|
| Schematic symbol | IEEE-315 + SnapMagic internal rules | Symbol graphics, reference designators, symbol conventions |
| PCB footprint / land pattern | IPC-7351B | Pad dimensions, land-pattern geometry, courtyard, solder mask, paste, orientation, naming |
| Symbol↔footprint mapping | Datasheet + pin-to-pad mapping | Ensures schematic pins correctly connect to physical pads |
| Reference designator | IEEE-315 / CAD-library convention | R, C, U, D, J, L, etc. |
| 3D model | Manufacturer mechanical dimensions | Physical representation; not defined by IPC-7351B itself |

### §1 Schematic symbol — IEEE-315 + SnapMagic

IEEE/ANSI 315 governs the graphical representation of electrical/electronic schematic symbols and
includes reference-designation letters. Practical CAD-library rules (feeds Section 6):

- **Symbol identification.** Use the MPN where appropriate; common components use generic names (R, C…);
  add the reference designator and the value/part number. SnapMagic places the MPN above the symbol and
  the reference/value below it.
- **Pin arrangement (SnapMagic).** Inputs → left · Outputs → right · I/O → middle-left · VCC/power →
  upper-right · GND → lower-right · Control → upper-left. *(This is the operative SYM-04 convention.)*
- **Pin properties.** Every pin carries the correct electrical type (Input, Output, Bidirectional/I/O,
  Passive, Power input, Power output, Open collector/drain, Tri-state, No-connect) because it drives
  ERC/DRC. SnapMagic requires the pin type to reflect the true input type.
- **Special pins.** No-connect pins are included; active-low pins use a bar/overline; clock pins use a
  triangle; one symbol pin represents one function even where that function maps to different package pins.
- **Caveat.** IEEE-315 does not specify every modern pin property (Input/Output/Passive/Power semantics,
  ERC behaviour, pin length, hidden pins). Use IEEE-315 for the graphical/reference basis, SnapMagic for
  practical CAD conventions, and the CAD tool's electrical pin types for ERC behaviour.

### §2 PCB footprint — IPC-7351B

IPC-7351B (*Generic Requirements for Surface Mount Design and Land Pattern Standard*) defines land-pattern
geometry and solder-joint recommendations, providing correct land size/shape/tolerances while considering
inspection, testing, and rework. SnapMagic uses **IPC-7351B nominal** and the IPC naming convention.
Coverage:

- **A. Land/pad geometry** — pad length/width, pad-to-pad spacing, land pitch, component-to-land and
  terminal-to-land relationships, solder-joint dimensions, manufacturing tolerances. Objective: enough
  land area for a reliable solder fillet given tolerances.
- **B. Three density levels** — least/low, nominal/median, most/high. Nominal is the default; the same
  physical component can have different recommended footprint sizes depending on density.
- **C. Solder mask** — mask opening, mask-to-pad clearance, registration/tolerance.
- **D. Paste mask / stencil** — paste aperture, stencil opening, paste reduction, paste distribution.
- **E. Courtyard** — component-to-component clearance, placement clearance, assembly planning, reflow
  considerations.
- **F. Silkscreen** — component outline, pin-1/polarity marking, reference-designator area,
  silkscreen-to-pad clearance.
- **G. Assembly layer** — physical component outline for assembly docs, pick-and-place, placement,
  BOM/assembly drawings, and 3D verification.
- **H. Component orientation** — standardized zero orientation so footprints behave consistently.
- **I. Footprint origin** — consistent origin/reference point affecting placement, rotation,
  pick-and-place, CAD interoperability, and automated assembly.

### §3 IPC footprint naming

IPC-7351B provides a land-pattern naming convention so footprints don't get named ad hoc. Names encode
package, lead style, pitch, pin count, body dimensions, density level, and other package characteristics.
(See FP-05.)

### §4 Through-hole footprints

IPC-7351B is primarily a *surface-mount* standard and must not be treated as the complete standard for
through-hole. For THT, also consider: manufacturer datasheet, terminal dimensions, hole diameter,
finished hole, drill tolerance, annular ring, pad diameter, pin pitch, body dimensions, assembly
clearance. IPC-7351B itself directs designers to the manufacturer datasheet for package dimensions.
(See FP-10, IPC-7251.)

### §5 Symbol + Footprint + Device — the three connected elements

- **① Schematic symbol** — graphics, reference, value/MPN, pin numbers, pin names, pin electrical types,
  pin orientation/position, no-connect pins, special graphical indicators. *Basis: IEEE-315 + CAD
  conventions.*
- **② PCB footprint** — pads, pad numbers/dimensions/shape, hole size (if any), solder-mask opening,
  paste opening, courtyard, assembly outline, silkscreen, polarity/pin-1 marking, reference designator,
  origin, orientation. *Basis: IPC-7351B + manufacturer datasheet.*
- **③ Device / part** — connects the two: schematic pin 1 → PCB pad 1, pin 2 → pad 2, … SnapMagic maps
  symbol and package so pins and pads connect per the datasheet, uses the MPN as the device name, and adds
  parametric info (manufacturer, value, tolerance). *(This is PL-02 + X-02.)*

### §6 Pad-dimension calculation (IPC-7351 land-pattern methodology)

Pad dimensions **cannot** be calculated from the 3D component dimensions alone. The IPC methodology
considers three directions — X (pad width / side extension), Y (pad length / heel-to-toe), Z (overall
land-pattern dimension):

```
Pad Width  = Terminal Width  + 2 × Side Extension
Pad Length = Terminal Length + Heel Extension + Toe Extension
```

The side, heel, and toe extensions are **not fixed** — they depend on component dimensions, tolerances,
manufacturing/assembly capability, and required solder-joint geometry per IPC. Spacing is then checked:

```
Pad-to-Pad Gap = Pitch − Pad Width
```

Pitch alone is not sufficient to determine pad size. *Example:* an SOIC/QFP terminal with width 0.30 mm,
length 0.60 mm, pitch 0.50 mm is **not** given a 0.30 × 0.60 mm pad — the IPC calculation applies
min/max terminal dimensions and tolerances, then adds solder-joint extensions, then verifies the gap.

**General workflow:** 3D model → measure terminal dimensions → identify package → apply IPC-7351
calculation → determine pad dimensions → verify spacing/clearance → create footprint. *(This is the
FP-02 formula path.)*

---

## Section 10 · Observed part issues (QC findings)

*Real defects found in generated output, each mapped to the rule it violates. These are the concrete
manifestations of the two reported defects and drive the checkable conditions above.*

### LM358P

**Schematic side**

| # | Issue | Rule violated |
|---|---|---|
| 1 | Pin arrangement does not follow the SnapMagic/IPC convention (Inputs left, Outputs right, I/O middle-left, VCC upper-right, GND lower-right, Control upper-left) | SYM-04, SYM-01 |
| 2 | Main body too large; body outline line thickness exceeds the pin line thickness | SYM-03 |
| 3 | Schematic has a Z height — it should be top-view only | SYM-17 |
| 4 | Schematic symbol is rotatable — it must not be | SYM-17 |

**2D / footprint side**

| # | Issue | Rule violated |
|---|---|---|
| 1 | Footprint is rotatable — it must not be | FP-18 (fixed zero orientation), SYM-17 (top-view-only intent) |
| 2 | Footprint has a Z height — it should be top-view only | (2D view constraint; cf. LAY-07) |
| 3 | Pin-1 pointer sits on the pads, not on the top-left outside the body | FP-08, FP-07 |
| 4 | Pad holes are filled | FP-10, FP-16 (hole must be an open drill, plated) |

### SN74HC595D

**Schematic side**

| # | Issue | Rule violated |
|---|---|---|
| 1 | First four points identical to LM358P (pin arrangement, oversized body/line, has height, rotatable) | SYM-04, SYM-03, SYM-17 |
| 2 | VCC pin missing and QH pin duplicated — pin set does not match the package | SYM-05, SYM-12, V-01 |
| 3 | Pin name overlaps the main body line and the pin — it should sit inside the body | SYM-13, SYM-03 |

**2D / footprint side** — same issues as LM358P above.

### TPS63060DSCR

**Schematic side**

| # | Issue | Rule violated |
|---|---|---|
| 1 | First four points identical to the parts above | SYM-04, SYM-03, SYM-17 |
| 2 | EXP (exposed/thermal pad) pin missing | SYM-12, FP-12, V-01 (thermal pad must be included) |

**2D / footprint side**

| # | Issue | Rule violated |
|---|---|---|
| 1 | First three issues same as LM358P (rotatable, has height, pin-1 pointer on pads) | FP-18, FP-08 |
| 2 | Yellow (fab/body outline) line crosses the pads | FP-07, LAY-06 |
| 3 | Footprint geometry does not match the datasheet package | PL-04, V-02 |

### Cross-cutting summary

The QC findings collapse to a small set of systemic failures:

1. **Pin arrangement ignores function** (all three parts) → SYM-01/SYM-04. The single highest-impact fix.
2. **Symbol carries height and is rotatable** (all three) → SYM-17. The symbol must be a flat, fixed
   top-view artifact.
3. **Pin names/body geometry malformed** — oversized body, thick outline, names on the pin/outline →
   SYM-03/SYM-13.
4. **Pin set incomplete** — missing VCC, duplicated QH, missing EXP thermal pad → SYM-05/SYM-12/FP-12/V-01.
5. **Silk/fab outline crosses pads and pin-1 marker lands on pads** → FP-07/FP-08/LAY-06.
6. **Footprint not derived from the datasheet** → PL-04/V-02, with filled holes → FP-10/FP-16.

Every one of these is a checkable condition already covered by a `must` rule above; none requires human
judgement to detect.

---

## Pre-flight checklist

Run on every generated part before it enters review. Any unchecked `must` item blocks publication. Each
item maps to a rule above.

### Pipeline & inputs
- [ ] Symbol, footprint, and model generated in parallel from one extraction — **PL-01**
- [ ] Artifacts linked by explicit ID, not filename matching — **PL-02**
- [ ] Manufacturer's recommended land pattern used where the datasheet gives one — **PL-04**
- [ ] Every mechanical dimension captured with its tolerance, not nominal-only — **IN-03**
- [ ] No dimension inferred, estimated, or borrowed from a similar part — **F-01**
- [ ] Datasheet URL, revision, page and table recorded on all three artifacts — **F-04**
- [ ] Part is PENDING REVIEW — not orderable, not RFQ-matchable — **F-05**

### Layer architecture
- [ ] Full layer tree generated, top and bottom — **LAY-01**
- [ ] Every object owns its `layerId` — never inferred from geometry — **LAY-02**
- [ ] Coincident geometry stays as independent objects — **LAY-03**
- [ ] Hide / select / delete / move / lock / export isolate correctly per layer — **LAY-04**
- [ ] THT pads emitted as multi-layer objects with explicit drill — **LAY-05**
- [ ] Silk-to-copper collision check ran as a pipeline stage — **LAY-06**
- [ ] Courtyard / assembly / fab excluded from manufacturing export — **LAY-07**

### Land pattern
- [ ] No silkscreen within 0.20 mm of any pad, ring, test point, or fiducial — **FP-07**
- [ ] Density level recorded and consistent with the assembly method — **FP-01**
- [ ] Pads from toe/heel/side fillet goals, not copied from a similar part — **FP-02**
- [ ] Origin at body centroid, identical to the 3D model origin — **FP-03 · 3D-02**
- [ ] Pad numbering counter-clockwise from pin 1, viewed from above — **FP-04**
- [ ] Courtyard, assembly, fabrication, silkscreen all present and distinct — **FP-06**
- [ ] Pin-1 / polarity marker on silk and assembly, outside the courtyard — **FP-08**
- [ ] Reference designator ≥ 0.80 mm, not inverted, not overlapping — **FP-09**
- [ ] Annular ring ≥ 0.05 mm on all sides after drill tolerance — **FP-10**
- [ ] Thermal pad paste segmented, vias specified — **FP-12**
- [ ] No via inside any pad unless filled-and-capped and flagged — **FP-13**
- [ ] Copper-to-copper spacing between adjacent pads ≥ minimum — **FP-14**
- [ ] Mask and paste derived from copper, expansion configurable — **FP-15**
- [ ] Plated and non-plated holes emitted as distinct types — **FP-16**
- [ ] Maximum component height recorded as a footprint field — **FP-17**
- [ ] Pick-and-place zero-rotation orientation set explicitly — **FP-18**

### Schematic symbol
- [ ] Every pin endpoint exactly on the 2.54 mm grid; pin length uniform — **SYM-02**
- [ ] Pins grouped by function per SnapMagic convention (inputs left, outputs right, I/O middle-left, VCC upper-right, GND lower-right, control upper-left) — **SYM-04**
- [ ] Layout does not follow datasheet pin numbering — **SYM-01**
- [ ] No text overlaps text, outline, or pins; body sized with margin; outline line ≤ pin line — **SYM-03**
- [ ] No hidden or auto-connected power pins — **SYM-05**
- [ ] Electrical pin types assigned truthfully, not blanket-passive — **SYM-07**
- [ ] Active-low notation consistent across symbol and library — **SYM-08**
- [ ] Reference designator prefix correct for the device class — **SYM-10**
- [ ] NC / DNC / reserved pins present with the datasheet's actual instruction — **SYM-11**
- [ ] No duplicated or skipped pin numbers across all units — **SYM-12**
- [ ] Reference, value, part number, description, datasheet, footprint all set — **SYM-14**
- [ ] Symbol is top-view only, no Z height, not rotatable — **SYM-17**

### 3D model
- [ ] STEP AP242/AP214 emitted, units declared as millimetres — **3D-01 · 3D-09**
- [ ] Z = 0 at seating plane, body in +Z, pin 1 matching the land pattern — **3D-02**
- [ ] Lead numbering corresponds to footprint pad numbering — **3D-03**
- [ ] Standoff modelled where the datasheet specifies one — **3D-05**
- [ ] Geometry validates as closed manifold solids — **3D-06**
- [ ] No PCB, pads, or solder included in the model — **3D-10**
- [ ] Model XY envelope fits inside the footprint courtyard — **3D-11**
- [ ] Maximum envelope recorded for worst-case clearance — **3D-04**

### Validation gates
- [ ] Electrical battery passed — pin/pad set mapping, not just count — **V-01**
- [ ] Mechanical battery passed — body, pitch, orientation, holes, courtyard — **V-02**
- [ ] 3D battery passed — origin, rotation, lead alignment, height, envelope — **V-03**
- [ ] DRC/DFM battery passed, including silk-to-pad clearance — **V-04**
- [ ] Machine-readable validation report emitted, every rule with a result — **V-05**

---

### On the values in this document

Density levels, courtyard excess, hole-to-lead allowance, and minimum annular ring come from the IPC
standards cited at the top. The 0.20 mm silkscreen clearance, 0.05 mm mask expansion, 0.15 mm copper
spacing, and text minimums are **house rules** set at the safe end of common fabrication capability — each
must be a configurable process parameter and confirmed against the fabricator's published capability,
never hard-coded as a universal PCB rule.

### Scope

These rules cover generation and self-verification. They do not replace the human review gate (F-05) —
they make that review fast by removing everything mechanically checkable from it.
