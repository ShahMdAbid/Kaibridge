#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blueprint_to_sch.py  --  abIDE (Agent Bridged IDE) logical blueprint -> KiCad schematic
=======================================================================================

WHY THIS EXISTS
---------------
Injecting footprints into live KiCad C++ memory over SWIG is fragile (dangling
pointers, ghost footprints, version-drifting API surface). KiCad already owns a
flawless, battle-tested "logical design -> board" pipeline: *Update PCB from
Schematic* (F8). So instead of fighting it, abIDE emits the ONE artifact that
pipeline consumes: a native `.kicad_sch` file.

    circuit_blueprint.yaml  ->  [this script]  ->  project.kicad_sch
                                                      |
                                                 (open in Eeschema, review)
                                                      |
                                                 F8  ->  project.kicad_pcb

CONNECTIVITY STRATEGY (the important bit)
-----------------------------------------
We do NOT attempt geometric auto-routing of wires between pins. That is a
graph-embedding problem and every heuristic produces ugly, overlapping,
review-hostile schematics.

Instead, for every pin that participates in a net we emit:

      [pin connection point] --(2.54mm stub wire)-- [net label "GND"]

KiCad's connectivity engine treats identically-named labels on the same sheet as
electrically identical. Power-class nets get `global_label` instead of `label`.
This is deterministic, O(n) in pins, never produces a shorted net, and is
100% reliable regardless of net fan-out.

OUTPUT CORRECTNESS CHECKLIST
----------------------------
  * `lib_symbols` block is populated with the *full* definition of every symbol
    used (KiCad requires embedded symbol defs; it does not chase lib tables).
  * Every symbol instance carries an `(instances (project ...(path ...)))`
    block keyed to the root sheet UUID -- WITHOUT this, KiCad 7+ renders every
    reference designator as "?" and F8 refuses to annotate.
  * `(sheet_instances (path "/" (page "1")))` present.
  * All geometry is snapped to the 1.27 mm grid, so pins land exactly on wire
    endpoints (off-grid == silently open circuit).
  * Missing symbols never abort the run: a synthesized placeholder symbol is
    generated from the pins referenced in the netlist, and the run is flagged.

USAGE
-----
    python blueprint_to_sch.py circuit_blueprint.yaml \
        --lib libs/easyeda2kicad.kicad_sym \
        --out build/myproject.kicad_sch \
        --emit-project

    python blueprint_to_sch.py --example > circuit_blueprint.yaml

EXIT CODES
----------
    0 = clean, 2 = generated with warnings (placeholders / unresolved pins),
    1 = fatal input error.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

#: KiCad schematic file-format stamp. 20250114 is the KiCad 9 format; KiCad 10 reads it
#: natively and silently upgrades on save. Emitting a *lower* version is always safe;
#: emitting a higher one makes KiCad refuse or warn. Override with --format-version.
SCH_FORMAT_VERSION = "20250114"
GENERATOR = "abIDE"
GENERATOR_VERSION = "9.0"

GRID = 1.27              # mm. KiCad's canonical schematic grid (50 mil).
STUB_LEN = 2.54          # mm. Length of the wire stub between a pin and its net label.
FONT = 1.27              # mm. Default text height.
DEFAULT_MARGIN = 12.7    # mm. Gap between placed symbol bounding boxes.
SHEET_MARGIN = 25.4      # mm. Gap from the page border.

#: Paper sizes (width, height) in mm; ordered smallest-first for auto-selection.
PAPERS = [("A4", 297.0, 210.0), ("A3", 420.0, 297.0),
          ("A2", 594.0, 420.0), ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0)]

#: Nets matching these patterns are emitted as *global* labels (power class).
POWER_NET_RE = re.compile(
    r"^(gnd\w*|[avd]?gnd|vss\w*|vcc\w*|vdd\w*|vbus|vin|vout|vbat|\+?\d+v\d*|\+?\d+[vV]\d*|"
    r"[+-]\d+(v|V)(\d+)?|pwr|power|earth)$", re.IGNORECASE)

#: Deterministic UUID namespace. Stable across machines, runs and Python versions.
ABIDE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://abide.dev/ns/kicad-schematic/v1")

PLACEHOLDER_LIB = "abIDE_Placeholder"

def det_uuid(*parts: Any) -> str:
    """Deterministic UUIDv5 from a tuple of key parts.

    Determinism matters: re-running the generator on an unchanged blueprint must
    produce a byte-identical file so that (a) git diffs are meaningful and (b)
    KiCad does not treat re-imported symbols as brand-new objects on F8.
    """
    return str(uuid.uuid5(ABIDE_NS, "\x1f".join(str(p) for p in parts)))

# --------------------------------------------------------------------------------------
# S-expression core: tokenizer / parser / pretty-printer
# --------------------------------------------------------------------------------------

class Atom:
    """A leaf token in an S-expression.

    We must preserve *whether the original token was quoted*. In KiCad's dialect
    `(hide yes)` and `(hide "yes")` are not interchangeable in every context, and
    symbol names must always round-trip quoted.
    """
    __slots__ = ("value", "quoted")

    def __init__(self, value: str, quoted: bool = False):
        self.value = value
        self.quoted = quoted

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Atom({self.value!r}, quoted={self.quoted})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Atom):
            return self.value == other.value
        return self.value == other

    def __hash__(self) -> int:
        return hash(self.value)

Node = Any  # Node = Atom | List[Node]

def A(v: Any) -> Atom:
    """Bare (unquoted) atom -- keywords, numbers, yes/no."""
    return Atom(str(v), quoted=False)

def Q(v: Any) -> Atom:
    """Quoted string atom -- names, values, free text."""
    return Atom("" if v is None else str(v), quoted=True)

def fmt(v: float) -> str:
    """Format a coordinate the way KiCad does: minimal digits, no '-0'."""
    v = round(float(v) + 0.0, 6)
    if v == 0:
        v = 0.0
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"

def N(v: float) -> Atom:
    """Numeric atom."""
    return A(fmt(v))

_TOKEN_END = set(" \t\r\n()")

def parse_sexp(text: str) -> List[Node]:
    """Parse a KiCad S-expression document into nested lists of Atom.

    Hand-rolled rather than regex-based: KiCad string escaping (\\" and \\\\)
    and the `;` free-text edge cases break naive splitters.
    """
    i, n = 0, len(text)
    stack: List[List[Node]] = [[]]

    while i < n:
        c = text[i]

        if c in " \t\r\n":
            i += 1
            continue

        if c == "(":
            new: List[Node] = []
            stack[-1].append(new)
            stack.append(new)
            i += 1
            continue

        if c == ")":
            if len(stack) == 1:
                raise ValueError(f"Unbalanced ')' at offset {i}")
            stack.pop()
            i += 1
            continue

        if c == '"':
            i += 1
            buf = io.StringIO()
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.write({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.write(ch)
                i += 1
            stack[-1].append(Atom(buf.getvalue(), quoted=True))
            continue

        # Bare token.
        start = i
        while i < n and text[i] not in _TOKEN_END:
            i += 1
        stack[-1].append(Atom(text[start:i], quoted=False))

    if len(stack) != 1:
        raise ValueError("Unbalanced '(' -- unexpected end of input")
    return stack[0]

_NEEDS_QUOTE = re.compile(r'[\s()"\\;]')

def _atom_str(a: Atom) -> str:
    v = a.value
    if a.quoted or v == "" or _NEEDS_QUOTE.search(v):
        v = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{v}"'
    return v

def dumps(node: Node, indent: int = 0, tab: str = "\t") -> str:
    """Pretty-print in KiCad's house style.

    Rule: a list with no sub-lists stays on one line; otherwise the head atoms
    stay on the opening line and every sub-list gets its own indented line.
    Any valid layout parses, but matching KiCad's style keeps `git diff` sane
    after a human opens and saves the file in Eeschema.
    """
    pad = tab * indent
    if isinstance(node, Atom):
        return pad + _atom_str(node)

    if not node:
        return pad + "()"

    if all(isinstance(c, Atom) for c in node):
        return pad + "(" + " ".join(_atom_str(c) for c in node) + ")"

    out = io.StringIO()
    head: List[str] = []
    idx = 0
    while idx < len(node) and isinstance(node[idx], Atom):
        head.append(_atom_str(node[idx]))
        idx += 1
    out.write(pad + "(" + " ".join(head))
    for child in node[idx:]:
        out.write("\n" + dumps(child, indent + 1, tab))
    out.write("\n" + pad + ")")
    return out.getvalue()

# --- small query helpers over parsed trees --------------------------------------------

def head(node: Node) -> str:
    """Keyword of a list node, or '' for atoms."""
    if isinstance(node, list) and node and isinstance(node[0], Atom):
        return node[0].value
    return ""

def children(node: Node, key: str) -> List[Node]:
    if not isinstance(node, list):
        return []
    return [c for c in node[1:] if head(c) == key]

def child(node: Node, key: str) -> Optional[Node]:
    c = children(node, key)
    return c[0] if c else None

def atoms(node: Node) -> List[Atom]:
    return [c for c in node[1:] if isinstance(c, Atom)] if isinstance(node, list) else []

def num(a: Atom, default: float = 0.0) -> float:
    try:
        return float(a.value)
    except (TypeError, ValueError):
        return default

def deepcopy_node(node: Node) -> Node:
    if isinstance(node, Atom):
        return Atom(node.value, node.quoted)
    return [deepcopy_node(c) for c in node]

# --------------------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------------------

def snap(v: float, grid: float = GRID) -> float:
    """Force a coordinate onto the schematic grid.

    Non-negotiable: a pin endpoint that is 0.001 mm off a wire endpoint is an
    OPEN CIRCUIT that looks perfectly connected on screen. Every emitted
    coordinate goes through this function.
    """
    return round(round(v / grid) * grid, 6)

def lib_to_sheet(lx: float, ly: float, at_x: float, at_y: float,
                 angle: float = 0.0, mirror: Optional[str] = None) -> Tuple[float, float]:
    """Map a point from symbol-library space into schematic-sheet space.

    Library space is Y-up (maths convention); sheet space is Y-down (screen
    convention). Hence the initial (lx, -ly) flip. Placement rotation is CCW as
    the user perceives it, which is CW in the Y-down frame.
    """
    if mirror == "y":
        lx = -lx
    elif mirror == "x":
        ly = -ly
    dx0, dy0 = lx, -ly
    t = math.radians(angle % 360.0)
    c, s = math.cos(t), math.sin(t)
    return (at_x + dx0 * c + dy0 * s, at_y - dx0 * s + dy0 * c)

def lib_vec_to_sheet(lx: float, ly: float, angle: float = 0.0,
                     mirror: Optional[str] = None) -> Tuple[float, float]:
    """Same transform, translation-free -- for direction vectors."""
    x, y = lib_to_sheet(lx, ly, 0.0, 0.0, angle, mirror)
    return (round(x, 6), round(y, 6))

# --------------------------------------------------------------------------------------
# Symbol library model
# --------------------------------------------------------------------------------------

@dataclass
class LibPin:
    """One pin of one unit of a library symbol."""
    number: str
    name: str
    x: float            # library-space connection point
    y: float
    angle: float        # direction from the connection point *toward the body*
    length: float
    unit: int
    style: int          # 0 = common to all body styles (De Morgan), 1 = normal
    etype: str = "passive"
    hidden: bool = False

@dataclass
class LibSymbol:
    """A parsed symbol definition plus a cached pin/geometry index."""
    name: str
    lib_nick: str
    node: Node
    pins: List[LibPin] = field(default_factory=list)
    extends: Optional[str] = None

    @property
    def lib_id(self) -> str:
        return f"{self.lib_nick}:{self.name}"

    # -- pin access --------------------------------------------------------------------

    def pins_for_unit(self, unit: int) -> List[LibPin]:
        """Pins belonging to a unit.

        Unit 0 is the 'common to every unit' pseudo-unit (typically the power
        pins of a quad op-amp), so it is always merged in.
        """
        return [p for p in self.pins if p.unit in (0, unit)]

    def find_pin(self, unit: int, token: str) -> Optional[LibPin]:
        """Resolve a blueprint pin token: exact number, then case-insensitive name."""
        cands = self.pins_for_unit(unit)
        for p in cands:
            if p.number == token:
                return p
        low = token.strip().lower()
        for p in cands:
            if p.name.strip().lower() == low:
                return p
        # Tolerate zero-padded / whitespace-y agent output ("01" == "1").
        for p in cands:
            if p.number.lstrip("0") == token.lstrip("0") and token.strip():
                return p
        return None

    @property
    def unit_count(self) -> int:
        us = [p.unit for p in self.pins if p.unit > 0]
        return max(us) if us else 1

    # -- geometry ----------------------------------------------------------------------

    def bbox(self, unit: int) -> Tuple[float, float, float, float]:
        """Library-space bounding box (min_x, min_y, max_x, max_y) of a unit.

        Used purely for auto-placement spacing and field positioning, so an
        approximation (arc chords rather than true arc extents) is acceptable.
        """
        xs: List[float] = []
        ys: List[float] = []

        def add(x: float, y: float) -> None:
            xs.append(x)
            ys.append(y)

        def walk(node: Node) -> None:
            k = head(node)
            if k in ("rectangle",):
                for key in ("start", "end"):
                    c = child(node, key)
                    if c:
                        a = atoms(c)
                        if len(a) >= 2:
                            add(num(a[0]), num(a[1]))
            elif k in ("polyline", "bezier"):
                pts = child(node, "pts")
                if pts:
                    for xy in children(pts, "xy"):
                        a = atoms(xy)
                        if len(a) >= 2:
                            add(num(a[0]), num(a[1]))
            elif k == "circle":
                c = child(node, "center")
                r = child(node, "radius")
                if c:
                    a = atoms(c)
                    rad = num(atoms(r)[0]) if r and atoms(r) else 0.0
                    if len(a) >= 2:
                        add(num(a[0]) - rad, num(a[1]) - rad)
                        add(num(a[0]) + rad, num(a[1]) + rad)
            elif k == "arc":
                for key in ("start", "mid", "end"):
                    c = child(node, key)
                    if c:
                        a = atoms(c)
                        if len(a) >= 2:
                            add(num(a[0]), num(a[1]))
            elif k == "symbol":
                for c in node[1:]:
                    if isinstance(c, list):
                        walk(c)

        # Only walk the sub-symbols belonging to this unit.
        for sub in children(self.node, "symbol"):
            sa = atoms(sub)
            if not sa:
                continue
            u, st = _parse_subunit_name(sa[0].value, self.name)
            if u in (0, unit) and st in (0, 1):
                walk(sub)

        for p in self.pins_for_unit(unit):
            add(p.x, p.y)
            ex = p.x + p.length * math.cos(math.radians(p.angle))
            ey = p.y + p.length * math.sin(math.radians(p.angle))
            add(ex, ey)

        if not xs:  # Degenerate/empty symbol -- give it a nominal body.
            return (-2.54, -2.54, 2.54, 2.54)
        return (min(xs), min(ys), max(xs), max(ys))

    def property_value(self, key: str, default: str = "") -> str:
        for prop in children(self.node, "property"):
            a = atoms(prop)
            if len(a) >= 2 and a[0].value.lower() == key.lower():
                return a[1].value
        return default

def _parse_subunit_name(sub_name: str, base: str) -> Tuple[int, int]:
    """Decode a sub-symbol name like `MCU_STM32_1_1` -> (unit=1, style=1).

    KiCad encodes unit and De Morgan body style as a `_<unit>_<style>` suffix on
    the child symbol name. We must not assume the base name is suffix-free
    (names legitimately contain underscores and digits), so we anchor on the
    trailing two numeric groups.
    """
    m = re.match(r"^(?P<base>.*)_(?P<unit>\d+)_(?P<style>\d+)$", sub_name)
    if not m:
        return (0, 1)
    return (int(m.group("unit")), int(m.group("style")))

def _parse_pin(node: Node, unit: int, style: int) -> Optional[LibPin]:
    a = atoms(node)
    etype = a[0].value if len(a) >= 1 else "passive"
    at = child(node, "at")
    if not at:
        return None
    aa = atoms(at)
    x = num(aa[0]) if len(aa) > 0 else 0.0
    y = num(aa[1]) if len(aa) > 1 else 0.0
    ang = num(aa[2]) if len(aa) > 2 else 0.0

    ln = child(node, "length")
    length = num(atoms(ln)[0]) if ln and atoms(ln) else 2.54

    name_node = child(node, "name")
    number_node = child(node, "number")
    name = atoms(name_node)[0].value if name_node and atoms(name_node) else "~"
    number = atoms(number_node)[0].value if number_node and atoms(number_node) else ""

    # `hide` appears both as a bare flag (legacy) and as `(hide yes)` (KiCad 8+).
    hidden = any(at_.value == "hide" for at_ in a)
    h = child(node, "hide")
    if h and atoms(h) and atoms(h)[0].value == "yes":
        hidden = True

    if not number:
        return None
    return LibPin(number=number, name=name, x=x, y=y, angle=ang, length=length,
                  unit=unit, style=style, etype=etype, hidden=hidden)

class SymbolLibrary:
    """Aggregates one or more `.kicad_sym` files into a single lookup table."""

    def __init__(self) -> None:
        self.symbols: Dict[str, LibSymbol] = {}          # "nick:Name" -> LibSymbol
        self.by_name: Dict[str, List[LibSymbol]] = {}    # "Name"      -> [LibSymbol]

    # -- loading -----------------------------------------------------------------------

    def load(self, path: str, nickname: Optional[str] = None) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        nick = nickname or os.path.splitext(os.path.basename(path))[0]
        top = parse_sexp(text)
        roots = [t for t in top if head(t) == "kicad_symbol_lib"] or top
        raw: Dict[str, Node] = {}
        for root in roots:
            for sym in children(root, "symbol"):
                a = atoms(sym)
                if not a:
                    continue
                raw[a[0].value] = sym

        # Resolve `extends` (derived symbols, e.g. R_Small extends R) before indexing.
        for name, node in raw.items():
            resolved = self._resolve_extends(name, node, raw, seen=set())
            sym = self._index(name, nick, resolved)
            self.symbols[sym.lib_id] = sym
            self.by_name.setdefault(name, []).append(sym)

    def _resolve_extends(self, name: str, node: Node, raw: Dict[str, Node],
                         seen: set) -> Node:
        ext = child(node, "extends")
        if not ext or not atoms(ext):
            return node
        base_name = atoms(ext)[0].value
        if base_name in seen or base_name not in raw:
            return node  # Broken/cyclic inheritance -- fail soft, keep the stub.
        seen.add(base_name)
        base = self._resolve_extends(base_name, raw[base_name], raw, seen)

        merged: Node = [A("symbol"), Q(name)]
        derived_props = {atoms(p)[0].value.lower(): p
                         for p in children(node, "property") if atoms(p)}

        for c in base[2:]:
            if isinstance(c, list) and head(c) == "property":
                pa = atoms(c)
                key = pa[0].value.lower() if pa else ""
                if key in derived_props:
                    merged.append(deepcopy_node(derived_props.pop(key)))
                    continue
            if isinstance(c, list) and head(c) == "extends":
                continue
            copied = deepcopy_node(c)
            # Re-key inherited sub-units onto the derived symbol's name.
            if head(copied) == "symbol" and atoms(copied):
                old = atoms(copied)[0].value
                u, st = _parse_subunit_name(old, base_name)
                copied[1] = Q(f"{name}_{u}_{st}")
            merged.append(copied)

        merged.extend(deepcopy_node(p) for p in derived_props.values())
        return merged

    def _index(self, name: str, nick: str, node: Node) -> LibSymbol:
        sym = LibSymbol(name=name, lib_nick=nick, node=node)
        for sub in children(node, "symbol"):
            sa = atoms(sub)
            if not sa:
                continue
            unit, style = _parse_subunit_name(sa[0].value, name)
            if style not in (0, 1):
                continue  # Skip De Morgan alternate bodies; we always draw style 1.
            for pin_node in children(sub, "pin"):
                p = _parse_pin(pin_node, unit, style)
                if p:
                    sym.pins.append(p)
        return sym

    # -- lookup ------------------------------------------------------------------------

    def resolve(self, token: str) -> Optional[LibSymbol]:
        """Resolve 'nick:Name', bare 'Name', or a case-insensitive fallback."""
        if not token:
            return None
        if token in self.symbols:
            return self.symbols[token]
        if ":" in token:
            _, bare = token.split(":", 1)
        else:
            bare = token
        cands = self.by_name.get(bare)
        if cands:
            return cands[0]
        low = bare.lower()
        for lid, sym in self.symbols.items():
            if sym.name.lower() == low or lid.lower() == token.lower():
                return sym
        return None

# --------------------------------------------------------------------------------------
# Placeholder symbol synthesis (robustness against missing library entries)
# --------------------------------------------------------------------------------------

def make_placeholder(ref: str, pin_numbers: Sequence[str], value: str) -> LibSymbol:
    """Synthesize a rectangular symbol from nothing but the netlist.

    A missing library symbol must never abort the pipeline: the agent should
    still get a reviewable schematic showing *exactly* which part it failed to
    source. The placeholder is drawn as a dashed-look box with the referenced
    pins split left/right, so the human sees the hole immediately.
    """
    nums = sorted(pin_numbers, key=lambda s: (0, int(s)) if s.isdigit() else (1, s))
    if not nums:
        nums = ["1"]
    left = nums[: (len(nums) + 1) // 2]
    right = nums[(len(nums) + 1) // 2:]
    rows = max(len(left), len(right), 1)

    half_h = snap(max(rows * 2.54, 5.08) / 2 + 2.54)
    half_w = 10.16
    name = f"{ref}_PLACEHOLDER"

    def eff(hide: bool = False) -> Node:
        e: Node = [A("effects"), [A("font"), [A("size"), N(FONT), N(FONT)]]]
        if hide:
            e.append([A("hide"), A("yes")])
        return e

    node: Node = [
        A("symbol"), Q(name),
        [A("pin_numbers"), [A("hide"), A("no")]],
        [A("pin_names"), [A("offset"), N(1.016)]],
        [A("exclude_from_sim"), A("no")],
        [A("in_bom"), A("yes")],
        [A("on_board"), A("yes")],
        [A("property"), Q("Reference"), Q(re.sub(r"\d+$", "", ref) or "U"),
         [A("at"), N(0), N(half_h + 2.54), N(0)], eff()],
        [A("property"), Q("Value"), Q(value or ref),
         [A("at"), N(0), N(-half_h - 2.54), N(0)], eff()],
        [A("property"), Q("Footprint"), Q(""), [A("at"), N(0), N(0), N(0)], eff(True)],
        [A("property"), Q("Datasheet"), Q(""), [A("at"), N(0), N(0), N(0)], eff(True)],
        [A("property"), Q("ki_description"),
         Q("abIDE placeholder: symbol not found in supplied libraries"),
         [A("at"), N(0), N(0), N(0)], eff(True)],
    ]

    body: Node = [
        A("symbol"), Q(f"{name}_1_1"),
        [A("rectangle"),
         [A("start"), N(-half_w), N(half_h)],
         [A("end"), N(half_w), N(-half_h)],
         [A("stroke"), [A("width"), N(0.254)], [A("type"), A("dash")]],
         [A("fill"), [A("type"), A("background")]]],
    ]

    pins: List[LibPin] = []

    def emit(numbers: Sequence[str], side: str) -> None:
        x = -half_w - 2.54 if side == "L" else half_w + 2.54
        angle = 0.0 if side == "L" else 180.0  # direction points *into* the body
        y0 = (len(numbers) - 1) * 2.54 / 2.0
        for i, numstr in enumerate(numbers):
            y = snap(y0 - i * 2.54)
            body.append([
                A("pin"), A("passive"), A("line"),
                [A("at"), N(x), N(y), N(angle)],
                [A("length"), N(2.54)],
                [A("name"), Q("~"), [A("effects"), [A("font"), [A("size"), N(FONT), N(FONT)]]]],
                [A("number"), Q(numstr), [A("effects"), [A("font"), [A("size"), N(FONT), N(FONT)]]]],
            ])
            pins.append(LibPin(number=numstr, name="~", x=x, y=y, angle=angle,
                               length=2.54, unit=1, style=1))

    emit(left, "L")
    emit(right, "R")
    node.append(body)

    sym = LibSymbol(name=name, lib_nick=PLACEHOLDER_LIB, node=node, pins=pins)
    return sym

# --------------------------------------------------------------------------------------
# Blueprint model + tolerant loader
# --------------------------------------------------------------------------------------

@dataclass
class Component:
    ref: str
    symbol_token: str = ""
    value: str = ""
    footprint: str = ""
    datasheet: str = ""
    unit: int = 1
    rotation: float = 0.0
    mirror: Optional[str] = None
    at: Optional[Tuple[float, float]] = None     # explicit placement (mm), optional
    fields: Dict[str, str] = field(default_factory=dict)
    dnp: bool = False
    in_bom: bool = True
    on_board: bool = True
    # resolved at build time:
    sym: Optional[LibSymbol] = None
    is_placeholder: bool = False
    pos: Tuple[float, float] = (0.0, 0.0)

@dataclass
class PinRef:
    ref: str
    pin: str

@dataclass
class Net:
    name: str
    pins: List[PinRef] = field(default_factory=list)
    is_power: bool = False

PIN_TOKEN_RE = re.compile(r"^\s*(?P<ref>[A-Za-z_][A-Za-z0-9_#]*)\s*[.:\-/]\s*(?P<pin>[A-Za-z0-9_+~/\.]+)\s*$")

def _parse_pin_token(tok: Any) -> Optional[PinRef]:
    """Accept every shape an LLM plausibly emits for a pin reference."""
    if isinstance(tok, dict):
        ref = tok.get("ref") or tok.get("component") or tok.get("designator") or tok.get("part")
        pin = tok.get("pin") or tok.get("pad") or tok.get("number") or tok.get("pin_number")
        if ref is None or pin is None:
            return None
        return PinRef(str(ref).strip(), str(pin).strip())
    if isinstance(tok, (list, tuple)) and len(tok) == 2:
        return PinRef(str(tok[0]).strip(), str(tok[1]).strip())
    if isinstance(tok, str):
        m = PIN_TOKEN_RE.match(tok)
        if m:
            return PinRef(m.group("ref"), m.group("pin"))
    return None

def _as_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def load_blueprint(path: str) -> Dict[str, Any]:
    """Load YAML or JSON. YAML is optional -- JSON always works with the stdlib."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise SystemExit(
                "PyYAML is required for .yaml blueprints (pip install pyyaml), "
                "or supply the blueprint as .json."
            )
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore
                data = yaml.safe_load(text)
            except Exception:
                raise
    if not isinstance(data, dict):
        raise SystemExit("Blueprint root must be a mapping/object.")
    
    # Unwrap 'circuit_blueprint' if it's nested
    if "circuit_blueprint" in data:
        data = data["circuit_blueprint"]
        
    return data

def parse_components(data: Dict[str, Any]) -> List[Component]:
    """Normalize `components:` from either a list or a ref-keyed mapping."""
    raw = data.get("components") or data.get("parts") or data.get("symbols") or []
    out: List[Component] = []

    def build(ref: str, spec: Dict[str, Any]) -> Component:
        at = spec.get("at") or spec.get("position") or spec.get("pos")
        pos = None
        if isinstance(at, (list, tuple)) and len(at) >= 2:
            pos = (float(at[0]), float(at[1]))
        elif isinstance(at, dict) and "x" in at and "y" in at:
            pos = (float(at["x"]), float(at["y"]))

        mirror = spec.get("mirror")
        mirror = str(mirror).lower() if mirror in ("x", "y", "X", "Y") else None

        known = {"ref", "reference", "designator", "symbol", "lib_id", "libid", "part",
                 "value", "val", "footprint", "fp", "datasheet", "unit", "rotation",
                 "rot", "angle", "mirror", "at", "position", "pos", "fields",
                 "properties", "dnp", "in_bom", "on_board"}
        extra = dict(spec.get("fields") or spec.get("properties") or {})
        for k, v in spec.items():
            if k not in known and isinstance(v, (str, int, float, bool)):
                extra.setdefault(k, str(v))

        return Component(
            ref=ref,
            symbol_token=str(spec.get("symbol") or spec.get("lib_id")
                             or spec.get("libid") or spec.get("part") or "").strip(),
            value=str(spec.get("value") or spec.get("val") or "").strip(),
            footprint=str(spec.get("footprint") or spec.get("fp") or "").strip(),
            datasheet=str(spec.get("datasheet") or "").strip(),
            unit=int(spec.get("unit") or 1),
            rotation=float(spec.get("rotation") or spec.get("rot") or spec.get("angle") or 0),
            mirror=mirror,
            at=pos,
            fields={str(k): str(v) for k, v in extra.items()},
            dnp=_as_bool(spec.get("dnp"), False),
            in_bom=_as_bool(spec.get("in_bom"), True),
            on_board=_as_bool(spec.get("on_board"), True),
        )

    if isinstance(raw, dict):
        for ref, spec in raw.items():
            spec = spec if isinstance(spec, dict) else {"symbol": str(spec)}
            out.append(build(str(ref).strip(), spec))
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("ref") or item.get("reference")
                      or item.get("designator") or "").strip()
            if not ref:
                continue
            out.append(build(ref, item))
    return out

def parse_nets(data: Dict[str, Any], warn) -> List[Net]:
    """Normalize `nets:` from mapping form or list-of-objects form."""
    raw = data.get("nets") or data.get("connections") or data.get("netlist") or []
    nets: List[Net] = []

    def build(name: str, conns: Iterable[Any], forced_power: Optional[bool] = None) -> Net:
        net = Net(name=name)
        for tok in conns or []:
            pr = _parse_pin_token(tok)
            if pr is None:
                warn(f"net '{name}': cannot parse pin reference {tok!r} -- skipped")
                continue
            net.pins.append(pr)
        net.is_power = bool(POWER_NET_RE.match(name)) if forced_power is None else forced_power
        return net

    if isinstance(raw, dict):
        for name, conns in raw.items():
            if isinstance(conns, dict):
                nets.append(build(str(name),
                                  conns.get("connections") or conns.get("pins") or [],
                                  _as_bool(conns.get("power"), None) if "power" in conns else None))
            else:
                nets.append(build(str(name), conns if isinstance(conns, list) else [conns]))
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("net") or "").strip()
            if not name:
                continue
            conns = item.get("connections") or item.get("pins") or item.get("nodes") or []
            forced = _as_bool(item.get("power"), None) if "power" in item else None
            nets.append(build(name, conns, forced))
    return nets

# --------------------------------------------------------------------------------------
# Schematic builder
# --------------------------------------------------------------------------------------

class SchematicBuilder:
    def __init__(self, project: str, lib: SymbolLibrary, *,
                 margin: float = DEFAULT_MARGIN, columns: Optional[int] = None,
                 paper: Optional[str] = None, fmt_version: str = SCH_FORMAT_VERSION,
                 nc_unused: bool = False, title: str = "", company: str = "",
                 rev: str = "") -> None:
        self.project = project
        self.lib = lib
        self.margin = margin
        self.columns = columns
        self.paper_override = paper
        self.fmt_version = fmt_version
        self.nc_unused = nc_unused
        self.title = title or project
        self.company = company
        self.rev = rev

        self.root_uuid = det_uuid("root-sheet", project)
        self.warnings: List[str] = []
        self.used_symbols: Dict[str, LibSymbol] = {}   # lib_id -> LibSymbol

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    # -- resolution --------------------------------------------------------------------

    def resolve_symbols(self, comps: List[Component], nets: List[Net]) -> None:
        """Bind every component to a library symbol, synthesizing on failure."""
        pins_by_ref: Dict[str, List[str]] = {}
        for net in nets:
            for pr in net.pins:
                pins_by_ref.setdefault(pr.ref, []).append(pr.pin)

        for comp in comps:
            sym = self.lib.resolve(comp.symbol_token) if comp.symbol_token else None
            if sym is None and comp.symbol_token:
                self.warn(f"{comp.ref}: symbol '{comp.symbol_token}' not found in any "
                          f"supplied library -- generating placeholder")
            elif sym is None:
                self.warn(f"{comp.ref}: no 'symbol'/'lib_id' given -- generating placeholder")

            if sym is None:
                sym = make_placeholder(comp.ref, pins_by_ref.get(comp.ref, []), comp.value)
                comp.is_placeholder = True

            comp.sym = sym
            if comp.unit < 1 or comp.unit > max(sym.unit_count, 1):
                if comp.unit != 1:
                    self.warn(f"{comp.ref}: unit {comp.unit} out of range for "
                              f"'{sym.lib_id}' -- clamped to 1")
                comp.unit = 1
            self.used_symbols[sym.lib_id] = sym

    # -- placement ---------------------------------------------------------------------

    def place(self, comps: List[Component]) -> Tuple[float, float]:
        """Deterministic grid placement; returns required (width, height) in mm.

        Explicitly placed components (`at:` in the blueprint) are honoured and
        excluded from the auto-flow, so a human can hand-tune a layout and
        re-run the generator without losing their work.
        """
        auto = [c for c in comps if c.at is None]
        fixed = [c for c in comps if c.at is not None]

        for c in fixed:
            c.pos = (snap(c.at[0]), snap(c.at[1]))

        # Cell sizing: worst-case symbol footprint + stub + label text allowance.
        cells: List[Tuple[Component, float, float, Tuple[float, float, float, float]]] = []
        for c in auto:
            bb = c.sym.bbox(c.unit)
            w = (bb[2] - bb[0]) + 2 * (STUB_LEN + 12.7)
            h = (bb[3] - bb[1]) + 2 * (STUB_LEN + 7.62)
            cells.append((c, max(w, 20.32), max(h, 20.32), bb))

        cols = self.columns or max(1, int(math.ceil(math.sqrt(max(len(cells), 1)))))
        col_w = [0.0] * cols
        rows: List[List[Tuple[Component, float, float, Tuple[float, float, float, float]]]] = []
        for i in range(0, len(cells), cols):
            rows.append(cells[i:i + cols])
        for row in rows:
            for ci, (_, w, _, _) in enumerate(row):
                col_w[ci] = max(col_w[ci], w)

        x_offsets: List[float] = []
        acc = SHEET_MARGIN
        for w in col_w:
            x_offsets.append(acc)
            acc += w + self.margin
        total_w = acc - self.margin + SHEET_MARGIN

        y = SHEET_MARGIN
        for row in rows:
            row_h = max((h for _, _, h, _ in row), default=0.0)
            for ci, (c, _w, _h, bb) in enumerate(row):
                # Anchor the symbol origin so its bbox sits inside the cell.
                cx = x_offsets[ci] + (STUB_LEN + 12.7) - bb[0]
                cy = y + (STUB_LEN + 7.62) + bb[3]
                c.pos = (snap(cx), snap(cy))
            y += row_h + self.margin
        total_h = y - self.margin + SHEET_MARGIN

        for c in fixed:
            total_w = max(total_w, c.pos[0] + SHEET_MARGIN)
            total_h = max(total_h, c.pos[1] + SHEET_MARGIN)
        return (total_w, total_h)

    def pick_paper(self, w: float, h: float) -> str:
        if self.paper_override:
            return self.paper_override
        for name, pw, ph in PAPERS:
            if w <= pw and h <= ph:
                return name
        return PAPERS[-1][0]

    # -- emission ----------------------------------------------------------------------

    def _effects(self, *, hide: bool = False, justify: Sequence[str] = (),
                 angle_bold: bool = False) -> Node:
        e: Node = [A("effects"), [A("font"), [A("size"), N(FONT), N(FONT)]]]
        if justify:
            e.append([A("justify")] + [A(j) for j in justify])
        if hide:
            e.append([A("hide"), A("yes")])
        return e

    def _property(self, key: str, value: str, x: float, y: float, angle: float = 0.0,
                  hide: bool = False, justify: Sequence[str] = ()) -> Node:
        return [A("property"), Q(key), Q(value),
                [A("at"), N(x), N(y), N(angle)],
                self._effects(hide=hide, justify=justify)]

    def _wire(self, x1: float, y1: float, x2: float, y2: float, key: str) -> Node:
        return [A("wire"),
                [A("pts"), [A("xy"), N(x1), N(y1)], [A("xy"), N(x2), N(y2)]],
                [A("stroke"), [A("width"), N(0)], [A("type"), A("default")]],
                [A("uuid"), Q(det_uuid("wire", self.project, key))]]

    def _label(self, name: str, x: float, y: float, direction: Tuple[float, float],
               is_power: bool, key: str) -> Node:
        """Emit a local or global label oriented away from the symbol body.

        KiCad normalizes label rotation to 0 or 90 degrees and expresses
        left/down orientation through text justification, so we do the same.
        """
        dx, dy = direction
        if abs(dx) >= abs(dy):
            angle = 0.0
            justify = ["left"] if dx >= 0 else ["right"]
        else:
            angle = 90.0
            justify = ["left"] if dy <= 0 else ["right"]

        if is_power:
            node: Node = [A("global_label"), Q(name),
                          [A("shape"), A("passive")],
                          [A("at"), N(x), N(y), N(angle)],
                          [A("fields_autoplaced"), A("yes")],
                          self._effects(justify=justify),
                          [A("uuid"), Q(det_uuid("glabel", self.project, key))],
                          [A("property"), Q("Intersheetrefs"), Q("${INTERSHEET_REFS}"),
                           [A("at"), N(x), N(y), N(0)],
                           self._effects(hide=True)]]
        else:
            node = [A("label"), Q(name),
                    [A("at"), N(x), N(y), N(angle)],
                    [A("fields_autoplaced"), A("yes")],
                    self._effects(justify=justify),
                    [A("uuid"), Q(det_uuid("label", self.project, key))]]
        return node

    def build(self, comps: List[Component], nets: List[Net]) -> str:
        self.resolve_symbols(comps, nets)
        width, height = self.place(comps)
        paper = self.pick_paper(width, height)

        by_ref: Dict[str, Component] = {}
        for c in comps:
            if c.ref in by_ref:
                self.warn(f"duplicate reference designator '{c.ref}' -- later one ignored")
                continue
            by_ref[c.ref] = c

        connected: set = set()   # (ref, pin_number) actually wired
        body: List[Node] = []

        # ---- nets: stub wires + labels -------------------------------------------------
        for net in sorted(nets, key=lambda n: n.name):
            if len(net.pins) < 2:
                self.warn(f"net '{net.name}' has {len(net.pins)} node(s) -- "
                          f"single-node nets will raise ERC warnings")
            for pr in net.pins:
                comp = by_ref.get(pr.ref)
                if comp is None:
                    self.warn(f"net '{net.name}': component '{pr.ref}' is not declared "
                              f"in components -- connection dropped")
                    continue
                lp = comp.sym.find_pin(comp.unit, pr.pin)
                if lp is None:
                    self.warn(f"net '{net.name}': {pr.ref} has no pin '{pr.pin}' in "
                              f"'{comp.sym.lib_id}' unit {comp.unit} -- connection dropped")
                    continue

                px, py = lib_to_sheet(lp.x, lp.y, comp.pos[0], comp.pos[1],
                                      comp.rotation, comp.mirror)
                px, py = snap(px), snap(py)

                # Outward = opposite of the pin's body-facing angle.
                out_a = math.radians(lp.angle + 180.0)
                dx, dy = lib_vec_to_sheet(math.cos(out_a), math.sin(out_a),
                                          comp.rotation, comp.mirror)
                mag = math.hypot(dx, dy) or 1.0
                dx, dy = dx / mag, dy / mag

                ex, ey = snap(px + dx * STUB_LEN), snap(py + dy * STUB_LEN)
                key = f"{net.name}|{pr.ref}|{lp.number}"
                body.append(self._wire(px, py, ex, ey, key))
                body.append(self._label(net.name, ex, ey, (dx, dy), net.is_power, key))
                connected.add((pr.ref, lp.number))

        # ---- symbol instances ----------------------------------------------------------
        for comp in comps:
            if by_ref.get(comp.ref) is not comp:
                continue
            body.append(self._symbol_instance(comp, connected))

        # ---- optional no-connect flags on unused pins ----------------------------------
        if self.nc_unused:
            for comp in comps:
                if by_ref.get(comp.ref) is not comp:
                    continue
                for lp in comp.sym.pins_for_unit(comp.unit):
                    if (comp.ref, lp.number) in connected or lp.hidden:
                        continue
                    if lp.etype in ("no_connect", "power_in"):
                        continue
                    x, y = lib_to_sheet(lp.x, lp.y, comp.pos[0], comp.pos[1],
                                        comp.rotation, comp.mirror)
                    body.append([A("no_connect"), [A("at"), N(snap(x)), N(snap(y))],
                                 [A("uuid"), Q(det_uuid("nc", self.project,
                                                        comp.ref, lp.number))]])

        # ---- document assembly ---------------------------------------------------------
        lib_syms: Node = [A("lib_symbols")]
        for lib_id in sorted(self.used_symbols):
            sym = self.used_symbols[lib_id]
            copied = deepcopy_node(sym.node)
            copied[1] = Q(lib_id)   # lib_symbols entries are keyed "nick:Name"
            lib_syms.append(copied)

        doc: Node = [
            A("kicad_sch"),
            [A("version"), A(self.fmt_version)],
            [A("generator"), Q(GENERATOR)],
            [A("generator_version"), Q(GENERATOR_VERSION)],
            [A("uuid"), Q(self.root_uuid)],
            [A("paper"), Q(paper)],
            [A("title_block"),
             [A("title"), Q(self.title)],
             [A("rev"), Q(self.rev)],
             [A("company"), Q(self.company)],
             [A("comment"), A(1), Q("Generated by abIDE -- do not hand-edit blindly")]],
            lib_syms,
        ]
        doc.extend(body)
        doc.append([A("sheet_instances"), [A("path"), Q("/"), [A("page"), Q("1")]]])
        doc.append([A("embedded_fonts"), A("no")])

        return dumps(doc) + "\n"

    def _symbol_instance(self, comp: Component, connected: set) -> Node:
        sym = comp.sym
        bb = sym.bbox(comp.unit)
        px, py = comp.pos

        # Reference above the body, value below -- in *sheet* space (Y grows down).
        top_y = snap(py - bb[3] - 2.54)
        bot_y = snap(py - bb[1] + 2.54)

        node: Node = [
            A("symbol"),
            [A("lib_id"), Q(sym.lib_id)],
            [A("at"), N(px), N(py), N(comp.rotation % 360)],
        ]
        if comp.mirror in ("x", "y"):
            node.append([A("mirror"), A(comp.mirror)])
        node.extend([
            [A("unit"), A(comp.unit)],
            [A("exclude_from_sim"), A("no")],
            [A("in_bom"), A("yes" if comp.in_bom else "no")],
            [A("on_board"), A("yes" if comp.on_board else "no")],
            [A("dnp"), A("yes" if comp.dnp else "no")],
            [A("fields_autoplaced"), A("no")],
            [A("uuid"), Q(det_uuid("symbol", self.project, comp.ref))],
            self._property("Reference", comp.ref, px, top_y),
            self._property("Value", comp.value or sym.property_value("Value", comp.ref),
                           px, bot_y),
            # Footprint is THE field that makes F8 work. Never omit it, even if empty
            # (an empty footprint yields an explicit KiCad error rather than a silent
            # missing part on the board).
            self._property("Footprint",
                           comp.footprint or sym.property_value("Footprint"),
                           px, py, hide=True),
            self._property("Datasheet",
                           comp.datasheet or sym.property_value("Datasheet"),
                           px, py, hide=True),
        ])
        if comp.is_placeholder:
            node.append(self._property("abIDE_Status", "PLACEHOLDER_SYMBOL_MISSING",
                                       px, py, hide=True))
        for k, v in sorted(comp.fields.items()):
            if k.lower() in ("reference", "value", "footprint", "datasheet"):
                continue
            node.append(self._property(k, v, px, py, hide=True))

        # Per-pin UUIDs: KiCad uses these to persist per-pin overrides across F8 runs.
        for lp in sorted(sym.pins_for_unit(comp.unit), key=lambda p: p.number):
            node.append([A("pin"), Q(lp.number),
                         [A("uuid"), Q(det_uuid("pin", self.project, comp.ref, lp.number))]])

        # THE critical block. Without it references render as "?" and F8 aborts.
        node.append([A("instances"),
                     [A("project"), Q(self.project),
                      [A("path"), Q(f"/{self.root_uuid}"),
                       [A("reference"), Q(comp.ref)],
                       [A("unit"), A(comp.unit)]]]])
        return node

# --------------------------------------------------------------------------------------
# Optional .kicad_pro emission (so the project opens and F8 is enabled immediately)
# --------------------------------------------------------------------------------------

def write_project_file(path: str, project: str, root_uuid: str) -> None:
    """Write a minimal, valid .kicad_pro. KiCad backfills every omitted default."""
    doc = {
        "board": {"design_settings": {}, "layer_presets": [], "viewports": []},
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": os.path.basename(path), "version": 1},
        "net_settings": {
            "classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25,
                         "via_diameter": 0.6, "via_drill": 0.3,
                         "microvia_diameter": 0.3, "microvia_drill": 0.1,
                         "diff_pair_gap": 0.25, "diff_pair_width": 0.2,
                         "wire_width": 6, "bus_width": 12,
                         "schematic_color": "rgba(0, 0, 0, 0.000)",
                         "pcb_color": "rgba(0, 0, 0, 0.000)"}],
            "meta": {"version": 3},
            "net_colors": None,
        },
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[root_uuid, "Root"]],
        "text_variables": {},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

# --------------------------------------------------------------------------------------
# Example blueprint (also serves as the schema documentation)
# --------------------------------------------------------------------------------------

EXAMPLE = """\
# circuit_blueprint.yaml -- abIDE logical blueprint schema
project: blinky

components:
  U1:
    symbol: easyeda2kicad:ATTINY85-20SU      # 'nick:Name' or bare 'Name'
    value: ATtiny85
    footprint: Package_SO:SOIC-8_3.9x4.9mm_P1.27mm
  R1:
    symbol: R
    value: 330R
    footprint: Resistor_SMD:R_0603_1608Metric
  D1:
    symbol: LED
    value: RED
    footprint: LED_SMD:LED_0603_1608Metric
  C1:
    symbol: C
    value: 100nF
    footprint: Capacitor_SMD:C_0603_1608Metric
    at: [180, 90]                            # optional manual placement (mm)

nets:
  VCC:  [U1.8, C1.1]                         # 'U1.8', 'U1:8', ['U1','8'] all work
  GND:  [U1.4, C1.2, R1.2]
  LED_A:
    connections: [U1.3, D1.1]
  LED_K: [D1.2, R1.1]

# Alternative list form is also accepted:
# nets:
#   - name: GND
#     power: true
#     connections:
#       - {ref: U1, pin: 4}
"""

# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="blueprint_to_sch.py",
        description="Convert an abIDE circuit blueprint (YAML/JSON) into a native "
                    "KiCad schematic (.kicad_sch) ready for Update PCB from Schematic.")
    ap.add_argument("blueprint", nargs="?", help="circuit_blueprint.yaml or .json")
    ap.add_argument("--lib", action="append", default=[], metavar="PATH",
                    help="A .kicad_sym library. Repeatable; earlier wins on name clash.")
    ap.add_argument("--lib-nick", action="append", default=[], metavar="NICK",
                    help="Nickname for the corresponding --lib (default: file stem).")
    ap.add_argument("-o", "--out", help="Output .kicad_sch path "
                                        "(default: <project>.kicad_sch)")
    ap.add_argument("--project-name", help="Override project name (drives instance paths).")
    ap.add_argument("--paper", choices=[p[0] for p in PAPERS], help="Force a paper size.")
    ap.add_argument("--columns", type=int, help="Force placement grid column count.")
    ap.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                    help=f"Gap between symbols in mm (default {DEFAULT_MARGIN}).")
    ap.add_argument("--format-version", default=SCH_FORMAT_VERSION,
                    help="KiCad sexp format stamp (default %(default)s).")
    ap.add_argument("--nc-unused", action="store_true",
                    help="Emit no-connect flags on pins absent from the netlist.")
    ap.add_argument("--emit-project", action="store_true",
                    help="Also write a minimal .kicad_pro next to the schematic.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero (1) on any warning; nothing is written.")
    ap.add_argument("--example", action="store_true",
                    help="Print an annotated example blueprint and exit.")
    args = ap.parse_args(argv)

    if args.example:
        sys.stdout.write(EXAMPLE)
        return 0
    if not args.blueprint:
        ap.error("blueprint path is required (or use --example)")

    # ---- load inputs -------------------------------------------------------------------
    try:
        data = load_blueprint(args.blueprint)
    except Exception as exc:
        print(f"FATAL: cannot read blueprint: {exc}", file=sys.stderr)
        return 1

    lib = SymbolLibrary()
    for i, path in enumerate(args.lib):
        nick = args.lib_nick[i] if i < len(args.lib_nick) else None
        try:
            lib.load(path, nick)
        except FileNotFoundError:
            print(f"FATAL: symbol library not found: {path}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"FATAL: cannot parse '{path}': {exc}", file=sys.stderr)
            return 1
    if not args.lib:
        print("WARN: no --lib supplied; every component will become a placeholder.",
              file=sys.stderr)

    project = (args.project_name or str(data.get("project") or data.get("name") or "")
               or (os.path.splitext(os.path.basename(args.out))[0] if args.out else "")
               or os.path.splitext(os.path.basename(args.blueprint))[0])
    project = re.sub(r"[^\w\-]+", "_", project).strip("_") or "abide_project"

    collected: List[str] = []
    comps = parse_components(data)
    nets = parse_nets(data, collected.append)
    if not comps:
        print("FATAL: blueprint declares no components.", file=sys.stderr)
        return 1

    # ---- build -------------------------------------------------------------------------
    builder = SchematicBuilder(
        project, lib,
        margin=args.margin, columns=args.columns, paper=args.paper,
        fmt_version=args.format_version, nc_unused=args.nc_unused,
        title=str(data.get("title") or project),
        company=str(data.get("company") or ""),
        rev=str(data.get("rev") or data.get("revision") or ""),
    )
    builder.warnings.extend(collected)
    try:
        text = builder.build(comps, nets)
    except Exception as exc:
        print(f"FATAL: schematic generation failed: {exc}", file=sys.stderr)
        return 1

    for w in builder.warnings:
        print(f"WARN: {w}", file=sys.stderr)
    if args.strict and builder.warnings:
        print("FATAL: --strict set and warnings were raised; nothing written.",
              file=sys.stderr)
        return 1

    out = args.out or f"{project}.kicad_sch"
    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)

    # Self-check: re-parse our own output. A file KiCad cannot read is worse than none.
    try:
        parse_sexp(text)
    except Exception as exc:
        print(f"FATAL: generated file failed self-validation: {exc}", file=sys.stderr)
        return 1

    if args.emit_project:
        pro = os.path.splitext(out)[0] + ".kicad_pro"
        write_project_file(pro, project, builder.root_uuid)
        print(f"Wrote {pro}", file=sys.stderr)

    placeholders = sum(1 for c in comps if c.is_placeholder)
    print(f"Wrote {out}  --  {len(comps)} symbols, {len(nets)} nets, "
          f"{placeholders} placeholder(s), paper "
          f"{builder.pick_paper(*builder.place(comps))}", file=sys.stderr)

    return 2 if builder.warnings else 0

if __name__ == "__main__":
    sys.exit(main())
