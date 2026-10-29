# QC re-test note — 5 parts (re-check of 2026-10-23)

**Before re-testing:** PR #27 must be merged and the service redeployed, then
**all 5 parts regenerated**. On 23 Oct only AD9106 and 74LVC1G99GT were rebuilt;
PGA2311P, TL16C2550PFBR and ADV7180KST48Z were byte-identical to 5 Oct, so none of
the fixes since then could show on them.

Item IDs refer to `docs/part-recheck-2026-10-23-checklist.md`.

## What to check, per part

### PGA2311P (PDIP-16)
- Symbol: SnapEDA sides — ZCEN/CS/MUTE/SCLK/SDI/VINL/VINR left; VA+/VA−/VD+,
  VOUTL/VOUTR/SDO, AGNDL/AGNDR/DGND right (B1). Pin numbers on the pin line (B2),
  U1 above the body (B3), body ≈ 13 × 33 mm, pins centred (B4). Names not
  scrambled (A3), active-low marked (A5), rail types (A7).
- Footprint: pin 1 square on top and bottom copper (D6), bottom land B.Cu (E5),
  designator on F.SilkS (E4), pin-1 mark (F1).
- Still open: drill layer (FP-09) — waiting on the platform's layer names.

### AD9106BCPZ (LFCSP-32)
- Symbol: DAC outputs right, EPAD lower right with the grounds (B1); CLDO
  power_out, EPAD power_in (A7); CS/RESET/TRIGGER active-low (A5).
- Footprint: lands 0.30 × 0.80 mm at 2.05–2.85 mm, all 32 equal (D2, D6); EP
  3.75 mm, 0.175 mm gap (D5); mask 0.05 mm, separate openings (E3); EP paste 2 × 2
  windows, 75 % (D5); body 5.00 × 5.00 (D1); designator F.SilkS (E4); pin-1 (F1).
- Dimensions now read from the datasheet text (no vision read).

### TL16C2550PFBR (TQFP-48)
- Symbol: 48 individual names, no grouped labels (A4); I/O directions from the
  datasheet (B1); numbers, designator, body (B2–B4).
- Footprint: pad rows, body, courtyard (D1, D2, D4); mask web at 0.5 mm (E3);
  paste on F.Paste (E1); designator F.SilkS (E4); pin-1 (F1).

### 74LVC1G99GT (SOT833-1 / XSON8)
- Symbol: no phantom EPAD (A1b); Y output right (B1).
- Footprint: no phantom exposed pad (A1a); 0.5 mm pitch, rows not shorted (D3);
  body 1.00 × 1.95 (D1); designator F.SilkS (E4); pin-1 (F1).

### ADV7180KST48Z (LQFP-48)
- Symbol: pin 24 ELPF / 25 PVDD, GPO0–3 on the right pins (A2); AIN/P/GPO
  individual names (A4); P0–P7 and GPO outputs on the right (B1); compact body.
- Footprint: rows, body (D1, D2); paste/mask (E1, E2); designator (E4); pin-1 (F1).

## Not ours / waiting on the platform
A6 overbar drawing (frontend), C1/C2/C3 part record fields, E5 FP-09 drill layer,
G1 3D model — see `docs/platform-questions-2026-10-26.md`.
