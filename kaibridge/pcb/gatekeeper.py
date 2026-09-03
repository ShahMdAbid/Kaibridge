"""
kaibridge/pcb/gatekeeper.py ? Pre-Placement Geometry Gate & Collision Auditor.

Computes courtyard+pad-hull collision envelopes for every footprint,
detects overlap pairs, identifies components outside the board outline,
and checks netclass track width validity.

Aligned with Kaibridge 2.0 headless architecture:
  - Takes project_dir, loads board via pcbnew.LoadBoard()
  - Returns machine-readable placement_report dict
  - No SWIG objects leak out
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import subprocess
import json

from ..core.paths import load_kicad_python


def _to_mm(nm: int) -> float:
    return round(nm / 1e6, 5)

def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


@dataclass
class Box:
    ref: str
    x0: float
    y0: float
    x1: float
    y1: float
    cx: float
    cy: float
    rot: float
    locked: bool
    source: str


def _box_of(fp, pad_margin_mm: float = 0.25) -> Box:
    """Compute true collision envelope: union of courtyard + pad hull."""
    import pcbnew

    pos = fp.GetPosition()
    ox, oy = _to_mm(pos.x), _to_mm(pos.y)
    rot = _try(lambda: fp.GetOrientationDegrees(), 0.0)
    locked = _try(lambda: bool(fp.IsLocked()), False)

    # Step 1: Compute pad hull (always)
    xs, ys = [], []
    for pad in fp.Pads():
        b = pad.GetBoundingBox()
        xs += [_to_mm(b.GetLeft()), _to_mm(b.GetRight())]
        ys += [_to_mm(b.GetTop()), _to_mm(b.GetBottom())]

    pad_hull = None
    if xs:
        m = pad_margin_mm
        pad_hull = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)

    # Step 2: Try courtyard polygon
    crt_hull = None
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        poly = _try(lambda: fp.GetCourtyard(layer))
        if poly is not None and _try(lambda: poly.OutlineCount(), 0):
            bb = poly.BBox()
            crt_hull = (_to_mm(bb.GetLeft()), _to_mm(bb.GetTop()),
                        _to_mm(bb.GetRight()), _to_mm(bb.GetBottom()))
            break

    # Step 3: Union envelope = max(courtyard, pad_hull)
    if crt_hull and pad_hull:
        return Box(fp.GetReference(),
                   min(crt_hull[0], pad_hull[0]), min(crt_hull[1], pad_hull[1]),
                   max(crt_hull[2], pad_hull[2]), max(crt_hull[3], pad_hull[3]),
                   ox, oy, rot, locked, "courtyard+pad_hull")

    if crt_hull:
        return Box(fp.GetReference(), crt_hull[0], crt_hull[1], crt_hull[2], crt_hull[3],
                   ox, oy, rot, locked, "courtyard")

    if pad_hull:
        return Box(fp.GetReference(), pad_hull[0], pad_hull[1], pad_hull[2], pad_hull[3],
                   ox, oy, rot, locked, "pad_hull")

    # Fallback: full bounding box
    b = fp.GetBoundingBox()
    return Box(fp.GetReference(),
               _to_mm(b.GetLeft()), _to_mm(b.GetTop()),
               _to_mm(b.GetRight()), _to_mm(b.GetBottom()),
               ox, oy, rot, locked, "bbox_fallback")


def _find_overlaps(boxes: List[Box], clearance: float = 0.25) -> List[Dict[str, Any]]:
    """Detect all AABB overlap pairs with clearance margin."""
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (a.x0 - clearance < b.x1 + clearance and
                a.x1 + clearance > b.x0 - clearance and
                a.y0 - clearance < b.y1 + clearance and
                a.y1 + clearance > b.y0 - clearance):
                # Compute overlap depth for resolution vector
                dx = min(a.x1, b.x1) - max(a.x0, b.x0)
                dy = min(a.y1, b.y1) - max(a.y0, b.y0)
                overlaps.append({
                    "ref_a": a.ref, "ref_b": b.ref,
                    "overlap_x_mm": round(max(dx, 0), 3),
                    "overlap_y_mm": round(max(dy, 0), 3),
                    "move_b_by": {
                        "dx": round(dx + clearance, 3) if dx > 0 else 0,
                        "dy": round(dy + clearance, 3) if dy > 0 else 0
                    }
                })
    return overlaps


def _find_outside(boxes: List[Box], bounds: Optional[Tuple], margin: float = 0.5) -> List[Dict[str, Any]]:
    """Find components hanging outside board outline."""
    if not bounds:
        return []
    bx0, by0, bx1, by1 = bounds
    outside = []
    for b in boxes:
        violations = []
        if b.x0 < bx0 + margin:
            violations.append(f"left edge by {round(bx0 + margin - b.x0, 2)}mm")
        if b.x1 > bx1 - margin:
            violations.append(f"right edge by {round(b.x1 - (bx1 - margin), 2)}mm")
        if b.y0 < by0 + margin:
            violations.append(f"top edge by {round(by0 + margin - b.y0, 2)}mm")
        if b.y1 > by1 - margin:
            violations.append(f"bottom edge by {round(b.y1 - (by1 - margin), 2)}mm")
        if violations:
            outside.append({"ref": b.ref, "violations": violations})
    return outside


def placement_audit(project_dir: str | Path, clearance: float = 0.25, edge_margin: float = 0.5) -> Dict[str, Any]:
    """Run pre-placement geometry gate audit.

    Returns a structured report with:
      - overlap pairs (with resolution vectors)
      - components outside board outline
      - footprints missing courtyard data
      - netclasses with zero track width
      - route_ready flag (True only if 0 overlaps and outline is closed)
    """
    try:
        import pcbnew
    except ImportError:
        kicad_python = load_kicad_python()
        root_pkg = Path(__file__).resolve().parents[2]
        payload = json.dumps({"project_dir": str(project_dir), "clearance": clearance, "edge_margin": edge_margin})
        runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.gatekeeper import placement_audit
kwargs = json.loads(r'''{payload}''')
res = placement_audit(**kwargs)
print("AUDIT_SUB_RESULT:" + json.dumps(res))
"""
        proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            if line.startswith("AUDIT_SUB_RESULT:"):
                return json.loads(line.replace("AUDIT_SUB_RESULT:", ""))
        return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}

    proj = Path(project_dir).resolve()
    pcb_files = list(proj.glob("*.kicad_pcb"))
    if not pcb_files:
        return {"success": False, "error": f"No .kicad_pcb in {proj}"}

    import gc
    gc.collect()
    board = pcbnew.LoadBoard(str(pcb_files[0]))
    if not hasattr(board, "GetFootprints"):
        gc.collect()
        board = pcbnew.LoadBoard(str(pcb_files[0]))

    # Compute collision boxes
    boxes = [_box_of(fp) for fp in board.GetFootprints()]

    # Board outline bounds
    poly = pcbnew.SHAPE_POLY_SET()
    has_outline = _try(lambda: board.GetBoardPolygonOutlines(poly, True), False)
    bounds = None
    if has_outline and poly.OutlineCount():
        bb = poly.BBox()
        bounds = (_to_mm(bb.GetLeft()), _to_mm(bb.GetTop()),
                  _to_mm(bb.GetRight()), _to_mm(bb.GetBottom()))

    # Detect overlaps
    overlaps = _find_overlaps(boxes, clearance)

    # Detect outside-outline
    outside = _find_outside(boxes, bounds, edge_margin)

    # Footprints without courtyard
    no_courtyard = sorted(b.ref for b in boxes if "courtyard" not in b.source)

    # Netclasses with zero track width
    zero_width = []
    try:
        for name, nc in board.GetAllNetClasses().items():
            if nc is not None:
                w = _try(lambda: _to_mm(nc.GetTrackWidth()), 0)
                if not w or w <= 0:
                    zero_width.append(str(name))
    except Exception:
        pass

    report = {
        "success": True,
        "outline_closed": bounds is not None,
        "board_bounds_mm": bounds,
        "clearance_used_mm": clearance,
        "footprint_count": len(boxes),
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "outside_outline_count": len(outside),
        "outside_outline": outside,
        "footprints_without_courtyard": no_courtyard,
        "netclasses_without_track_width": zero_width,
        "route_ready": bool(bounds) and len(overlaps) == 0 and len(zero_width) == 0,
        "footprint_boxes": [
            {"ref": b.ref, "x0": b.x0, "y0": b.y0, "x1": b.x1, "y1": b.y1,
             "cx": b.cx, "cy": b.cy, "rot": b.rot, "locked": b.locked, "source": b.source}
            for b in boxes
        ]
    }

    del board
    return report
