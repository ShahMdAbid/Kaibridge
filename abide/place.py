"""
abide/place.py -- where every symbol goes, one sheet at a time.

Same model as your pack(): upright symbols, a stub off every connected pin, a
label at the end of the stub, groups laid out as shelves. What changed:

  1. Extents come from the real symbol bbox (klib), not a fixed 10.16 halo.
  2. 'near' parts leave the group flow and park beside their anchor pin.
  3. No 2000x2000 fallback. Paper escalates A4 -> A0, then the build fails
     with an instruction to split the sheet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .model import Design, DesignError

GRID = 1.27
STUB = 7.62
STUB_STEP = 5.08
STUB_CYCLE = 3
PART_GAP_X = 12.7
PART_GAP_Y = 15.24
GROUP_PAD = 10.16
GROUP_GAP = 15.24
SAT_GAP = 7.62
MARGIN = 12.7
TITLE_H = 7.62
FONT = 1.27
CHAR_W = 0.85 * FONT
SHEET_PIN_PITCH = 2.54
SHEET_PIN_TOP = 5.08
SHEET_MIN_W = 50.8
SHEET_MIN_H = 25.4
PAPERS = [("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0),
          ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0)]

@dataclass
class Frame:
    """A drawn rectangle on a page: a group box or a child-sheet box."""
    kind: str          # "group" | "sheet"
    key: str
    title: str
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    gutter: float = 0.0    # label space reserved left of a sheet box

@dataclass
class Layout:
    labels: Dict[Tuple[str, str], Tuple[str, str]] = field(default_factory=dict)
    frames: Dict[str, List[Frame]] = field(default_factory=dict)
    pins: Dict[str, List[str]] = field(default_factory=dict)

def snap(value):
    return round(value / GRID) * GRID

def _text_width(name):
    return len(name) * CHAR_W + 1.27

def stubs(part, labels):
    """[(number, pin, end_xy, label, length)] for every labelled pin."""
    out = []
    sides: Dict[Tuple[int, int], list] = {}
    for number, pin in part.symbol.pins.items():
        label = labels.get((part.ref, number))
        if label is None:
            continue
        sides.setdefault(pin.away, []).append((number, pin, label[0]))
    for away, items in sides.items():
        flip = 1 if away[0] else 0
        items.sort(key=lambda it: (it[1].offset[flip], it[1].offset[1 - flip]))
        for index, (number, pin, name) in enumerate(items):
            length = STUB + STUB_STEP * (index % STUB_CYCLE)
            end = (pin.offset[0] + away[0] * length, pin.offset[1] + away[1] * length)
            out.append((number, pin, end, name, length))
    return out

def measure(part, labels):
    """(left, top, right, bottom) around the symbol, its stubs and its text."""
    left, top, right, bottom = part.symbol.bbox
    if not part.hidden:
        top = min(top, -3.81)      # Reference above
        bottom = max(bottom, 3.81)  # Value below
    for _, pin, end, name, _ in stubs(part, labels):
        left, right = min(left, end[0]), max(right, end[0])
        top, bottom = min(top, end[1]), max(bottom, end[1])
        span = _text_width(name)
        if pin.away[0] > 0:
            right = max(right, end[0] + span)
        elif pin.away[0] < 0:
            left = min(left, end[0] - span)
        elif pin.away[1] < 0:
            top = min(top, end[1] - span)
        else:
            bottom = max(bottom, end[1] + span)
    return (left, top, right, bottom)

def _cluster(anchor, sats, extents):
    """Park each satellite on the side its anchor pin points at.
    Returns ({ref: (dx, dy)}, union extent). Purely visual: nothing here can
    change the netlist, because wiring is by label."""
    place = {anchor.ref: (0.0, 0.0)}
    base = extents[anchor.ref]
    box = list(base)
    sides: Dict[Tuple[int, int], list] = {}
    for sat in sats:
        number = sat.near.split(".", 1)[1]
        pin = anchor.symbol.pins[number]
        sides.setdefault(pin.away, []).append((pin, sat))
    for away, items in sides.items():
        flip = 1 if away[0] else 0
        items.sort(key=lambda it: (it[0].offset[flip], it[0].offset[1 - flip]))
        cursor = None
        for pin, sat in items:
            box_s = extents[sat.ref]
            if away[0]:
                x = base[2] + SAT_GAP - box_s[0] if away[0] > 0 \
                    else base[0] - SAT_GAP - box_s[2]
                y = pin.offset[1]
                if cursor is not None and y + box_s[1] < cursor + SAT_GAP:
                    y = cursor + SAT_GAP - box_s[1]
                cursor = y + box_s[3]
            else:
                y = base[3] + SAT_GAP - box_s[1] if away[1] > 0 \
                    else base[1] - SAT_GAP - box_s[3]
                x = pin.offset[0]
                if cursor is not None and x + box_s[0] < cursor + SAT_GAP:
                    x = cursor + SAT_GAP - box_s[0]
                cursor = x + box_s[2]
            x, y = snap(x), snap(y)
            place[sat.ref] = (x, y)
            box[0] = min(box[0], x + box_s[0])
            box[1] = min(box[1], y + box_s[1])
            box[2] = max(box[2], x + box_s[2])
            box[3] = max(box[3], y + box_s[3])
    return place, tuple(box)

def _clusters(group, design, extents):
    """Group members, with 'near' parts folded into their anchor's cluster."""
    members = [design.parts[r] for r in group.refs]
    owned = {p.ref for p in members}
    sats: Dict[str, list] = {}
    flow = []
    for part in members:
        anchor_ref = part.near.split(".", 1)[0] if part.near else ""
        if anchor_ref and anchor_ref in owned:
            sats.setdefault(anchor_ref, []).append(part)
        else:
            flow.append(part)
    out = []
    for part in flow:
        mine = sats.get(part.ref) or []
        if mine:
            out.append(_cluster(part, mine, extents))
        else:
            out.append(({part.ref: (0.0, 0.0)}, extents[part.ref]))
    return out

def _layout_group(group, design, extents, max_width):
    """Shelf-pack one group. Returns ({ref: (x, y)}, width, height), all
    relative to the group box's inner top-left corner."""
    x = y = 0.0
    shelf = 0.0
    width = 0.0
    out: Dict[str, Tuple[float, float]] = {}
    for place, box in _clusters(group, design, extents):
        cw, ch = box[2] - box[0], box[3] - box[1]
        if x > 0.0 and x + cw > max_width:
            x = 0.0
            y += shelf + PART_GAP_Y
            shelf = 0.0
        for ref, (dx, dy) in place.items():
            out[ref] = (snap(x - box[0] + dx), snap(y - box[1] + dy))
        x += cw + PART_GAP_X
        width = max(width, x - PART_GAP_X)
        shelf = max(shelf, ch)
    return out, width, y + shelf

def _sheet_box(sheet, names):
    """Size of a child-sheet box on the root page, from its pin names."""
    longest = max([len(n) for n in names] or [0])
    w = max(SHEET_MIN_W, longest * CHAR_W * 1.6 + 2 * GROUP_PAD,
            len(sheet.title) * CHAR_W + 2 * GROUP_PAD)
    h = max(SHEET_MIN_H, SHEET_PIN_TOP * 2 + SHEET_PIN_PITCH * max(len(names) - 1, 0))
    gutter = STUB + max([_text_width(n) for n in names] or [0.0])
    return snap(w), snap(h), snap(gutter)

def _try_page(frames, boxes, width, height):
    """Shelf-pack the frames into one page. None means it does not fit."""
    usable_w = width - 2 * MARGIN
    usable_h = height - 2 * MARGIN
    x = y = 0.0
    row = 0.0
    for frame in frames:
        fw, fh = boxes[frame.key]
        if fw > usable_w or fh > usable_h:
            return None
        if x > 0.0 and x + fw > usable_w:
            x = 0.0
            y += row + GROUP_GAP
            row = 0.0
        if y + fh > usable_h:
            return None
        frame.x = snap(MARGIN + x)
        frame.y = snap(MARGIN + y)
        frame.w, frame.h = fw, fh
        x += fw + GROUP_GAP
        row = max(row, fh)
    return y + row <= usable_h

def plan(design):
    """Fill in part.x/part.y and sheet paper, and return the Layout."""
    layout = Layout()
    for net in design.nets.values():
        for conn in net.conns:
            layout.labels[(conn.ref, conn.pin)] = (net.name, net.style)
    extents = {ref: measure(part, layout.labels)
               for ref, part in design.parts.items()}
    for sheet in design.sheets[1:]:
        names = sorted({n.name for n in design.nets.values()
                        if n.style == "hierarchical" and sheet.id in n.sheets})
        layout.pins[sheet.id] = names
    for sheet in design.sheets:
        _plan_sheet(sheet, design, layout, extents)
    return layout

def _plan_sheet(sheet, design, layout, extents):
    frames: List[Frame] = []
    if sheet.root and design.hierarchical:
        for child in design.sheets[1:]:
            frames.append(Frame(kind="sheet", key=child.id, title=child.title))
    groups = design.sheet_groups(sheet.id)
    for group in groups:
        frames.append(Frame(kind="group", key=group.id, title=group.title))
    if not frames:
        raise DesignError(f"sheet '{sheet.id}' has no parts and no sub-sheets")
    for paper, page_w, page_h in PAPERS:
        inner = page_w - 2 * MARGIN - 2 * GROUP_PAD
        placements: Dict[str, Dict[str, Tuple[float, float]]] = {}
        boxes: Dict[str, Tuple[float, float]] = {}
        gutters: Dict[str, float] = {}
        for frame in frames:
            if frame.kind == "sheet":
                child = next(s for s in design.sheets if s.id == frame.key)
                w, h, gutter = _sheet_box(child, layout.pins.get(child.id) or [])
                boxes[frame.key] = (w + gutter, h)
                gutters[frame.key] = gutter
                continue
            group = next(g for g in groups if g.id == frame.key)
            place, gw, gh = _layout_group(group, design, extents, inner)
            placements[frame.key] = place
            boxes[frame.key] = (gw + 2 * GROUP_PAD, gh + 2 * GROUP_PAD + TITLE_H)
        if _try_page(frames, boxes, page_w, page_h):
            sheet.paper, sheet.width, sheet.height = paper, page_w, page_h
            for frame in frames:
                if frame.kind == "sheet":
                    frame.gutter = gutters[frame.key]
                    continue
                ox = frame.x + GROUP_PAD
                oy = frame.y + GROUP_PAD + TITLE_H
                for ref, (dx, dy) in placements[frame.key].items():
                    part = design.parts[ref]
                    part.x = snap(ox + dx)
                    part.y = snap(oy + dy)
            layout.frames[sheet.id] = frames
            return
    biggest = max(groups, key=lambda g: len(g.refs)) if groups else None
    hint = f" The largest group is '{biggest.id}' with {len(biggest.refs)} parts." \
        if biggest is not None else ""
    raise DesignError(
        f"sheet '{sheet.id}' does not fit on A0 with readable spacing."
        f"{hint} Split it into more sheets or more groups -- abIDE will not "
        f"emit an oversized custom page.")
