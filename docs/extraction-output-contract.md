# Extraction output contract (Component Record v1)

The target the extractor must hit. Defining it *before* touching prompts is
deliberate: the current pipeline uses two divergent free-text `function`
word-lists, which is why pin semantics are inconsistent. These vocabularies are
the closed sets the extractor produces and downstream generation/ERC consume.

Grounding: IEEE-315 (symbol/pin semantics), the SnapMagic/IPC pin-type list, and
the IDEEZA spec rules **SYM-04** (grouping), **SYM-07** (types), **SYM-08**
(active-low), **SYM-10** (refdes), **SYM-11** (NC), **F-01** (never invent).

Source of truth in code: `src/models/component_record.py`
(`ELECTRICAL_TYPES`, `PIN_ROLES`, `DEVICE_CLASSES`/`REFDES_PREFIX`, `ROLE_SIDE`,
+ `normalize_*` / `validate_pin_semantics` helpers).

## Golden rule: never force a guess (F-01)

Every enum has an explicit **unknown** member. An unstated field resolves to the
unknown value, not a fabricated concrete one:

| field | "unknown" value |
|---|---|
| `electrical_type` | `unspecified` |
| `role` | `other` |
| `active_low` | `false` (only `true` when inversion is explicit) |
| `nc_instruction` | `null` |
| dimension | `None` → if the dim is *required*, the record is `blocked` (F-01) |
| `device_class` | `other` → refdes prefix `U` |

## 1. `electrical_type` — ERC set (SYM-07)

Closed set; drives electrical-rule checking.

| value | meaning | example |
|---|---|---|
| `input` | receives a signal | CLK, OE |
| `output` | drives a signal | QA, DOUT |
| `bidirectional` | drives and receives | GPIO, DQ |
| `tri_state` | output that can go high-Z | bus driver |
| `passive` | no direction (R/C/L terminals, EP) | pin 1 of a resistor |
| `power_in` | supply/ground consumed by the part | VCC, GND |
| `power_out` | supply the part sources | LDO VOUT, VREF out |
| `open_collector` | sinks only (incl. open-drain) | INT, /INT |
| `open_emitter` | sources only | rare logic outputs |
| `no_connect` | must be left unconnected | NC |
| `unspecified` | datasheet doesn't state direction | ambiguous IO |

Normalized aliases: `open_drain→open_collector`, `tristate/tri-state/3state→tri_state`,
`power→power_in`, `analog→passive`, `nc→no_connect`, `""/unknown/free→unspecified`.

## 2. `role` — functional grouping (SYM-04) → symbol side

`role` is for **layout**; `electrical_type` is for **ERC**. A pin carries both
(e.g. `VCC` = `power_in` + `supply`; `SRCLR` = `input` + `reset`).

| role | side | examples |
|---|---|---|
| `supply` | top | VCC, VDD, AVDD |
| `ground` | bottom | GND, VSS, AGND |
| `thermal` | bottom | EP / exposed pad |
| `input`,`clock`,`reset`,`enable`,`control`,`address`,`oscillator` | left | CLK, OE, SRCLR, A0, XTAL |
| `output`,`io`,`data`,`analog` | right | QA, DOUT, D0, AIN |
| `nc` | unplaced | NC / DNC / reserved |
| `other` | left | anything unclassified |

## 3. `active_low` (SYM-08)

- Representation: `active_low: bool` + the **base `name`** with inversion markers
  stripped (`nRESET`/`RESET#`/`/RESET`/`RESET_N` → name `RESET`, `active_low=true`).
- The symbol renderer applies **one** consistent notation later — we do not store
  five different notations in the name.
- **No guessing:** set `true` only when the datasheet clearly marks inversion
  (overbar, leading `n`, trailing `#`, `/`, `_N`); otherwise `false`.

## 4. NC / DNC / RESERVED / connection instructions (SYM-11)

The key distinction: **"leave unconnected" vs "must be wired to a net".**

| datasheet says | `nc` | `electrical_type` | `role` | `nc_instruction` |
|---|---|---|---|---|
| NC / "no connect" | `true` | `no_connect` | `nc` | `"no connect"` |
| DNC / "do not connect" | `true` | `no_connect` | `nc` | `"do not connect"` |
| RESERVED | `true` | `no_connect` | `nc` | `"reserved"` |
| "connect to GND" | `false` | `passive` | `ground` | `"connect to GND"` |
| "tie to VCC" | `false` | `power_in` | `supply` | `"tie to VCC"` |

`nc_instruction` always preserves the datasheet's verbatim wording.

## 5. Exposed / thermal pad

Represented as a normal `RecordPin` **only when the datasheet assigns it a pin
number** (existing behaviour). Defaults: `electrical_type = passive`,
`role = thermal` (groups to the bottom). If the datasheet requires it tied to a
net, capture that in `nc_instruction`/`description` (and it may take `role=ground`).

## 6. `device_class` → refdes prefix (SYM-10)

`identity.device_class` holds the semantic class; the prefix is derived:

`resistor→R · capacitor→C · inductor→L · ferrite_bead→FB · diode→D · led→D ·
transistor→Q · ic→U · connector→J · plug→P · switch→SW · crystal→Y ·
oscillator→Y · fuse→F · test_point→TP · other→U`

## 7. Dimensions & units (recap — see requirements-matrix)

Each mechanical field is a `Dimension{min,nom,max,unit,provenance}`. Missing a
*required* dimension → `blocked` (F-01), never defaulted silently. Units are mm;
the original printed value/unit is kept in `source_value`/`source_unit`.

## Resolved decisions

1. **open_drain is NOT distinct** from `open_collector` — same ERC behaviour;
   `open_drain` normalizes to `open_collector`. `open_emitter` is kept (opposite).
2. **`analog` is a role, not an electrical_type** — analog pins are electrically
   input/output/bidirectional/passive; `analog→passive` on the type axis.
3. **type and role are separate fields**, both carried per pin.
4. **`device_class` is a semantic class** with a prefix map (fixes the old
   `IC`/`LED` letter-stub).
5. Every enum has an explicit **unknown** member so the extractor never guesses.
