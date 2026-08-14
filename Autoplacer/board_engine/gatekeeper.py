"""
Autoplacer/board_engine/gatekeeper.py — Geometry Gate, Courtyard bounding boxes, overlap detection, and physics auto-separation.
"""

import pcbnew
from abide.geometry import Box, find_overlaps, outside, separate
from .common import (
    to_mm, from_mm, mk_point, _try, _call_any, uuid_of
)

def box_of(fp, pad_margin_mm=0.25):
    pos = fp.GetPosition()
    ox, oy = to_mm(pos.x), to_mm(pos.y)
    rot = _try(lambda: fp.GetOrientationDegrees(), 0.0)
    locked = _try(lambda: bool(fp.IsLocked()), False)

    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        poly = _try(lambda: fp.GetCourtyard(layer))
        if poly is not None and _try(lambda: poly.OutlineCount(), 0):
            bb = poly.BBox()
            return Box(fp.GetReference(),
                       to_mm(bb.GetLeft()), to_mm(bb.GetTop()),
                       to_mm(bb.GetRight()), to_mm(bb.GetBottom()),
                       ox, oy, rot, locked, "courtyard")

    xs, ys = [], []
    for pad in fp.Pads():
        b = pad.GetBoundingBox()
        xs += [to_mm(b.GetLeft()), to_mm(b.GetRight())]
        ys += [to_mm(b.GetTop()), to_mm(b.GetBottom())]
    if xs:
        m = pad_margin_mm
        return Box(fp.GetReference(), min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m,
                   ox, oy, rot, locked, "pad_hull")

    b = fp.GetBoundingBox()
    return Box(fp.GetReference(),
               to_mm(b.GetLeft()), to_mm(b.GetTop()),
               to_mm(b.GetRight()), to_mm(b.GetBottom()),
               ox, oy, rot, locked, "bbox_with_text")

def board_bounds(board):
    poly = pcbnew.SHAPE_POLY_SET()
    if not _try(lambda: board.GetBoardPolygonOutlines(poly, True), False):
        return None
    if not poly.OutlineCount():
        return None
    bb = poly.BBox()
    return (to_mm(bb.GetLeft()), to_mm(bb.GetTop()),
            to_mm(bb.GetRight()), to_mm(bb.GetBottom()))

def get_netclasses_without_track_width(board):
    """Find netclasses defined with 0 or missing track width."""
    zero_width = []
    try:
        items = board.GetAllNetClasses().items()
        for name, nc in items:
            if nc is not None:
                w = _try(lambda: to_mm(nc.GetTrackWidth()), 0)
                if not w or w <= 0:
                    zero_width.append(str(name))
    except Exception:
        pass
    return zero_width

def placement_report(board, clearance=0.25, edge_margin=0.5):
    boxes = [box_of(fp) for fp in board.GetFootprints()]
    bounds = board_bounds(board)
    no_courtyard = sorted(b.ref for b in boxes if b.source != "courtyard")
    zero_width = get_netclasses_without_track_width(board)
    return {
        "outline_closed": bounds is not None,
        "board_bounds_mm": bounds,
        "clearance_used_mm": clearance,
        "overlaps": find_overlaps(boxes, clearance),
        "outside_outline": outside(boxes, bounds, edge_margin) if bounds else [],
        "netclasses_without_track_width": zero_width,
        "footprints_without_courtyard": no_courtyard,
        "route_ready": bool(bounds) and not find_overlaps(boxes, clearance) and not zero_width,
    }

def _geometry_gate(board, clearance=0.25, edge_margin=0.5, autoresolve=True):
    rep = placement_report(board, clearance, edge_margin)
    if not rep["overlaps"] and not rep["outside_outline"]:
        return rep, []
    if not autoresolve:
        return rep, ["placement rejected: %d overlap(s), %d part(s) outside the outline"
                     % (len(rep["overlaps"]), len(rep["outside_outline"]))]
    boxes = [box_of(fp) for fp in board.GetFootprints()]
    moved, left = separate(boxes, clearance, rep["board_bounds_mm"], edge_margin)
    for ref, (ox, oy) in moved.items():
        fp = board.FindFootprintByReference(ref)
        if fp is not None and not fp.IsLocked():
            fp.SetPosition(mk_point(ox, oy))
    rep = placement_report(board, clearance, edge_margin)
    rep["auto_separated"] = moved
    return rep, ([] if not left else
                 ["could not separate %d pair(s) automatically" % len(left)])
