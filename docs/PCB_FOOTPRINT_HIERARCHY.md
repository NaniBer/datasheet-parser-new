# PCB Footprint Hierarchy Documentation

## Overview
This document describes the correct hierarchy and structure for PCB footprints generated from datasheets.

---

## 1. Body Hierarchy

The body should be organized into 3 PCB layers:

```
Package
└── body
    ├── fab_layer (fabrication layer)
    │   ├── body_outline
    │   └── first_pin_marker
    ├── silk_layer (silkscreen layer)
    │   ├── body_outline
    │   └── first_pin_marker
    └── crtyd_layer (courtyard layer)
        └── courtyard_outline
```

### Key Points:
- **fab_layer**: Manufacturing reference data - shows complete component outline (4 BodyLines: top, bottom, left, right)
- **silk_layer**: Silkscreen markings - avoids pin areas to prevent ink contamination (2 BodyLines: top, bottom only for DIP)
- **crtyd_layer**: Clearance boundary - defines component placement boundary (4 BodyLines: top, bottom, left, right)

### Why silk_layer has fewer BodyLines:
Silkscreen should have clearance from solder pads. For through-hole components like DIP:
- Left and right sides have pins → no silk lines
- Top and bottom have no pins → silk lines present

---

## 2. FirstPinMarker (Pin 1 Indicator)

### Purpose
The **FirstPinMarker** identifies pin 1 orientation on PCB footprints for correct component placement during assembly.

### Hierarchy
```
FirstPinMarker
├── silk_firstPinMarker (F.SilkS layer)
└── fab_firstPinMarker (F.Fab layer)
```

### 2.1 Silkscreen Pin 1 Marker (`silk_firstPinMarker`)

**Layer:** `F.SilkS` - Front silkscreen layer

**Purpose:** Visible marking on assembled board for inspection, debugging, and assembly guidance

**KiCad KLC Requirement:** "Polarity marking / Pin-1 designator must be drawn on the `F.SilkS` layer" (F5.1)

**Preferred Styles:**
- **SMD packages:** Filled chevron `▶` (can be rotated 45° for better fit)
- **THT/SMD packages:** Corner bracket, extra line, or `+` sign
- **SMD diodes:** `⊔` shape
- **Small packages (0201):** 0.25mm dot
- **Connectors:** Corner bracket or extra line

**Requirements:**
- Must be visible after board assembly
- Must be visible after connector mating (for connectors)
- Should be positioned inside the courtyard to prevent silkscreen overlap
- If device marking is NOT on pin 1 (e.g., digital LEDs), place digit `1` next to pin 1

### 2.2 Fabrication Pin 1 Marker (`fab_firstPinMarker`)

**Layer:** `F.Fab` - Front fabrication layer

**Purpose:** Manufacturing reference data showing pin 1 location for correct component orientation

**KiCad KLC Requirement:** "Footprint polarisation / location of pin-1 is drawn" (F5.2)

**Styles:**
- **IC packages:** Bevel (chamfered corner) next to pin 1
  - Size: 1mm or 25% of package size (whichever is smaller)
- **Connectors:** Small arrow indicator next to pin 1

**Requirements:**
- Simplified outline (not complex features)
- Based on nominal component body size
- Line width: 0.10mm to 0.15mm (recommended 0.10mm)

### 2.3 FirstPinMarker Accuracy

✅ **CORRECT** - The FirstPinMarker hierarchy with both silk and fab layers matches the official KiCad Library Conventions (KLC).

The dual-layer approach serves two purposes:
1. **Silkscreen (silk_firstPinMarker):** Visual aid for assembly, inspection, and debugging
2. **Fabrication (fab_firstPinMarker):** Manufacturing reference for correct component orientation during production

---

## 3. PackageValue (Component Label)

### Purpose
**PackageValue** is a 3D assembly that contains the component label/name information for identification in the 3D viewer.

### Hierarchy
```
PackageValue
├── Body (visible)
└── BoundingBox (invisible)
```

### 3.1 Body (Visible Text)

**Purpose:** Visible 3D text showing the component name or value

**Content:** Component name (e.g., "ATmega328P", "74HC595", "LM7805")

**Visibility:** Visible in 3D viewer

**Use Case:** Component identification and reference in 3D view

### 3.2 BoundingBox (Invisible Selection Area)

**Purpose:** Invisible box for selection/collision detection in the 3D viewer

**Visibility:** Invisible

**Function:**
- Makes the component easier to select in the 3D viewer
- User can click anywhere in the bounding box area to select the component
- Improves user experience when selecting thin text objects
- Common pattern in 3D applications to add larger selection areas

**Use Case:** Enhanced selection and interaction in 3D viewers

### Summary
PackageValue serves as a **component label assembly** containing:
1. **Body**: The visible 3D text label (component name)
2. **BoundingBox**: An invisible selection area for easier component selection in 3D viewers

This is a 3D viewer-specific feature and is not part of standard PCB manufacturing layers (fab, silk, courtyard).

---

## 4. DesignatorName (Reference Designator)

### Purpose
**DesignatorName** is the Reference Designator (RefDes) - the unique identifier for each component on a PCB.

### Hierarchy
```
DesignatorName
├── Body (visible)
└── BoundingBox (invisible)
```

### 4.1 Body (Visible Text)

**Purpose:** Visible 3D text showing the Reference Designator (RefDes)

**Content:** Component reference identifier
- **U1, U2, U3** - Integrated circuits
- **R1, R2, R3** - Resistors
- **C1, C2, C3** - Capacitors
- **J1, J2, J3** - Connectors
- **L1, L2, L3** - Inductors

**Visibility:** Visible in 3D viewer

**KiCad KLC Requirement (F5.2):**
- RefDes must be **centered on component body** (inside component outline)
- Orientation of RefDes should **match major component axis**
- Size of text should be **scaled to match component size**
- Recommended text size = **1.00mm**
- Allowable text size = **0.5mm to 1.0mm**
- Text thickness should be approximately **15% of text size**
- Recommended to scale such that **4 characters fit** without overlapping other features

**Use Case:** Component identification and referencing on the PCB

### 4.2 BoundingBox (Invisible Selection Area)

**Purpose:** Invisible box for selection/collision detection in the 3D viewer

**Visibility:** Invisible

**Function:**
- Makes the RefDes text easier to select in the 3D viewer
- User can click anywhere in the bounding box area to select the RefDes
- Improves user experience when selecting thin text objects
- Same pattern as PackageValue for consistent interaction

**Use Case:** Enhanced selection and interaction in 3D viewers

### Summary
DesignatorName serves as a **component identifier assembly** containing:
1. **Body**: The visible 3D text label (RefDes like "U1", "R5")
2. **BoundingBox**: An invisible selection area for easier RefDes selection in 3D viewers

### Difference from PackageValue:

| Layer | Content | Example |
|-------|---------|---------|
| **DesignatorName** | Reference Designator (RefDes) | "U1", "R5", "C10" |
| **PackageValue** | Component Name/Value | "ATmega328P", "10k", "10µF" |

DesignatorName is the unique component identifier on the PCB (like "U1" for the first IC), while PackageValue is the component's actual name or value (like "ATmega328P").

---

## 5. Complete PCB Footprint Hierarchy

```
Package (main assembly)
├── DesignatorName
│   ├── Body (visible - RefDes text like "U1", "R5")
│   └── BoundingBox (invisible - selection area)
├── PackageValue
│   ├── Body (visible - component name like "ATmega328P")
│   └── BoundingBox (invisible - selection area)
├── FirstPinMarker
│   ├── silk_firstPinMarker (F.SilkS layer)
│   └── fab_firstPinMarker (F.Fab layer)
├── Legs (all pins)
│   ├── 1
│   │   ├── CopperCirclePad      # Top pad (F.Cu)
│   │   ├── SolderMask           # Opening in solder mask
│   │   ├── HoleCylinderPin      # DIP only - drilled hole
│   │   ├── CopperCylinderPin    # DIP only - plated hole walls
│   │   ├── CopperCirclePin      # DIP only - bottom pad (B.Cu)
│   │   └── text                 # Pin number
│   ├── 2 (same structure)
│   └── ...
└── Body
    ├── fab_layer (F.Fab)
    │   ├── BodyLine
    │   ├── BodyLine
    │   ├── BodyLine
    │   └── BodyLine
    ├── silk_layer (F.SilkS)
    │   ├── BodyLine
    │   └── BodyLine
    └── crtyd_layer (courtyard)
        ├── BodyLine
        ├── BodyLine
        ├── BodyLine
        └── BodyLine
```

The reference `2d.glb` uses the same `BodyLine` node name for every outline segment; the segment identity comes from child order within each layer.

### Top-Level Package Children (5 items)

1. **DesignatorName** - Reference Designator
2. **PackageValue** - Component name/value
3. **FirstPinMarker** - Pin 1 indicator
4. **Legs** - All pins/pads
5. **Body** - PCB layers (fab, silk, courtyard)

---

## 7. Current Implementation Status

### Missing Components:
- None

### Current Code Has:
- CopperCirclePad ✅
- SolderMask ✅
- HoleCylinderPin ✅ (DIP only)
- CopperCylinderPin ✅ (DIP only)
- CopperCirclePin ✅
- text ✅

---

## 8. References

- KiCad PCB Editor Documentation: https://docs.kicad.org
- KiCad Library Conventions (KLC): https://klc.kicad.org
- Through-hole technology: Components mounted by inserting leads through holes and soldering to copper traces on both sides
- PCB layer standards: fab (fabrication), silk (silkscreen), crtyd (courtyard)
- Silkscreen clearance: Silkscreen should avoid solder pads to prevent contamination during soldering
- glTF/GLB format: 3D model format standard (https://www.khronos.org/gltf)
- DesignatorName: Reference Designator (RefDes) per KiCad KLC F5.2 - standard PCB footprint requirement
- PackageValue: 3D viewer-specific feature for component labeling and selection

---

## 9. Notes

- Silkscreen layers are the only layers that avoid pin areas
- Fab and courtyard layers show complete component outlines regardless of pin placement
- Through-hole components require pads on both top and bottom copper layers
- Surface mount components only require top-side copper pads
- Solder mask openings are typically larger than the underlying copper pads
- **Body** (capital B) is the container for PCB layers (fab, silk, crtyd)
- **BodyLines** are direct children of each layer (not nested), 4 for fab/crtyd, 2 for silk
- **Pin names** are just numbers ("1", "2", "3"), not "pin1", "pin2", "pin3"
- **DesignatorName is a standard KiCad requirement** for the fabrication layer (RefDes centered on component body)
- **DesignatorName and PackageValue are 3D viewer-specific features** for component labeling and improved selection experience
- **Top-level Package order**: DesignatorName, PackageValue, FirstPinMarker, Legs, Body
