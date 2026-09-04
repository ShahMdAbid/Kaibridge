"""
kaibridge/model.py -- design.json in, a validated Design out.

Accepts your current schema 2 (no 'sheets' key) and schema 3-lite. A schema 2
file is upgraded in memory to one implicit root sheet, so old designs keep
compiling to a single .kicad_sch exactly as they do today.

Everything the renderer needs is decided here: group and sheet membership,
label kind, synthesized power flags and decoupling caps, and every error
message a human can act on. No geometry, no s-expressions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

class DesignError(ValueError):
    """A problem in design.json that a human has to fix."""

class LibError(ValueError):
    """Anything wrong with a library, a symbol or a footprint reference."""

RAIL_NAMES = {"GND", "GNDA", "GNDD", "AGND", "DGND", "PGND", "VBUS", "VIN",
              "VSS", "VDD", "VCC", "VEE", "VDDA", "VCCA", "VREF"}
RAIL_PREFIX = ("+", "-V", "VCC", "VDD", "VSS", "VBUS")
FLAG_GROUP = "_flags"
_REF = re.compile(r"^(#?[A-Za-z_]+)(\d+)$")
_NUM = re.compile(r"(\d+)")

@dataclass
class Part:
    ref: str
    lib_id: str
    value: str = ""
    footprint: str = ""
    group: str = ""
    sheet: str = ""
    near: str = ""
    fields: Dict[str, str] = field(default_factory=dict)
    dnp: bool = False
    in_bom: bool = True
    on_board: bool = True
    synthetic: bool = False
    symbol: Optional[SymbolDef] = None
    x: float = 0.0            # filled in by place.py
    y: float = 0.0

    @property
    def hidden(self):
        """'#' refs (power flags) draw no Reference and no Value."""
        return self.ref.startswith("#")

@dataclass
class Conn:
    ref: str
    pin: str

@dataclass
class Net:
    name: str
    netclass: str = "Default"
    style: str = "auto"       # auto | local | global | hierarchical
    rail: bool = False
    conns: List[Conn] = field(default_factory=list)
    sheets: List[str] = field(default_factory=list)

@dataclass
class Group:
    id: str
    title: str
    sheet: str = ""
    refs: List[str] = field(default_factory=list)

@dataclass
class Sheet:
    id: str
    title: str
    root: bool = False
    groups: List[str] = field(default_factory=list)
    paper: str = "A4"         # filled in by place.py
    width: float = 297.0
    height: float = 210.0

@dataclass
class Design:
    design_id: str
    meta: dict
    board: dict
    netclasses: dict
    checks: dict
    parts: Dict[str, Part]
    nets: Dict[str, Net]
    groups: List[Group]
    sheets: List[Sheet]
    no_connect: List[Conn] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def hierarchical(self):
        return len(self.sheets) > 1

    @property
    def root(self):
        return self.sheets[0]

    def sheet_groups(self, sheet_id):
        return [g for g in self.groups if g.sheet == sheet_id and g.refs]

    def sheet_parts(self, sheet_id):
        return [self.parts[r] for g in self.sheet_groups(sheet_id) for r in g.refs]

def _text(value, default=""):
    return default if value is None else str(value).strip()

def _flag(spec, key, default=True):
    value = spec.get(key, default)
    if isinstance(value, bool):
        return value
    return _text(value).lower() in ("true", "yes", "1")

def _natural(text):
    return [int(p) if p.isdigit() else p for p in _NUM.split(str(text))]

def _next_index(parts, prefix):
    """C7 exists -> the next synthesized cap is C8. Never reuses a reference."""
    highest = 0
    for ref in parts:
        match = _REF.match(ref)
        if match and match.group(1) == prefix:
            highest = max(highest, int(match.group(2)))
    return highest + 1

def _split_pin(token, where):
    text = _text(token)
    if "." not in text:
        raise DesignError(f"{where}: '{text}' must be REF.PIN, e.g. U1.3 or U1.VDD")
    ref, pin = text.split(".", 1)
    return ref.strip(), pin.strip()

def resolve_pin(part, token, where):
    """Accept a pin number or a pin name, always return the pin number."""
    pins = part.symbol.pins
    if token in pins:
        return token
    hits = [n for n, p in pins.items() if p.name == token]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise DesignError(
            f"{where}: pin name '{token}' is ambiguous on {part.ref} "
            f"(pins {', '.join(sorted(hits, key=_natural))}) -- use the number")
    known = ", ".join(sorted(pins, key=_natural)[:14])
    more = " ..." if len(pins) > 14 else ""
    raise DesignError(f"{where}: {part.ref} ({part.lib_id}) has no pin '{token}'. "
                      f"Pins: {known}{more}")

def _read_parts(raw, lib):
    parts: Dict[str, Part] = {}
    specs = raw.get("parts") or {}
    if not specs and "components" in raw and isinstance(raw["components"], list):
        specs = {c["ref"]: c for c in raw["components"] if isinstance(c, dict) and c.get("ref")}
    if not isinstance(specs, dict) or not specs:
        raise DesignError("design.json needs a non-empty 'parts' object or 'components' list")
    for ref, spec in specs.items():
        ref = str(ref)
        if not isinstance(spec, dict):
            raise DesignError(f"parts.{ref} must be an object")
        lib_id = _text(spec.get("lib_id") or spec.get("symbol"))
        if not lib_id:
            raise DesignError(f"parts.{ref}: 'lib_id' (or 'symbol') is required, e.g. Device:R")
        try:
            symbol = lib.symbol(lib_id)
        except LibError as e:
            raise DesignError(f"parts.{ref}: {e}")
        parts[ref] = Part(
            ref=ref,
            lib_id=lib_id,
            value=_text(spec.get("value") or spec.get("val")) or ref,
            footprint=_text(spec.get("footprint") or spec.get("fp") or spec.get("package")),
            group=_text(spec.get("group")),
            near=_text(spec.get("near")),
            fields={str(k): _text(v) for k, v in (spec.get("fields") or {}).items()},
            dnp=_flag(spec, "dnp", False),
            in_bom=_flag(spec, "in_bom", True),
            on_board=_flag(spec, "on_board", True),
            symbol=symbol)
    return parts

def _read_groups(raw, parts):
    """Declared groups first, then parts that named an undeclared group,
    then everything left over into 'misc'. Every part ends up in exactly one."""
    groups: List[Group] = []
    by_id: Dict[str, Group] = {}
    for spec in raw.get("groups") or []:
        gid = _text(spec.get("id"))
        if not gid:
            raise DesignError("every entry in 'groups' needs an 'id'")
        if gid in by_id:
            raise DesignError(f"duplicate group id '{gid}'")
        group = Group(id=gid, title=_text(spec.get("title")) or gid,
                      sheet=_text(spec.get("sheet")))
        by_id[gid] = group
        groups.append(group)
        for ref in spec.get("parts") or []:
            ref = _text(ref)
            if ref not in parts:
                raise DesignError(f"group '{gid}' lists unknown part '{ref}'")
            owner = parts[ref].group
            if owner and owner != gid:
                raise DesignError(f"{ref} says group '{owner}' but group '{gid}' "
                                  f"also lists it -- pick one")
            parts[ref].group = gid
            if ref not in group.refs:
                group.refs.append(ref)
    for ref, part in parts.items():
        if not part.group:
            continue
        group = by_id.get(part.group)
        if group is None:
            group = Group(id=part.group, title=part.group)
            by_id[group.id] = group
            groups.append(group)
        if ref not in group.refs:
            group.refs.append(ref)
    loose = [ref for ref, part in parts.items() if not part.group]
    if loose:
        group = by_id.get("misc")
        if group is None:
            group = Group(id="misc", title="Ungrouped")
            by_id[group.id] = group
            groups.append(group)
        for ref in loose:
            parts[ref].group = group.id
            group.refs.append(ref)
    return groups, by_id

def _read_sheets(raw, groups, by_id):
    """No 'sheets' key -> one implicit root sheet -> today's single file."""
    title = _text((raw.get("meta") or {}).get("title")) or "Root"
    root = Sheet(id="root", title=title, root=True)
    specs = raw.get("sheets") or []
    if not specs:
        for group in groups:
            if group.sheet and group.sheet != "root":
                raise DesignError(
                    f"group '{group.id}' names sheet '{group.sheet}' but the "
                    f"design declares no 'sheets'")
            group.sheet = "root"
        root.groups = [g.id for g in groups]
        return [root]
    sheets = [root]
    seen = {"root": root}
    for spec in specs:
        sid = _text(spec.get("id"))
        if not sid:
            raise DesignError("every entry in 'sheets' needs an 'id'")
        if sid == "root":
            raise DesignError("'root' is reserved: the root sheet is implicit")
        if sid in seen:
            raise DesignError(f"duplicate sheet id '{sid}'")
        sheet = Sheet(id=sid, title=_text(spec.get("title")) or sid)
        seen[sid] = sheet
        sheets.append(sheet)
        for gid in spec.get("groups") or []:
            gid = _text(gid)
            group = by_id.get(gid)
            if group is None:
                raise DesignError(f"sheet '{sid}' lists unknown group '{gid}'")
            if group.sheet and group.sheet != sid:
                raise DesignError(f"group '{gid}' is claimed by sheet "
                                  f"'{group.sheet}' and by sheet '{sid}'")
            group.sheet = sid
    for group in groups:
        if not group.sheet:
            group.sheet = "root"
        if group.sheet not in seen:
            raise DesignError(f"group '{group.id}' names sheet '{group.sheet}', "
                              f"which is not declared in 'sheets'")
    for sheet in sheets:
        sheet.groups = [g.id for g in groups if g.sheet == sheet.id]
    return sheets

def _read_nets(raw, parts):
    nets: Dict[str, Net] = {}
    specs = raw.get("nets") or {}
    if not isinstance(specs, dict):
        raise DesignError("'nets' must be an object of name -> net")
    for name, spec in specs.items():
        name = _text(name)
        if not name:
            raise DesignError("a net has an empty name")
        if isinstance(spec, list):          # shorthand: "GND": ["U1.1", "C1.2"]
            spec = {"connections": spec}
        if not isinstance(spec, dict):
            raise DesignError(f"nets.{name} must be an object or a list")
        style = _text(spec.get("style")) or "auto"
        if style not in ("auto", "local", "global", "hierarchical"):
            raise DesignError(f"nets.{name}: style must be auto, local, "
                              f"global or hierarchical")
        net = Net(name=name, netclass=_text(spec.get("class")) or "Default", style=style)
        seen = set()
        for token in spec.get("connections") or []:
            ref, pin = _split_pin(token, f"nets.{name}")
            part = parts.get(ref)
            if part is None:
                raise DesignError(f"nets.{name}: unknown part '{ref}' in '{token}'")
            number = resolve_pin(part, pin, f"nets.{name}")
            if (ref, number) in seen:
                continue
            seen.add((ref, number))
            net.conns.append(Conn(ref, number))
        nets[name] = net
    return nets

def _decouple(raw, parts, nets, by_id, lib, warnings):
    """Synthesize the caps. The rail must already exist -- we never guess it."""
    entries = raw.get("decoupling") or []
    if not entries:
        return
    owner = {}
    for net in nets.values():
        for conn in net.conns:
            owner[(conn.ref, conn.pin)] = net.name
    index = _next_index(parts, "C")
    for spec in entries:
        ic = _text(spec.get("ic"))
        where = f"decoupling for '{ic}'"
        part = parts.get(ic)
        if part is None:
            raise DesignError(f"{where}: unknown part")
        gnd = _text(spec.get("gnd")) or "GND"
        if gnd not in nets:
            raise DesignError(f"{where}: ground net '{gnd}' is not declared in 'nets'")
        lib_id = _text(spec.get("lib_id")) or "Device:C"
        try:
            symbol = lib.symbol(lib_id)
        except LibError as e:
            raise DesignError(f"{where}: {e}")
        for needed in ("1", "2"):
            if needed not in symbol.pins:
                raise DesignError(f"{where}: '{lib_id}' has no pin {needed} -- a "
                                  f"decoupling symbol must be a plain 2-pin part")
        wanted = spec.get("pins")
        if wanted:
            numbers = [resolve_pin(part, _text(p), where) for p in wanted]
        else:
            numbers = [n for n, p in part.symbol.pins.items()
                       if p.etype == "power_in" and (ic, n) in owner]
            if not numbers:
                warnings.append(f"{where}: no power_in pin of {ic} is on a net, "
                                f"nothing generated")
                continue
        value = _text(spec.get("value")) or "100nF"
        footprint = _text(spec.get("footprint"))
        for number in sorted(set(numbers), key=_natural):
            rail = owner.get((ic, number))
            if rail is None:
                raise DesignError(f"{where}: pin {number} is not on any net. "
                                  f"Declare the rail in 'nets' first.")
            if rail == gnd:
                continue
            ref = f"C{index}"
            index += 1
            parts[ref] = Part(ref=ref, lib_id=lib_id, value=value,
                              footprint=footprint, group=part.group,
                              sheet=part.sheet, near=f"{ic}.{number}",
                              synthetic=True, symbol=symbol)
            by_id[part.group].refs.append(ref)
            nets[rail].conns.append(Conn(ref, "1"))
            nets[gnd].conns.append(Conn(ref, "2"))

def _flags(raw, parts, nets, groups, by_id, sheets, lib):
    """One PWR_FLAG per declared rail, all of them on the root sheet."""
    names = [n for n in (_text(x) for x in (raw.get("power_flags") or [])) if n]
    if not names:
        return
    try:
        symbol = lib.symbol("power:PWR_FLAG")
    except LibError as e:
        raise DesignError(f"power_flags: {e}")
    group = by_id.get(FLAG_GROUP)
    if group is None:
        group = Group(id=FLAG_GROUP, title="Power flags", sheet="root")
        by_id[FLAG_GROUP] = group
        groups.append(group)
        sheets[0].groups.append(FLAG_GROUP)
    index = 1
    for name in names:
        net = nets.get(name)
        if net is None:
            raise DesignError(f"power_flags lists '{name}', which is not in 'nets'")
        ref = f"#FLG{index:02d}"
        while ref in parts:
            index += 1
            ref = f"#FLG{index:02d}"
        index += 1
        parts[ref] = Part(ref=ref, lib_id="power:PWR_FLAG", value="PWR_FLAG",
                          group=FLAG_GROUP, sheet="root", synthetic=True,
                          in_bom=False, on_board=False, symbol=symbol)
        group.refs.append(ref)
        net.conns.append(Conn(ref, "1"))

def _is_rail(name, declared):
    if name in declared or name in RAIL_NAMES:
        return True
    return name.upper().startswith(RAIL_PREFIX)

def _styles(design, declared):
    """Decide every label kind exactly once, here."""
    for net in design.nets.values():
        seen = []
        for conn in net.conns:
            sheet = design.parts[conn.ref].sheet
            if sheet not in seen:
                seen.append(sheet)
        net.sheets = seen
        net.rail = _is_rail(net.name, declared)
        if net.style == "auto":
            if net.rail:
                net.style = "global"
            elif len(seen) > 1:
                net.style = "hierarchical"
            else:
                net.style = "local"
        elif net.style == "hierarchical" and not design.hierarchical:
            net.style = "local"
            design.warnings.append(
                f"net '{net.name}': hierarchical downgraded to local, the "
                f"design has only one sheet")
        if len(seen) > 1 and net.style == "local":
            net.style = "global"
            design.warnings.append(
                f"net '{net.name}' touches {len(seen)} sheets: promoted to a "
                f"global label so the netlist stays correct")
        if net.style == "hierarchical" and design.root.id in seen:
            net.style = "global"
            design.warnings.append(
                f"net '{net.name}' also lives on the root sheet: promoted to "
                f"a global label (a hierarchical label only works inside a "
                f"sub-sheet)")

def _validate(design, lib):
    checks = design.checks
    known = set(design.netclasses) | {"Default"}
    for net in design.nets.values():
        if net.netclass not in known:
            raise DesignError(
                f"net '{net.name}' uses netclass '{net.netclass}', which is "
                f"not declared in 'netclasses' ({', '.join(sorted(known))})")
    owner = {}
    for net in design.nets.values():
        if len(net.conns) < 2 and not _flag(checks, "allow_single_pin_nets", False):
            raise DesignError(
                f"net '{net.name}' has {len(net.conns)} connection(s). Fix it, or "
                f"set checks.allow_single_pin_nets to true.")
        for conn in net.conns:
            key = (conn.ref, conn.pin)
            if key in owner and owner[key] != net.name:
                raise DesignError(f"{conn.ref}.{conn.pin} is on two nets: "
                                  f"'{owner[key]}' and '{net.name}'")
            owner[key] = net.name
    for conn in design.no_connect:
        key = (conn.ref, conn.pin)
        if key in owner:
            raise DesignError(f"no_connect lists {conn.ref}.{conn.pin}, but it is "
                              f"on net '{owner[key]}'")
    mode = _text(checks.get("unused_pins"), "warn") or "warn"
    if mode not in ("ignore", "warn", "error"):
        raise DesignError("checks.unused_pins must be ignore, warn or error")
    if mode != "ignore":
        nc = {(c.ref, c.pin) for c in design.no_connect}
        for ref in sorted(design.parts):
            part = design.parts[ref]
            if part.synthetic:
                continue
            loose = [n for n in part.symbol.pins
                     if (ref, n) not in owner and (ref, n) not in nc]
            if not loose:
                continue
            listed = ", ".join(sorted(loose, key=_natural)[:10])
            more = " ..." if len(loose) > 10 else ""
            message = f"{ref} ({part.lib_id}): {len(loose)} unconnected pin(s): {listed}{more}"
            if mode == "error":
                raise DesignError(message + ". Add them to 'nets' or to 'no_connect'.")
            design.warnings.append(message)
    if _flag(checks, "require_footprints", True):
        problems = []
        for ref in sorted(design.parts):
            part = design.parts[ref]
            if part.hidden or not part.on_board:
                continue
            problem = lib.footprint_problem(part.footprint, ref, part.symbol)
            if problem:
                problems.append(problem)
        if problems:
            raise DesignError("footprint problems:\n  - " + "\n  - ".join(problems))
    for ref in sorted(design.parts):
        part = design.parts[ref]
        if not part.near:
            continue
        anchor_ref, pin = _split_pin(part.near, f"parts.{ref}.near")
        if anchor_ref == ref:
            raise DesignError(f"parts.{ref}.near points at itself")
        anchor = design.parts.get(anchor_ref)
        if anchor is None:
            raise DesignError(f"parts.{ref}.near names unknown part '{anchor_ref}'")
        if anchor.sheet != part.sheet:
            raise DesignError(f"parts.{ref}.near points at {anchor_ref} on sheet "
                              f"'{anchor.sheet}', but {ref} is on '{part.sheet}'")
        part.near = anchor_ref + "." + resolve_pin(anchor, pin, f"parts.{ref}.near")

def load(raw, lib):
    """The only entry point. Raises DesignError with a fixable message."""
    if not isinstance(raw, dict):
        raise DesignError("design.json must be a JSON object")
    try:
        schema = int(raw.get("schema", 2))
    except (TypeError, ValueError):
        raise DesignError("'schema' must be a number (2 or 3)")
    if schema not in (2, 3):
        raise DesignError(f"unsupported schema {schema}: this compiler reads 2 and 3")
    meta = dict(raw.get("meta") or {})
    design_id = _text(meta.get("design_id")) or _text(meta.get("title")) or "kaibridge"
    parts = _read_parts(raw, lib)
    groups, by_id = _read_groups(raw, parts)
    sheets = _read_sheets(raw, groups, by_id)
    for group in groups:
        for ref in group.refs:
            parts[ref].sheet = group.sheet
    nets = _read_nets(raw, parts)
    warnings: List[str] = []
    _decouple(raw, parts, nets, by_id, lib, warnings)
    _flags(raw, parts, nets, groups, by_id, sheets, lib)
    no_connect = []
    for token in raw.get("no_connect") or []:
        ref, pin = _split_pin(token, "no_connect")
        part = parts.get(ref)
        if part is None:
            raise DesignError(f"no_connect: unknown part '{ref}' in '{token}'")
        no_connect.append(Conn(ref, resolve_pin(part, pin, "no_connect")))
    design = Design(design_id=design_id,
                    meta=meta,
                    board=dict(raw.get("board") or {}),
                    netclasses=dict(raw.get("netclasses") or {}),
                    checks=dict(raw.get("checks") or {}),
                    parts=parts,
                    nets=nets,
                    groups=groups,
                    sheets=sheets,
                    no_connect=no_connect,
                    warnings=warnings)
    _styles(design, {_text(n) for n in (raw.get("power_flags") or [])})
    _validate(design, lib)
    return design

def sidecar(design):
    """kaibridge_build.json -- the resolved design metadata sidecar."""
    return {
        "schema": 3,
        "generated_by": "kaibridge",
        "design_id": design.design_id,
        "sheets": [
            {"id": s.id, "title": s.title, "paper": s.paper}
            for s in design.sheets
        ],
        "groups": [
            {"id": g.id, "title": g.title, "sheet": g.sheet,
             "parts": [r for r in g.refs if r in design.parts and design.parts[r].on_board and not design.parts[r].hidden]}
            for g in design.groups if any(design.parts[r].on_board and not design.parts[r].hidden for r in g.refs)
        ],
        "parts": {
            ref: {"lib_id": p.lib_id, "value": p.value, "footprint": p.footprint,
                  "group": p.group, "sheet": p.sheet, "dnp": p.dnp,
                  "synthetic": p.synthetic}
            for ref, p in design.parts.items() if p.on_board and not p.hidden
        },
        "nets": {
            name: [f"{c.ref}.{c.pin}" for c in net.conns]
            for name, net in design.nets.items()
        },
    }
