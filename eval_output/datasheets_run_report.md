# Datasheets Folder — Pipeline Test Report

Running record of every PDF in `datasheets/` through the full pipeline
(`python3 -m src.main <pdf> <out> --both`), with one verdict per part:
**correct** (output matches the datasheet, or a justified refusal) or **not**.

Code under test: branch `worktree-fixes-round2` (round-2 fixes, PR #1).
Harness: `tools/run_full_flow_eval.py`. GLB outputs and raw JSON reports are
kept next to each run's folder under `eval_output/` in the worktree.

---

## Batch: stems 1–20 (DigiKey corpus) — run 2026-07-19, after all round-2 fixes

**Score: 16/20 correct** (11 generated correctly, 5 correct refusals), 4 not.

| Part | Verdict | Pins | Pitch (mm) | Notes |
|---|---|---|---|---|
| 1_LS7641-S | ✅ CORRECT | 14 | 1.27 | schematic + footprint generated, pin data matches ground truth |
| 2_CDBHM1100L-HF | ✅ CORRECT (refusal) | — | — | no pin-function table in the sheet; refusing is the right outcome |
| 3_MB10S | ✅ CORRECT | 4 | 1.27 | schematic + footprint generated, pin data matches ground truth |
| 4_MB6S-E3-80 | ✅ CORRECT (refusal) | — | — | no pin-function table in the sheet; refusing is the right outcome |
| 5_SN6501QDBVRQ1 | ✅ CORRECT | 5 | 0.635* | all 5 pins placed (3+2 SOT-23-5); *pitch is a measurement artifact of the asymmetric rows, real pitch 0.95 |
| 6_SN6505ADBVR | ❌ FAIL | — | — | page detection still feeds wrong pages; grounding gate blocks invented pin names, fails closed after retries |
| 7_TPS2514DBVR | ✅ CORRECT | 6 | 0.95 | schematic + footprint generated, pin data matches ground truth |
| 8_MMBD3004CA-RFG | ✅ CORRECT | 3 | — | schematic + footprint generated, pin data matches ground truth |
| 9_BQ25570RGRT | ✅ CORRECT | 20 | 0.8 | schematic + footprint generated, pin data matches ground truth |
| 10_BQ500211RGZR | ✅ CORRECT | 48 | 0.55 | schematic + footprint generated, pin data matches ground truth |
| 11_BQ500511ARHAR | ✅ CORRECT | 40 | 0.55 | schematic + footprint generated, pin data matches ground truth |
| 12_BQ51050BRHLR | ✅ CORRECT | 20 | 0.8 | schematic + footprint generated, pin data matches ground truth |
| 13_MAX845EUA+ | ✅ CORRECT | 8 | 0.65 | µMAX on the correct MSOP grid (was 1.27 before round-2 fixes) |
| 14_TPS23751PWP | ❌ WRONG | 20 | 0.65 | right family/grid, but read the sheet's 20-pin column; expected 16 pins |
| 15_SN65LVDS104PWR | ❌ WRONG | 20 | 0.65 | right family/grid, but read the sheet's 20-pin column; expected 16 pins |
| 16_TPS23751PWPR | ❌ WRONG | 20 | 0.65 | right family/grid, but read the sheet's 20-pin column; expected 16 pins |
| 17_DF10S | ✅ CORRECT | 4 | 2.54 | schematic + footprint generated, pin data matches ground truth |
| 18_HD06-T | ✅ CORRECT (refusal) | — | — | no pin-function table in the sheet; refusing is the right outcome |
| 19_MB10F-13 | ✅ CORRECT (refusal) | — | — | no pin-function table in the sheet; refusing is the right outcome |
| 20_CDBU40-HF | ✅ CORRECT (refusal) | — | — | no pin-function table in the sheet; refusing is the right outcome |

---

## Batch: stems 21–30 (new parts) — run 2026-07-19, tests only (no code changes)

**Score: 5/10 correct** (1 generated correctly, 4 correct refusals), 1 partial, 4 not.
No ground-truth table exists for these stems yet; every verdict below was
verified manually against the datasheet's own ordering/package pages.

| Part | Verdict | Pins | Pitch (mm) | Notes |
|---|---|---|---|---|
| 21_ATTINY13A-MMU | ❌ WRONG VARIANT | 8 | 2.54 | extracted the PDIP-8 column; the MMU order code is the 10-pad QFN/MLF. Atmel/Microchip order codes are not decoded (designator system is TI-only) |
| 22_MAX5969BETB+T | ✅ CORRECT | 10 | 0.5 | ETB+ = 10-pin TDFN-EP 3×3 mm, 0.5 mm pitch — matches |
| 23_NCP4308DMTTWG | ⚠️ PARTIAL | 8 | 0.65 | 8 pins correct, but footprint used the DFN-8 0.65 default; the DMTT orderable is WDFN8 2×2 at 0.5 mm pitch. ON Semi suffixes not decoded |
| 24_UCC24610DRBT | ❌ WRONG VARIANT | 8 | 1.27 | extracted the D (SOIC-8) variant; DRB = SON-8 3×3 with thermal pad. DRB is a real TI designator missing from TI_DESIGNATOR_FAMILIES |
| 25_B40C800DM-E3-45 | ✅ CORRECT (refusal) | — | — | 4-terminal bridge; grounding gate blocked hallucinated 'Anode/Cathode' names, failed closed |
| 26_B80C800DM-E3-45 | ✅ CORRECT (refusal) | — | — | same as 25 |
| 27_DB102-BP | ✅ CORRECT (refusal) | — | — | 4-terminal bridge, no relevant pages — correct refusal |
| 28_DB107-BP | ✅ CORRECT (refusal) | — | — | same as 27 |
| 29_AVR128DA48-I-PT | ❌ FAIL (no output) | — | — | expected 48-pin TQFP. Grounding gate blocked pin names not present in extracted text — incl. 'VCC', which genuinely doesn't exist on AVR-Dx (it's VDD), i.e. the LLM recited from memory. Pinout is a figure; page/diagram handling gap |
| 30_dsPIC33FJ128MC204-I-PT | ❌ FAIL (no output) | — | — | expected 44-pin TQFP. Grounding gate blocked 'RA5'/'RA6' etc. — pins that only exist on larger dsPIC packages; the LLM recited a sibling package's pinout and the validator correctly refused it |

### Findings from this batch (for the next fix round — no code changed today)
1. **Vendor coverage of order-code decoding is TI-only.** Atmel `-MMU` (10-QFN),
   ON Semi `DMTT` (WDFN8 2×2), and even TI's own `DRB` (SON-8) are not in the
   designator tables, so the wrong-variant gate cannot fire for them.
   Adding published designators is the highest-leverage follow-up.
2. **Large microcontroller sheets (29, 30) fail closed instead of extracting.**
   Their pinouts are drawings, not tables; the grounding gate is doing its job
   (both blocked extractions were provably hallucinated), but producing correct
   output needs diagram-aware extraction (vision path) plus page detection that
   surfaces the pinout figure page.
3. The `Cannot set gray non-stroke color` messages in the logs are harmless
   pdfminer noise from these PDFs' color operators, not the failure cause.

---

## Batch: stems 31–40 (new parts) — run 2026-07-19, tests only (no code changes)

**Score: 2/10 correct**, 8 not. Every verdict verified against the document
(package/pin-assignment pages) — no ground-truth table exists for these stems.

| Part | Verdict | Pins | Notes |
|---|---|---|---|
| 31_dsPIC33FJ128MC710A-I-PF | ❌ FAIL (no output) | — | expected TQFP-100. Grounding gate blocked 'RC0'/'RC5'–'RC11' — port pins that don't exist on the MC710A (Port C is RC1–4/RC12–15); the LLM recited a generic dsPIC port map and the validator refused it |
| 32_dsPIC33FJ256MC710A-I-PF | ❌ FAIL (no output) | — | **byte-identical file to #31** (same shared datasheet); identical outcome |
| 33_INA234AIYBJR | ✅ CORRECT (by design) | 8 | 8-pin schematic matches the 8-bump DSBGA; footprint deliberately refused for ball-grid packages (same policy as ADXL345) |
| 34_MKL17Z256CAL4R | ❌ WRONG | 12 | schematic has 12 pins; the CAL orderable is a **36-ball WLCSP** (per the sheet's own selector table). NXP order codes not decoded |
| 35_MKL43Z256VMP4 | ❌ WRONG | 13 | schematic has 13 pins; VMP = **64-ball MAPBGA** (verified in sheet) |
| 36_MKL46Z256VMC4 | ❌ WRONG | 13 | schematic has 13 pins; VMC orderable is an **84-pin** package (verified in sheet) |
| 37_ESP32-WROOM-32D-N16 | ❌ WRONG | 36 | module has 38 pins + keepout/pad 39 per its Pin Definitions; schematic has 36. Footprint refused (castellated module) |
| 38_ESP32C3WROOM02H4 | ❌ WRONG (silent) | 20 | **only silently-wrong output of the batch**: exit 0, both GLBs written — a 20-pin, 0.8 mm QFN-style footprint for a module with 18 castellated pins. Modules are not detected as out-of-scope |
| 39_MAX-M10S-00B | ❌ WRONG | 16 | pin-assignment table is 1–18 (LCC-18); schematic has 16. Footprint refused |
| 40_CAM-M8Q-0 | ✅ CORRECT (by design) | 31 | 31-pin schematic matches the module's 31-pin LGA; footprint refused for grid-array. (Pin names not individually verified) |

### Findings from this batch (recorded only — no code changed)
1. **Modules (castellated/LGA) are not recognized as out-of-scope.** #38 shipped
   a QFN-style footprint for a castellated Wi-Fi module with exit 0 — the same
   silent-wrong class the round-2 gates eliminated for chips. A module detector
   (castellated/LGA keywords, "module" in title) should force schematic-only or
   refusal.
2. **Pin-count-vs-order-code decoding covers only STM32.** NXP Kinetis
   (CAL=WLCSP-36, VMP=MAPBGA-64, VMC=84), Microchip (-I/PF=TQFP-100) all encode
   the package/pin count in the orderable; none are decoded, so 12-pin
   schematics for 64-ball parts pass validation.
3. **Big-MCU pinouts are figures, not tables** (31/32, and 29/30 in the prior
   batch). The grounding gate demonstrably catches the resulting LLM
   hallucinations (every blocked name was provably absent from the device),
   so these fail closed — but producing correct output needs diagram-aware
   extraction.
4. **Corpus intake:** #31/#32 are byte-identical files — the intake
   validation recommended in the 1–20 report (flag byte-duplicates) applies.

---

## Batch: stems 41–50 (new parts) — run 2026-07-21, tests only (no code changes)

**Score: 3/10 correct**, 2 partial, 5 not (3 silently wrong, 2 fail-closed refusals).
Every verdict verified against the sheet's own ordering/package pages
(pin counts read from the GLB node tree, pitch measured from pad centers).

| Part | Verdict | Pins | Pitch (mm) | Notes |
|---|---|---|---|---|
| 41_SN6507DGQR | ⚠️ PARTIAL | 10 | 0.65 | 10 pins correct, but DGQ = HVSSOP-10 at **0.5 mm** pitch; HVSSOP normalized to SSOP, which "has no dedicated geometry; approximating with SOIC" landed on the 0.65 grid. DGQ missing from TI designator tables |
| 42_INA228AIDGSR | ✅ CORRECT | 10 | 0.5 | VSSOP (DGS) 10-pin, 0.5 mm — matches the sheet exactly |
| 43_INA238AIDGSR | ✅ CORRECT | 10 | 0.5 | same as 42 — matches |
| 44_TPS51100DGQ | ❌ WRONG (silent) | 20 | 0.5 | **20-pin footprint+schematic for a 10-pin part**, exit 0, no warnings. Deterministic parser bailed; LLM emitted a self-consistent 20-pin package so no gate fired (DGQ not in designator tables). A repeat run of the same extraction failed closed — the outcome is nondeterministic |
| 45_NCP5623BMUTBG | ❌ WRONG (silent) | 16 | 1.27 | true package is **LLGA-12** (12 pins, leadless). LLM claimed 'SOIC-16'; validator feedback said "re-extract ensuring all 16 pins are present" and the retry **invented 4 pins to satisfy the wrong package claim**. Exit 0, SOIC-16 footprint for a leadless 12-pad part |
| 46_LSM6DSO32TR | ✅ CORRECT (by design) | 14 | — | 14-pin schematic matches LGA-14; footprint deliberately refused (grid-array policy) |
| 47_NRF9160-SICA | ❌ FAIL (no output) | — | — | 400-page LGA-127 SiP module; no pins extracted after retries, failed closed. Pin assignments live on p385 of a 400-page doc — page detection never surfaces them |
| 48_NRF9160-SICA | ❌ FAIL (no output) | — | — | **byte-identical file to #47** — yet took a different path: LLM claimed package type 'B13' (a ball designator), refused as unknown package. Same input, different refusal = extraction nondeterminism, but both fail closed |
| 49_ADT7516ARQZ-REEL7 | ❌ WRONG (silent) | 16 | 1.27 | 16 pins correct, but QSOP-16 is **0.635 mm** pitch; output is on the 1.27 SOIC grid — pads align with every other lead. Exit 0 |
| 50_ADT7470ARQZ-REEL7 | ⚠️ PARTIAL | 16 | 0.65 | same QSOP-16 as 49 but landed on the 0.65 SSOP grid — 15 µm/pin off the true 0.635; near-usable but not the datasheet grid. The 49-vs-50 split shows the grid depends on which alias the LLM happens to utter |

### Findings from this batch (recorded only — no code changed)
1. **The retry-with-feedback loop can coerce hallucination (#45).** When the
   package claim (SOIC-16) disagreed with the extracted pins (12), the feedback
   told the LLM to produce more pins instead of questioning the package. The
   grounded quantity (pins found in the sheet) should win over the ungrounded
   package string; today the loop resolves the conflict in the wrong direction.
2. **Three new silent-wrong outputs (44, 45, 49)** — the class round-2 had
   eliminated for stems 1–20. Common thread: the failing gates are all
   order-code/package-shape gates that only cover a few TI designators. `DGQ`
   (HVSSOP-10) and `DGS` (VSSOP-10) are ordinary TI designators still missing
   from TI_DESIGNATOR_FAMILIES; QSOP/`RQ` (0.635 mm) has no geometry mapping at
   all and gets whichever of SOIC/SSOP the LLM names.
3. **SSOP/QSOP geometry gap:** "Package type 'SSOP' has no dedicated geometry;
   approximating with SOIC" quietly substitutes wrong grids (0.65 for HVSSOP's
   0.5; 1.27 or 0.65 for QSOP's 0.635). Identical parts 49/50 got different
   grids depending on the LLM's package wording.
4. **Extraction nondeterminism:** byte-identical 47/48 took different failure
   paths; a rerun of 44 refused where the batch run silently emitted 20 pins.
   Verdicts for LLM-path parts are not stable run-to-run.
5. **Corpus intake:** #47/#48 are byte-identical files (same MD5) — second
   duplicate pair after #31/#32.

---

## Batch: stems 51–55 (new parts) — run 2026-07-21, tests only (no code changes)

**Score: 4/5 correct** (all four are justified refusals), 1 not (silent).

| Part | Verdict | Pins | Pitch (mm) | Notes |
|---|---|---|---|---|
| 51_AMC6821SDBQR | ❌ WRONG (silent) | 16 | 1.27 | 16 pins correct, but DBQ = QSOP-16 at **0.635 mm**; footprint is on the 1.27 SOIC grid — pads hit every other lead. Exit 0, identical failure to #49 |
| 52_PIC16F1512-I-SS | ✅ CORRECT (refusal) | — | — | **the file is not the datasheet** — it is Microchip's "LCD Clock Demo User's Guide" (DS41448A). Grounding gate blocked the LLM's from-memory PIC pins ('RA2', 'RB1', …16 names not in the document) and failed closed. Corpus intake: mislabeled file |
| 53_MBR1535CTG | ✅ CORRECT (refusal) | — | — | TO-220 Schottky pair, no pin-function table; blocked hallucinated 'Anode'/'Cathode' labels — same class as the bridge rectifiers (25–28) |
| 54_STPS30M60ST | ✅ CORRECT (refusal) | — | — | TO-220AB rectifier; same refusal as 53 |
| 55_STTH8R06DIRG | ✅ CORRECT (refusal) | — | — | order code = TO-220AC Ins. (2-lead); refused honestly: "Unknown package type 'TO-220AC'" with a `--force-best-effort` escape hatch |

### Findings from this batch (recorded only — no code changed)
1. **QSOP grid failure reproduced (#51):** third QSOP-16 part (after 49, 50)
   and again a wrong grid at exit 0. QSOP (TI designator `DBQ`, ADI `RQ`)
   needs a geometry mapping at 0.635 mm; until then every QSOP part is a
   coin-flip between 1.27 and 0.65.
2. **The grounding gate handled a mislabeled corpus file perfectly (#52):**
   fed a document that isn't a datasheet, the LLM recited the part's pinout
   from memory and every name was blocked as absent from the text.
3. **Corpus intake:** #52 is a demo-board user's guide, not the PIC16F1512
   datasheet — third intake defect (after duplicate pairs 31/32 and 47/48).

---

## Batch: stems 56–60 (new parts) — run 2026-07-21, tests only (no code changes)

**Score: 5/5 correct** — all justified refusals; every part is an out-of-scope
discrete (triac, axial diodes, SMA diodes), and each failed closed with a clear
reason and a `--force-best-effort` escape hatch. Zero silent errors.

| Part | Verdict | Notes |
|---|---|---|
| 56_BT136-600E-127 | ✅ CORRECT (refusal) | TO220AB triac; the sheet has a real 3-pin PINNING table, but the package family is unsupported — refused honestly: "Unknown package type 'TO220AB'" |
| 57_1N4001RLG | ✅ CORRECT (refusal) | axial-lead rectifier (CASE 59-10); no relevant pages found — nothing to extract |
| 58_1N5408-E3-54 | ✅ CORRECT (refusal) | DO-201AD axial rectifier; refused as unknown package type |
| 59_MBRA140T3G | ✅ CORRECT (refusal) | SMA (CASE 403D) Schottky; grounding gate blocked a hallucinated 'Anode' pin name |
| 60_SS14 | ✅ CORRECT (refusal) | SMA (DO-214AC) Schottky; refused as unknown package type |

---

## Batch: stems 61–75 (new parts) — run 2026-07-22, tests only (no code changes)

**Score: 13/15 correct** (all justified refusals), 2 not (both silent wrong
variants). The batch is dominated by out-of-scope discretes, which the gates
handled cleanly; the two misses are both multi-variant sheets where the order
code was not decoded.

| Part | Verdict | Notes |
|---|---|---|
| 61_X0202NN-5BA4 | ✅ CORRECT (refusal) | SOT-223 triac; the LLM proposed **'Base'/'Collector'/'Emitter' — BJT pins for a triac** — and the grounding gate blocked all three |
| 62_Z0103NN5AA4 | ✅ CORRECT (refusal) | refused honestly: "Unknown package type 'SOT223'" (real pinning table exists; SOT-223 geometry is a coverage gap) |
| 63_Z0107MN-5AA4 | ✅ CORRECT (refusal) | **byte-identical file to 62** (shared family sheet); same refusal |
| 64_Z0109MN-6AA4 | ✅ CORRECT (refusal) | **byte-identical file to 62/63**; same refusal |
| 65_STPS20L60CG-TR | ✅ CORRECT (refusal) | D2PAK diode; grounding gate blocked a hallucinated 'C3' pin |
| 66_STTH2003CG-TR | ✅ CORRECT (refusal) | blocked hallucinated 'Anode'/'Cathode' |
| 67_MBRB60H100CTT4G | ✅ CORRECT (refusal) | refused honestly: unknown package 'D2PAK' |
| 68_LM2673S-5.0-NOPB | ❌ WRONG VARIANT (silent) | built the sheet's **VSON-14** (14 pads, 0.5 mm) but the `S` order code = **TO-263 7-lead**. Exit 0, no warnings — order code not decoded |
| 69_AD536AKH | ✅ CORRECT (refusal) | picked the right variant from the order code (`H` = TO-100 can) and refused it honestly as unsupported |
| 70_AD636JHZ | ❌ WRONG VARIANT (silent) | built the sheet's **SBDIP-14** (2.54 mm) but `JHZ` = **TO-100 10-lead metal can**. Exit 0 |
| 71_AD537JH | ✅ CORRECT (refusal) | refused unknown package 'D-14' — fail-closed; note the LLM had picked the DIP variant over the ordered TO-100 can |
| 72_AD537KH | ✅ CORRECT (refusal) | **byte-identical file to 71**; same refusal |
| 73_GBU6K-E3-45 | ✅ CORRECT (refusal) | GBU bridge; blocked hallucinated terminal names (same class as 25–28) |
| 74_GBJ2506-F | ✅ CORRECT (refusal) | GBJ bridge; blocked 'A1'/'K1'/'K2' |
| 75_GBU4M-E3-51 | ✅ CORRECT (refusal) | GBU bridge; blocked hallucinated terminal names |

### Findings from this batch (recorded only — no code changed)
1. **Both misses are the order-code gap again (68, 70):** multi-variant sheets
   where the pipeline extracted a *different real variant* than the one
   ordered (VSON-14 vs TO-263-7; SBDIP-14 vs TO-100). Same root cause as
   21/24/34–36; NSC/TI `S` and ADI `H`/`JHZ` suffixes are not decoded.
2. **The refusal gates are now the strongest part of the pipeline:** 13
   out-of-scope discretes refused with correct reasons, including catching
   BJT pin names proposed for a triac (61) — zero false outputs among them.
3. **SOT-223 is a plausible support gap** (62–64 have clean 3-pin+tab pinning
   tables) if surface-mount triacs/regulators matter for the product.
4. **Corpus intake:** 62/63/64 are a byte-identical *triple*, 71/72 a
   byte-identical pair — duplicate count is now 4 groups (31/32, 47/48,
   62/63/64, 71/72).

---

## Overall standing (75 parts tested, 2026-07-22)

- **48/75 correct** (16 correct outputs + 32 correct refusals/by-design outcomes),
  3 partial, 24 not.
- Stems 1–20 (chip-scale corpus): 16/20 correct, zero silent errors.
- Stems 21–40 (new, heavier corpus: big MCUs, BGAs, modules): 7/20 correct —
  dominated by three systematic gaps: vendor order-code decoding (TI-only
  today), diagram-only pinouts on large MCUs, and no module/out-of-scope
  detector. One silent wrong output (#38, module-as-QFN).
- Stems 41–50 (small-package mix): 3/10 correct, 2 partial. Three silent-wrong
  outputs (44, 45, 49), all traceable to two gaps: designator/geometry coverage
  (DGQ, DGS, QSOP/RQ) and the retry loop resolving package-vs-pin-count
  conflicts toward the ungrounded package claim. 47/48 are byte-identical
  duplicates (like 31/32).
- Stems 51–55: 4/5 correct — all four justified refusals (TO-220 diodes and a
  mislabeled corpus file the grounding gate caught); the one miss is a third
  QSOP wrong-grid at exit 0 (#51, same as #49).
- Stems 56–60: 5/5 correct — all out-of-scope discretes refused cleanly,
  zero silent errors.
- Stems 61–75: 13/15 correct — every refusal justified (incl. blocking BJT
  pin names proposed for a triac); both misses are silent wrong-variant
  outputs on multi-variant sheets (68 VSON-14 vs TO-263-7, 70 SBDIP-14 vs
  TO-100 can) — the order-code decoding gap again.
