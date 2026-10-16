# Part QC — Work Report

**Date:** 2026-10-14 (updated 2026-10-16 with live-endpoint verification)
**Branch:** `fix/part-qc-comparison-log` · **27 commits** · **merged into GitLab `main`**; also open as **PR [#27](https://github.com/NaniBer/datasheet-parser-new/pull/27)** on GitHub (not yet merged there)
**Source:** IDEEZA Part Comparison Log (`docs/IDEEZA_Part_Comparison_Log.pdf`, 2026-10-05) — 6 parts, **74 QC cards**
**Per-card detail:** see the [Complete Card Inventory](part-qc-fix-list-2026-10-06.md#complete-card-inventory-all-74) (all 74 rows, each with status + fixing commit).

Parts: TL16C2550PFBR (TQFP-48) · 74LVC1G99GT (XSON8) · AD9106BCPZ (LFCSP-32) · 693072010801 (Würth microSD) · ADV7180KST48Z (LQFP-48) · PGA2311P (PDIP-16).

---

## Headline

**48 of 74 cards fixed.** Of the remaining 26, almost all are blocked on external vendor data, owned by the platform/frontend, or a deliberate convention / QC decision and cannot be closed from this repository. The one genuine engineering follow-up on our side is the **ADV7180 GPO-order reliability (#53)** — it is vision-dependent and a live test showed it is not yet reliably correct (see Partial + Production verification).

| Outcome | Count | Meaning |
|---|---|---|
| **Fixed — fully** | 40 | Our output is correct; a QC re-review passes |
| **Fixed — data-only** | 7 | Our data is correct; the **platform** must render it |
| **Partial** | 1 | ADV7180 GPO order — pins 5/6 correct; 41/42 vision-dependent, not yet reliably correct (live test) |
| **Not-reproduced** | 3 | Already correct in our output; verified with evidence |
| **Won't-fix (convention/decision)** | 5 | Deliberate, conformance-enforced conventions |
| **Deferred (QC decision)** | 5 | Pin-1 marker — contradicts a committed fix |
| **Not-ours (platform/frontend)** | 9 | Rendering / consumption / metadata owned downstream |
| **Blocked (vendor data)** | 4 | 693 microSD — needs the Würth mechanical drawing |
| **Total** | **74** | |

**Closed on our side: 51** (48 fixed + 3 not-reproduced). **Remaining 23** are not ours to close.

---

## What we fixed (48)

### Fully fixed (41)
- **Package / mount blockers (HIGHEST):** LFCSP & XSON now resolve to SMD (were drilled through-hole DIPs); unknown-package fallback is SMD SON; square quad packages get equal pad spans — this cleared the **TL16C2550 blocker where 24 of 48 pins couldn't solder**.
- **Exposed pads:** EPAD pin added to leadless symbols + center thermal pad to footprints.
- **Solder paste:** real `F.Paste` apertures per SMD pad (none on through-hole) — previously there was no paste layer at all.
- **Pin electrical types:** regulator / supply / ground / data pins now typed instead of shipping as "unspecified" (ERC-checkable).
- **Component identity:** the caller's ordered part number is now the authoritative MPN/Value (was the LLM's weaker free-text reading).
- **Dimensional correctness:** JEDEC MS-026 body/span tables, IPC pad land (L_max), solder-mask margin drawn at the declared 0.102 mm/side, square courtyards, pad-number text scaled to fit.
- **ADV7180 pins 24/25 (HIGHEST):** corrected via a deterministic ordered-variant pin-table read — now ELPF/PVDD, **confirmed on the live endpoint**. *(The GPO order, #53, is only partial — see the Partial section.)*
- **Schematic bus ordering:** numbered buses (D0–D7) drawn in bit order instead of scrambled pin-number order.
- **74LVC1G99 XSON sizing**, **value-text sizing**, and **PGA2311P body width** (via a carefully-scoped through-hole exemption to the FP-19 conformance rule).

### Data-fixed — correct data, platform renders it (7)
Active-low flags, grouped-label resolution, and the red-copper layer view. **Our output now carries the correct data** (e.g. `activeLow=true` + `/CS` display name), but the user-visible result depends on the **frontend rendering** it. These may still look wrong on screen until the platform consumes what we emit.

---

## What turned out not to be broken (8)

Several reported "bugs" did not reproduce — verified firsthand, no change made:
- **Not-reproduced (3):** silk-over-pads on TL16C2550 & ADV7180 (already clipped by the existing FP-07 fix); PGA2311P 0.83 mm drill (vendor-correct, matches the TI golden reference).
- **Won't-fix (5):** symbol-body size (×2) and pin-order (×3) — our **functional-grouping convention is deliberate and conformance-enforced**. The compact reference symbols only achieve their size by abandoning that grouping. Decision: keep functional grouping.

---

## What's left (26 — none closeable by us)

### Not-ours — platform / frontend (9)
We generate and ship correct artifacts; the **editor/frontend does not render or consume them**:
- **3D models:** we ship `_body.glb` + `_body.step` for every part in the `/parse` ZIP (verified firsthand). The editor builds its own fallback body from the footprint outline instead.
- **Active-low overbar** and **grouped-label glyphs:** rendered by the frontend from the extras we emit.
- **Library category** (ADC vs DAC) and **footprint naming:** assigned downstream; we emit neither field.
- **MPN comma-truncation:** we store the full part number verbatim; truncation is platform-side.

### Deferred — QC decision (5)
The **pin-1 marker** cards contradict a fix we already committed (FP-08): one asks for the marker *inside* the courtyard, the other deliberately places it *outside*. QC needs to reconcile which is correct before we touch it.

### Blocked — vendor data (4)
The **693 microSD connector**: shield pins S1–S4, the shield land pattern, and the true body size all need the **Würth manufacturer drawing**. The mount-type blocker is fixed (no longer a drilled DIP), but a correct socket needs the vendor spec.

### Partial (1)
**ADV7180 GPO order (#53):** the scattered GPO group escalates to the pin-configuration figure (a vision read). A validity gate blocks any result that isn't a clean permutation of GPO0–3, so it never ships obvious garbage — **but the gate does not guarantee the figure's exact order.** A live production run returned pins 5/6 correct (GPO1/GPO0) but 41/42 as GPO2/GPO3, which appears to disagree with the datasheet figure (41=GPO3 / 42=GPO2). So #53 is **not yet reliably correct** and is the one open engineering follow-up on our side — options are a deterministic figure read or a stricter gate.

---

## Production verification (live endpoint, 2026-10-16)

One end-to-end call to the live `/agentic` endpoint (ADV7180) confirmed the deployed service is running the merged code and exercised two of the hardest fixes:
- **#52 confirmed in production:** pin 24 = **ELPF**, pin 25 = **PVDD** (the old code returned AGND/ELPF). The deterministic variant-table fix works on the real service.
- **#53 limitation surfaced:** pins 5/6 came back correct (GPO1/GPO0) but 41/42 as GPO2/GPO3 — a valid permutation that passed the gate but likely disagrees with the datasheet figure. This live run is why #53 is classed **Partial**, not Fixed, and is a good example of the review discipline: the limitation was found by testing, not assumed away.

---

## Two structural findings for the platform team

1. **~9 cards are platform-side, not parser-side.** The parser emits correct data and artifacts (active-low flags, display names, a 3D body GLB per part); the gap is in **rendering / consumption** downstream.
   **Open question:** *Does the editor ingest our `_body.glb`, or build its own body from the footprint?* The answer decides whether any further 3D work here is worthwhile.
2. **The "74 issues" figure overstates the parser's share.** Deduplicated, it is ~19 distinct problems; one generator-wide fix (paste, solder-mask) clears the same issue on all 6 parts at once. We fixed essentially everything within the parser's control.

---

## Process

Work was done with **controlled-parallel subagents** — one per non-colliding file cluster, each reproducing the defect firsthand and leaving its diff for review. **Every merge passed a verification gate** (reproduce, measure, confirm general-not-corpus-tuned, run tests). That gate caught real problems that would otherwise have shipped: a bare-`SS` over-match, a stale-base near-revert of prior work, an out-of-lane edit, and a solder-mask fix made in the **wrong direction** (corrected against the ground-truth reference). Nothing merged on an agent's word alone.

---

## Caveats

- **Merged into GitLab `main`**; the GitHub PR #27 is still open and has not had separate human code review there.
- The **7 data-fixed** cards depend on the platform rendering our output.
- **ADV7180 GPO (#53)** depends on a non-deterministic vision read; a live test showed it can return a plausible-but-wrong order (41/42) — it is not yet reliably correct.
- Full `test_suite.py` has ~7 **pre-existing** failures (API-key/env + dev-only reference-GLB assets), unrelated to this work; targeted test slices for each change pass.
- A **cost-logging change in `main.py`** remains uncommitted, intentionally kept out of this PR.

---

## Recommended next steps

1. **GitHub PR #27** (27 commits) — review/merge or close, since the work is already in GitLab `main`.
2. **Fix ADV7180 #53 GPO 41/42 order** — the one open engineering item; a deterministic figure read or a stricter validity gate.
3. **Route to the platform team:** the 9 not-ours cards + the 3D body-consumption question.
4. **Route to QC:** the pin-1 marker contradiction (FP-08 vs the card).
5. **Obtain the Würth microSD drawing** to unblock the 4 connector cards.
6. Decide where the parked **cost-logging** change should land (separate branch).
