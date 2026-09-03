"""
kaibridge/render.py -- Design + Layout -> .kicad_sch text, one file per sheet.

The two rules:

  1. Every UUID is uuid5(design_id, kind, key). Regenerating a design that
     did not change produces byte-identical files, so 'Update PCB from
     Schematic' re-links footprints instead of deleting and re-adding them.
     This is what protects your placement and FreeRouting work.
  2. Every version-specific token is gated. One generator, KiCad 6 to 10.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .place import FONT, SHEET_PIN_PITCH, SHEET_PIN_TOP, STUB, stubs
from ..core.sexpr import Quoted, dumps, first, parse, value

GENERATOR = "kaibridge_json2sch"
GENERATOR_VERSION = "9.0"
VERSION = 20250114          # KiCad 9 schematic format
NS = uuid.NAMESPACE_URL

#Straight from your json2sch.py. The away vector is the direction the stub
#leaves the body in, so the text hangs off the far end of the stub.
JUSTIFY = {(1, 0): ["left", "bottom"], (-1, 0): ["right", "bottom"],
           (0, -1): ["left", "bottom"], (0, 1): ["right", "bottom"]}
LABEL_ANGLE = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}
LABEL_TAG = {"global": "global_label", "hierarchical": "hierarchical_label"}

def uid(design_id, kind, key):
    """The whole determinism story, in one line."""
    return str(uuid.uuid5(NS, f"kaibridge:{design_id}:{kind}:{key}"))

def _n(number):
    text = f"{float(number):.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text

def _yn(flag):
    return "yes" if flag else "no"

def _hide(version):
    """KiCad 7+ writes (hide yes); KiCad 6 writes a bare 'hide' atom."""
    return ["hide", "yes"] if version >= 20230000 else "hide"

def _effects(version, size=FONT, justify=None, hide=False, bold=False):
    font = ["font", ["size", _n(size), _n(size)]]
    if bold:
        font.append(["bold", "yes"] if version >= 20230000 else "bold")
    node = ["effects", font]
    if justify:
        node.append(["justify", *justify])
    if hide:
        node.append(_hide(version))
    return node

def _prop(version, name, text, x, y, hide=False, justify=None):
    return ["property", Quoted(name), Quoted(str(text)),
            ["at", _n(x), _n(y), "0"],
            _effects(version, justify=justify, hide=hide)]

def _wire(design, start, end, key):
    return ["wire",
            ["pts", ["xy", _n(start[0]), _n(start[1])],
             ["xy", _n(end[0]), _n(end[1])]],
            ["stroke", ["width", "0"], ["type", "default"]],
            ["uuid", Quoted(uid(design.design_id, "wire", key))]]

def _label(design, version, name, style, at, away, key):
    tag = LABEL_TAG.get(style, "label")
    node = [tag, Quoted(name)]
    if tag != "label":
        node.append(["shape", "bidirectional"])
    node.append(["at", _n(at[0]), _n(at[1]), _n(LABEL_ANGLE[away])])
    node.append(["fields_autoplaced", "yes"])
    node.append(_effects(version, justify=JUSTIFY[away]))
    node.append(["uuid", Quoted(uid(design.design_id, "label", key))])
    if tag == "global_label":
        node.append(["property", Quoted("Intersheetrefs"),
                     Quoted("${INTERSHEET_REFS}"),
                     ["at", _n(at[0]), _n(at[1]), "0"],
                     _effects(version, hide=True)])
    return node

def _symbol_props(design, version, part):
    """Reference above the body, Value below, everything else hidden."""
    above = part.y + part.symbol.bbox[1] - 1.27
    below = part.y + part.symbol.bbox[3] + 1.27
    fields = dict(part.fields)
    props = [
        _prop(version, "Reference", part.ref, part.x, above, hide=part.hidden),
        _prop(version, "Value", part.value, part.x, below, hide=part.hidden),
        _prop(version, "Footprint", part.footprint, part.x, part.y, hide=True),
        _prop(version, "Datasheet", fields.pop("Datasheet", "~"), part.x, part.y,
              hide=True),
        _prop(version, "Description", fields.pop("Description", ""), part.x,
              part.y, hide=True),
    ]
    for name in sorted(fields):
        props.append(_prop(version, name, fields[name], part.x, part.y, hide=True))
    return props

def _symbol(design, version, part, path, project):
    key = f"{path}:{part.ref}"
    node = ["symbol",
            ["lib_id", Quoted(part.lib_id)],
            ["at", _n(part.x), _n(part.y), "0"],
            ["unit", "1"]]
    if version >= 20231120:
        node.append(["exclude_from_sim", "no"])
    node += [["in_bom", _yn(part.in_bom)],
             ["on_board", _yn(part.on_board)],
             ["dnp", _yn(part.dnp)],
             ["fields_autoplaced", "yes"],
             ["uuid", Quoted(uid(design.design_id, "symbol", key))]]
    node += _symbol_props(design, version, part)
    for number in sorted(part.symbol.pins, key=lambda n: (len(n), n)):
        node.append(["pin", Quoted(number),
                     ["uuid", Quoted(uid(design.design_id, "pin",
                                         f"{key}:{number}"))]])
    node.append(["instances",
                 ["project", Quoted(project),
                  ["path", Quoted(path),
                   ["reference", Quoted(part.ref)], ["unit", "1"]]]])
    return node

def _stub_nodes(design, layout, version, part):
    """One wire and one label per connected pin. This is your model, kept."""
    out = []
    for number, pin, end, name, _length in stubs(part, layout.labels):
        style = layout.labels[(part.ref, number)][1]
        start = (part.x + pin.offset[0], part.y + pin.offset[1])
        finish = (part.x + end[0], part.y + end[1])
        key = f"{part.sheet}:{part.ref}.{number}"
        out.append(_wire(design, start, finish, key))
        out.append(_label(design, version, name, style, finish, pin.away, key))
    return out

def _frame_nodes(design, version, frame):
    """The dashed box and bold title your current output already draws."""
    rect = ["rectangle",
            ["start", _n(frame.x), _n(frame.y)],
            ["end", _n(frame.x + frame.w), _n(frame.y + frame.h)],
            ["stroke", ["width", "0.1"], ["type", "dash"]],
            ["fill", ["type", "none"]],
            ["uuid", Quoted(uid(design.design_id, "frame", frame.key))]]
    title = ["text", Quoted(frame.title)]
    if version >= 20231120:
        title.append(["exclude_from_sim", "no"])
    title += [["at", _n(frame.x + 1.27), _n(frame.y + 5.08), "0"],
              _effects(version, size=2.0, justify=["left", "bottom"], bold=True),
              ["uuid", Quoted(uid(design.design_id, "title", frame.key))]]
    return [rect, title]

def _sheet(design, layout, version, child, frame, page, project,
           root_uuid, block_uuid, filename):
    """A child-sheet box on the root page, with its pins down the left edge."""
    x = frame.x + frame.gutter
    node = ["sheet",
            ["at", _n(x), _n(frame.y)],
            ["size", _n(frame.w - frame.gutter), _n(frame.h)],
            ["fields_autoplaced", "yes"],
            ["stroke", ["width", "0.1524"], ["type", "solid"]],
            ["fill", ["color", "0", "0", "0", "0.0000"]],
            ["uuid", Quoted(block_uuid)],
            _prop(version, "Sheetname", child.title, x, frame.y - 1.27,
                  justify=["left", "bottom"]),
            _prop(version, "Sheetfile", filename, x, frame.y + frame.h + 1.27,
                  justify=["left", "top"])]
    py = frame.y + SHEET_PIN_TOP
    for name in layout.pins.get(child.id) or []:
        node.append(["pin", Quoted(name), "bidirectional",
                     ["at", _n(x), _n(py), "0"],
                     _effects(version, justify=["left"]),
                     ["uuid", Quoted(uid(design.design_id, "sheetpin",
                                         f"{child.id}:{name}"))]])
        py += SHEET_PIN_PITCH
    node.append(["instances",
                 ["project", Quoted(project),
                  ["path", Quoted("/" + root_uuid),
                   ["page", Quoted(str(page))]]]])
    return node

def _sheet_stubs(design, layout, version, child, frame):
    """On the root page, every sheet pin gets a short wire and a local label.
    That local label is what actually joins two sub-sheets together."""
    out = []
    x = frame.x + frame.gutter
    py = frame.y + SHEET_PIN_TOP
    for name in layout.pins.get(child.id) or []:
        key = f"sheetpin:{child.id}:{name}"
        out.append(_wire(design, (x - STUB, py), (x, py), key))
        out.append(_label(design, version, name, "local", (x - STUB, py),
                          (-1, 0), key))
        py += SHEET_PIN_PITCH
    return out

def _title_block(design, version, sheet):
    meta = design.meta
    title = str(meta.get("title") or design.design_id)
    if not sheet.root:
        title = title + " - " + sheet.title
    when = str(meta.get("date") or datetime.now().strftime("%Y-%m-%d"))
    node = ["title_block",
            ["title", Quoted(title)],
            ["date", Quoted(when)],
            ["rev", Quoted(str(meta.get("rev") or ""))],
            ["company", Quoted(str(meta.get("company") or ""))]]
    notes = str(meta.get("notes") or "").strip()
    if notes:
        node.append(["comment", "1", Quoted(notes[:120])])
    node.append(["comment", "2",
                 Quoted(f"generated by {GENERATOR} from design.json -- "
                        f"hand edits are overwritten")])
    return node

def _page(design, layout, lib, version, sheet, page, project, root_uuid,
          blocks, filenames):
    """One complete .kicad_sch tree."""
    parts = design.sheet_parts(sheet.id)
    path = "/" + root_uuid
    if not sheet.root:
        path = path + "/" + blocks[sheet.id]
    node = ["kicad_sch",
            ["version", str(version)],
            ["generator", Quoted(GENERATOR)]]
    if version >= 20231120:
        node.append(["generator_version", Quoted(GENERATOR_VERSION)])
    node.append(["uuid", Quoted(uid(design.design_id, "sheet", sheet.id))])
    node.append(["paper", Quoted(sheet.paper)])
    node.append(_title_block(design, version, sheet))

    # Only the symbols this page actually uses, so each file stands alone.
    used = {}
    for part in parts:
        used.setdefault(part.lib_id, part.symbol)
    node.append(["lib_symbols", *[lib.embed(used[k]) for k in sorted(used)]])

    graphics, wiring, symbols, children = [], [], [], []
    for frame in layout.frames.get(sheet.id) or []:
        if frame.kind == "group":
            graphics += _frame_nodes(design, version, frame)
            continue
        child = next(s for s in design.sheets if s.id == frame.key)
        wiring += _sheet_stubs(design, layout, version, child, frame)
        children.append(_sheet(design, layout, version, child, frame,
                               design.sheets.index(child) + 1, project,
                               root_uuid, blocks[child.id],
                               filenames[child.id]))
    for part in parts:
        wiring += _stub_nodes(design, layout, version, part)
        symbols.append(_symbol(design, version, part, path, project))
    for conn in design.no_connect:
        part = design.parts[conn.ref]
        if part.sheet != sheet.id:
            continue
        pin = part.symbol.pins[conn.pin]
        wiring.append(["no_connect",
                       ["at", _n(part.x + pin.offset[0]),
                        _n(part.y + pin.offset[1])],
                       ["uuid", Quoted(uid(design.design_id, "nc",
                                           f"{conn.ref}.{conn.pin}"))]])

    node += graphics + wiring + symbols + children
    if sheet.root:
        node.append(["sheet_instances",
                     ["path", Quoted("/"), ["page", Quoted(str(page))]]])
    if version >= 20241209:
        node.append(["embedded_fonts", "no"])
    return node

def build(design, layout, lib, project, root_stem, version=VERSION):
    """{filename: text}. The root file first, then one file per sub-sheet."""
    root_uuid = uid(design.design_id, "sheet", "root")
    blocks = {s.id: uid(design.design_id, "sheetblock", s.id)
              for s in design.sheets[1:]}
    filenames = {design.sheets[0].id: f"{root_stem}.kicad_sch"}
    for child in design.sheets[1:]:
        filenames[child.id] = f"{child.id}.kicad_sch"
    files = {}
    for page, sheet in enumerate(design.sheets, start=1):
        tree = _page(design, layout, lib, version, sheet, page, project,
                     root_uuid, blocks, filenames)
        files[filenames[sheet.id]] = dumps(tree, indent=1) + "\n"
    return files

def is_generated(path):
    """True when we wrote this file, so overwriting it is safe."""
    try:
        tree = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return False
    return str(value(tree, "generator", "")) == GENERATOR

def existing_uuid(path):
    """The uuid already inside a .kicad_sch, or ''.

    The CLI compares this with the new root uuid: if they differ, the
    design_id changed and KiCad is about to treat every footprint as new."""
    try:
        tree = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    node = first(tree, "uuid")
    return str(node[1]) if node is not None and len(node) > 1 else ""

def write(files, out_dir, backup=True):
    """Write every file. Returns ([(name, status)], [orphaned files]).

    Identical content is left alone so the mtime does not change and KiCad
    does not think the schematic moved under it."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []
    for name in sorted(files):
        text = files[name]
        parse(text)          # never leave a file we cannot read back
        path = out_dir / name
        status = "created"
        if path.exists():
            if path.read_text(encoding="utf-8", errors="replace") == text:
                results.append((name, "unchanged"))
                continue
            status = "updated" if is_generated(path) else "REPLACED a foreign file"
            if backup:
                shutil.copy2(path, path.with_name(f"{path.name}.{stamp}.bak"))
        path.write_text(text, encoding="utf-8")
        results.append((name, status))
    orphans = [p.name for p in sorted(out_dir.glob("*.kicad_sch"))
               if p.name not in files and is_generated(p)]
    return results, orphans
