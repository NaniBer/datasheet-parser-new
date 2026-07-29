# Pin-count accuracy: corpus-wide measurement + defect list (2026-07-29)

After the fail-open flip (#13) lifted GLB coverage to 116/127 (91%), we built a
complete, independent ground-truth answer key and measured **accuracy** for the
first time across the whole corpus.

## How ground truth was built
For every datasheet, the true pin count of the **ordered** part was derived
from its package (part-number suffix + the datasheet's own Ordering/package
table) and corroborated by printed "N-lead/N-pin" wording — deliberately **not**
by counting pinout-table rows (that is what the parser does and what we are
validating). Built by 5 parallel subagents, each citing evidence + a confidence
level; web lookups only for ambiguous/diagram-only parts.

- `EXPECTED_PINS` in `tools/run_full_flow_eval.py`: 27 pdfs/ fixtures + **147
  corpus parts** (144 high-confidence, 3 medium). Excluded: `142_1982`,
  `143_1982` (Adafruit tutorials, not datasheets).
- Independent cross-check: the subagents agreed with **all 30** earlier
  hand-verified values — **zero conflicts**.

## Result (against the current fail-open corpus run)
| | Count |
|---|------:|
| Correct pin count | **78** |
| Wrong pin count | 33 |
| No GLB (cannot grade) | 16 |

- **Accuracy among gradable GLBs: 78/111 = 70%**
- **Correct of all 127 scored parts: 78/127 = 61%**

---

## The 33 defects, by class

### Class A — Big diagram-only parts (needs the vision path, Option D)
Pinout is a package drawing, no clean text table; parser collapses.

| Part | True | Parser |
|------|:----:|:------:|
| 30_dsPIC33FJ128MC204 | 44 | 28 |
| 31_dsPIC33FJ128MC710A | 100 | 64 |
| 34_MKL17Z256CAL4R | 36 | 12 |
| 35_MKL43Z256VMP4 | 64 | 13 |
| 36_MKL46Z256VMC4 | 121 | 13 |
| 52_PIC16F1512-I-SS | 28 | 3 | (also: corpus PDF is the *wrong* document) |
| 86_PIC16F871-I-L | 44 | 28 |
| 141_UC200 (Quectel module) | 112 | 32 |
| 146_W25Q128JVSIM | 8 | 16 |

### Class B — Small-IC over-count (highest-volume, likely one root cause)
Parser reports MORE pins than exist; the `10→16` cluster is suspiciously uniform.

| Part | True | Parser |
|------|:----:|:------:|
| 42_INA228AIDGSR | 10 | 16 |
| 43_INA238AIDGSR | 10 | 16 |
| 123_L4984D | 10 | 16 |
| 124_L6564TDTR | 10 | 16 |
| 14_TPS23751PWP | 16 | 20 |
| 68_LM2673S-5.0 | 7 | 14 (2×) |
| 92_ACS773LCB | 5 | 8 |
| 71_AD537JH | 10 | 14 |
| 80_MCP101-460DI-TO | 3 | 8 |
| 102_MCP1700T-3002E | 3 | 6 |

### Class C — Diode/tab off-by-one (counting the mounting tab/pad as a pin)
| Part | True | Parser |
|------|:----:|:------:|
| 55_STTH8R06DIRG | 2 | 3 |
| 81_1N4148W-E3-08 | 2 | 3 |
| 105_PB86-BP | 4 | 3 |
| 125_ADXRS645HDYZ | 15 | 14 |
| 130_BD9778HFP-TR | 7 | 8 |
| 21_ATTINY13A-MMU | 10 | 8 |

### Class D — Wrong variant (ordered suffix not honored)
| Part | True | Parser |
|------|:----:|:------:|
| 148_STM32L031E4Yx | 25 (WLCSP) | 20 (TSSOP) |
| BQ25570RGRR | 20 | 16 (sibling RGRT reads 20 ✓) |

### Class E — Modules / near-miss (lower priority)
ESP32-WROOM (38 vs 40), ESP32-C3 (19 vs 20), MAX-M10S (18 vs 16),
CAM-M8Q (31 vs 28), TDA7850 (25 vs 28), MAXREFDES117 board (8 vs 4).

---

## Follow-ups (priority order)
1. **Class B** — one fix likely clears the `10→16` cluster; ~10 parts, low risk.
2. **Class D** — ordered-suffix → variant selection (existing ordering logic).
3. **Class C** — stop counting the package tab/pad as a signal pin.
4. **Class A** — vision path (Option D); also unblocks the no-GLB parts.
5. Fix corpus data bug: `52_PIC16F1512` PDF is the wrong document.
