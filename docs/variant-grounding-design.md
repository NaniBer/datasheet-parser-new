# Variant grounding — design for the wrong-variant accuracy fix (Phase 1, C+D)

**Date:** 2026-08-09
**Status:** Design (no code changed). Prep for the highest-leverage accuracy fix.
**Problem class:** wrong package variant selected → wrong pin count.

## 1. Problem

A datasheet documents several package variants of one part, each with a
different pin count. The extractor picks the wrong one, so the pin count is
wrong. This is the single dominant in-scope failure mode: eval classes **C**
(wrong-variant) and **D** (small-IC over-count) are the *same* root cause,
covering ~10 of the ~19 in-scope IC failures in the 2026-08-09 baseline.

Two independent triggers were found:

1. **Bad part-number inference** — the inferer crowned a *package label*
   ("DFN-6") as the part number when the ordered part number was absent from the
   extracted text. **Fixed** (`part_number_hint._token_is_plausible` rejects
   package labels; commit 6f05821). MCP1700's hint is now "MCP1700".
2. **No suffix→pin-count grounding** — even with the right part number, the LLM
   picks whichever variant's pinout table is most prominent on the page. The
   ordered part number's *package suffix* (which uniquely identifies the
   variant and its pin count) is never used to reconcile. **This doc.**

## 2. Evidence (mappings confirmed from the corpus datasheets)

| Part (ordered) | Suffix | Package | True pins | Extractor picked |
|---|---|---|---|---|
| MCP1700T-3002E**/MB** | `/MB` | SOT-89 | **3** | DFN-6 (6) |
| MCP1700 `/CB` `/TO` `/MC` | — | SOT-23 / TO-92 / DFN | 3 / 3 / (3) | — |
| W25Q128JV**SIM** | `SI`(+`M`) | SOIC 208-mil | **8** | SOIC-16 (16) |
| AD636J**H**Z | `H` | H-10 (TO-100 can) | **10** | D-14 (14) |
| AD537J**H** | `H` | H-10 | **10** | 14 |
| LM2673**S**-5.0 | `S` | TO-263 | **7** | 14 |
| TPS23751**PWP** | `PWP` | HTSSOP | **16** | 20 (read sibling TPS23752) |

Package suffix codes are **vendor-specific facts** (published in each
datasheet's ordering section), not corpus tuning.

## 3. Mechanism

Extend the existing `part_number` → package infrastructure (today TI-only in
`part_number_hint._PACKAGE_DESIGNATORS` / `TI_DESIGNATOR_FAMILIES`) with
per-vendor suffix decoders, then **reconcile** the extracted pin count against
the count the ordered package implies.

```
resolved part number (already have it)
      │
      ▼
decode_package_suffix(pn)  →  (family, pin_count?)      # per-vendor tables
      │
      ▼
if datasheet corroborates that family+count            # guard: never invent
   and extracted count != grounded count:
        reconcile:
          - if extracted is a superset with the extras all NC → trim (exists)
          - if a matching-count variant table exists → select it
          - else prefer grounded count, mark provenance
```

Reuse what already exists:
- `apply_ordering_ground_truth` / `_reconcile_ordered_nc_padding` (NC trim down).
- `pin_data.packages[]` + `package_index` (multi-variant selection — already
  used when `--part-number` is supplied; ATmega TQFP works this way).
- `enforce_known_package_type`, family gates.

## 4. Per-vendor suffix tables (initial, extend as needed)

- **Microchip** (`/XX` after the part): `MB`→SOT-89(3), `CB`→SOT-23(3),
  `TO`→TO-92(3), `MC`/`MF`→DFN, `SN`/`SL`→SOIC, `P`→PDIP, `ST`→TSSOP,
  `MG`→QFN, `ML`→QFN. Pin count from the family + the numeric already in the
  part or the datasheet's package section.
- **Winbond flash** (trailing letters): `SI`→SOIC 208-mil(8), `SF`→SOIC 300-mil,
  `IM`/`IN`→WSON-8, `T`→packing. (W25Q family.)
- **Analog Devices** (`J/A/S` grade + package letter): `H`→TO-100 metal can(10),
  `D`→CERDIP/SOIC(14), `R`→SOIC, `E`→LFCSP. Grade letter (J/K/A/B/S) precedes it.
- **ST**: `Yx`→WLCSP, `T`→LQFP, `U`→VFQFPN, `P`→TSSOP, `D`→SO. Pin count from
  the numeric drawing code on the outline page.
- **TI**: already handled (`PWP`→HTSSOP, `DW`→SOIC, …). Extend the sibling-part
  disambiguation so TPS23751 ≠ TPS23752.

## 5. Risk & validation

- **Core-path change** — runs for all 84 currently-passing parts. Regression
  risk is the main hazard.
- **Conservative rule:** only override when the datasheet corroborates the
  grounded package+count (never invent a count from the suffix alone). If in
  doubt, leave the extracted value and watermark.
- **Validation:** TDD on each vendor decoder; then a **full gate re-run**
  (`tools/run_full_flow_eval.py`, now parallel) after each vendor is added —
  must not drop any passing part. Trust the gate, not single runs.

## 6. Phasing

1. Microchip decoder + reconcile (MCP1700). Gate re-run.
2. Analog Devices (AD636/AD537). Gate re-run.
3. Winbond (W25Q128), ST (STM32L031), TI sibling disambiguation (TPS2375x).
4. Fold the wrong-corpus-PDF fix: `52_PIC16F1512` is actually an MCP9701
   datasheet — replace it (data bug, not a parser fault).

Target: close C+D → in-scope IC accuracy from ~75% toward ~90%.
