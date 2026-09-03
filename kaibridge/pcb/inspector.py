"""
kaibridge/pcb/inspector.py ? Board State Introspection Engine.

Extracts a complete, structured, UUID-keyed JSON representation of the
live board state from .kicad_pcb: footprints (with pads, nets, courtyards),
tracks, vias, zones, drawings, design rules, and netclasses.

Aligned with Kaibridge 2.0 headless architecture:
  - Takes project_dir, loads board via pcbnew.LoadBoard()
  - Returns a plain dict (no SWIG objects leak out)
  - Stores ai_context JSON in kaibridge_dump/
"""
from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..core.paths import load_kicad_python


def _to_mm(nm: int) -> float:
    return round(nm / 1e6, 5)

def _pt(pos) -> Optional[Dict[str, float]]:
    if pos is None:
        return None
    return {"x": _to_mm(pos.x), "y": _to_mm(pos.y)}

def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

def _layers_of(board, item) -> List[str]:
    try:
        ls = item.GetLayerSet()
        return [board.GetLayerName(lid) for lid in ls.Seq()]
    except Exception:
        try:
            return [item.GetLayerName()]
        except Exception:
            return []

def _uuid_of(item) -> str:
    try:
        u = item.m_Uuid
        return str(u.AsString()) if hasattr(u, "AsString") else str(u)
    except Exception:
        return ""


def _extract_pad(board, pad) -> Dict[str, Any]:
    sz = _try(lambda: pad.GetSize())
    dr = _try(lambda: pad.GetDrillSize())
    return {
        "uuid": _uuid_of(pad),
        "number": _try(lambda: pad.GetNumber(), ""),
        "pin_function": _try(lambda: pad.GetPinFunction()),
        "net_name": _try(lambda: pad.GetNetname(), ""),
        "net_code": _try(lambda: pad.GetNetCode(), 0),
        "shape": _try(lambda: pad.GetShapeStr()),
        "position_mm": _pt(_try(lambda: pad.GetPosition())),
        "size_mm": {"w": _to_mm(sz.x), "h": _to_mm(sz.y)} if sz else None,
        "drill_mm": {"w": _to_mm(dr.x), "h": _to_mm(dr.y)} if dr else None,
        "layers": _layers_of(board, pad),
    }


def _extract_footprint(board, fp) -> Dict[str, Any]:
    pos = fp.GetPosition()
    # Compute courtyard bounding box
    courtyard_mm = None
    for layer_id in (_try(lambda: board.GetLayerID("F.CrtYd")), _try(lambda: board.GetLayerID("B.CrtYd"))):
        if layer_id is None:
            continue
        poly = _try(lambda: fp.GetCourtyard(layer_id))
        if poly and _try(lambda: poly.OutlineCount(), 0) > 0:
            bb = poly.BBox()
            courtyard_mm = {
                "x0": _to_mm(bb.GetLeft()), "y0": _to_mm(bb.GetTop()),
                "x1": _to_mm(bb.GetRight()), "y1": _to_mm(bb.GetBottom()),
                "w": _to_mm(bb.GetWidth()), "h": _to_mm(bb.GetHeight())
            }
            break

    return {
        "uuid": _uuid_of(fp),
        "reference": _try(lambda: fp.GetReference(), ""),
        "value": _try(lambda: fp.GetValue(), ""),
        "fpid": _try(lambda: fp.GetFPIDAsString()) or _try(lambda: str(fp.GetFPID().GetUniStringLibId())),
        "layer": _try(lambda: fp.GetLayerName()),
        "position_mm": {"x": _to_mm(pos.x), "y": _to_mm(pos.y)},
        "rotation_deg": _try(lambda: fp.GetOrientationDegrees(), 0.0),
        "is_locked": _try(lambda: bool(fp.IsLocked()), False),
        "courtyard_mm": courtyard_mm,
        "pad_count": _try(lambda: fp.GetPadCount(), 0),
        "pads": [_extract_pad(board, p) for p in fp.Pads()],
    }


def _extract_track(board, t) -> Dict[str, Any]:
    import pcbnew
    is_via = isinstance(t, pcbnew.PCB_VIA)
    if is_via:
        # KiCad 10: PCB_VIA.GetWidth() requires a layer argument
        via_dia = _try(lambda: _to_mm(t.GetWidth(pcbnew.F_Cu)))
        if via_dia is None:
            via_dia = _try(lambda: _to_mm(t.GetWidth()))
        return {
            "type": "via",
            "uuid": _uuid_of(t),
            "position_mm": _pt(_try(lambda: t.GetPosition())),
            "net_name": _try(lambda: t.GetNetname(), ""),
            "diameter_mm": via_dia,
            "drill_mm": _try(lambda: _to_mm(t.GetDrillValue())),
            "layers": _layers_of(board, t),
        }
    return {
        "type": "track",
        "uuid": _uuid_of(t),
        "start_mm": _pt(_try(lambda: t.GetStart())),
        "end_mm": _pt(_try(lambda: t.GetEnd())),
        "width_mm": _try(lambda: _to_mm(t.GetWidth())),
        "net_name": _try(lambda: t.GetNetname(), ""),
        "layer": _try(lambda: t.GetLayerName()),
    }


def _extract_zone(board, z) -> Dict[str, Any]:
    return {
        "uuid": _uuid_of(z),
        "net_name": _try(lambda: z.GetNetname(), ""),
        "layer": _try(lambda: z.GetLayerName()),
        "priority": _try(lambda: z.GetAssignedPriority(), 0),
        "is_filled": _try(lambda: bool(z.IsFilled()), False),
        "clearance_mm": _try(lambda: _to_mm(z.GetLocalClearance())),
        "min_thickness_mm": _try(lambda: _to_mm(z.GetMinThickness())),
    }


def _extract_design_rules(board) -> Dict[str, Any]:
    ds = _try(lambda: board.GetDesignSettings())
    if not ds:
        return {}
    return {
        "min_clearance_mm": _try(lambda: _to_mm(ds.m_MinClearance)),
        "min_track_width_mm": _try(lambda: _to_mm(ds.m_TrackMinWidth)),
        "min_via_diameter_mm": _try(lambda: _to_mm(ds.m_ViasMinSize)),
        "min_via_drill_mm": _try(lambda: _to_mm(ds.m_MinThroughDrill)),
        "copper_edge_clearance_mm": _try(lambda: _to_mm(ds.m_CopperEdgeClearance)),
        "board_thickness_mm": _try(lambda: _to_mm(ds.GetBoardThickness())),
    }


def _fingerprint(state: dict) -> str:
    raw = json.dumps(state, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def get_board_state(project_dir: str | Path, mode: str = "summary") -> Dict[str, Any]:
    """Extract structured board state from .kicad_pcb.

    Args:
        project_dir: Path to the KiCad project directory.
        mode: 'summary' (footprints + nets + rules, no track geometry) or
              'full' (everything including individual tracks/vias/zones).

    Returns:
        Complete board state dict with fingerprint hash.
    """
    try:
        import pcbnew
    except ImportError:
        kicad_python = load_kicad_python()
        root_pkg = Path(__file__).resolve().parents[2]
        payload = json.dumps({"project_dir": str(project_dir), "mode": mode})
        runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.inspector import get_board_state
kwargs = json.loads(r'''{payload}''')
res = get_board_state(**kwargs)
print("INSPECT_SUB_RESULT:" + json.dumps(res))
"""
        proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            if line.startswith("INSPECT_SUB_RESULT:"):
                return json.loads(line.replace("INSPECT_SUB_RESULT:", ""))
        return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}

    proj = Path(project_dir).resolve()
    pcb_files = list(proj.glob("*.kicad_pcb"))
    if not pcb_files:
        return {"success": False, "error": f"No .kicad_pcb file found in {proj}"}

    import gc
    gc.collect()
    pcb_file = pcb_files[0]
    board = pcbnew.LoadBoard(str(pcb_file))

    # Board outline bounds
    import pcbnew as _pcb
    poly = _pcb.SHAPE_POLY_SET()
    has_outline = _try(lambda: board.GetBoardPolygonOutlines(poly, True), False)
    board_bounds = None
    if has_outline and poly.OutlineCount():
        bb = poly.BBox()
        board_bounds = {
            "x0": _to_mm(bb.GetLeft()), "y0": _to_mm(bb.GetTop()),
            "x1": _to_mm(bb.GetRight()), "y1": _to_mm(bb.GetBottom()),
            "w": _to_mm(bb.GetWidth()), "h": _to_mm(bb.GetHeight())
        }
    else:
        edge_drawings = [d for d in board.GetDrawings() if d.GetLayer() == _pcb.Edge_Cuts]
        if edge_drawings:
            x0 = min(d.GetBoundingBox().GetLeft() for d in edge_drawings)
            y0 = min(d.GetBoundingBox().GetTop() for d in edge_drawings)
            x1 = max(d.GetBoundingBox().GetRight() for d in edge_drawings)
            y1 = max(d.GetBoundingBox().GetBottom() for d in edge_drawings)
            board_bounds = {
                "x0": _to_mm(x0), "y0": _to_mm(y0),
                "x1": _to_mm(x1), "y1": _to_mm(y1),
                "w": _to_mm(x1 - x0), "h": _to_mm(y1 - y0)
            }
        else:
            bbox = board.ComputeBoundingBox()
            board_bounds = {
                "x0": _to_mm(bbox.GetX()), "y0": _to_mm(bbox.GetY()),
                "x1": _to_mm(bbox.GetX() + bbox.GetWidth()), "y1": _to_mm(bbox.GetY() + bbox.GetHeight()),
                "w": _to_mm(bbox.GetWidth()), "h": _to_mm(bbox.GetHeight())
            }

    # Nets
    nets = {}
    for code, net in board.GetNetsByNetcode().items():
        name = net.GetNetname()
        if name:
            nets[name] = {"code": code, "name": name}

    # Footprints (always included)
    footprints = [_extract_footprint(board, fp) for fp in board.GetFootprints()]

    state = {
        "success": True,
        "pcb_file": str(pcb_file),
        "mode": mode,
        "board_bounds_mm": board_bounds,
        "board_bounds": board_bounds,
        "outline_closed": has_outline and board_bounds is not None,
        "net_count": len(nets),
        "nets": nets,
        "footprint_count": len(footprints),
        "footprints": footprints,
        "design_rules": _extract_design_rules(board),
    }

    # Full mode: include tracks, vias, zones
    if mode == "full":
        tracks_vias = [_extract_track(board, t) for t in board.GetTracks()]
        state["tracks"] = [t for t in tracks_vias if t["type"] == "track"]
        state["vias"] = [t for t in tracks_vias if t["type"] == "via"]
        state["track_count"] = len(state["tracks"])
        state["via_count"] = len(state["vias"])
        state["zones"] = [_extract_zone(board, z) for z in board.Zones()]
        state["zone_count"] = len(state["zones"])
    else:
        state["track_count"] = len(list(board.GetTracks()))
        state["zone_count"] = len(list(board.Zones()))

    state["fingerprint"] = _fingerprint(state)

    # Write to kaibridge_dump/
    dump_dir = proj / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    out_path = dump_dir / f"board_state_{mode}.json"
    out_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    state["state_file"] = str(out_path)

    del board
    import gc
    gc.collect()
    return state

