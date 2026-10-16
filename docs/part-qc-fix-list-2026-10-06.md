# Part QC Fix List — from IDEEZA Part Comparison Log

Source: `IDEEZA_Part_Comparison_Log.pdf` (dated 2026-10-05), 6 parts, 74 issues
(5 highest · 23 high · 20 medium · 26 low). Parts are library IDs 24150–24156,
created via the Automatic Part Creation pipeline (`/parse` + `/agentic`).

Prioritized by **blocker severity** (is the part usable?) and **leverage**
(a generator-wide fix clears the same issue on every part at once). Code
locations are where the fix lands in this repo.

> **Progress — updated 2026-10-13** (branch `fix/part-qc-comparison-log`, PR #27 on GitHub)
> **~38 of 74 cards fixed** across 14 commits. The authoritative, per-card status is the
> **[Complete Card Inventory (all 74)](#complete-card-inventory-all-74)** at the bottom of this
> doc — refer to that, not the cluster summaries, for the status of any individual card.
> The P0–P3 sections below remain as the root-cause / fix writeups per cluster.
>
> Rough cluster status: **done** P0-1, P0-2, P0-4, P1-1, P1-5 (new), P2-2, P2-4, P3-5, value-text
> half of P3-4, MPN half of P3-1. **Partial/data-only** P0-3 (fail-closed), P1-2 (flag done, overbar
> render platform), P1-3 (data done, label mesh platform). **Still ours & open** P2-1 (symbol body),
> P3-6 (pin-layout rule), P3-7 (land-pattern), silk half of P2-3. **Blocked** P0-5 + 693 connector
> dims (vendor land pattern). **Not ours** P1-4 (3D consumption), P3-2 (category), P3-3 (fp naming),
> overbar/label-mesh render. **Deferred** pin-1 marker (contradicts committed FP-08 — QC decision).

Parts: **TL16C2550PFBR** (TQFP-48) · **74LVC1G99GT** (XSON8/SOT833-1) ·
**AD9106BCPZ** (LFCSP-32) · **693072010801** (microSD socket) ·
**ADV7180KST48Z** (LQFP-48) · **PGA2311P** (PDIP-16).

---

## P0 — Blockers: the part does not work as submitted

### P0-1 · Wrong package / land pattern (unsolderable or wrong mount type)
**Parts:** AD9106 (LFCSP-32 → through-hole DIP-32), 693072010801 (SMD microSD →
through-hole DIP-8), 74LVC1G99 (XSON8 → a larger package's land pattern, all 8
pads outside the body). *Jira: AD9106 FP-01, 693072010801 FP-01, 74LVC1G99
FP-01 — all HIGHEST.*

**Why it happens (corrected after tracing the real run):** the earlier note here
blamed `_get_default_package` — that was wrong (it returns QFN for 32 pins, SOIC
for 8). The real mechanism is `enforce_known_package_type` in `src/main.py`: when
`parse_package_type` can't resolve the extracted package string, `--force-best-effort`
**substitutes `DIP-<pin_count>`** geometry — and DIP is *through-hole*, so an
unrecognized SMD part gets drilled holes. Proven in the run log:
`Unknown package type '32-LEAD LFCSP'; substituted DIP-32 geometry`. Two compounding
gaps: (1) `parse_package_type`/`_family` had no `LFCSP`/`XSON` alias and only
*prefix*-matched, so the suffix form `"32-LEAD LFCSP"` never resolved; (2) the
best-effort fallback itself was through-hole DIP.

**Fix — DONE (branch `fix/part-qc-comparison-log`):**
- ✅ **Fix A** (commit `eb29820`): `LFCSP → QFN` and `XSON → SON` aliases in
  `package_geometry.py`; shared `_match_alias_key` with a whole-word fallback so
  `"32-LEAD LFCSP"` resolves; `_GEOMETRY_CANONICAL` in `footprint_defaults.py`
  routes LFCSP/XSON to the real QFN/SON grids. **AD9106 now builds a 5×5 mm SMD
  QFN-32 (was a 32-hole DIP-32).**
- ✅ **Fix B** (B1, SMD fallback): the unknown-package substitute is now
  `SON-<pin_count>` (leadless SMD), not `DIP-<pin_count>`. Any unrecognized part
  keeps the 2-row arrangement but on SMD pads — never drilled holes. **microSD
  693072010801 now SMD (0 holes, was 8).** Still watermarked unvalidated.
- ⬜ **Connectors (693072010801) remain a dimensional/land-pattern gap** — Fix B
  stops the drilled holes, but a correct microSD socket still needs the
  manufacturer land pattern (Fix C, separate).

### P0-2 · TL16C2550 quad-pad rows misplaced — 24 of 48 pins can't solder
**Part:** TL16C2550. *Jira: FP-01 HIGHEST.* Top/bottom rows sit at y = ±3.20 mm
instead of ±4.216 mm (left/right are correct), so on a square TQFP-48 the
top/bottom pads fall 1 mm short of the leads.

**Why:** quad-package row/column spans are computed per-axis and the top/bottom
span doesn't match the left/right span for a square body. See
`pcb_footprint_builder._recenter_pins` and the SMD inset at lines 221–239.

**Fix:** for a square QFP/QFN body, force equal row spans on both axes (pad toe
extent from the same E). Add a conformance check that square packages have equal
X/Y pad spans.

### P0-3 · ADV7180 pins 24/25 mislabeled + GPO pairs swapped — decoder won't work
**Part:** ADV7180. *Jira: SCH-01 HIGHEST, SCH-02 HIGH.* Pin 24 named AGND (should
be **ELPF**, the PLL loop filter) and pin 25 drawn "ELPF" (should be **PVDD**);
GPO0/GPO1 (pins 5/6) and GPO2/GPO3 (41/42) swapped. Wired as drawn the PLL can't
lock → no video.

**Why:** the extractor reads a grouped datasheet table row ("5, 6, 41, 42: GPO0
to GPO3") and assigns names in ascending pin order instead of from the per-pin
pin-configuration figure. Lives in the extraction / pin-grounding path
(`src/pdf_extractor/pin_grounding.py`, `deterministic_table_parser.py`).

**Fix:** when a datasheet row groups multiple pins under a range name, take the
per-pin names from the pin-configuration **figure**, not the function table.
This is the same grouped-row root cause as P1-3; here it produces wrong
*assignments*, not just wrong *labels*.

### P0-4 · Exposed pad (EPAD) missing from symbol and footprint
**Part:** AD9106 (and any QFN/LFCSP/DFN with a thermal pad). *Jira: AD9106 SCH-01
HIGH, FP-02 HIGH.* The datasheet requires the exposed pad tied to ground; our
symbol has no EPAD pin and the footprint has no center pad → no thermal path, no
ground return.

**Fix:** when the package family has an exposed pad, add an **EPAD pin** to the
symbol and a **center exposed pad** (with windowed paste) to the footprint,
mapped to each other. Drive this off the QFN/LFCSP/DFN/SON family in
`footprint_defaults` + the symbol builder.

### P0-5 · Connector shield pins/pads missing
**Part:** 693072010801 (microSD). *Jira: SCH-01 HIGH, FP-02 HIGH.* Shield tabs
S1–S4 are absent from both symbol and footprint → shell can't be grounded; the
socket can tear off when a card is inserted.

**Fix:** connector packages must carry their shield/mounting pads and a shield
pin. Part of the connector-path work in P0-1.

---

## P1 — Generator-wide defects (fix once, clears every part)

### P1-1 · Paste mask tagged as copper (F.Cu) on every pad — all 6 parts
*Jira: FP-05 on TL16C2550/74LVC1G99/AD9106, FP-04 on ADV7180/PGA2311P, etc.*
Each pad's `PasteMask` node is a copy of the copper record: `name=CopperCirclePad`,
`layerId=F.Cu`. Nothing is tagged `F.Paste`, so the stencil exports empty (or as
duplicate copper), and every layer view draws the pads as red copper. Paste also
appears on through-hole pads, which should have none.

**Exact location:** `src/core/pcb_footprint_extras.py:283` — `_footprint_layer_id`
handles `CopperCirclePad → F.Cu` and `SolderMask → F.Mask` but has **no case for
the paste node**, so it inherits copper. The paste node is also mis-named
(`CopperCirclePad`).

**Fix:**
- Give the paste node its own name (e.g. `PasteMask`) and return `F.Paste` for it
  in `_footprint_layer_id`.
- **Skip paste entirely on through-hole pads.**
- Add it to the expected pin children / conformance check
  (`pcb_footprint_hierarchy.py:214` currently lists only SolderMask, CopperCirclePad,
  text for SMD).
- Verify with a Gerber export: paste layer has one aperture per SMD pad, none on TH.

### P1-2 · Active-low overbar not rendered (and flag not always set) — 5 parts
*Jira: TL16C2550 SCH-02, 74LVC1G99 SCH-01, AD9106 SCH-02, ADV7180 SCH-04,
PGA2311P SCH-01 (HIGH/MEDIUM).* Two sub-problems:
- **(a) overbar not drawn** even when `activeLow=true` is stored. The extras are
  correct (`schematic_extras.py:226` writes `activeLow` + a `/`-prefixed
  `displayName`, and the comment at line 183 says the frontend renders the bar) —
  so the drawn **label mesh/renderer never shows the bar.**
- **(b) flag not set** on some pins that are active-low per the datasheet
  (AD9106 CS/RESET/TRIGGER, ADV7180 PWRDWN/INTRQ) — an extraction/classification
  gap in `src/models/pin_classifier.py`.

**Fix:** (a) render the overbar from `activeLow`/`displayName` wherever the pin
label is drawn (rebuild the text mesh, not just the extra); (b) ensure the
active-low detector sets the flag from the datasheet's `*`/overbar/`#`/`/`
notation.

### P1-3 · Pin label drawn from grouped/stale text, not the per-pin name — 3 parts
*Jira: TL16C2550 SCH-01, ADV7180 SCH-03, PGA2311P SCH-02 (HIGH/MEDIUM).* `pinName`
is correct per pin, but the **drawn label** shows the datasheet's grouped row
("CSA, CSB", "D0-D4", "P7 to P2", "AIN1 to AIN6", "GPO0 to GPO3") or a scrambled
subscript ("V R IN" for VINR, "V CC").

**Why:** the schematic **text mesh is built once from the raw extraction** and is
not regenerated from `pinName` after the `/agentic` repair splits/cleans names
(confirmed by the handover note: "only the pinName extras are patched after
/agentic; text meshes are not"). So our accuracy work reaches the data but not
the rendered glyphs.

**Fix:** draw the label from the per-pin `pinName`/`displayName`, and **regenerate
the label mesh after `/agentic`** (or have the renderer read the extra instead of
baking text). Same code touched as P1-2(a) — the label-render path in
`src/schematic_generator/pinout_diagram_builder.py`.

### P1-4 · No 3D model on any part — all 6
*Jira: 3D-01 on every part (HIGH).* The GLB has only flat footprint layers + drill
cylinders. The editor's fallback body is built from the (wrong) footprint outline,
so it inherits the footprint's dimensional errors (e.g. AD9106 DIP box).

**Why:** `src/model3d/registry.py` is fail-closed — `select_template` raises for
any lead style without a parametric template (gull-wing families work; LFCSP /
XSON / microSD / SOT-223 / SOT-23 do not), and `build_body_model` then skips the
body (`builder.py:98–101`).

**Fix:**
- Attach the real vendor/catalog STEP where available (ADI LFCSP, Würth socket,
  TI PFB) — the pipeline's web rail can already fetch STEP for some.
- Add parametric templates for the missing lead styles (leadless QFN/SON, SOT-223,
  SOT-23).
- If a generated placeholder is kept, **size it from the datasheet package
  dimensions, not the footprint**, and color it like a real part.

> **Correction (2026-10-13, verified firsthand):** the "Why" above is inaccurate.
> The API runner *does* pass `--body-3d` (`src/api/jobs.py:215`), `_body.glb` +
> `_body.step` *are* registered downloadable artifacts, and all 6 QC parts
> *produce* a body (none fail-closed; TQFP/LQFP→quad_gullwing, XSON/LFCSP→leadless,
> PDIP→through_hole, microSD→gullwing). So "no 3D model" is **not** a generation
> gap. The body is written as a *separate* GLB, never merged into the footprint,
> and nothing in this repo consumes it — the editor builds its own fallback from
> the footprint outline. **3D render/consumption is therefore platform-side.** The
> only in-repo improvement left is *verified* bodies (extract A/A1 height dims so
> they aren't watermarked `unverified`) — worth doing only if the platform ingests
> our body GLB. Open gating question for the platform team: *do you ingest our
> `_body.glb`, or build your own from the footprint?*

### P1-5 · Pin electrical types left "unspecified" — 3 parts  *(was MISSING from this list)*
*Jira: AD9106 SCH-05, 693072010801 SCH-02, PGA2311P SCH-03 (all LOW).* Several
pin names fell through `classify_pin_name` as `(None, None)` and shipped as
electrical type `unspecified`, so ERC could not check them: AD9106 CLDO/DLDO
(should be power_out) and FSADJ2/CAL_SENSE; 693 DAT0–DAT2/CD-DAT3/CMD/CLK
(should be bidirectional/clock); PGA2311P VD+/VA+/VA−/AGNDR/AGNDL (power rails).

**Fix — DONE (commit `bd2b6d3`):** general name-pattern rules in
`src/models/pin_classifier.py` (LDO→power_out, ADJ/SENSE→passive/analog, rail
families→power_in, SD data→bidirectional); no part numbers hard-coded. The bare
`SS` (SPI slave-select) over-match was caught in review and tightened to require
the leading V. This cluster was absent from the original fix-list; recorded here
so the doc covers all 74 cards.

---

## P2 — Dimensional / drawing correctness (per-part HIGH/MEDIUM)

### P2-1 · Body / fab outline wrong size
Y-dimension comes out too small or wrong-package on several parts: TL16C2550
(101×107 mm vs 30×81; also 6.88×4.88 fab vs 7×7), 74LVC1G99 (1.28×3.35 vs
1.0×1.95), AD9106 (13.5×40.7 DIP outline vs 5×5), 693072010801 (DIP-8 outline),
ADV7180 (7.38 vs 7.00, minor). *Jira: various FP body + SCH body-size cards.*
Mostly downstream of P0-1 (wrong package) and the body-sizing math in
`pcb_footprint_builder`. Size the fab body from the real package, and the symbol
body from pin-column + label lengths (TL16C2550/ADV7180 symbols are ~3× too big).

### P2-2 · Courtyard wrong size
Follows the wrong pads (too big on 74LVC1G99/AD9106, too small on TL16C2550/
693072010801). *Jira: FP courtyard cards (HIGH/MEDIUM).* Recompute as pad
extents + 0.25 mm **after** P0-1/P2-1 land; for connectors include the
card-insertion side.

### P2-3 · Silkscreen runs over pads
TL16C2550 and ADV7180 draw a full silk rectangle whose edges lie on 24 pads.
*Jira: TL16C2550 FP-03, ADV7180 FP-02 (HIGH).* Draw silk as corner marks only,
≥0.2 mm clear of any pad, and add a silk-to-pad clearance check (≥0.15 mm) to
footprint generation.

### P2-4 · Solder-mask margin: declared 0.102 mm, applied 0.051 mm — all parts
*Jira: FP solder-mask cards (LOW).* The `SolderMask` shape is drawn at pad+0.051
while the pad declares 0.102. Store and apply one value per side consistently.
Lives alongside the `SolderMask` node in `pcb_footprint_extras.py`.

---

## P3 — Metadata & cosmetics (LOW, mostly one-line fixes)

- **P3-1 · MPN/Value hygiene.** 74LVC1G99: number truncated `74LVC1G99GT,115` →
  `74LVC1G99GT,1` (comma-split bug — check part-name parsing). 693072010801:
  MPN/Value hold the full product description instead of the bare part number.
  *Jira: SCH-02 / SCH-04.*
- **P3-2 · Library category.** AD9106 filed under ADC (it's a DAC); ADV7180 under
  drivers/receivers (it's a video decoder); 693072010801 under a generic
  placeholder (should be connector/memory card). *Jira: SCH-04/06.*
- **P3-3 · Footprint named after the part number, not the package** (AD9106,
  ADV7180) — give no package info. Name after the package (CP-32-12, ST-48).
- **P3-4 · Pin-1 marker outside the courtyard** and **value text ~15 mm wide**
  (most parts). Move the marker next to pad 1 inside the courtyard; scale value
  text to ~1 mm.
- **P3-5 · Pad-number text fixed 0.58 mm → two-digit numbers overlap** (TL16C2550,
  ADV7180). Size the number to fit inside its pad.
- **P3-6 · Pin layout house rule** (74LVC1G99, AD9106): functional grouping vs
  package order differs from the reference. Decide one rule and apply it to all
  generated symbols. *Jira: SCH-03 (Improvement).*
- **P3-7 · Land-pattern fine-tuning:** ADV7180 pads shifted 0.23 mm outward (short
  heel); TL16C2550 pads 0.17 mm short; PGA2311P 0.83 mm drill tight for PDIP
  leads. Use the vendor/IPC land pattern. *Jira: FP (LOW/Improvement).*

---

## Suggested order of work

1. **P1-1 (paste layer)** — smallest, precise, clears a defect on all 6 parts.
2. **P0-1 (package selection) + P0-4 (EPAD)** — unblocks AD9106, 693072010801,
   74LVC1G99 and feeds P2-1/P2-2 (body & courtyard follow the right package).
3. **P1-3 + P1-2 (label mesh + overbar render)** — one render path, clears the
   grouped-label and active-low findings our data layer already got right.
4. **P0-2 (square-package pad spans)** and **P0-3 (grouped-row assignment)**.
5. **P1-4 (3D)**, then **P2** dimensional items, then **P3** metadata/cosmetics.

---

## Complete Card Inventory (all 74)

Every issue in `IDEEZA_Part_Comparison_Log.pdf` (now also at `docs/IDEEZA_Part_Comparison_Log.pdf`),
one row per card, cross-referenced to the cluster above and to the commit that fixed it. **This table
is the authoritative per-card status** — the cluster sections are the root-cause writeups.

Reconciles to 74 (severity 5 HIGHEST / 23 HIGH / 20 MEDIUM / 26 LOW) and to the log's per-part counts
(TL16C2550 16 · 74LVC1G99 10 · AD9106 13 · 693072010801 12 · ADV7180 14 · PGA2311P 9). One caveat:
the PDF body prints only 73 cards — PGA2311P footprint **FP-03 is skipped and PDF page 105 is blank**,
while the summary credits PGA2311P footprint=5. Row 72 below is that dropped card, inferred as the
pin-1-marker defect (LOW, P3-4) since every other part carries it and the "seen on every part" section
lists it as universal.

Status legend: **Fixed `<hash>`** / **Open** (ours, not done) / **Blocked** (needs vendor data) /
**Not-ours** (platform/frontend). "data" notes mean our data layer is fixed but the rendered glyph is
platform-side.

| # | Part | Section | Sev | Issue | Cluster | Status |
|---|------|---------|-----|-------|---------|--------|
| 1 | TL16C2550 | Sch | HIGH | 31/48 pins show grouped label instead of pinName | P1-3 | Fixed `7a68c99` (data; render platform) |
| 2 | TL16C2550 | Sch | HIGH | No active-low marking (22 pins) | P1-2 | Fixed `277a927` |
| 3 | TL16C2550 | Sch | MED | Pins not grouped by function; D0-D7 split/out of order | P3-6 | Fixed `6cbacb6` (bus drawn in bit order; data+address blocks) |
| 4 | TL16C2550 | Sch | MED | Symbol body 101.6×106.7 mm, >3× reference | P2-1 | Won't-fix (functional grouping is deliberate — see note) |
| 5 | TL16C2550 | Sch | LOW | Value "TL16C2550" not "TL16C2550PFBR" | P3-1 | Fixed `307b5c7` |
| 6 | TL16C2550 | FP | HIGHEST | Top/bottom rows y=±3.20 not ±4.22; 24/48 miss leads | P0-2 | Fixed `2b640f0` |
| 7 | TL16C2550 | FP | HIGH | F.Fab 6.88×4.88 not 7.00×7.00 | P2-1 | Fixed `2b640f0` |
| 8 | TL16C2550 | FP | HIGH | Silk lines run over 24 pads | P2-3 | Not-reproduced (silk-pad clearance 0.23 mm ≥ 0.20; FP-07 clip handles it) |
| 9 | TL16C2550 | FP | MED | Courtyard 10.2×8.2, inside leads in Y | P2-2 | Fixed `2b640f0` |
| 10 | TL16C2550 | FP | MED | Paste tagged F.Cu on all 48 pads | P1-1 | Fixed `4b02744` |
| 11 | TL16C2550 | FP | MED | Layer views show red copper on every layer | P1-1 | Fixed `4b02744` (render platform) |
| 12 | TL16C2550 | FP | LOW | Pads 0.17 mm short of land pattern | P3-7 | Fixed `358577b` (L_max=0.75; pad 1.30→1.45) |
| 13 | TL16C2550 | FP | LOW | Pin-1 marker outside courtyard; value text 15.4 mm | P3-4 | Partial `a2c2864` (value text); marker deferred |
| 14 | TL16C2550 | FP | LOW | Solder mask 0.051 vs 0.102 declared | P2-4 | Fixed `6a70e86` |
| 15 | TL16C2550 | FP | LOW | Pad-number 0.58 mm overlaps at 0.5 mm pitch | P3-5 | Fixed `f1cf76c` |
| 16 | TL16C2550 | 3D | HIGH | No real 3D model; box at wrong size | P1-4 | Not-ours (3D consumption) |
| 17 | 74LVC1G99 | Sch | MED | OE flagged active-low but drawn without overbar | P1-2 | Fixed `277a927` (overbar render platform) |
| 18 | 74LVC1G99 | Sch | MED | Part number cut to 74LVC1G99GT,1 not ...,115 | P3-1 | Fixed `307b5c7` (worked around; comma-split root platform) |
| 19 | 74LVC1G99 | Sch | LOW | Pin order differs from standard | P3-6 | Won't-fix (D,C,B,A single letters, not a numbered bus — convention) |
| 20 | 74LVC1G99 | FP | HIGHEST | Wrong land pattern; 8 pads outside package | P0-1 | Fixed `eb29820` (+`a276816`) |
| 21 | 74LVC1G99 | FP | HIGH | Body 1.28×3.35 not 1.0×1.95 | P2-1 | Fixed `a2c2864` |
| 22 | 74LVC1G99 | FP | MED | Courtyard 4.2×3.85, 4× standard | P2-2 | Fixed `a2c2864` (follows XSON body → courtyard now 2.20×2.50, = standard; verified) |
| 23 | 74LVC1G99 | FP | MED | Paste tagged F.Cu on all 8 pads | P1-1 | Fixed `4b02744` |
| 24 | 74LVC1G99 | FP | LOW | Solder mask 0.051 vs 0.102 | P2-4 | Fixed `6a70e86` |
| 25 | 74LVC1G99 | FP | LOW | Pin-1 only a dot outside courtyard | P3-4 | Deferred (FP-08 contradiction) |
| 26 | 74LVC1G99 | 3D | HIGH | No 3D model; body follows wrong footprint | P1-4 | Not-ours (3D consumption) |
| 27 | AD9106 | Sch | HIGH | EPAD pin missing from symbol | P0-4 | Fixed `ea25c2e` |
| 28 | AD9106 | Sch | HIGH | No active-low on CS, RESET, TRIGGER | P1-2 | Fixed `277a927` (flag; bare-name render platform) |
| 29 | AD9106 | Sch | LOW | Pin order/shape differ from standard | P3-6 | Won't-fix (mixed-prefix analog block — convention, like #4/#56) |
| 30 | AD9106 | Sch | LOW | Filed under ADC but is a DAC | P3-2 | Not-ours (category) |
| 31 | AD9106 | Sch | LOW | CLDO unspecified; pin 24 type inconsistent | P1-5 | Fixed `bd2b6d3` |
| 32 | AD9106 | FP | HIGHEST | Through-hole DIP-32 not 5×5 LFCSP-32 | P0-1 | Fixed `eb29820` |
| 33 | AD9106 | FP | HIGH | No exposed pad | P0-4 | Fixed `bc102a9` |
| 34 | AD9106 | FP | HIGH | Body 13.5×40.7 not 5×5 | P2-1 | Fixed `eb29820` (follows package; outline unverified) |
| 35 | AD9106 | FP | MED | Courtyard 17.3×41.2, 18× standard | P2-2 | Fixed `eb29820` (follows package) |
| 36 | AD9106 | FP | MED | Paste tagged F.Cu | P1-1 | Fixed `4b02744` |
| 37 | AD9106 | FP | LOW | Solder mask 0.051 vs 0.102 | P2-4 | Fixed `6a70e86` |
| 38 | AD9106 | FP | LOW | Pin-1 marker outside courtyard | P3-4 | Deferred (FP-08 contradiction) |
| 39 | AD9106 | 3D | HIGH | 3D shows DIP-32 box not 5×5 LFCSP | P1-4 | Not-ours (3D consumption) |
| 40 | 693072010801 | Sch | HIGH | Shield pins S1–S4 missing from symbol | P0-5 | Blocked (only 8 contacts extracted; shield tabs need vendor spec, like #45) |
| 41 | 693072010801 | Sch | MED | MPN/value hold product description not part number | P3-1 | Fixed `307b5c7` |
| 42 | 693072010801 | Sch | LOW | Signal pins typed unspecified | P1-5 | Fixed `bd2b6d3` |
| 43 | 693072010801 | Sch | LOW | Pin order/side/shape differ from standard | P3-6 | Won't-fix (connector vs IC symbol — convention) |
| 44 | 693072010801 | FP | HIGHEST | Through-hole DIP-8 not SMD microSD socket | P0-1 | Fixed `93dc79b` |
| 45 | 693072010801 | FP | HIGH | No shield pads | P0-5 | Blocked (Würth land pattern) |
| 46 | 693072010801 | FP | HIGH | Body 5.9×10.2 not 13.6×13.7 | P2-1 | Blocked (vendor dims) |
| 47 | 693072010801 | FP | MED | Courtyard smaller than real connector | P2-2 | Blocked (vendor dims) |
| 48 | 693072010801 | FP | MED | Paste tagged F.Cu | P1-1 | Fixed `4b02744` |
| 49 | 693072010801 | FP | LOW | Solder mask 0.051 vs 0.102 | P2-4 | Fixed `6a70e86` |
| 50 | 693072010801 | FP | LOW | Pin-1 marker outside courtyard | P3-4 | Deferred (FP-08 contradiction) |
| 51 | 693072010801 | 3D | HIGH | No 3D model | P1-4 | Blocked (vendor STEP) / Not-ours consumption |
| 52 | ADV7180 | Sch | HIGHEST | Pins 24/25 wrong: ELPF↔AGND, PVDD↔ELPF | P0-3 | Fixed `97c5540` (deterministic variant-table read: 24=ELPF, 25=PVDD) |
| 53 | ADV7180 | Sch | HIGH | GPO0/1 and GPO2/3 swapped | P0-3 | Partial `97c5540` (vision figure-read; live test: 5/6 correct, 41/42 returned GPO2/GPO3 — not yet reliably correct) |
| 54 | ADV7180 | Sch | HIGH | 16 pins show grouped label | P1-3 | Fixed `7a68c99` (data; render platform) |
| 55 | ADV7180 | Sch | HIGH | Active-low missing on PWRDWN, INTRQ; not drawn on RESET | P1-2 | Fixed `277a927` (flag; render platform) |
| 56 | ADV7180 | Sch | MED | Symbol body 86×91 mm, 2.8× reference | P2-1 | Won't-fix (functional grouping is deliberate — see note) |
| 57 | ADV7180 | Sch | LOW | Category drivers/receivers (is video decoder) | P3-2 | Not-ours (category) |
| 58 | ADV7180 | FP | HIGH | Silk lines run over 24 pads | P2-3 | Not-reproduced (silk-pad clearance 0.23 mm ≥ 0.20; FP-07 clip handles it) |
| 59 | ADV7180 | FP | MED | Pads shifted 0.23 mm outward (short heel) | P3-7 | Fixed `358577b` (pad center 4.45→4.20, on the foot) |
| 60 | ADV7180 | FP | MED | Paste tagged F.Cu | P1-1 | Fixed `4b02744` |
| 61 | ADV7180 | FP | LOW | Body 7.38 mm larger than package max | P2-1 | Fixed `358577b` (MS-026 body 7.38→7.00) |
| 62 | ADV7180 | FP | LOW | Solder mask 0.051 vs 0.102 | P2-4 | Fixed `6a70e86` |
| 63 | ADV7180 | FP | LOW | Pin-1 marker outside courtyard | P3-4 | Deferred (FP-08 contradiction) |
| 64 | ADV7180 | FP | LOW | Pad numbers larger than pads, overlap | P3-5 | Fixed `f1cf76c` |
| 65 | ADV7180 | 3D | HIGH | No 3D model | P1-4 | Not-ours (3D consumption) |
| 66 | PGA2311P | Sch | HIGH | CS and MUTE lost active-low marking | P1-2 | Fixed `277a927` |
| 67 | PGA2311P | Sch | MED | 7 labels scrambled ("V R IN" for VINR) | P1-3 | Not-ours (subscript render / label mesh) |
| 68 | PGA2311P | Sch | LOW | 5 power pins typed unspecified | P1-5 | Fixed `bd2b6d3` |
| 69 | PGA2311P | FP | MED | Body 5.87×20.38 not 6.4×19.3 | P2-1 | Fixed `358577b`+`fe9dc14` (length 19.38; width now 6.35 via FP-19 through-hole exemption) |
| 70 | PGA2311P | FP | MED | Paste nodes on through-hole pads, F.Cu | P1-1 | Fixed `4b02744` (no paste on TH) |
| 71 | PGA2311P | FP | LOW | Drill 0.83 mm tight for PDIP leads | P3-7 | Not-reproduced (0.83 mm is vendor-correct: TI golden ref 0.813, IPC-2222) |
| 72 | PGA2311P | FP | LOW | *[FP-03 dropped from PDF; inferred pin-1-marker]* | P3-4 | Deferred (FP-08 contradiction) |
| 73 | PGA2311P | FP | LOW | Solder mask 0.051 vs 0.102 | P2-4 | Fixed `6a70e86` |
| 74 | PGA2311P | 3D | HIGH | No 3D model (EasyEDA links PDIP-16, not exported) | P1-4 | Not-ours (3D consumption) |

### Tally (of 74)
- **Fixed / data-fixed:** ~38 (generator-wide fixes count per-part: paste ×6, solder-mask ×6, etc.)
- **Open — ours, doable:** P2-1 symbol body (#4, #56) + fp body (#61, #69), P2-3 silk (#8, #58), P3-6 pin layout (#3, #19, #29, #43), P3-7 land pattern (#12, #59, #71), P0-3 ADV7180 pins 24/25 (#52) + GPO order (#53)
- **Blocked (vendor data):** #45, #46, #47, #51 (693 microSD)
- **Deferred (FP-08 contradiction):** pin-1 marker #13(part), #25, #38, #50, #63, #72
- **Not-ours (platform/frontend):** 3D consumption #16/26/39/65/74, category #30/#57, label-mesh/subscript render #67, overbar render (render half of #17/#28/#55)

### Decision note — symbol body size #4 / #56 (WON'T-FIX, 2026-10-13)
Verified firsthand: the oversized schematic body is **not a sizing bug**. `ROLE_SIDE`
(`component_record.py`) maps every pin role to **left or right only**, and
`check_functional_grouping` (conformance SYM-04) enforces it — so a 48-pin part stacks
~32 pins in one column at the 2.54 mm grid → ~100 mm tall. The "mostly empty" width is
load-bearing too: narrowing below `column_floor` flips the tall column's end pins to
top/bottom and breaks 3 conformance tests. The compact reference (~35 mm) achieves its
size only by using a **4-sided, package-order** layout that **abandons functional
grouping** — the opposite of what card **#3** asks for (group by function) and of our
deliberate, conformance-enforced convention. Decision: **keep functional grouping**;
#4/#56 are accepted as-is. Changing it would be a cross-cutting layout redesign
(`src/models` ROLE_SIDE + `src/conformance`), not a bug fix.

### Follow-up — #69 PGA2311P body WIDTH (open, needs a conformance decision)
The length is fixed (`358577b`, 20.38→19.38). The width stays clamped to 5.87 mm
instead of the real 6.35 mm because a real DIP body overlaps the through-hole
annular rings (normal for DIP), and the **FP-19 conformance check**
(`src/conformance/checks.py`) forbids any fab-over-pad — its committed test
asserts DIP-8 passes, so the builder clamps the width. Correcting it needs an
**FP-19 through-hole exemption** (let leaded/TH bodies overlap their own
annulus), a conformance change out of scope for the footprint-defaults work.
