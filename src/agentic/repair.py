"""Agentic repair of an extracted pinout (POST /agentic).

Why: on grouped pin tables the extraction LLM often returns the printed group
label as the name of every pin in the group (``D0-D4`` on pins 44-48, ``P7 to
P2, P1, P0``, ``DIG0:DIG7``, ``CSA, CSB``), picks the wrong package column when
the table has several, or carries the text extractor's subscript damage
(``V + D`` for ``VD+``) and header rows (``DIP/ LAP/ SOIC``) into pin names.
Measured on 9 datasheets (288 pins): raw gpt-6-luna 85%, raw claude-opus-4.8
94%, luna + this layer 99.3% for ~$0.003 extra per part.

Steps, cheapest first:

1. package-column check: if the pin page mentions several packages, ask the
   repair model (text) whether the extracted numbering matches the ordered
   package's column; take its full re-map only when it says the column is wrong.
2. numeric range labels (``D0-D4``, ``P7 to P2``, ``DIG0:DIG7``) whose member
   count matches the range length -> expanded deterministically, no LLM.
3. other grouped labels -> repair model (text) with the pin-table page text.
4. garbled subscript / header names -> repair model (vision) on the rendered page.
5. letter-range groups (``SEGA:SEGG``) that only the pinout drawing resolves ->
   escalation model (vision) on the rendered page.
6. verify: duplicates, leftover group-looking names, pin count.

Every LLM call goes through :mod:`src.chat_bot` so usage/cost accounting and
provider configuration are shared with the rest of the pipeline. Vision steps
need a vision-capable provider (OpenRouter models); on a text-only provider they
fail softly and the affected pins keep their extracted names.
"""

from __future__ import annotations

import base64
import contextvars
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:  # package-relative first, then legacy top-level imports
    from .. import chat_bot
except ImportError:  # pragma: no cover
    import src.chat_bot as chat_bot

DEFAULT_ESCALATION_MODEL = "anthropic/claude-opus-4.8"

# Names that legitimately repeat across pins (never flagged as duplicates).
SHARED_NAMES = {
    "GND", "VCC", "VDD", "VSS", "NC", "N.C.", "N.C", "AGND", "DGND", "PGND", "VS",
    "AVDD", "DVDD", "DVDDIO", "VCCIO", "VCC1", "VCC2", "BSTD", "EP", "EPAD", "VBAT", "VIN", "VOUT",
}
_PKG_WORDS = re.compile(
    r"\b(QSOP|TQFN|TSSOP|SOIC|PDIP|DIP|PLCC|LQFP|TQFP|QFN|LFCSP|LAP|SSOP|MSOP|SOP|PFB|RHB|VQFN|XSON|WSON|DFN|BGA)\b",
    re.I,
)
_PKG_TOKENS = re.compile(
    r"\b(QSOP|TQFN|TSSOP|SOIC|PDIP|DIP|PLCC|LQFP|TQFP|QFN|LFCSP|LAP|SSOP|MSOP|SOP|PFB|RHB|VQFN|XSON|WSON|DFN)[\s-]*\d*\b",
    re.I,
)
_RANGE = re.compile(r"^([A-Za-z_]+?)(\d+)\s*(?:-|–|:|\s+to\s+)\s*(?:[A-Za-z_]+?)?(\d+)$", re.I)
_LETTER_RANGE = re.compile(r"^([A-Za-z_]+)([A-Z])\s*[:\-–]\s*(?:[A-Za-z_]+)?([A-Z])\b")


# --------------------------------------------------------------------------- pin data
# Per-pin fields that describe the signal a NAME stands for, not the pin number.
_PIN_DATA_FIELDS = ("electrical_type", "type", "role", "function", "active_low", "nc", "nc_instruction")


def _pin_get(pin, key):
    return pin.get(key) if isinstance(pin, dict) else getattr(pin, key, None)


def _pin_has(pin, key) -> bool:
    return key in pin if isinstance(pin, dict) else hasattr(pin, key)


def _pin_set(pin, key, value) -> None:
    if isinstance(pin, dict):
        pin[key] = value
    else:
        setattr(pin, key, value)


def _series_prefix(name: str) -> str:
    """Leading letters of a pin name or group label (``AIN1 to AIN6`` -> AIN)."""
    m = re.match(r"\s*([A-Za-z_]+)", name or "")
    return m.group(1).upper() if m else ""


def carry_pin_data(pins: Dict[int, object], old_names: Dict[int, str],
                   new_names: Dict[int, str]) -> int:
    """Move each pin's type/role/active-low with its NAME when a repair re-maps names.

    A repair that re-numbers (wrong package column, variant pin table) renames
    pins but used to leave the extraction's type and role on the pin number, so
    they described the old name: ADV7180 pin 24 became ELPF yet kept AGND's
    ground type, pin 25 became PVDD yet kept ELPF's analog input (deployed run
    26 Oct). Rules, per renamed pin (dicts or Pin objects, fields that exist):

    - the new name was a unique name on another pin -> take that pin's data;
    - else, when the old name now lives on another pin (the data belonged to it)
      -> re-derive from the new name (PVDD -> power/supply) or clear, so later
      fill-only steps (the datasheet's I/O column) can set it;
    - else, when a group label became a name outside the group (``AIN1 to AIN6``
      -> AGND) -> re-derived or cleared the same way;
    - else (a cosmetic fix such as ``V + D`` -> ``VD+``, or a group label split
      into its members) the data still describes this pin and is kept.

    Names are not written here. Returns the number of pins whose data changed.
    """
    from ..models.pin_classifier import classify_pin_name

    counts: Dict[str, int] = {}
    for v in old_names.values():
        counts[v.upper()] = counts.get(v.upper(), 0) + 1
    unique_at = {v.upper(): n for n, v in old_names.items() if counts[v.upper()] == 1}
    new_upper = {n: (v or "").upper() for n, v in new_names.items()}
    snap = {n: {f: _pin_get(p, f) for f in _PIN_DATA_FIELDS if _pin_has(p, f)} for n, p in pins.items()}
    moved = 0
    for n, pin in pins.items():
        old, new = old_names.get(n, ""), new_names.get(n) or ""
        if not new or new.upper() == old.upper():
            continue
        src = unique_at.get(new.upper())
        if src is not None and src != n and src in snap:
            for f, v in snap[src].items():
                if isinstance(pin, dict) or _pin_has(pin, f):
                    _pin_set(pin, f, v)
            for f in set(_PIN_DATA_FIELDS) - set(snap[src]):   # the source never had it
                if isinstance(pin, dict):
                    pin.pop(f, None)
            moved += 1
        elif (is_group(old) and _series_prefix(new) != _series_prefix(old)) or (
                old and not is_group(old)
                and any(m != n and u == old.upper() for m, u in new_upper.items())):
            c_type, c_role, c_active = classify_pin_name(new)
            fresh = {"electrical_type": c_type, "type": c_type, "role": c_role,
                     "function": c_role, "active_low": bool(c_active),
                     "nc": c_role == "nc", "nc_instruction": None}
            for f, v in fresh.items():
                if _pin_has(pin, f):
                    _pin_set(pin, f, v)
            moved += 1
    return moved


# --------------------------------------------------------------------------- classification
def is_group(name: str) -> bool:
    """True when a pin *name* is really a group label covering several pins."""
    n = (name or "").strip()
    if not n:
        return False
    if _RANGE.match(n):
        return True
    if re.search(r"\bto\b", n, re.I):
        return True
    return "," in n or ":" in n


def is_suspicious(name: str) -> bool:
    """True when a name looks like text-extraction damage rather than a pin name."""
    n = (name or "").strip()
    if _PKG_WORDS.search(n) and "/" in n:  # "DIP/ LAP/ SOIC" header row
        return True
    if re.fullmatch(r"[A-Z]\s*[+\-–]\s*[A-Z]{1,3}", n):  # "V + D"  (VD+ with a split subscript)
        return True
    if re.fullmatch(r"[A-Z]\s+[A-Z]{1,2}\s+(IN|OUT)", n):  # "V R IN"
        return True
    if re.fullmatch(r"[A-Z]\s+[A-Z]{1,3}", n):  # "V CC"
        return True
    return False


def expand_numeric(label: str) -> Optional[List[str]]:
    """``D0-D4`` -> ``[D0, D1, D2, D3, D4]``; ``P7 to P2`` -> ``[P7 .. P2]``; ``DIG0:DIG7`` -> ``[...]``.

    Returns ``None`` when the label is not a numeric range.
    """
    m = _RANGE.match((label or "").strip())
    if not m:
        return None
    prefix, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    step = 1 if b >= a else -1
    return [f"{prefix}{i}" for i in range(a, b + step, step)]


def _is_letter_range(label: str) -> bool:
    return bool(_LETTER_RANGE.match((label or "").strip()))


def _squash(label: str) -> str:
    """``A 1 to A 6`` -> ``A1 to A6`` (spaces the text extractor left where a subscript was)."""
    return re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", (label or "").strip())


def _lost_subscript(label: str) -> bool:
    """A numeric range whose letters are separated from their digits by spaces
    (``A 1 to A 6``) usually lost a subscript (``AIN1``): only the drawing has the full name."""
    return label != _squash(label) and expand_numeric(_squash(label)) is not None


def range_numbers(label: str) -> Optional[List[int]]:
    """The pin-name numbers a numeric range covers: ``A 1 to A 6`` -> ``[1..6]``."""
    exp = expand_numeric(_squash(label))
    if not exp:
        return None
    return [int(re.search(r"(\d+)$", e).group(1)) for e in exp]


def _series_ok(fix: Dict[int, str], numbers: List[int]) -> bool:
    """Names must share one prefix and end in exactly the range's numbers (``AIN1..AIN6``)."""
    vals = [_tidy(str(v)) for v in fix.values()]
    if len(vals) != len(numbers) or not all(vals):
        return False
    parts = [re.fullmatch(r"([A-Za-z_/]+?)(\d+)", v) for v in vals]
    if not all(parts):
        return False
    return len({m.group(1).upper() for m in parts}) == 1 and sorted(int(m.group(2)) for m in parts) == sorted(numbers)


# --------------------------------------------------------------------------- datasheet helpers
def _page_texts(pdf: Path) -> List[Tuple[int, str]]:
    import pdfplumber

    with pdfplumber.open(str(pdf)) as doc:
        return [(i + 1, (pg.extract_text() or "")) for i, pg in enumerate(doc.pages)]


def _mentions(text: str, pin: int) -> bool:
    return re.search(rf"(?<![\w.]){pin}(?![\w.])", text) is not None


def _best_pin_page(texts, pins: List[int]) -> Optional[int]:
    best = (0, None)
    for pno, t in texts:
        if not any(k in t.upper() for k in ("PIN", "TERMINAL")):
            continue
        hits = sum(1 for p in pins if _mentions(t, p))
        if hits > best[0]:
            best = (hits, pno)
    return best[1]


_PIN_HEADINGS = ("PIN CONFIGURATION", "PIN ASSIGNMENT", "PINOUT", "PIN FUNCTION", "PIN DESCRIPTION",
                 "TERMINAL FUNCTION", "PIN DEFINITION", "PINNING", "TOP VIEW")


def _variant_tokens(package: Optional[str], pin_count: Optional[int]) -> List[str]:
    """Strings that mark the ordered variant's own table/drawing: ``48-LEAD``, ``LQFP-48``, ``48-PIN``..."""
    toks: List[str] = []
    if pin_count:
        toks += [f"{pin_count}-LEAD", f"{pin_count} LEAD", f"{pin_count}-PIN", f"{pin_count} PIN", f"{pin_count}-TERMINAL"]
    fam = None
    if package:
        m = re.search(r"[A-Za-z]{2,}", package)
        fam = m.group(0).upper() if m else None
        if fam and pin_count:
            toks += [f"{fam}-{pin_count}", f"{fam}{pin_count}", f"{fam}({pin_count})", f"{pin_count}-{fam}", f"{pin_count} {fam}"]
    return toks


def _score_pages(texts, pins: List[int], package: Optional[str] = None, pin_count: Optional[int] = None) -> List[int]:
    """Pages ranked as the ordered variant's pin table / drawing.

    Score = pin-table heading present (+3) + variant token present (+5, e.g. ``48-LEAD``)
    + share of the wanted pin numbers mentioned (0..2) - register-map penalty. A page with
    no heading, no variant token and few pin hits scores <= 0 and is never returned.
    """
    vt = _variant_tokens(package, pin_count)
    scored = []
    for pno, t in texts:
        u = t.upper()
        s = 3.0 if any(h in u for h in _PIN_HEADINGS) else 0.0
        if vt and any(v in u for v in vt):
            s += 5.0
        s += 2.0 * sum(1 for p in pins if _mentions(t, p)) / max(len(pins), 1)
        if "REGISTER" in u and "PIN" not in u:
            s -= 3.0
        if s > 0.5:
            scored.append((s, -pno))
    scored.sort(reverse=True)
    return [-p for _, p in scored]


def _page_context(texts, pins: List[int], maxc: int = 7000, package: Optional[str] = None,
                  pin_count: Optional[int] = None) -> List[Tuple[int, str]]:
    ranked = _score_pages(texts, pins, package, pin_count)
    if not ranked:
        return []
    pno = ranked[0]
    out = [(pno, texts[pno - 1][1][:maxc])]
    if pno < len(texts) and any(_mentions(texts[pno][1], p) for p in pins):  # continuation page
        out.append((pno + 1, texts[pno][1][:maxc]))
    elif len(ranked) > 1:
        out.append((ranked[1], texts[ranked[1] - 1][1][:maxc]))
    return out


def _pinout_pages(texts, pins: List[int]) -> List[int]:
    scored = []
    for pno, t in texts:
        u = t.upper()
        s = sum(k in u for k in ("PIN CONFIGURATION", "PIN ASSIGNMENT", "PINOUT", "PIN FUNCTION", "TOP VIEW", "PIN DESCRIPTION"))
        s += sum(1 for p in pins if _mentions(t, p)) / max(len(pins), 1)
        scored.append((s, pno))
    scored.sort(reverse=True)
    return [p for s, p in scored[:2] if s > 0]


def _beside(num_box, label_box) -> bool:
    """True when a label sits right next to a pin number: on the same row (side
    pins) or in the same column (top/bottom pins, rotated labels), separated by
    at most ~1.5x the label's font size."""
    nx0, ny0, nx1, ny1 = num_box
    lx0, ly0, lx1, ly1 = label_box
    limit = 1.5 * min(lx1 - lx0, ly1 - ly0)
    row_overlap = min(ny1, ly1) - max(ny0, ly0)
    if row_overlap >= 0.5 * min(ny1 - ny0, ly1 - ly0):
        gap = max(lx0 - nx1, nx0 - lx1)
        return -1 <= gap <= limit
    col_overlap = min(nx1, lx1) - max(nx0, lx0)
    if col_overlap >= 0.5 * min(nx1 - nx0, lx1 - lx0):
        gap = max(ly0 - ny1, ny0 - ly1)
        return -1 <= gap <= limit
    return False


_DRAWING_HEADINGS = ("TOP VIEW", "BOTTOM VIEW", "PIN CONFIGURATION", "PIN ASSIGNMENT", "PINOUT")


def read_series_from_drawing(pdf: Path, members: List[int], series: List[str]) -> Dict[int, str]:
    """Which series name sits on which pin, read from the pin drawing's words.

    For a numeric group on scattered pins (ADV7180 "GPO0 to GPO3" on pins 5, 6,
    41, 42, where pin 5 is GPO1) only the drawing gives the order. On a pin
    drawing each label is printed right beside its numbered pin. A page counts
    only if every member pin has exactly one series label beside it and the
    labels are all distinct; every qualifying page must agree. Anything less
    returns {} and the caller falls back to vision.

    Only pin-drawing pages (TOP VIEW / PIN CONFIGURATION ...) are read: the
    ADV7180 application circuit (p110) labels pins 5/6 the other way round,
    and the pin configuration is the authority for the pinout.
    """
    if len(series) != len(members):
        return {}
    import fitz  # PyMuPDF

    wanted = {name.upper(): name for name in series}
    numbers = {str(n): n for n in members}
    readings = []
    try:
        doc = fitz.open(str(pdf))
    except Exception:  # noqa: BLE001 - unreadable PDF: no drawing evidence
        return {}
    with doc:
        for page in doc:
            if not any(h in page.get_text().upper() for h in _DRAWING_HEADINGS):
                continue
            words = page.get_text("words")
            labels = [(w[:4], wanted[w[4].upper()]) for w in words if w[4].upper() in wanted]
            if len({name for _, name in labels}) < len(series):
                continue
            pins = [(w[:4], numbers[w[4]]) for w in words if w[4] in numbers]
            mapping: Dict[int, str] = {}
            for pin in members:
                beside = {name for box, n in pins if n == pin
                          for label_box, name in labels if _beside(box, label_box)}
                if len(beside) != 1:
                    break
                mapping[pin] = beside.pop()
            if len(mapping) == len(members) and len(set(mapping.values())) == len(members):
                readings.append(mapping)
    if not readings or any(r != readings[0] for r in readings[1:]):
        return {}
    return readings[0]


def _render_page_b64(pdf: Path, pno: int, zoom: float = 2.0, rotate: int = 0) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf))
    pix = doc[pno - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom).prerotate(rotate))
    return base64.b64encode(pix.tobytes("png")).decode()


# --------------------------------------------------------------------------- LLM helpers
_last_raw = {"text": ""}


def _parse_json(txt: str) -> dict:
    """First JSON object in the reply (tolerates code fences and prose around it)."""
    _last_raw["text"] = (txt or "")[:300].replace("\n", " ")
    txt = re.sub(r"```(?:json)?", "", txt or "")
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # trailing commas / single quotes from a chatty model
        fixed = re.sub(r",\s*}", "}", m.group(0)).replace("'", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return {}


def _rebuild_subscript_name(name: str) -> Optional[str]:
    """Rebuild a supply/signal name whose subscript the text extractor split apart.

    ``V R IN`` -> ``VINR`` (V, subscript IN, channel R), ``V L OUT`` -> ``VOUTL``,
    ``V + D`` -> ``VD+``, ``V – A`` -> ``VA-``, ``V CC`` -> ``VCC``. Returns ``None``
    when the name does not match one of these shapes.
    """
    n = (name or "").strip().replace("\u2013", "-").replace("\u2212", "-")
    m = re.fullmatch(r"V\s+([A-Z])\s+(IN|OUT)", n)
    if m:
        return f"V{m.group(2)}{m.group(1)}"
    m = re.fullmatch(r"V\s*([+\-])\s*([A-Z]{1,2})", n)
    if m:
        return f"V{m.group(2)}{m.group(1)}"
    m = re.fullmatch(r"V\s+([A-Z]{2,3})", n)
    if m:
        return f"V{m.group(1)}"
    return None


def _tidy(name: str) -> str:
    """Collapse OCR spacing inside a short all-caps token: ``SEG E`` -> ``SEGE``."""
    n = (name or "").strip()
    if re.fullmatch(r"[A-Z0-9]+(?: [A-Z0-9]{1,2})+", n) and len(n) <= 10:
        return n.replace(" ", "")
    return n


# False while repair_pins runs with use_llm=False: every text/vision ask answers
# {} without a call, which each step already treats as "no answer" (fail closed).
_LLM_ENABLED: contextvars.ContextVar = contextvars.ContextVar("repair_llm_enabled", default=True)


def _ask_text(model: str, prompt: str) -> dict:
    if not _LLM_ENABLED.get():
        return {}
    return _parse_json(chat_bot.get_completion_from_messages([{"role": "user", "content": prompt}], model=model))


def _ask_vision(model: str, prompt: str, pdf: Path, pages: List[int], rotations: Tuple[int, ...] = (0,)) -> dict:
    """Send the rendered page(s) with the prompt. ``rotations`` adds turned copies of
    each page (pinout drawings are often printed sideways)."""
    if not _LLM_ENABLED.get():
        return {}
    content = [{"type": "text", "text": prompt}]
    for p in pages:
        for r in rotations:
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + _render_page_b64(pdf, p, rotate=r)}})
    return _parse_json(chat_bot.get_completion_from_messages([{"role": "user", "content": content}], model=model))


# --------------------------------------------------------------------------- comma-list groups
def comma_tokens(label: str) -> List[str]:
    """``"CDA, CDB"`` -> ``["CDA", "CDB"]``; empty list when the label is not a comma list."""
    n = (label or "").strip()
    if "," not in n or re.search(r"\bto\b|:", n, re.I):
        return []
    toks = [t.strip() for t in n.split(",")]
    return toks if all(toks) and len(toks) >= 2 else []


def letter_range_tokens(label: str) -> List[str]:
    """``SEGA:SEGG, SEGDP`` -> ``[SEGA, SEGB, ..., SEGG, SEGDP]``; ``[]`` if not a letter range."""
    n = (label or "").strip()
    parts = [p.strip() for p in n.split(",")]
    m = _LETTER_RANGE.match(parts[0])
    if not m:
        return []
    prefix, a, b = m.group(1), m.group(2), m.group(3)
    if ord(b) < ord(a):
        return []
    toks = [f"{prefix}{chr(c)}" for c in range(ord(a), ord(b) + 1)]
    return toks + [p for p in parts[1:] if p]


def resolve_from_row(texts, tokens: List[str], members: List[int]) -> Dict[int, str]:
    """Map a comma-list group onto its pins from the datasheet row text, no LLM.

    TI-style rows print the names and then one number list per package column::

        CDA,CDB 40,16 42,21 – I
        TXRDYA,TXRDYB 43,6 1,12 – O

    The number list whose set equals ``members`` gives the order: ``CDA`` -> 40,
    ``CDB`` -> 16. Returns ``{}`` when no row matches unambiguously.
    """
    if not tokens or len(members) != len(tokens):
        return {}
    key = ",".join(tokens).upper()
    want = set(members)
    for _, t in texts:
        for ln in t.splitlines():
            compact = re.sub(r"\s*,\s*", ",", ln.upper())
            if key not in compact:
                continue
            tail = compact.split(key, 1)[1]
            for grp in re.findall(r"(?<![\w.])(\d+(?:[.,]\d+)+)(?![\w.])", tail):
                nums = [int(x) for x in re.split(r"[.,]", grp)]
                if len(nums) == len(tokens) and set(nums) == want:
                    return dict(zip(nums, tokens))
    return {}


def _scattered_dupes(mapping: Dict[int, str]) -> set:
    """Non-power signal names carried by more than one pin (a per-pin pinout never
    legitimately repeats one): the verification's duplicate rule, reused so the
    package-column remap can be rejected *before* it scatters such a name rather
    than only flagging the damage afterwards. Power/ground/no-connect names that
    do repeat across pins are excluded (see :data:`SHARED_NAMES`)."""
    vals = [str(v) for v in mapping.values()]
    return {v for v in vals if vals.count(v) > 1 and v.upper() not in SHARED_NAMES
            and not v.upper().startswith(("GND", "VCC", "VDD", "VS", "NC", "N.C"))}


def _fix_matches_tokens(fix: Dict[int, str], tokens: List[str], prefix: Optional[str] = None) -> bool:
    """A comma-list group may only be resolved into a permutation of its own tokens.

    For a letter range (``SEGA:SEGG``) the printed group may carry extra members the
    label omitted (``SEGDP``), so there the rule is: all names distinct, all starting
    with the range prefix.
    """
    got = [_tidy(str(v)).upper() for v in fix.values()]
    if prefix:
        return len(set(got)) == len(got) and all(g.startswith(prefix.upper()) and len(g) > len(prefix) for g in got)
    return sorted(got) == sorted(t.upper() for t in tokens)


# --------------------------------------------------------------------------- deterministic step
def expand_groups_deterministic(pins: Dict[int, str]) -> Tuple[Dict[int, str], List[str]]:
    """Expand numeric range labels shared by a run of pins. Pure, no LLM.

    ``{44: "D0-D4", 45: "D0-D4", ...}`` -> ``{44: "D0", 45: "D1", ...}`` when the
    number of pins carrying the label equals the range length.
    """
    out, log = dict(pins), []
    groups: Dict[str, List[int]] = {}
    for n, name in pins.items():
        if is_group(name):
            groups.setdefault(name, []).append(n)
    for label, members in groups.items():
        members.sort()
        exp = expand_numeric(label)
        if not exp or _lost_subscript(label):
            continue
        # Fail closed on scattered groups: a deterministic ascending zip only maps
        # pins to names correctly when the members are a CONTIGUOUS run (D0-D4 on
        # pins 44-48 read in order). When they are non-contiguous (GPO0 to GPO3 on
        # pins 5, 6, 41, 42) the pin-number order does NOT encode which pin holds
        # which name, so an ascending guess would emit a confidently-wrong order
        # (the GPO-swap defect). Leave the label in place: the group loop then
        # resolves it from the pin-configuration drawing (vision) or, failing that,
        # leaves it flagged rather than shipping a wrong permutation.
        if members != list(range(members[0], members[-1] + 1)):
            log.append(
                f"non-contiguous group {label!r} pins={members}: not expanded "
                "deterministically (pin order unreliable); left for drawing/vision"
            )
            continue
        if len(exp) == len(members):
            for n, nm in zip(members, exp):
                out[n] = nm
            log.append(f"expand {label!r} -> {dict(zip(members, exp))}")
            continue
        # Partial: some pins of the range already carry their expanded name
        # (44=D0, 45=D1, 48=D4 named, 46-47 still "D0-D4"). Fill the gaps in order.
        used = {v.upper() for n, v in out.items() if n not in members}
        remaining = [e for e in exp if e.upper() not in used]
        if len(remaining) == len(members):
            for n, nm in zip(members, remaining):
                out[n] = nm
            log.append(f"expand-partial {label!r} -> {dict(zip(members, remaining))}")
    return out, log


# A package "Version"/outline code as it appears in a pin-table column header
# ("SOT833-1"). Used to identify which number column belongs to the ordered
# variant on a multi-variant pin-description table.
_VER_TOKEN = re.compile(r"SOT\d{2,4}-\d+", re.IGNORECASE)


def read_variant_column(
    texts: List[Tuple[int, str]],
    names: Dict[int, str],
    version: str,
    pin_count: Optional[int] = None,
) -> Optional[Dict[int, str]]:
    """Read the ordered variant's pin-number column straight from a multi-variant
    pin-description table. Pure text, NO LLM. Returns ``{number: name}`` for the
    column headed by ``version``, or ``None`` when the table cannot be parsed
    unambiguously (fail closed -> the caller keeps its existing pins).

    Table layout handled (as PyMuPDF extracts it, one cell per line)::

        Symbol / Pin / Description
        SOT505-2 and / SOT833-1 / SOT902-1     <- K number-columns, grouped by "and"/","
        OE / 1 / 7 / output enable ...          <- name, K numbers, description
        A  / 2 / 6 / data input
        ...

    Only ACTS when: ``version`` heads one of >= 2 number columns, every extracted
    name is found as a row with exactly K integers, and the recovered name-set is
    identical to ``names`` (we only re-number, never rename). Any deviation -> None.
    """
    if not version or not names:
        return None
    want = version.upper().replace(" ", "")
    name_set = {str(v).strip().upper() for v in names.values() if str(v).strip()}
    if not name_set:
        return None

    lines: List[str] = []
    for _, t in texts:
        lines.extend(ln.strip() for ln in t.splitlines())
    n = len(lines)

    for start in range(n):
        if not _VER_TOKEN.search(lines[start]):
            continue
        # Build the column groups from the contiguous run of version-header lines,
        # merging a line into the next when it ends with "and"/"," (a shared column).
        groups: List[set] = []
        cur: set = set()
        j = start
        while j < n:
            toks = [m.group(0).upper().replace(" ", "") for m in _VER_TOKEN.finditer(lines[j])]
            if not toks:
                break
            cur.update(toks)
            if re.search(r"(?:\band\b|[,&])\s*$", lines[j], re.IGNORECASE):
                pass  # shared column continues onto the next line
            else:
                groups.append(cur)
                cur = set()
            j += 1
        if cur:
            groups.append(cur)

        col = next((i for i, g in enumerate(groups) if want in g), None)
        if col is None or len(groups) < 2:
            continue  # not the multi-variant header we need; keep scanning
        K = len(groups)

        # Walk the data rows: a known name line, then exactly K integer lines.
        result: Dict[int, str] = {}
        seen: set = set()
        p = j
        while p < n and len(seen) < len(name_set):
            up = lines[p].upper()
            if up in name_set and up not in seen:
                nums: List[int] = []
                q = p + 1
                while q < n and len(nums) < K and re.fullmatch(r"\d{1,3}", lines[q]):
                    nums.append(int(lines[q]))
                    q += 1
                if len(nums) == K:
                    result[nums[col]] = up
                    seen.add(up)
                    p = q
                    continue
            p += 1
            if p - j > 500:  # runaway guard: never scan unboundedly
                break

        # Validate: exact bijection over the whole extracted name-set.
        if seen == name_set and len(result) == len(name_set):
            if pin_count and len(result) != pin_count:
                return None
            return result
        # Header matched but the rows didn't. This can be a real multi-variant
        # table we couldn't parse OR a false positive (prose that happens to
        # name two package versions on adjacent lines, e.g. per-package derating
        # notes). Keep scanning rather than bailing: later headers, then the
        # single-column read below, are all bijection-gated and fail closed.
        continue

    # No multi-variant number-column header found. Newer datasheets (e.g. NXP
    # Rev.13, 2024) consolidate the per-variant columns into a SINGLE
    # "Symbol / Pin / Description" pin-description table when the ordered
    # numbering is variant-independent. Read that single column straight.
    return _read_single_pin_column(lines, name_set, pin_count)


# A pin-description table column header as PyMuPDF extracts it, one cell per line
# ("Symbol" / "Pin" / "Description"). Anchors the single-column table read below.
_SINGLE_COL_HEADER = ("SYMBOL", "PIN")


def _read_single_pin_column(
    lines: List[str],
    name_set: set,
    pin_count: Optional[int] = None,
) -> Optional[Dict[int, str]]:
    """Read a SINGLE-column ``Symbol / Pin / Description`` pin-description table.

    The row layout (one cell per line, as PyMuPDF extracts it) is::

        Symbol / Pin / Description
        OE / 1 / output enable input ...
        A  / 2 / data input
        ...

    i.e. each name is immediately followed by exactly ONE pin number. Only ACTS
    when: a ``Symbol``+``Pin`` header with NO package-version token is found (a
    version token means a multi-variant table, handled above), no row has a
    SECOND bare number after the first (that would be a hidden multi-column
    table), and the recovered name->number map is an exact bijection over the
    whole extracted name-set (we only re-number, never rename). Any deviation ->
    ``None`` (fail closed, caller keeps its pins).
    """
    n = len(lines)
    for h in range(n - 1):
        if lines[h].upper() != _SINGLE_COL_HEADER[0]:
            continue
        hdr = [lines[k].upper() for k in range(h, min(h + 4, n))]
        if _SINGLE_COL_HEADER[1] not in hdr:
            continue
        if any(_VER_TOKEN.search(x) for x in hdr):
            continue  # a per-variant header -> the multi-column path handles it

        result: Dict[int, str] = {}
        seen: set = set()
        p = h + 1
        while p < n and len(seen) < len(name_set):
            up = lines[p].upper()
            if up in name_set and up not in seen and p + 1 < n and re.fullmatch(r"\d{1,3}", lines[p + 1]):
                if p + 2 < n and re.fullmatch(r"\d{1,3}", lines[p + 2]):
                    return None  # a second number column -> ambiguous, fail closed
                result[int(lines[p + 1])] = up
                seen.add(up)
                p += 2
                continue
            p += 1

        if seen == name_set and len(result) == len(name_set):
            if pin_count and len(result) != pin_count:
                return None
            return result
    return None


# A line that is ONLY a pin-number list ("1, 13, 19, 43", "7 to 12, 20, 22",
# "24"): digits joined by commas / ranges, no letters. This is how the "Pin No."
# cell of a grouped pin-function table extracts (one cell per line in PyMuPDF).
_PIN_NO_LINE = re.compile(r"^\d{1,3}(?:\s*(?:,|to|-|–|and|&)\s*\d{1,3})*$", re.IGNORECASE)
# A variant pin-function table heading: "Table 12. 48-Lead LQFP Pin Function
# Descriptions", "... 20-Pin Pin Assignment". The lead/pin count is group 1.
_VARIANT_TABLE_HEADING = re.compile(
    r"^Table\s+[\w.]+.*?\b(\d{1,3})\s*[- ]?\s*(?:LEAD|LEADS|PIN|PINS|TERMINAL|TERMINALS)\b"
    r".*\b(?:FUNCTION|DESCRIPTION|DESCRIPTIONS|ASSIGNMENT|ASSIGNMENTS|CONFIGURATION)\b",
    re.IGNORECASE,
)
# Any table caption. Marks where one table's rows end (the next table -- often a
# register map whose rows would otherwise be misread as pin rows -- begins).
_ANY_TABLE_HEADING = re.compile(r"^Table\s+[\w.]+[.\s]", re.IGNORECASE)


def _parse_pin_no_cell(line: str, pin_count: int) -> Optional[List[int]]:
    """``"7 to 12, 20, 22"`` -> ``[7,8,9,10,11,12,20,22]`` (the printed order).

    Returns ``None`` when the line is not a pure pin-number list or any number
    falls outside ``1..pin_count`` (so a stray numeric line in a description,
    ``see Table 100``, can never be mistaken for a row)."""
    s = (line or "").strip()
    if not _PIN_NO_LINE.fullmatch(s):
        return None
    out: List[int] = []
    for part in re.split(r"\s*,\s*", s):
        m = re.fullmatch(r"(\d+)\s*(?:to|-|–)\s*(\d+)", part.strip(), re.IGNORECASE)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a or (b - a) >= pin_count:
                return None
            out.extend(range(a, b + 1))
        elif part.strip().isdigit():
            out.append(int(part.strip()))
        else:
            return None
    if not out or any(n < 1 or n > pin_count for n in out):
        return None
    return out


def _is_mnemonic_cell(line: str) -> bool:
    """True when a line looks like a pin-name / group cell ("ELPF", "VS/FIELD",
    "GPO0 to GPO3", "N.C.") rather than a prose description ("Digital Ground.").

    Pin names are all-caps tokens; the only lowercase allowed is the word ``to``
    inside a range label, so any other lowercase run marks the line as prose."""
    s = (line or "").strip()
    if not s or len(s) > 40 or not re.search(r"[A-Za-z]", s):
        return False
    return re.fullmatch(r"[A-Z0-9 ,/.:_+\-–()]+", re.sub(r"\bto\b", " ", s)) is not None


def read_variant_pin_table(
    full_text: str,
    pin_count: Optional[int],
    package: Optional[str] = None,
) -> Optional[Dict[int, str]]:
    """Read the ordered variant's grouped pin-function table straight from the
    datasheet text. Pure text, NO LLM. Returns ``{number: name}`` or ``None``.

    Handles the Analog Devices / TI style multi-variant layout where each
    package has its OWN "Pin No. | Mnemonic | Type | Description" table and the
    pin numbers are GROUPED per mnemonic (one cell per line in PyMuPDF)::

        Table 12. 48-Lead LQFP Pin Function Descriptions
        Pin No. / Mnemonic / Type / Description
        23, 28, 32 / AGND / G / Analog Ground.
        24 / ELPF / I / The recommended external loop filter ...
        25 / PVDD / P / PLL Supply Voltage ...
        5, 6, 41, 42 / GPO0 to GPO3 / O / General-Purpose Outputs ...

    Picking the WRONG variant table is the usual cause of a mis-numbered pinout
    (the 40/64-lead tables put different names on pin 24), so the ordered
    variant is selected by its own ``<pin_count>-Lead`` heading. A single-name
    row maps that name onto every pin in its cell. A range/group mnemonic
    (``GPO0 to GPO3``) whose member count matches the pin cell is left AS THE
    GROUP LABEL on each pin: the pin-number order does not reveal which pin holds
    which member, so the group loop resolves the order from the drawing (vision)
    or leaves it flagged -- never a guessed order.

    Fails closed (returns ``None``) unless: the document is multi-variant (>= 2
    distinct variant function-tables, so there is a selection to get right), the
    ordered variant's table(s) are found, and the parsed rows cover EXACTLY pins
    ``1..pin_count`` with no pin assigned twice. Any ambiguity keeps the caller's
    existing pins.
    """
    if not pin_count or pin_count < 2 or not full_text:
        return None
    lines = [ln.strip() for ln in full_text.splitlines()]

    # Multi-variant gate: how many DISTINCT variant pin-function tables exist?
    variants = {int(m.group(1)) for ln in lines if (m := _VARIANT_TABLE_HEADING.match(ln))}
    if len(variants) < 2 or pin_count not in variants:
        return None

    fam = None
    if package:
        fm = re.search(r"[A-Za-z]{2,}", package)
        fam = fm.group(0).upper() if fm else None

    result: Dict[int, str] = {}
    conflict = False
    n = len(lines)
    i = 0
    while i < n:
        hm = _VARIANT_TABLE_HEADING.match(lines[i])
        # Only the ordered variant's own table(s) (its pin count; and, when the
        # package family is known, that family too -- some sheets reuse a lead
        # count across two families).
        if not (hm and int(hm.group(1)) == pin_count and (not fam or fam in lines[i].upper())):
            i += 1
            continue
        j = i + 1
        # Stop at the NEXT table caption of any kind: a variant's function table
        # is split across pages as "...(Continued)" (re-entered by the outer
        # loop), and the register-map tables that follow must not be scanned as
        # pin rows.
        while j < n and not _ANY_TABLE_HEADING.match(lines[j]):
            pins = _parse_pin_no_cell(lines[j], pin_count)
            if pins:
                k = j + 1
                while k < n and not lines[k]:
                    k += 1
                if k < n and _is_mnemonic_cell(lines[k]):
                    mnem = lines[k]
                    for p in pins:
                        if p in result and result[p] != mnem:
                            conflict = True
                        else:
                            result.setdefault(p, mnem)
                    j = k + 1
                    continue
            j += 1
        i = j

    # Full, unambiguous coverage of the whole variant, or nothing.
    if conflict or set(result) != set(range(1, pin_count + 1)):
        return None
    if len({v.upper() for v in result.values()}) < 2:  # degenerate
        return None
    return result


# --------------------------------------------------------------------------- entry point
def repair_pins(
    pins: List[dict],
    pdf_path: Path,
    part_number: Optional[str],
    repair_model: Optional[str] = None,
    escalation_model: Optional[str] = None,
    package: Optional[str] = None,
    pin_count: Optional[int] = None,
    use_llm: bool = True,
) -> dict:
    """Repair an extracted pin list; see :func:`_repair_pins`.

    ``use_llm=False`` runs only the deterministic steps (ordered variant's pin
    table, group expansion, pin-drawing read): no model calls and no reset of
    the caller's LLM usage counter. The GLB pipeline uses this mode.
    """
    token = _LLM_ENABLED.set(use_llm)
    try:
        return _repair_pins(pins, pdf_path, part_number, repair_model,
                            escalation_model, package, pin_count, use_llm)
    finally:
        _LLM_ENABLED.reset(token)


def _repair_pins(
    pins: List[dict],
    pdf_path: Path,
    part_number: Optional[str],
    repair_model: Optional[str],
    escalation_model: Optional[str],
    package: Optional[str],
    pin_count: Optional[int],
    use_llm: bool,
) -> dict:
    """Repair an extracted pin list in place of the caller's judgement.

    Args:
        pins: the ``pins`` list as produced by ``--emit-pins`` / ``POST /pins``
            (dicts with ``number``, ``name``, ``type``, ``nc``).
        pdf_path: the datasheet the pins came from.
        part_number: ordered part number (drives the package-column check).
        repair_model: cheap text+vision model for steps 1, 3, 4 (default: LLM_MODEL).
        escalation_model: vision model for step 5 (default: AGENTIC_ESCALATION_MODEL
            env, else ``anthropic/claude-opus-4.8``).
        package: ordered package as known to the caller or the extraction
            (``LQFP``, ``QSOP-24``); steers page choice on multi-variant datasheets.
        pin_count: ordered pin count; defaults to the number of extracted pins.

    Returns a dict with ``pins`` (same shape, names repaired), ``changed`` (count),
    ``repairs`` (human-readable log), ``flags`` (verification findings) and
    ``usage`` (LLM usage of the repair calls only).
    """
    repair_model = repair_model or chat_bot.default_model()
    escalation_model = escalation_model or os.getenv("AGENTIC_ESCALATION_MODEL", DEFAULT_ESCALATION_MODEL)
    pdf_path = Path(pdf_path)
    part_number = part_number or ""

    by_num: Dict[int, dict] = {}
    for p in pins:
        try:
            by_num[int(p.get("number"))] = p
        except (TypeError, ValueError):
            continue
    names: Dict[int, str] = {}
    for n, p in by_num.items():
        raw = str(p.get("name") or "")
        rebuilt = _rebuild_subscript_name(raw)
        names[n] = rebuilt or _tidy(raw)
    original = {n: str(p.get("name") or "") for n, p in by_num.items()}
    log: List[str] = [f"rebuild {original[n]!r} -> {names[n]!r}" for n in names if names[n] != _tidy(original[n])]
    if use_llm:
        chat_bot.reset_usage()
    pin_count = pin_count or len(names) or None
    variant = f"{pin_count}-pin {package}" if package and pin_count else (package or (f"{pin_count}-pin" if pin_count else ""))
    variant_note = (f" The ordered part is {part_number} in the {variant} package: use ONLY that variant's pin "
                    f"table / drawing and ignore other package variants on the page(s).") if variant else ""

    try:
        texts = _page_texts(pdf_path) if pdf_path.is_file() else []
    except Exception as exc:  # noqa: BLE001 - unreadable PDF: text/vision steps are skipped
        texts = []
        log.append(f"page text unavailable ({type(exc).__name__}); only deterministic repairs applied")

    # 1) package-column check ---------------------------------------------------------------
    # 1a) Deterministic first: if the datasheet's ordering table grounds the exact
    # ordered variant (its Version/outline code, e.g. SOT833-1) and the multi-variant
    # pin-description table can be read straight, take that variant's number column
    # verbatim -- no LLM, no guessing. Fails closed to the LLM check below when the
    # ordering table or the pin table can't be parsed unambiguously.
    column_resolved = False
    if part_number and pdf_path.is_file():
        try:
            from ..pdf_extractor.ordering_table import find_ordering_match, full_pdf_text
            fitz_text = full_pdf_text(str(pdf_path))
            om = find_ordering_match(fitz_text, part_number)
            if om and om.version:
                det = read_variant_column([(0, fitz_text)], names, om.version, om.pin_count)
                if det:
                    names = det
                    package = om.package or package
                    column_resolved = True
                    log.append(
                        f"column (deterministic) [{om.version}]: read {len(det)} pins "
                        f"from the pin table; LLM column-check skipped"
                    )
            # 1b) Deterministic grouped-table read: on a MULTI-VARIANT datasheet
            # where each package has its own "Pin No. | Mnemonic" function table
            # (Analog Devices / TI), select the ordered variant's table by its
            # own lead-count heading and take its names verbatim -- the usual
            # root cause of a mis-numbered pinout is reading the wrong variant's
            # table (the 40/64-lead tables name pin 24 differently). Fails closed
            # unless the ordered variant's rows cover pins 1..N exactly. Range/
            # group mnemonics (``GPO0 to GPO3``) are left as the group LABEL so
            # the group loop resolves their per-pin order from the drawing.
            if not column_resolved:
                det = read_variant_pin_table(
                    fitz_text, pin_count or len(names) or None, package
                )
                if det:
                    names = det
                    column_resolved = True
                    log.append(
                        f"variant pin table (deterministic): read {len(det)} pins "
                        f"from the {pin_count or len(names)}-pin variant's function "
                        f"table; LLM column-check skipped"
                    )
        except Exception as exc:  # noqa: BLE001 - never lose the extraction to a repair bug
            log.append(f"deterministic column read skipped: {type(exc).__name__}: {exc}")

    ctx = _page_context(texts, list(names), package=package, pin_count=pin_count) if texts else []
    pkg_cols = {m.group(1).upper() for _, t in ctx for m in _PKG_TOKENS.finditer(t)}
    if not column_resolved and len(pkg_cols) >= 2 and ctx:
        order_txt = "\n".join(t[:3000] for _, t in texts if "ORDERING" in t.upper())[:4000]
        prompt = (
            f"Part number ordered: {part_number or 'unknown'}. Packages mentioned on the pin page: {sorted(pkg_cols)}.\n"
            f"Ordering information text:\n{order_txt}\n\nPin table page text:\n"
            + "\n".join(t for _, t in ctx)
            + "\n\nExtracted pin map (number -> name), possibly taken from the WRONG package column:\n"
            + json.dumps({str(k): v for k, v in sorted(names.items())})
            + "\n\nStep 1: decide which package the ordered part number is (ordering table / suffix rules).\n"
            "Step 2: if the pin table has one column of pin numbers per package, check whether the extracted map uses that package's column.\n"
            'Respond JSON only: {"package": "<package>", "column_ok": true|false, "pins": {"<number>": "<name>", ...}} '
            "where pins is the FULL corrected map for the ordered package (copy grouped labels as printed when one row covers several pins; never invent names)."
        )
        try:
            ans = _ask_text(repair_model, prompt)
        except Exception as exc:  # noqa: BLE001 - soft-fail, keep extraction
            ans = {}
            log.append(f"column-check failed: {type(exc).__name__}: {exc}")
        if ans.get("package"):
            package = str(ans["package"])          # the ordering table beats the extraction's guess
            variant = f"{pin_count}-pin {package}" if pin_count else package
            variant_note = (f" The ordered part is {part_number} in the {variant} package: use ONLY that variant's pin "
                            f"table / drawing and ignore other package variants on the page(s).")
        remap = ({int(k): _tidy(str(v)) for k, v in ans["pins"].items() if str(k).strip().isdigit()}
                 if isinstance(ans.get("pins"), dict) else {})
        if ans.get("column_ok") is False and len(remap) >= 0.8 * len(names):
            # A real column fix re-numbers: many pins move, but the set of names stays the same.
            old_set = {v.upper() for v in names.values()}
            moved = sum(1 for n, v in remap.items() if names.get(n, "").upper() != v.upper())
            kept = sum(1 for v in remap.values() if v.upper() in old_set) / max(len(remap), 1)
            # A real column fix only RE-NUMBERS: it must not duplicate a non-power
            # signal that the extraction had on a single pin. Rejecting a remap that
            # introduces a new scattered name keeps a wrong-column read (which can
            # confuse a shared compound pin like VS/FIELD into a scattered "FIELD")
            # from shipping -- fail closed to the extraction instead.
            new_dupes = _scattered_dupes(remap) - _scattered_dupes(names)
            if moved >= 0.3 * len(names) and kept >= 0.7 and not new_dupes:
                names = remap
                log.append(f"column-check: package={ans.get('package')} column_ok=False -> re-mapped {len(names)} pins ({moved} moved)")
            elif new_dupes and moved >= 0.3 * len(names) and kept >= 0.7:
                log.append(f"column-check: package={ans.get('package')} column_ok=False but re-map rejected "
                           f"(would scatter {sorted(new_dupes)} across pins); keeping extraction")
            else:
                log.append(f"column-check: package={ans.get('package')} column_ok=False but re-map rejected "
                           f"(moved={moved}, names kept={kept:.0%}); keeping extraction")
        else:
            log.append(f"column-check: package={ans.get('package')} column_ok={ans.get('column_ok')}")

    # 2) deterministic numeric expansion ------------------------------------------------------
    names, exp_log = expand_groups_deterministic(names)
    log += exp_log

    # 3-5) remaining groups / suspicious names -------------------------------------------------
    # Garbled single names (subscript damage, header rows): one vision read of the pin
    # table for all of them together, by the escalation model, so the spellings are
    # consistent (VINR vs VRIN) and the page is only rendered once.
    garbled_fix: Dict[int, str] = {}
    garbled = sorted(n for n, v in names.items() if is_suspicious(v) and not is_group(v))
    if garbled and texts:
        gpages = _score_pages(texts, garbled, package, pin_count)[:2]
        if gpages:
            try:
                shown = {n: names[n] for n in garbled}
                ans_g = _ask_vision(
                    escalation_model,
                    f"Part {part_number}.{variant_note} The text extractor produced garbled pin names for pins {garbled} "
                    f"({shown}): subscripts or table headers got scrambled. Read the pin-function table / pin diagram on the "
                    f"attached page image(s) and give the correct printed name for each of these pin numbers: {garbled}. "
                    "Write subscripts inline in reading order (V IN R -> VINR, V D+ -> VD+). "
                    'Respond with JSON only: {"<pin number>": "<name>"}; "?" if unreadable.',
                    pdf_path, gpages[:1],
                )
                garbled_fix = {n: _tidy(str(ans_g.get(str(n), ""))) for n in garbled}
                log.append(f"vision({escalation_model}) garbled pins={garbled} pages={gpages[:1]} -> {ans_g}")
            except Exception as exc:  # noqa: BLE001
                log.append(f"garbled-name read failed: {type(exc).__name__}: {exc}")

    groups: Dict[str, List[int]] = {}
    for n, name in names.items():
        if is_group(name) or is_suspicious(name):
            groups.setdefault(name, []).append(n)

    def _taken(exclude: List[int]) -> set:
        """Names already used by pins outside the group (shared power/ground names excluded)."""
        return {v.upper() for n, v in names.items() if n not in exclude
                and v.upper() not in SHARED_NAMES and not is_group(v) and not is_suspicious(v)}

    for label, members in groups.items():
        members = sorted(n for n in members if names.get(n) == label)
        if not members:
            continue
        fix: dict = {}
        letter_range = _is_letter_range(label)
        tokens = comma_tokens(label) or (letter_range_tokens(label) if letter_range else [])
        prefix = _LETTER_RANGE.match(label.strip()).group(1) if letter_range else None
        if tokens and not letter_range and len(tokens) != len(members):
            tokens = []  # a partial group (some members already named): no permutation constraint
        numbers = range_numbers(label) if not tokens else None   # numbered series constraint
        pages_txt = _page_context(texts, members, package=package, pin_count=pin_count) if texts else []
        try:
            if letter_range:
                log.append(f"letter-range {label!r} pins={members}: needs the drawing, escalating")
            elif _lost_subscript(label):
                log.append(f"lost-subscript range {label!r} pins={members}: full names only in the drawing, escalating")
            elif numbers and members != list(range(members[0], members[-1] + 1)):
                # Pure numeric range (GPO0 to GPO3) on NON-CONTIGUOUS pins. The
                # page text lists the pins and the range together but does NOT
                # encode which pin holds which member -- only the pin-configuration
                # DRAWING does. Skip the text step: it would read the pins in
                # printed order and emit a confident ascending map (the GPO-swap
                # defect). Fall through to the drawing/vision escalation, which is
                # gated to a valid series permutation below (fail closed otherwise).
                # First read the drawing's word positions (free, exact); vision
                # only when that read is incomplete or ambiguous.
                drawn = read_series_from_drawing(pdf_path, members, expand_numeric(label) or [])
                if drawn:
                    fix = {str(n): v for n, v in drawn.items()}
                    log.append(f"drawing (deterministic) {label!r} pins={members} -> {drawn}")
                else:
                    log.append(f"non-contiguous numeric range {label!r} pins={members}: "
                               "per-pin order only in the drawing, escalating to vision")
            elif tokens and (row := resolve_from_row(texts, tokens, members)):
                fix = {str(n): v for n, v in row.items()}
                log.append(f"row-order {label!r} -> {row}")
            elif is_suspicious(label) and not is_group(label):
                fix = {str(n): garbled_fix.get(n, "") for n in members}
                log.append(f"garbled {label!r} pins={members} -> {fix}")
            elif pages_txt:
                fix = _ask_text(
                    repair_model,
                    f"Datasheet pin-function table text for part {part_number} (page text, may be messy):\n"
                    + "\n".join(f"--- page {pg} ---\n{t}" for pg, t in pages_txt)
                    + f"\n\nThe extractor assigned the grouped label \"{label}\" to pins {members}. A pin has exactly one name.\n"
                    "Using the row text (pin numbers are listed in the same order as the names in the row; when several package "
                    f"columns exist, use the column whose numbers match {members}), give one name per pin.\n"
                    'Respond with JSON only: {"<pin number>": "<name>", ...} for exactly those pins. Use "?" when the text cannot tell.',
                )
                log.append(f"text({repair_model}) {label!r} pins={members} -> {fix}")
        except Exception as exc:  # noqa: BLE001
            log.append(f"repair of {label!r} failed: {type(exc).__name__}: {exc}")

        # Constraint checks: a comma-list group resolves only into its own tokens, and no
        # repair may reuse a name that another pin already has. Anything else escalates.
        if fix and tokens and not _fix_matches_tokens({n: fix.get(str(n), "") for n in members}, tokens, prefix):
            log.append(f"rejected {label!r} -> {fix}: not a permutation of {tokens}")
            fix = {}
        if fix and numbers and len(members) == len(numbers) and not _series_ok({n: fix.get(str(n), "") for n in members}, numbers):
            log.append(f"rejected {label!r} -> {fix}: not a numbered series over {numbers}")
            fix = {}
        taken = _taken(members)
        for n in list(members):
            v = _tidy(str(fix.get(str(n), "")))
            if v and v.upper() in taken:
                log.append(f"rejected pin {n} -> {v!r}: name already used elsewhere")
                fix.pop(str(n), None)

        unresolved = []
        for n in members:
            v = _tidy(str(fix.get(str(n), "")))
            if v and v != "?" and not is_group(v):
                names[n] = v
            else:
                unresolved.append(n)
        if unresolved and texts:
            # Prefer the pages whose text carries these pin numbers (the ordered
            # variant's own pin table / drawing), then the generic pinout pages.
            pages = [pg for pg, _ in pages_txt][:2] or _score_pages(texts, unresolved, package, pin_count)[:2]
            if pages:
                try:
                    if prefix:
                        hint = (f" All of these names start with \"{prefix}\" (a lettered series like {tokens[:3]}...); "
                                f"the drawing may also show members the label omitted (e.g. {prefix}DP). One distinct name per pin.")
                    elif tokens:
                        hint = f" The names must be exactly these, one each: {tokens}."
                    elif numbers:
                        hint = (f" The names form a numbered series ending in {numbers} (the printed prefix may include a "
                                f"subscript the text lost, e.g. AIN1 rather than A1); give the full printed name.")
                    else:
                        hint = ""
                    prompt2 = (
                        f"Part {part_number}.{variant_note} From the pin configuration drawing / table on these datasheet page(s), give the pin NAME "
                        f"for each of these pin numbers: {unresolved}. They belong to the group \"{label}\"; the drawing shows which "
                        f'name sits on which number.{hint} Respond with JSON only: {{"<pin number>": "<name>"}}. '
                        'Use the names exactly as printed; "?" if unreadable.'
                    )
                    # First read: the top-ranked page alone (one drawing, no competing variant);
                    # second read with the continuation page only if the first is unusable.
                    fix2 = _ask_vision(escalation_model, prompt2, pdf_path, pages[:1])
                    log.append(f"vision({escalation_model}) {label!r} pins={unresolved} pages={pages[:1]} -> {fix2}"
                               + ("" if fix2 else f" raw={_last_raw['text']!r}"))

                    def _usable(f2):
                        vals = {n: f2.get(str(n), "") for n in unresolved}
                        if any(not str(v).strip() or str(v).strip() == "?" for v in vals.values()):
                            return False
                        if tokens and len(unresolved) == len(tokens) and not _fix_matches_tokens(vals, tokens, prefix):
                            return False
                        return True

                    if not _usable(fix2):
                        # Retry with the page turned (sideways pinout drawings) plus the continuation page.
                        fix2 = _ask_vision(escalation_model, prompt2, pdf_path, pages[:2], rotations=(0, 90, 270))
                        log.append(f"vision({escalation_model}) retry {label!r} pages={pages[:2]} rotated -> {fix2}")
                    if tokens and (prefix or len(unresolved) == len(tokens)) and not _fix_matches_tokens(
                            {n: fix2.get(str(n), "") for n in unresolved}, tokens, prefix):
                        log.append(f"rejected escalation {label!r} -> {fix2}: not a permutation of {tokens}")
                        fix2 = {}
                    # Numeric-series groups (GPO0 to GPO3): the drawing read is
                    # trusted for the ORDER, but only if it is a clean permutation
                    # of the series (one prefix, exactly the range's numbers). An
                    # incomplete or off-series read is rejected -> the pins keep the
                    # group label (fail closed) rather than take a guessed order.
                    if numbers and len(unresolved) == len(numbers) and not _series_ok(
                            {n: fix2.get(str(n), "") for n in unresolved}, numbers):
                        log.append(f"rejected escalation {label!r} -> {fix2}: not a numbered series over {numbers}")
                        fix2 = {}
                    # Otherwise the escalation model's reading of the drawing is taken as-is
                    # (the series/permutation constraints police the guessers). When a
                    # group's pins were mis-assigned by the extraction, the drawing may
                    # legitimately say pin 29 = VREFP although 29 "belonged" to the A_IN
                    # group; when it names a pin another pin already holds, both are
                    # re-read together so the older, wrong one can move.
                    for n in unresolved:
                        v = _tidy(str(fix2.get(str(n), "")))
                        if not v or v == "?" or is_group(v):
                            continue
                        clash = [m for m, w in names.items() if m != n and w.upper() == v.upper()
                                 and v.upper() not in SHARED_NAMES and not is_group(w)]
                        if not clash:
                            names[n] = v
                            continue
                        pair = sorted([n] + clash)
                        fix3 = _ask_vision(
                            escalation_model,
                            f"Part {part_number}.{variant_note} Two pins were both read as \"{v}\": pins {pair}. From the pin configuration "
                            f"drawing / table on these page(s), give the printed NAME of each of these pins: {pair}. "
                            'Respond with JSON only: {"<pin number>": "<name>"}; "?" if unreadable.',
                            pdf_path, pages,
                        )
                        got = {m: _tidy(str(fix3.get(str(m), ""))) for m in pair}
                        log.append(f"collision {v!r} pins={pair} -> {fix3}")
                        others = _taken(pair)
                        if (all(got.values()) and "?" not in got.values()
                                and len({x.upper() for x in got.values()}) == len(pair)
                                and not any(x.upper() in others for x in got.values())):
                            for m, w in got.items():
                                names[m] = w
                except Exception as exc:  # noqa: BLE001
                    log.append(f"escalation of {label!r} failed: {type(exc).__name__}: {exc}")

    # 5b) duplicate names that no group step touched (the extraction itself doubled a
    # name, e.g. two pins read as IRQ): re-read all pins holding a duplicated name from
    # the drawing in one go; accept only a fully distinct, non-conflicting answer.
    if texts:
        vals0 = [v.upper() for v in names.values()]
        dup_names = {v for v in vals0 if vals0.count(v) > 1 and v not in SHARED_NAMES
                     and not v.startswith(("GND", "VCC", "VDD", "VS", "NC", "N.C"))}
        dup_pins = sorted(n for n, v in names.items() if v.upper() in dup_names and not is_group(v))
        if dup_pins and len(dup_pins) <= 16:
            pages = _score_pages(texts, dup_pins, package, pin_count)[:2]
            if pages:
                try:
                    todo = list(dup_pins)
                    for _round in range(3):   # widen the read when the answer clashes with other pins
                        fixd = _ask_vision(
                            escalation_model,
                            f"Part {part_number}.{variant_note} The extractor gave the same name to several pins "
                            f"({sorted(dup_names)}). From the pin configuration drawing / table on these page(s), give the printed "
                            f'NAME of each of these pins: {todo}. Respond with JSON only: {{"<pin number>": "<name>"}}; "?" if unreadable.',
                            pdf_path, pages[:1],
                        )
                        got = {m: _tidy(str(fixd.get(str(m), ""))) for m in todo}
                        log.append(f"duplicates {sorted(dup_names)} pins={todo} pages={pages[:1]} -> {fixd}")
                        if not (all(got.values()) and "?" not in got.values() and not any(is_group(x) for x in got.values())
                                and len({x.upper() for x in got.values()}) == len(todo)):
                            log.append("duplicates: answer rejected (incomplete / not distinct), left flagged")
                            break
                        clash = sorted(m for m, w in names.items() if m not in todo and w.upper() in {x.upper() for x in got.values()}
                                       and w.upper() not in SHARED_NAMES)
                        if not clash:
                            for m, w in got.items():
                                names[m] = w
                            break
                        log.append(f"duplicates: answer clashes with pins {clash}; re-reading them too")
                        todo = sorted(set(todo) | set(clash))
                        if len(todo) > 16:
                            log.append("duplicates: too many pins to re-read, left flagged")
                            break
                except Exception as exc:  # noqa: BLE001
                    log.append(f"duplicate re-read failed: {type(exc).__name__}: {exc}")

    # 6) verify -----------------------------------------------------------------------------
    dups = sorted(_scattered_dupes(names))
    leftover = sorted(n for n, v in names.items() if is_group(v) or is_suspicious(v))
    flags = {"duplicates": dups, "unresolved": leftover, "pin_count": len(names)}

    out_pins = []
    copies = {n: dict(p) for n, p in sorted(by_num.items())}
    carry_pin_data(copies, original, names)
    for n, q in copies.items():
        q["name"] = names.get(n, q.get("name"))
        out_pins.append(q)
    for n in sorted(set(names) - set(by_num)):  # pins introduced by a column re-map
        out_pins.append({"number": n, "name": names[n], "type": None, "nc": False})
    out_pins.sort(key=lambda p: p["number"])
    changed = sum(1 for n in names if names[n] != original.get(n))

    u = chat_bot.get_usage()
    return {
        "pins": out_pins,
        "changed": changed,
        "repairs": log,
        "flags": flags,
        "usage": {
            "repair_model": repair_model,
            "escalation_model": escalation_model,
            "calls": u["calls"],
            "prompt_tokens": u["prompt_tokens"],
            "completion_tokens": u["completion_tokens"],
            "total_tokens": u["prompt_tokens"] + u["completion_tokens"],
            "cost_usd": round(u["cost"], 6) if u["cost_known"] else None,
        },
    }
