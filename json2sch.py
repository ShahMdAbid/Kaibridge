#!/usr/bin/env python3
"""
json2sch.py -- compile design.json into a loadable, readable KiCad schematic.

    python json2sch.py "<PROJECT_DIR>" design.json --dry-run
    python json2sch.py "<PROJECT_DIR>" design.json --apply-netclasses

Layout rules that keep it readable and electrically safe:
  * every symbol is placed upright (0 deg) -- no rotation maths, no wrong pin coords
  * every used pin gets its own stub wire + net label; stub lengths fan out (7.62 /
    12.7 / 17.78 mm) so neighbouring labels never overlap
  * parts are packed using their real measured extent (body + stubs + label text)
  * label justification follows the stub direction, the way KiCad writes it
  * every footprint is checked to exist BEFORE the file is written, otherwise
    "Update PCB from Schematic" silently skips those parts
"""

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

from kicad_pins import Quoted, collect_pins, dumps, find, head, load_paths, parse

GRID = 1.27
STUB = 7.62            # base stub length
STUB_STEP = 5.08       # fan-out step
STUB_CYCLE = 3         # stagger repeats every 3 pins on the same side
PART_GAP_X = 12.7
PART_GAP_Y = 15.24
GROUP_PAD = 10.16
GROUP_GAP = 15.24
MARGIN = 12.7
PAPERS = [("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0),
          ("A1", 841.0, 594.0),  ("A0", 1189.0, 841.0)]
FONT = 1.27
CHAR_W = 0.85 * FONT
JUSTIFY = {(1, 0): ["left", "bottom"], (-1, 0): ["right", "bottom"],
           (0, -1): ["left", "bottom"], (0, 1): ["right", "bottom"]}
LABEL_ANGLE = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}

def q(value):
    return Quoted(str(value))

def fmt(value):
    if isinstance(value, str):
        return value
    if abs(value) < 1e-9:
        return "0"
    return f"{value:.4f}".rstrip("0").rstrip(".")

def snap(value):
    return round(round(value / GRID) * GRID, 4)

def uid():
    return q(str(uuid.uuid4()))

def at(x, y, angle=None):
    node = ["at", fmt(x), fmt(y)]
    if angle is not None:
        node.append(fmt(angle))
    return node

def effects(version, hide=False, size=FONT, justify=None):
    node = ["effects", ["font", ["size", fmt(size), fmt(size)]]]
    if justify:
        node.append(["justify", *justify])
    if hide:
        node.append(["hide", "yes"] if version >= 20230000 else "hide")
    return node

def prop(version, name, value, x, y, hide=False):
    return ["property", q(name), q(value), at(x, y, 0), effects(version, hide=hide)]

def text_width(text, style="label"):
    w = CHAR_W * len(str(text))
    return w + 2.54 if style == "global" else w

def fail(message):
    raise ValueError(message)

# ---------------- symbol libraries ----------------

class Libraries:
    def __init__(self, cfg, project_libs):
        self.cfg = cfg
        self.project_libs = project_libs
        self.cache = {}

    def _load(self, lib):
        if lib in self.cache:
            return self.cache[lib]
        stock = self.cfg.get("kicad_symbol_dir")
        for candidate in [self.project_libs / f"{lib}.kicad_sym",
                          (stock / f"{lib}.kicad_sym") if stock else None]:
            if candidate and candidate.is_file():
                root = parse(candidate.read_text(encoding="utf-8", errors="replace"))
                if not head(root, "kicad_symbol_lib"):
                    fail(f"{candidate} is not a symbol library")
                self.cache[lib] = {s[1]: s for s in find(root, "symbol") if len(s) > 1}
                return self.cache[lib]
        fail(f"symbol library '{lib}' not found in {self.project_libs} or kicad_symbol_dir")

    def get(self, lib_id):
        if lib_id.count(":") != 1:
            fail(f"lib_id must be 'Library:Symbol', got '{lib_id}'")
        lib, name = lib_id.split(":")
        entries = self._load(lib)
        if name not in entries:
            fail(f"symbol '{name}' not in library '{lib}' ({len(entries)} symbols present)")
        node = entries[name]
        parent_name = next((e[1] for e in find(node, "extends") if len(e) > 1), None)
        parent = entries.get(parent_name) if parent_name else None
        if parent_name and parent is None:
            fail(f"'{lib_id}' extends missing symbol '{parent_name}'")
        pins = {}
        collect_pins(node, pins)
        if not pins and parent is not None:
            collect_pins(parent, pins)
        if not pins:
            fail(f"'{lib_id}' has no pins -- broken or wrong symbol")
        return lib, name, node, parent, pins

    @staticmethod
    def embed(lib, name, node, parent):
        """Flatten a derived symbol, rename its unit children, key it as lib:name."""
        base = parent if parent is not None else node
        parent_name = parent[1] if parent is not None else name
        children = []
        for child in base[2:]:
            if head(child, "extends") or head(child, "property"):
                continue
            if head(child, "symbol") and len(child) > 1 and isinstance(child[1], str):
                child = list(child)
                # "LED_0_1" -> "<derived name>_0_1"  (KiCad matches units by this name)
                child[1] = q(str(child[1]).replace(parent_name, name, 1))
            children.append(child)
        props = [c for c in node[2:] if head(c, "property")]
        if parent is not None:
            defined = {p[1] for p in props if len(p) > 1}
            props += [c for c in parent[2:]
                      if head(c, "property") and len(c) > 1 and c[1] not in defined]
        return ["symbol", q(f"{lib}:{name}"), *props, *children]

def pin_nodes(node, parent):
    found = []

    def walk(current):
        for child in current:
            if head(child, "pin"):
                found.append(child)
            elif head(child, "symbol"):
                walk(child)

    walk(node)
    if not found and parent is not None:
        walk(parent)
    return found

def pin_geometry(pin_node):
    """-> ((dx, dy) offset in schematic coords, unit vector away from the body)."""
    node = next((c for c in pin_node if head(c, "at")), None)
    if node is None or len(node) < 3:
        fail("pin without an (at ...) position")
    x, y = float(node[1]), float(node[2])
    angle = int(float(node[3])) % 360 if len(node) > 3 else 0
    body = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}.get(angle)
    if body is None:
        fail(f"unsupported pin angle {angle}")
    return (x, -y), (-body[0], -body[1])

# ---------------- design normalisation ----------------

def normalise(design):
    if design.get("schema") != 2:
        fail('design.json needs "schema": 2')

    parts = design.get("parts") or {}
    if not parts:
        fail("design.json has no parts")
    for key, spec in parts.items():
        if not isinstance(spec, dict) or "lib_id" not in spec:
            fail(f"part '{key}' needs a lib_id")
        spec.setdefault("reference", key)
        spec.setdefault("value", spec["reference"])
        spec.setdefault("unit", 1)
        spec.setdefault("footprint", "")
        spec.setdefault("fields", {})
        spec.setdefault("in_bom", True)
        spec.setdefault("on_board", True)
        spec.setdefault("dnp", False)

    nets = {}
    for name, spec in (design.get("nets") or {}).items():
        if isinstance(spec, list):
            spec = {"connections": spec}
        if not isinstance(spec, dict) or not isinstance(spec.get("connections"), list):
            fail(f"net '{name}' must be a list, or an object with 'connections'")
        if re.match(r"^Net-\(", str(name)):
            fail(f"net name '{name}' is a KiCad auto-generated name -- give it a real name")
        if not str(name).strip() or any(c in str(name) for c in ' \t"'):
            fail(f"invalid net name '{name}'")
        nets[name] = {"connections": spec["connections"],
                      "class": spec.get("class", "Default"),
                      "style": spec.get("style", "local")}

    for index, net in enumerate(design.get("power_flags") or [], start=1):
        if net not in nets:
            fail(f"power_flags references unknown net '{net}'")
        ref = f"#FLG{index}"
        parts[ref] = {"lib_id": "power:PWR_FLAG", "reference": ref, "value": "PWR_FLAG",
                      "footprint": "", "fields": {}, "unit": 1, "in_bom": False,
                      "on_board": False, "dnp": False, "group": "_power_flags"}
        nets[net]["connections"] = list(nets[net]["connections"]) + [f"{ref}.1"]

    groups = list(design.get("groups") or [])
    if design.get("power_flags"):
        groups.append({"id": "_power_flags", "title": "Power flags (ERC)", "parts": []})
    known = {g["id"] for g in groups}
    for group in groups:
        group.setdefault("parts", [])
        for ref in group["parts"]:
            if ref not in parts:
                fail(f"group '{group['id']}' lists unknown part '{ref}'")
    assigned = {ref for g in groups for ref in g["parts"]}
    loose = []
    for key, spec in parts.items():
        gid = spec.get("group")
        if gid and gid not in known:
            fail(f"part '{key}' belongs to unknown group '{gid}'")
        if gid:
            group = next(g for g in groups if g["id"] == gid)
            if key not in group["parts"]:
                group["parts"].append(key)
        elif key not in assigned:
            loose.append(key)
    if loose:
        groups.append({"id": "_misc", "title": "Unsorted", "parts": loose})

    design["parts"], design["nets"], design["groups"] = parts, nets, groups
    design.setdefault("no_connect", [])
    design.setdefault("checks", {})
    design.setdefault("netclasses", {"Default": {}})
    return design

def resolve_pin(ref, parts, pinmap):
    if "." not in ref:
        fail(f"pin reference '{ref}' must look like U1.3 or U1.GND")
    key, token = ref.rsplit(".", 1)
    if key not in parts:
        fail(f"'{ref}' points at unknown part '{key}'")
    pins = pinmap[key]
    if token in pins:
        return key, token
    matches = [n for n, p in pins.items() if p["name"] == token] or \
              [n for n, p in pins.items() if p["name"].lower() == token.lower()]
    if not matches:
        listing = ", ".join(f"{n}:{p['name']}" for n, p in sorted(pins.items())[:12])
        fail(f"'{ref}' is not a pin of {parts[key]['lib_id']} (has {listing} ...)")
    if len(matches) > 1:
        fail(f"'{ref}' is ambiguous: name '{token}' is on pins {', '.join(matches)}")
    return key, matches[0]

def check_footprint(spec, project_libs, cfg):
    """Return None if fine, else a message. Missing footprints break Update PCB."""
    value = spec["footprint"]
    if not value:
        return f"{spec['reference']}: Footprint is empty -- Update PCB will skip it"
    if value.count(":") != 1:
        return f"{spec['reference']}: footprint '{value}' must be 'Library:Name'"
    lib, name = value.split(":")
    local = project_libs / f"{lib}.pretty"
    stock = cfg.get("kicad_footprint_dir")
    for folder in [local, (stock / f"{lib}.pretty") if stock else None]:
        if folder and (folder / f"{name}.kicad_mod").is_file():
            return None
    return (f"{spec['reference']}: footprint file '{name}.kicad_mod' not found in "
            f"{lib}.pretty (looked in {local} and kicad_footprint_dir)")

def validate(design, pinmap, project_libs, cfg, report):
    parts, nets, checks = design["parts"], design["nets"], design["checks"]
    strict_fp = checks.get("require_footprints", True)

    seen = {}
    for key, spec in parts.items():
        slot = (spec["reference"], spec["unit"])
        if slot in seen:
            fail(f"reference {spec['reference']} unit {spec['unit']} used by "
                 f"'{seen[slot]}' and '{key}'")
        seen[slot] = key
        if spec["on_board"]:
            problem = check_footprint(spec, project_libs, cfg)
            if problem:
                fail(problem) if strict_fp else report.append(f"WARN  {problem}")

    owner, used = {}, {}
    for name, net in nets.items():
        if net["class"] not in design["netclasses"]:
            fail(f"net '{name}' uses undefined netclass '{net['class']}'")
        resolved = []
        for ref in net["connections"]:
            slot = resolve_pin(ref, parts, pinmap)
            if slot in owner and owner[slot] != name:
                fail(f"pin {ref} is in two nets: '{owner[slot]}' and '{name}' (short)")
            owner[slot] = name
            if slot in resolved:
                report.append(f"WARN  {ref} listed twice in net '{name}'")
                continue
            resolved.append(slot)
        if len(resolved) < 2 and not checks.get("allow_single_pin_nets", False):
            fail(f"net '{name}' has only {len(resolved)} pin(s)")
        net["resolved"] = resolved
        used.update({slot: name for slot in resolved})

    nc = []
    for ref in design["no_connect"]:
        slot = resolve_pin(ref, parts, pinmap)
        if slot in used:
            fail(f"{ref} is no_connect but also in net '{used[slot]}'")
        nc.append(slot)
    design["nc_resolved"] = nc

    policy = checks.get("unused_pins", "warn")
    if policy not in ("warn", "error", "no_connect"):
        fail("checks.unused_pins must be warn, error or no_connect")
    for key, pins in pinmap.items():
        for number, pin in sorted(pins.items()):
            if (key, number) in used or (key, number) in nc:
                continue
            label = f"{parts[key]['reference']}.{number} ({pin['name']}, {pin['type']})"
            if pin["type"] == "power_in":
                fail(f"unconnected power pin {label} -- wire it or list it in no_connect")
            if policy == "error":
                fail(f"unconnected pin {label}")
            nc.append((key, number)) if policy == "no_connect" else \
                report.append(f"WARN  unconnected pin {label}")

    layers = (design.get("board") or {}).get("layers", 2)
    if layers not in (1, 2, 4, 6, 8):
        fail(f"board.layers must be 1, 2, 4, 6 or 8 (got {layers})")

# ---------------- schematic construction ----------------

def detect_project(project: Path):
    """Identity comes from the .kicad_pro. Never from the folder name."""
    pros = sorted(project.glob("*.kicad_pro"))
    if not pros:
        fail(f"no .kicad_pro in {project} -- create the project in KiCad first")
    if len(pros) > 1:
        fail(f"{len(pros)} .kicad_pro files in {project} -- one project per folder")
    stem = pros[0].stem
    root_sch = project / f"{stem}.kicad_sch"
    if not root_sch.is_file():
        fail(f"{root_sch.name} missing -- open the project in KiCad once so it writes the root sheet")
    text = root_sch.read_text(encoding="utf-8", errors="replace")[:4000]
    version = re.search(r"\(\s*version\s+([0-9]+)\s*\)", text)
    if not version:
        fail(f"cannot read the schematic format version from {root_sch.name}")
    gen = re.search(r'\(\s*generator_version\s+"([^"]+)"', text)
    return stem, pros[0], root_sch, int(version.group(1)), (gen.group(1) if gen else None)

def measure(design, libs):
    """Per part: pin offsets, stub lengths, and the real extent around the origin."""
    netof = {slot: (name, net["style"])
             for name, net in design["nets"].items() for slot in net["resolved"]}
    info = {}
    for key, spec in design["parts"].items():
        lib, name, node, parent, _ = libs.get(spec["lib_id"])
        rel = {}
        for pin_node in pin_nodes(node, parent):
            number = next((p[1] for p in find(pin_node, "number") if len(p) > 1), None)
            if number is not None:
                rel[number] = pin_geometry(pin_node)

        stub, sides = {}, {}
        for number, (_, away) in rel.items():
            if (key, number) in netof:
                sides.setdefault(away, []).append(number)
        for away, numbers in sides.items():
            axis = 1 if away[0] else 0     # sort along the perpendicular axis
            numbers.sort(key=lambda n: rel[n][0][axis])
            for index, number in enumerate(numbers):
                rev_idx = (STUB_CYCLE - 1) - (index % STUB_CYCLE)
                stub[number] = STUB + rev_idx * STUB_STEP

        left = right = top = bottom = 10.16
        for number, ((ox, oy), away) in rel.items():
            reach = stub.get(number, 0.0)
            ex, ey = ox + away[0] * reach, oy + away[1] * reach
            width = text_width(netof[(key, number)][0], netof[(key, number)][1]) if (key, number) in netof else 0.0
            left = max(left, -ox + 2.54, -ex + (width if away[0] < 0 else 0))
            right = max(right, ox + 2.54, ex + (width if away[0] > 0 else 0))
            top = max(top, -oy + 7.62, -ey + (width if away[1] < 0 else 0))
            bottom = max(bottom, oy + 7.62, ey + (width if away[1] > 0 else 0))

        info[key] = {"lib": lib, "name": name, "node": node, "parent": parent,
                     "rel": rel, "stub": stub,
                     "ext": {"left": left, "right": right, "top": top, "bottom": bottom}}
    return info, netof

def layout_group(group, info, target_w):
    members = list(group["parts"])
    offsets = {}
    x = 0.0
    row_top = 0.0
    row_height = 0.0
    box_right = 0.0
    for key in members:
        ext = info[key]["ext"]
        if row_height and x + ext["left"] + ext["right"] > target_w:
            x = 0.0
            row_top += row_height + PART_GAP_Y
            row_height = 0.0
        px, py = snap(x + ext["left"]), snap(row_top + ext["top"])
        offsets[key] = (px, py)
        x = px + ext["right"] + PART_GAP_X
        box_right = max(box_right, px + ext["right"])
        row_height = max(row_height, ext["top"] + ext["bottom"])
    box_bottom = row_top + row_height
    return {
        "w": box_right,
        "h": box_bottom,
        "offsets": offsets,
        "title": group.get("title", group["id"]),
        "members": members
    }

def try_pack(design, info, paper_w, paper_h):
    usable_w, usable_h = paper_w - 2 * MARGIN, paper_h - 2 * MARGIN
    blocks = []
    for group in design["groups"]:
        if not group["parts"]:
            continue
        area = sum((info[k]["ext"]["left"] + info[k]["ext"]["right"]) *
                   (info[k]["ext"]["top"] + info[k]["ext"]["bottom"])
                   for k in group["parts"])
        target_w = min(usable_w, max(60.0, (area * 1.6) ** 0.5))
        blocks.append(layout_group(group, info, target_w))

    col_x = col_w = y = 0.0
    placed_blocks = []
    for b in blocks:
        # block bounding box includes pads and title space
        block_total_w = b["w"] + 2 * GROUP_PAD
        block_total_h = b["h"] + 2 * GROUP_PAD + 7.62
        if y > 0 and y + block_total_h > usable_h:
            col_x += col_w + GROUP_GAP
            col_w = y = 0.0
        if col_x + block_total_w > usable_w or block_total_h > usable_h:
            return None
        placed_blocks.append({
            **b,
            "origin": (snap(MARGIN + col_x), snap(MARGIN + y))
        })
        y += block_total_h + GROUP_GAP
        col_w = max(col_w, block_total_w)
    return placed_blocks

def pack(design, info):
    for name, w, h in PAPERS:
        packed = try_pack(design, info, w, h)
        if packed:
            return name, packed
    packed = try_pack(design, info, 2000.0, 2000.0)
    return "User", packed

def build(design, libs, version, project_name, root_uuid):
    parts = design["parts"]
    info, netof = measure(design, libs)
    symbols, wires, labels, ncs, shapes = [], [], [], [], []
    embedded, placed = {}, {}

    paper, packed_blocks = pack(design, info)

    for b in packed_blocks:
        ox, oy = b["origin"]
        title_y = oy + GROUP_PAD
        
        shapes.append(["rectangle",
                       ["start", fmt(ox), fmt(title_y - 2.54)],
                       ["end", fmt(ox + b["w"] + 2 * GROUP_PAD), fmt(oy + b["h"] + 2 * GROUP_PAD + 7.62)],
                       ["stroke", ["width", "0.15"], ["type", "dash"]],
                       ["fill", ["type", "none"]], ["uuid", uid()]])
        shapes.append(["text", q(b["title"]),
                       at(ox + 1.27, title_y - 4.06, 0),
                       effects(version, size=2.0, justify=["left", "bottom"]),
                       ["uuid", uid()]])
                       
        for key, (px, py) in b["offsets"].items():
            placed[key] = (ox + GROUP_PAD + px, title_y + 7.62 + py)

    for key, spec in parts.items():
        data = info[key]
        embedded.setdefault(f"{data['lib']}:{data['name']}",
                            libs.embed(data["lib"], data["name"], data["node"], data["parent"]))
        x, y = placed[key]
        pin_ys = [oy for (ox, oy), _ in data["rel"].values()]
        ref_dy = min(pin_ys) - 2.54 if pin_ys else -5.08
        val_dy = max(pin_ys) + 2.54 if pin_ys else 5.08

        hide_refval = (spec["lib_id"] == "power:PWR_FLAG")
        
        fields = [prop(version, "Reference", spec["reference"], x, y + ref_dy, hide=hide_refval),
                  prop(version, "Value", spec["value"], x, y + val_dy, hide=hide_refval),
                  prop(version, "Footprint", spec["footprint"], x, y, hide=True),
                  prop(version, "Datasheet", spec.get("datasheet", ""), x, y, hide=True)]
        fields += [prop(version, str(k), str(v), x, y, hide=True)
                   for k, v in spec["fields"].items()]

        body = ["symbol", ["lib_id", q(spec["lib_id"])], at(x, y, 0),
                ["unit", str(spec["unit"])]]
        if version >= 20231120:
            body.append(["exclude_from_sim", "no"])
        body += [["in_bom", "yes" if spec["in_bom"] else "no"],
                 ["on_board", "yes" if spec["on_board"] else "no"],
                 ["dnp", "yes" if spec["dnp"] else "no"],
                 ["uuid", uid()], *fields,
                 ["instances", ["project", q(project_name),
                                ["path", q(f"/{root_uuid}"),
                                 ["reference", q(spec["reference"])],
                                 ["unit", str(spec["unit"])]]]]]
        symbols.append(body)

        for number, ((ox, oy), away) in data["rel"].items():
            slot = (key, number)
            px, py = snap(x + ox), snap(y + oy)
            if slot in netof:
                reach = data["stub"][number]
                ex, ey = snap(px + away[0] * reach), snap(py + away[1] * reach)
                wires.append(["wire",
                              ["pts", ["xy", fmt(px), fmt(py)], ["xy", fmt(ex), fmt(ey)]],
                              ["stroke", ["width", "0"], ["type", "default"]],
                              ["uuid", uid()]])
                name, style = netof[slot]
                key_dir = (int(away[0]), int(away[1]))
                node = ["global_label" if style == "global" else "label", q(name),
                        at(ex, ey, LABEL_ANGLE[key_dir])]
                if style == "global":
                    node.append(["shape", "passive"])
                node += [effects(version, justify=JUSTIFY[key_dir]), ["uuid", uid()]]
                labels.append(node)
            elif slot in design["nc_resolved"]:
                ncs.append(["no_connect", at(px, py), ["uuid", uid()]])

    if paper == "User":
        paper = "User 2000.0000 2000.0000"
    return embedded, symbols, wires, labels, ncs, shapes, paper

def render(design, header, embedded, symbols, wires, labels, ncs, shapes, paper, root_uuid):
    version, gen_version = header
    meta = design.get("meta") or {}
    lines = ["(kicad_sch", f"  (version {version})", '  (generator "abide_json2sch")']
    if gen_version:
        lines.append(f'  (generator_version "{gen_version}")')
    lines += [f'  (uuid "{root_uuid}")', f'  (paper "{paper}")',
              "  " + dumps(["title_block",
                            ["title", q(meta.get("title", meta.get("design_id", "")))],
                            ["date", q(meta.get("date", ""))],
                            ["rev", q(meta.get("rev", ""))],
                            ["company", q(meta.get("company", ""))]]),
              "  (lib_symbols"]
    lines += ["    " + dumps(node) for node in embedded.values()]
    lines.append("  )")
    for bucket in (shapes, ncs, wires, labels, symbols):
        lines += ["  " + dumps(node) for node in bucket]
    lines.append('  (sheet_instances (path "/" (page "1")))')
    if version >= 20241209:
        lines.append("  (embedded_fonts no)")
    lines.append(")")
    return "\n".join(lines) + "\n"

def apply_netclasses(path: Path, design):
    original = path.read_text(encoding="utf-8")
    path.with_name(path.name + ".bak").write_text(original, encoding="utf-8")
    data = json.loads(original)
    settings = data.setdefault("net_settings", {})
    settings["classes"] = [dict(name=name, **spec)
                           for name, spec in design["netclasses"].items()]
    settings["netclass_patterns"] = [{"netclass": net["class"], "pattern": name}
                                     for name, net in design["nets"].items()
                                     if net["class"] != "Default"]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"net classes written to {path.name} (backup: {path.name}.bak)"

# ---------------- cli ----------------

def main():
    ap = argparse.ArgumentParser(description="Compile design.json into a KiCad schematic.")
    ap.add_argument("project_dir")
    ap.add_argument("design_json")
    ap.add_argument("-o", "--out", help="output .kicad_sch (default: project root schematic)")
    ap.add_argument("--dry-run", action="store_true", help="validate only, write nothing")
    ap.add_argument("--apply-netclasses", action="store_true")
    a = ap.parse_args()

    project = Path(a.project_dir).expanduser().resolve()
    if not project.is_dir():
        fail(f"project directory not found: {project}")
    design_file = Path(a.design_json).expanduser()
    if not design_file.is_file():
        fail(f"design file not found: {design_file}")

    design = normalise(json.loads(design_file.read_text(encoding="utf-8")))
    project_name, pro_file, root_sch, version, gen_version = detect_project(project)
    cfg = load_paths("kicad_symbol_dir")
    libs = Libraries(cfg, project / "libs")

    pinmap = {key: libs.get(spec["lib_id"])[4] for key, spec in design["parts"].items()}
    report = []
    validate(design, pinmap, project / "libs", cfg, report)

    root_uuid = str(uuid.uuid4())
    embedded, symbols, wires, labels, ncs, shapes, paper = build(
        design, libs, version, project_name, root_uuid)
    text = render(design, (version, gen_version), embedded, symbols, wires,
                  labels, ncs, shapes, paper, root_uuid)

    parse(text)  # structural self-check: the file we are about to write must re-parse

    for line in report:
        print(line)
    print(f"\nsymbols {len(symbols)} | nets {len(design['nets'])} | stubs {len(wires)} | "
          f"labels {len(labels)} | no-connects {len(ncs)} | paper {paper}")
    for name, net in design["nets"].items():
        print(f"  {name:10} {len(net['resolved'])} pins [{net['class']}]")

    if a.dry_run:
        print("\ndry run: validation passed, nothing written.")
        return

    out = Path(a.out).expanduser() if a.out else root_sch
    if out.exists():
        out.with_name(out.name + ".bak").write_text(
            out.read_text(encoding="utf-8"), encoding="utf-8")
    out.write_text(text, encoding="utf-8")
    print(f"\nwrote {out}")
    if a.apply_netclasses:
        print(apply_netclasses(pro_file, design))

    print("\nIn KiCad: reopen the project, then Tools > Annotate (keep existing) > "
          "Inspect > ERC, then Tools > Update PCB from Schematic (F8).")
    board = design.get("board") or {}
    if board.get("layers", 2) > 2:
        print(f"Board Setup > Physical Stackup: copper layers = {board['layers']}")
        for index, layer in enumerate(board.get("stackup", []), start=1):
            print(f"  {index}. {layer}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as e:
        sys.exit(f"Error: {type(e).__name__}: {e}")
