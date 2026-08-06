"""
abide/klib.py -- real KiCad library resolution.

Nickname -> file, in exactly KiCad's order:
  1. <PROJECT_DIR>/sym-lib-table         (project table, ${KIPRJMOD} aware)
  2. <kicad_config_dir>/sym-lib-table    (global table)
  3. <kicad_symbol_dir>/<nick>.kicad_sym (stock fallback, no table needed)
  4. <PROJECT_DIR>/libs/<nick>.kicad_sym (legacy abIDE fallback)
Same four steps for footprints via fp-lib-table and <nick>.pretty.

One parse per library file per run; symbols are cached by lib_id.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .paths import env_dirs, load_paths
from .sexpr import Quoted, find, first, head, parse, value, walk

class LibError(ValueError):
    """Anything wrong with a library, a symbol or a footprint reference."""

# A pin's (at ...) angle points TOWARD the body. Symbol Y is up, schematic Y
# is down, so the schematic offset is (x, -y) and 'away' is the reverse of the
# body direction. This is your existing pin_geometry(), kept verbatim: it is
# correct and every downstream coordinate depends on it.
_BODY = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}
_ART = ("rectangle", "circle", "arc", "polyline", "bezier", "text")
_VAR = re.compile(r"\$[{(]([A-Za-z0-9_]+)[})]")

@dataclass
class Pin:
    number: str
    name: str
    etype: str
    offset: Tuple[float, float]   # connection point, relative to symbol origin
    away: Tuple[float, float]     # unit vector pointing away from the body
    length: float = 2.54

@dataclass
class SymbolDef:
    lib_id: str
    lib: str
    name: str
    node: list
    parent: Optional[list]
    pins: Dict[str, Pin]
    bbox: Tuple[float, float, float, float]   # left, top, right, bottom

    @property
    def is_power(self):
        return self.lib == "power" or first(self.node, "power") is not None

def _expand(uri, subst):
    def sub(match):
        key = match.group(1)
        if key not in subst:
            raise LibError(f"library table uses ${{{key}}}, which is not set")
        return str(subst[key])
    return _VAR.sub(sub, str(uri))

def _read_table(path, subst, skipped):
    """{nickname: Path} from a sym-lib-table or fp-lib-table."""
    out = {}
    if path is None or not path.is_file():
        return out
    try:
        root = parse(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError as e:
        raise LibError(f"{path} is not a valid library table ({e})")
    for lib in find(root, "lib"):
        nick = value(lib, "name")
        uri = value(lib, "uri")
        off = str(value(lib, "disabled", "")).lower() in ("true", "yes", "1")
        if not nick or not uri or off:
            continue
        try:
            out[str(nick)] = Path(_expand(uri, subst))
        except LibError as e:
            # One unexpandable row (a stale KICAD7_* path) must not break the
            # other 200 rows. Remember it for the error message instead.
            skipped.append(f"{nick} ({e})")
    return out

def _collect_pins(node):
    """{number: Pin}, including pins inside unit sub-symbols."""
    pins = {}
    if node is None:
        return pins
    for item in walk(node, "pin"):
        at = first(item, "at")
        number = value(item, "number")
        if at is None or len(at) < 3 or number is None:
            continue
        try:
            x, y = float(at[1]), float(at[2])
            angle = int(float(at[3])) % 360 if len(at) > 3 else 0
        except (TypeError, ValueError):
            continue
        body = _BODY.get(angle)
        if body is None:
            raise LibError(f"unsupported pin angle {angle} on pin {number}")
        try:
            length = float(value(item, "length", 2.54) or 2.54)
        except (TypeError, ValueError):
            length = 2.54
        etype = item[1] if len(item) > 1 and isinstance(item[1], str) else "passive"
        pins.setdefault(str(number), Pin(
            number=str(number),
            name=str(value(item, "name", "~")),
            etype=str(etype),
            offset=(x, -y),
            away=(-body[0], -body[1]),
            length=length))
    return pins

def _bbox(node):
    """(left, top, right, bottom) of the drawn symbol, in schematic coords."""
    if node is None:
        return None
    xs, ys = [], []

    def add(point):
        if point is not None and len(point) > 2:
            try:
                xs.append(float(point[1]))
                ys.append(float(point[2]))
            except (TypeError, ValueError):
                pass

    for item in walk(node):
        tag = item[0] if item and isinstance(item[0], str) else ""
        if tag == "circle":
            centre = first(item, "center")
            try:
                radius = float(value(item, "radius", 0) or 0)
            except (TypeError, ValueError):
                radius = 0.0
            if centre is not None and len(centre) > 2:
                cx, cy = float(centre[1]), float(centre[2])
                xs += [cx - radius, cx + radius]
                ys += [cy - radius, cy + radius]
        elif tag in _ART:
            for key in ("start", "mid", "end", "at"):
                add(first(item, key))
            for point in walk(item, "xy"):
                add(point)
        elif tag == "pin":
            add(first(item, "at"))
    if not xs:
        return None
    return (min(xs), -max(ys), max(xs), -min(ys))

def _closest(name, entries):
    near = difflib.get_close_matches(name, list(entries), n=3, cutoff=0.55)
    return ("\n  did you mean: " + ", ".join(near)) if near else ""

class LibIndex:
    """Every library question the compiler needs to ask, answered once."""

    def __init__(self, project_dir):
        self.project = Path(project_dir).resolve()
        self.cfg = load_paths("kicad_symbol_dir")
        self.subst = env_dirs(self.project)
        self.skipped: List[str] = []
        self.symbol_tables = self._tables("sym-lib-table")
        self.footprint_tables = self._tables("fp-lib-table")
        self._files: Dict[str, Dict[str, list]] = {}
        self._symbols: Dict[str, SymbolDef] = {}

    def _tables(self, name):
        """Global first, then project, so the project table wins on a clash."""
        merged = {}
        config_dir = self.cfg.get("kicad_config_dir")
        sources = [config_dir / name if config_dir else None, self.project / name]
        for path in sources:
            merged.update(_read_table(path, self.subst, self.skipped))
        return merged

    def _symbol_file(self, nick):
        stock = self.cfg.get("kicad_symbol_dir")
        tried = [self.symbol_tables.get(nick),
                 (stock / f"{nick}.kicad_sym") if stock else None,
                 self.project / "libs" / f"{nick}.kicad_sym"]
        for path in tried:
            if path is not None and path.is_file():
                return path
        known = ", ".join(sorted(self.symbol_tables)[:10]) or "none"
        note = f"\n  unusable table rows: {'; '.join(self.skipped)}" if self.skipped else ""
        raise LibError(
            f"symbol library '{nick}' not found.\n  tried: "
            + "\n         ".join(str(p) for p in tried if p is not None)
            + f"\n  nicknames in your lib tables: {known}" + note)

    def _entries(self, nick):
        if nick not in self._files:
            path = self._symbol_file(nick)
            root = parse(path.read_text(encoding="utf-8", errors="replace"))
            if not head(root, "kicad_symbol_lib"):
                raise LibError(f"{path} is not a kicad_symbol_lib file")
            self._files[nick] = {s[1]: s for s in find(root, "symbol")
                                 if len(s) > 1 and isinstance(s[1], str)}
        return self._files[nick]

    def symbol(self, lib_id):
        """SymbolDef for 'Library:Name'. Resolves extends, pins and geometry."""
        cached = self._symbols.get(lib_id)
        if cached is not None:
            return cached
        if str(lib_id).count(":") != 1:
            raise LibError(f"lib_id must be 'Library:Symbol', got '{lib_id}'")
        nick, name = str(lib_id).split(":")
        entries = self._entries(nick)
        node = entries.get(name)
        if node is None:
            raise LibError(f"symbol '{name}' is not in library '{nick}' "
                           f"({len(entries)} symbols present)"
                           f"{_closest(name, entries)}")
        parent_name = value(node, "extends")
        parent = entries.get(str(parent_name)) if parent_name else None
        if parent_name and parent is None:
            raise LibError(f"'{lib_id}' extends missing symbol '{parent_name}'")
        pins = _collect_pins(node) or _collect_pins(parent)
        if not pins:
            raise LibError(f"'{lib_id}' has no pins -- broken or wrong symbol")
        box = _bbox(node) or _bbox(parent) or (-2.54, -2.54, 2.54, 2.54)
        sym = SymbolDef(lib_id=str(lib_id), lib=nick, name=name, node=node,
                        parent=parent, pins=pins, bbox=box)
        self._symbols[lib_id] = sym
        return sym

    def embed(self, sym):
        """One lib_symbols entry: derived symbols flattened, keyed 'lib:name'."""
        base = sym.parent if sym.parent is not None else sym.node
        parent_name = sym.parent[1] if sym.parent is not None else sym.name
        children = []
        for child in base[2:]:
            if head(child, "extends") or head(child, "property"):
                continue
            if head(child, "symbol") and len(child) > 1 and isinstance(child[1], str):
                child = list(child)
                child[1] = Quoted(str(child[1]).replace(str(parent_name), sym.name, 1))
            children.append(child)
        props = [c for c in sym.node[2:] if head(c, "property")]
        if sym.parent is not None:
            defined = {p[1] for p in props if len(p) > 1}
            props += [c for c in sym.parent[2:]
                      if head(c, "property") and len(c) > 1 and c[1] not in defined]
        return ["symbol", Quoted(f"{sym.lib}:{sym.name}"), *props, *children]

    def _footprint_dir(self, nick):
        stock = self.cfg.get("kicad_footprint_dir")
        for folder in (self.footprint_tables.get(nick),
                       (stock / f"{nick}.pretty") if stock else None,
                       self.project / "libs" / f"{nick}.pretty"):
            if folder is not None and folder.is_dir():
                return folder
        return None

    def footprint_problem(self, fpid, ref=""):
        """None if the .kicad_mod exists, else a message. Missing footprints
        are the silent killer: Update PCB from Schematic just skips them."""
        label = f"{ref}: " if ref else ""
        if not fpid:
            return f"{label}Footprint is empty -- Update PCB will skip this part"
        if str(fpid).count(":") != 1:
            return f"{label}footprint '{fpid}' must be 'Library:Name'"
        nick, name = str(fpid).split(":")
        folder = self._footprint_dir(nick)
        if folder is None:
            legacy = self.project / "libs"
            return (f"{label}footprint library '{nick}' is not reachable: no "
                    f"fp-lib-table row, no {nick}.pretty in the stock folder "
                    f"and none in {legacy}")
        if not (folder / f"{name}.kicad_mod").is_file():
            return f"{label}{name}.kicad_mod not found in {folder}"
        return None

    def summary(self):
        return (f"{len(self.symbol_tables)} symbol nicknames, "
                f"{len(self.footprint_tables)} footprint nicknames, "
                f"{len(self._files)} library file(s) read")
