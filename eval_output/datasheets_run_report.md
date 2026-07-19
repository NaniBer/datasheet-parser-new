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

## Overall standing (40 parts tested, 2026-07-19)

- **23/40 correct** (13 correct outputs + 10 correct refusals/by-design outcomes),
  1 partial, 16 not.
- Stems 1–20 (chip-scale corpus): 16/20 correct, zero silent errors.
- Stems 21–40 (new, heavier corpus: big MCUs, BGAs, modules): 7/20 correct —
  dominated by three systematic gaps: vendor order-code decoding (TI-only
  today), diagram-only pinouts on large MCUs, and no module/out-of-scope
  detector. One silent wrong output (#38, module-as-QFN).
