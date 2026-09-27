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


def _page_context(texts, pins: List[int], maxc: int = 7000) -> List[Tuple[int, str]]:
    pno = _best_pin_page(texts, pins)
    if pno is None:
        return []
    out = [(pno, texts[pno - 1][1][:maxc])]
    if pno < len(texts) and any(_mentions(texts[pno][1], p) for p in pins):  # continuation page
        out.append((pno + 1, texts[pno][1][:maxc]))
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


def _render_page_b64(pdf: Path, pno: int, zoom: float = 2.0) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf))
    pix = doc[pno - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return base64.b64encode(pix.tobytes("png")).decode()


# --------------------------------------------------------------------------- LLM helpers
def _parse_json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _tidy(name: str) -> str:
    """Collapse OCR spacing inside a short all-caps token: ``SEG E`` -> ``SEGE``."""
    n = (name or "").strip()
    if re.fullmatch(r"[A-Z0-9]+(?: [A-Z0-9]{1,2})+", n) and len(n) <= 10:
        return n.replace(" ", "")
    return n


def _ask_text(model: str, prompt: str) -> dict:
    return _parse_json(chat_bot.get_completion_from_messages([{"role": "user", "content": prompt}], model=model))


def _ask_vision(model: str, prompt: str, pdf: Path, pages: List[int]) -> dict:
    content = [{"type": "text", "text": prompt}]
    for p in pages:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + _render_page_b64(pdf, p)}})
    return _parse_json(chat_bot.get_completion_from_messages([{"role": "user", "content": content}], model=model))


# --------------------------------------------------------------------------- comma-list groups
def comma_tokens(label: str) -> List[str]:
    """``"CDA, CDB"`` -> ``["CDA", "CDB"]``; empty list when the label is not a comma list."""
    n = (label or "").strip()
    if "," not in n or re.search(r"\bto\b|:", n, re.I):
        return []
    toks = [t.strip() for t in n.split(",")]
    return toks if all(toks) and len(toks) >= 2 else []


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


def _fix_matches_tokens(fix: Dict[int, str], tokens: List[str]) -> bool:
    """A comma-list group may only be resolved into a permutation of its own tokens."""
    got = sorted(_tidy(str(v)).upper() for v in fix.values())
    return got == sorted(t.upper() for t in tokens)


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
        if exp and len(exp) == len(members):
            for n, nm in zip(members, exp):
                out[n] = nm
            log.append(f"expand {label!r} -> {dict(zip(members, exp))}")
    return out, log


# --------------------------------------------------------------------------- entry point
def repair_pins(
    pins: List[dict],
    pdf_path: Path,
    part_number: Optional[str],
    repair_model: Optional[str] = None,
    escalation_model: Optional[str] = None,
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
    names: Dict[int, str] = {n: str(p.get("name") or "") for n, p in by_num.items()}
    original = dict(names)
    log: List[str] = []
    chat_bot.reset_usage()

    try:
        texts = _page_texts(pdf_path) if pdf_path.is_file() else []
    except Exception as exc:  # noqa: BLE001 - unreadable PDF: text/vision steps are skipped
        texts = []
        log.append(f"page text unavailable ({type(exc).__name__}); only deterministic repairs applied")

    # 1) package-column check ---------------------------------------------------------------
    ctx = _page_context(texts, list(names)) if texts else []
    pkg_cols = {m.group(1).upper() for _, t in ctx for m in _PKG_TOKENS.finditer(t)}
    if len(pkg_cols) >= 2 and ctx:
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
        if ans.get("column_ok") is False and isinstance(ans.get("pins"), dict) and len(ans["pins"]) >= 0.8 * len(names):
            names = {int(k): str(v) for k, v in ans["pins"].items() if str(k).strip().isdigit()}
            log.append(f"column-check: package={ans.get('package')} column_ok=False -> re-mapped {len(names)} pins")
        else:
            log.append(f"column-check: package={ans.get('package')} column_ok={ans.get('column_ok')}")

    # 2) deterministic numeric expansion ------------------------------------------------------
    names, exp_log = expand_groups_deterministic(names)
    log += exp_log

    # 3-5) remaining groups / suspicious names -------------------------------------------------
    groups: Dict[str, List[int]] = {}
    for n, name in names.items():
        if is_group(name) or is_suspicious(name):
            groups.setdefault(name, []).append(n)
    def _taken(exclude: List[int]) -> set:
        """Names already used by pins outside the group (shared power/ground names excluded)."""
        return {v.upper() for n, v in names.items() if n not in exclude
                and v.upper() not in SHARED_NAMES and not is_group(v) and not is_suspicious(v)}

    for label, members in groups.items():
        members.sort()
        fix: dict = {}
        letter_range = _is_letter_range(label)
        tokens = comma_tokens(label)
        pages_txt = _page_context(texts, members) if texts else []
        try:
            if letter_range:
                log.append(f"letter-range {label!r} pins={members}: needs the drawing, escalating")
            elif tokens and (row := resolve_from_row(texts, tokens, members)):
                fix = {str(n): v for n, v in row.items()}
                log.append(f"row-order {label!r} -> {row}")
            elif is_suspicious(label) and not is_group(label):
                vpages = [pg for pg, _ in pages_txt][:2] or _pinout_pages(texts, members)
                if vpages:
                    fix = _ask_vision(
                        repair_model,
                        f"Part {part_number}. The text extractor produced the garbled pin name \"{label}\" for pin(s) {members} "
                        "(subscripts or table headers got scrambled). Read the pin-function table / pin diagram on the attached "
                        f"page image(s) and give the correct printed name for each of these pin numbers: {members}. Write subscripts "
                        'inline (VIN R -> VINR, VD+ -> VD+). Respond with JSON only: {"<pin number>": "<name>"}.',
                        pdf_path, vpages,
                    )
                    log.append(f"vision({repair_model}) {label!r} pins={members} pages={vpages} -> {fix}")
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
        if fix and tokens and not _fix_matches_tokens({n: fix.get(str(n), "") for n in members}, tokens):
            log.append(f"rejected {label!r} -> {fix}: not a permutation of {tokens}")
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
            pages = _pinout_pages(texts, unresolved)
            if pages:
                try:
                    hint = f" The names must be exactly these, one each: {tokens}." if tokens else ""
                    fix2 = _ask_vision(
                        escalation_model,
                        f"Part {part_number}. From the pin configuration drawing / table on these datasheet page(s), give the pin NAME "
                        f"for each of these pin numbers: {unresolved}. They belong to the group \"{label}\"; the drawing shows which "
                        f'name sits on which number.{hint} Respond with JSON only: {{"<pin number>": "<name>"}}. '
                        'Use the names exactly as printed; "?" if unreadable.',
                        pdf_path, pages,
                    )
                    if tokens and len(unresolved) == len(tokens) and not _fix_matches_tokens(
                            {n: fix2.get(str(n), "") for n in unresolved}, tokens):
                        log.append(f"rejected escalation {label!r} -> {fix2}: not a permutation of {tokens}")
                        fix2 = {}
                    taken = _taken(members)
                    for n in unresolved:
                        v = _tidy(str(fix2.get(str(n), "")))
                        if v and v != "?" and not is_group(v) and v.upper() not in taken:
                            names[n] = v
                    log.append(f"vision({escalation_model}) {label!r} pins={unresolved} pages={pages} -> {fix2}")
                except Exception as exc:  # noqa: BLE001
                    log.append(f"escalation of {label!r} failed: {type(exc).__name__}: {exc}")

    # 6) verify -----------------------------------------------------------------------------
    vals = list(names.values())
    dups = sorted({v for v in vals if vals.count(v) > 1 and v.upper() not in SHARED_NAMES
                   and not v.upper().startswith(("GND", "VCC", "VDD", "VS", "NC", "N.C"))})
    leftover = sorted(n for n, v in names.items() if is_group(v) or is_suspicious(v))
    flags = {"duplicates": dups, "unresolved": leftover, "pin_count": len(names)}

    out_pins = []
    for n, p in sorted(by_num.items()):
        q = dict(p)
        q["name"] = names.get(n, p.get("name"))
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
