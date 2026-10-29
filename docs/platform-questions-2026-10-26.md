# Questions for the platform team — 2026-10-26

From the QC re-check of 23 Oct (5 parts). These items need a platform answer
before we can fix them on our side; everything else in the re-check is fixed in
our code (PR #27).

## 1. Footprint layer names (QC PGA2311P FP-09, also E5)

QC: the drill holes stay on screen with every layer hidden ("the layer panel has
no 'drill' switch"), and the holes look filled in 3D.

What we found:
- We tag each footprint node with `extras.layerId`. The hole (`HoleCylinderPin`)
  has `"drill"` — a name we chose; the platform's own reference footprints
  (NE555P, LM358P, CD4017BE, 74HC595N) carry no `layerId` on any node, so we have
  no example of the names the layer panel understands.
- The red rings QC saw are likely our copper barrel / bottom land
  (`CopperCylinderPin` `"*.Cu"`, `CopperCirclePin` `"B.Cu"`), not the hole (black).
- We build the hole 0.2 mm tall, exactly like the platform's NE555P reference;
  the ×18 height (3.6 mm) QC measured is applied by the viewer.

Questions:
1. Which `layerId` values does the footprint layer panel recognise? KiCad names
   (`F.Cu`, `B.Cu`, `F.Mask`, `B.Mask`, `F.Paste`, `F.SilkS`, `F.Fab`,
   `F.CrtYd`)? Are the multi-layer wildcards `*.Cu` / `*.Mask` supported?
2. What `layerId` should a plated hole get so it hides with the copper / drill
   control (and a non-plated hole)?
3. Does the viewer scale `HoleCylinderPin` ×18 in Z, and is there a supported way
   to mark it as an opening rather than a solid?

## 2. Part record fields (C1, C2, C3)

- C1: we now write `manufacturer`, `description`, `footprintName`,
  `supplierFootprint`, `manufacturerPartNumber` on the `Package` node of both
  GLBs and in the pins JSON. Does the platform read these, and under which keys?
  (Datasheet link and library category are platform-side.)
- C2: the MPN loses its orderable suffix (AD9106**BCPZ**, 74LVC1G99GT**,115**).
  We use the part number the caller passes as authoritative — which part number
  does the platform pass to `/part/build`?
- C3: library category and footprint name — we emit neither; who sets them?

## 3. 3D model (G1)

We ship `_body.glb` + `_body.step` in the `/parse` ZIP; the editor shows its own
grey placeholder box. Does the platform ingest our body model, or build its own
from the footprint?

## 4. Corrections (28 Oct)

Two items we raised earlier turned out to be ours, not the platform's:
- **3D orientation:** the platform's GLBs are Z-up (flat in X-Y), and our body
  GLB now follows that with no root transform. Our own conformance check had
  assumed Y-up; that is fixed.
- **Pin renames:** the repair step that swapped ADV7180 pins 24/25 is our code
  (`/agentic`); a renamed pin now carries its type, role and active-low mark.
  One question remains: when `/part/build` patches pin names into the GLB
  (`glb_pins_patched`), does it also take each pin's type/role from our
  `/agentic` response? If it copies names only, the types can still be stale.
