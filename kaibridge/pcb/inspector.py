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
import math
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
    except (AttributeError, TypeError, KeyError, ValueError, RuntimeError):
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
    if proj.is_file() and proj.suffix == ".kicad_pcb":
        pcb_file = proj
        proj = proj.parent
    else:
        pcb_files = list(proj.glob("*.kicad_pcb"))
        if not pcb_files:
            return {"success": False, "error": f"No .kicad_pcb file found in {proj}"}
        pcb_file = pcb_files[0]

    import gc
    gc.collect()
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


def get_spatial_occupancy(
    project_dir: str | Path,
    grid_step: float = 0.5,
    margin: float = 1.5,
    clearance: float = 0.5
) -> Dict[str, Any]:
    """Calculates physical component dimensions, 2D board occupancy grid, and
    identifies maximal contiguous free rectangular pockets available for component placement.
    """
    state = get_board_state(project_dir, mode="summary")
    if not state.get("success"):
        return state

    bounds = state.get("board_bounds_mm") or {}
    if not bounds or bounds.get("w", 0) <= 0 or bounds.get("h", 0) <= 0:
        return {"success": False, "error": "No valid board outline (Edge.Cuts) found."}

    x0 = bounds["x0"]
    y0 = bounds["y0"]
    x1 = bounds["x1"]
    y1 = bounds["y1"]
    bw = bounds["w"]
    bh = bounds["h"]

    # Component geometry catalog
    components = {}
    fps = state.get("footprints", [])
    for fp in fps:
        ref = fp.get("reference")
        if not ref:
            continue
        c_box = fp.get("courtyard_mm")
        pos = fp.get("position_mm") or {"x": 0.0, "y": 0.0}
        if c_box:
            w = c_box.get("w", 2.0)
            h = c_box.get("h", 2.0)
            box = [
                c_box.get("x0", pos["x"] - w / 2.0),
                c_box.get("y0", pos["y"] - h / 2.0),
                c_box.get("x1", pos["x"] + w / 2.0),
                c_box.get("y1", pos["y"] + h / 2.0)
            ]
        else:
            w = 2.5
            h = 2.5
            box = [pos["x"] - w / 2.0, pos["y"] - h / 2.0, pos["x"] + w / 2.0, pos["y"] + h / 2.0]

        is_on_board = not (box[2] < x0 or box[0] > x1 or box[3] < y0 or box[1] > y1)
        components[ref] = {
            "reference": ref,
            "value": fp.get("value", ""),
            "width_mm": round(w, 2),
            "height_mm": round(h, 2),
            "position_mm": pos,
            "rotation_deg": fp.get("rotation_deg", 0.0),
            "is_locked": fp.get("is_locked", False),
            "on_board": is_on_board,
            "bbox_mm": [round(b, 2) for b in box]
        }

    # Board inner envelope
    bx0 = x0 + margin
    by0 = y0 + margin
    bx1 = x1 - margin
    by1 = y1 - margin

    if bx1 <= bx0 or by1 <= by0:
        return {"success": False, "error": f"Board too small for margin={margin}mm"}

    cols = max(1, int(round((bx1 - bx0) / grid_step)))
    rows = max(1, int(round((by1 - by0) / grid_step)))

    occ = [[False for _ in range(cols)] for _ in range(rows)]

    # Mark occupied cells (only for components on board)
    for comp in components.values():
        if not comp.get("on_board", True):
            continue
        cb = comp["bbox_mm"]
        min_c = max(0, int(math.floor((cb[0] - clearance / 2.0 - bx0) / grid_step)))
        max_c = min(cols - 1, int(math.ceil((cb[2] + clearance / 2.0 - bx0) / grid_step)))
        min_r = max(0, int(math.floor((cb[1] - clearance / 2.0 - by0) / grid_step)))
        max_r = min(rows - 1, int(math.ceil((cb[3] + clearance / 2.0 - by0) / grid_step)))
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                occ[r][c] = True

    total_cells = rows * cols
    occupied_cells = sum(sum(1 for c in row if c) for row in occ)
    free_cells = total_cells - occupied_cells
    board_area = round(bw * bh, 2)
    inner_area = round((bx1 - bx0) * (by1 - by0), 2)
    occ_pct = round((occupied_cells / total_cells) * 100.0, 1)

    # Maximal Empty Rectangles using histogram method
    heights = [0] * cols
    candidate_rects = []
    min_cells = max(1, int(2.0 / grid_step))
    for r in range(rows):
        for c in range(cols):
            if not occ[r][c]:
                heights[c] += 1
            else:
                heights[c] = 0

        stack = []
        for c in range(cols + 1):
            h_val = heights[c] if c < cols else 0
            start = c
            while stack and stack[-1][1] > h_val:
                prev_idx, prev_h = stack.pop()
                w_cells = c - prev_idx
                if w_cells >= min_cells and prev_h >= min_cells:
                    top_r = r - prev_h + 1
                    area_cells = w_cells * prev_h
                    candidate_rects.append((area_cells, prev_idx, top_r, w_cells, prev_h))
                start = prev_idx
            stack.append((start, h_val))

    # Sort candidates by area descending and filter overlapping
    candidate_rects.sort(key=lambda x: x[0], reverse=True)
    claimed = [[False for _ in range(cols)] for _ in range(rows)]
    free_pockets = []

    for area_cells, c_start, r_start, w_cells, h_cells in candidate_rects:
        overlap_cnt = 0
        for r in range(r_start, r_start + h_cells):
            for c in range(c_start, c_start + w_cells):
                if claimed[r][c]:
                    overlap_cnt += 1
        overlap_ratio = overlap_cnt / area_cells
        if overlap_ratio > 0.25:
            continue

        for r in range(r_start, r_start + h_cells):
            for c in range(c_start, c_start + w_cells):
                claimed[r][c] = True

        px0 = round(bx0 + c_start * grid_step, 2)
        py0 = round(by0 + r_start * grid_step, 2)
        pw = round(w_cells * grid_step, 2)
        ph = round(h_cells * grid_step, 2)
        free_pockets.append({
            "x0": px0,
            "y0": py0,
            "x1": round(px0 + pw, 2),
            "y1": round(py0 + ph, 2),
            "width_mm": pw,
            "height_mm": ph,
            "area_mm2": round(pw * ph, 2)
        })
        if len(free_pockets) >= 8:
            break

    return {
        "success": True,
        "board_file": state.get("pcb_file"),
        "board_bounds_mm": bounds,
        "occupancy_stats": {
            "board_area_mm2": board_area,
            "inner_routable_area_mm2": inner_area,
            "occupied_percentage": occ_pct,
            "free_percentage": round(100.0 - occ_pct, 1),
            "grid_step_mm": grid_step
        },
        "components": components,
        "free_pockets": free_pockets
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Live KiCad PCB State Inspector")
    ap.add_argument("project_dir", help="Path to KiCad project directory or .kicad_pcb file")
    ap.add_argument("--summary", action="store_true", default=True, help="Extract summary state (footprints, nets, rules; default)")
    ap.add_argument("--full", action="store_true", help="Extract full state (including all individual tracks, vias, zones)")
    ap.add_argument("--free-space", action="store_true", help="Analyze board spatial occupancy and report maximal free rectangular pockets")
    ap.add_argument("--audit", "--route-ready", dest="audit", action="store_true", help="Execute fail-closed Gatekeeper Route-Readiness Proof (placement audit)")
    ap.add_argument("--json", action="store_true", help="Output raw JSON instead of human-readable summary")
    args = ap.parse_args(argv)

    mode = "full" if args.full else "summary"
    proj_path = Path(args.project_dir).expanduser().resolve()

    if proj_path.is_file() and proj_path.suffix == ".kicad_pcb":
        proj_dir = proj_path.parent
    else:
        proj_dir = proj_path

    if not proj_dir.is_dir():
        print(f"Error: {proj_dir} is not a directory.", file=sys.stderr)
        return 1

    if args.audit:
        from .gatekeeper import placement_audit
        res = placement_audit(proj_dir)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print("\n================================================================================================")
            print(" [KAIBRIDGE GATEKEEPER ROUTE-READINESS PROOF]")
            print("================================================================================================")
            print(f"  Project           : {proj_dir.name}")
            print(f"  Outline Closed    : {res.get('outline_closed')}")
            print(f"  Overlap Count     : {res.get('overlap_count')}")
            print(f"  Outside Outline   : {res.get('outside_outline_count')}")
            missing_nc = res.get('netclasses_without_track_width', [])
            print(f"  Missing Netclasses: {missing_nc if missing_nc else 'None (All configured)'}")
            ready = res.get('route_ready', False)
            print(f"  Route Readiness   : {'[VERIFIED - ROUTE READY]' if ready else '[FAIL - NOT READY]'}")
            print("================================================================================================\n")
        return 0 if res.get('route_ready') else 1

    if args.free_space:
        res = get_spatial_occupancy(proj_dir)
        if not res.get("success"):
            print(f"[-] Error calculating spatial occupancy: {res.get('error')}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(res, indent=2, default=str))
            return 0

        bounds = res.get("board_bounds_mm") or {}
        stats = res.get("occupancy_stats") or {}
        pockets = res.get("free_pockets") or []
        comps = res.get("components") or {}

        print("\n=======================================================")
        print(f"   KAIBRIDGE 2D SPATIAL OCCUPANCY & FREE SPACE: {proj_dir.name}")
        print("=======================================================")
        print(f"  Board Dimensions : {bounds.get('w', 0.0):.2f} mm x {bounds.get('h', 0.0):.2f} mm")
        print(f"  Total Area       : {stats.get('board_area_mm2', 0.0):.1f} mm²")
        print(f"  Routable Area    : {stats.get('inner_routable_area_mm2', 0.0):.1f} mm²")
        print(f"  Occupied Density : {stats.get('occupied_percentage', 0.0)}% (Courtyards + 0.5mm buffers)")
        print(f"  Free Space Ratio : {stats.get('free_percentage', 0.0)}%")
        print(f"  Total Footprints : {len(comps)}")

        print("\n--- Available Free Rectangular Pockets (Sorted by Area) ---")
        if pockets:
            print(f"  {'#':<3} {'Origin (X, Y) mm':<22} {'Size (W x H) mm':<20} {'Area mm²':<12} {'Fit Guide'}")
            print("  " + "-" * 78)
            for idx, p in enumerate(pockets, 1):
                pos_str = f"({p['x0']:.1f}, {p['y0']:.1f})"
                dim_str = f"{p['width_mm']:.1f} x {p['height_mm']:.1f} mm"
                area_str = f"{p['area_mm2']:.1f} mm²"
                guide = "Large IC / Dense Cluster" if p['area_mm2'] >= 150 else ("Small IC / Passives" if p['area_mm2'] >= 50 else "Local Passives")
                print(f"  {idx:<3} {pos_str:<22} {dim_str:<20} {area_str:<12} {guide}")
        else:
            print("  [!] No large free pockets found (High component density).")

        print("\n--- Component Geometry Catalog ---")
        print(f"  {'Ref':<8} {'Value':<16} {'Size (W x H) mm':<16} {'Pos (X, Y) mm':<18} {'Locked':<8} {'Status'}")
        print("  " + "-" * 80)
        for ref in sorted(comps.keys()):
            c = comps[ref]
            val = str(c.get("value", ""))[:15]
            dim_str = f"{c.get('width_mm', 0.0):.1f} x {c.get('height_mm', 0.0):.1f} mm"
            p = c.get("position_mm") or {}
            pos_str = f"({p.get('x', 0.0):.1f}, {p.get('y', 0.0):.1f})"
            locked = "YES" if c.get("is_locked") else "NO"
            status = "ON BOARD" if c.get("on_board") else "STAGING"
            print(f"  {ref:<8} {val:<16} {dim_str:<16} {pos_str:<18} {locked:<8} {status}")
        print("")
        return 0

    res = get_board_state(proj_dir, mode=mode)

    if not res.get("success"):
        print(f"[-] Error extracting board state: {res.get('error')}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0

    bounds = res.get("board_bounds_mm") or {}
    print("\n=======================================================")
    print(f"   KAIBRIDGE LIVE BOARD STATE INSPECTOR: {proj_dir.name}")
    print("=======================================================")
    print(f"  PCB File      : {res.get('pcb_file')}")
    print(f"  Mode          : {res.get('mode', mode).upper()}")
    print(f"  Fingerprint   : {res.get('fingerprint')}")
    if bounds:
        print(f"  Board Size    : {bounds.get('w', 0.0):.2f} mm x {bounds.get('h', 0.0):.2f} mm")
        print(f"  Coordinates   : X=[{bounds.get('x0', 0.0):.2f} .. {bounds.get('x1', 0.0):.2f}], Y=[{bounds.get('y0', 0.0):.2f} .. {bounds.get('y1', 0.0):.2f}]")
    print(f"  Outline Closed: {'YES' if res.get('outline_closed') else 'NO'}")
    print(f"  Footprints    : {res.get('footprint_count', 0)}")
    print(f"  Active Nets   : {res.get('net_count', 0)}")
    print(f"  Tracks        : {res.get('track_count', 0)}")
    if mode == "full":
        print(f"  Vias          : {res.get('via_count', 0)}")
    print(f"  Zones         : {res.get('zone_count', 0)}")

    rules = res.get("design_rules", {})
    if rules:
        print("\n--- Design Rules ---")
        for k, v in rules.items():
            if v is not None:
                print(f"  {k:25}: {v}")

    fps = res.get("footprints", [])
    if fps:
        print("\n--- Placed Footprints ---")
        print(f"  {'Ref':<8} {'Value':<18} {'Pos (X, Y) mm':<22} {'Size (W x H)':<14} {'Rot':<6} {'Layer':<8} {'Locked'}")
        print("  " + "-" * 90)
        for fp in sorted(fps, key=lambda x: x.get("reference", "")):
            ref = fp.get("reference", "")
            val = fp.get("value", "")[:17]
            pos = fp.get("position_mm") or {}
            pos_str = f"({pos.get('x', 0.0):.2f}, {pos.get('y', 0.0):.2f})"
            c_box = fp.get("courtyard_mm") or {}
            sz_str = f"{c_box.get('w', 0.0):.1f}x{c_box.get('h', 0.0):.1f}" if c_box else "N/A"
            rot = f"{fp.get('rotation_deg', 0.0):.1f}°"
            layer = fp.get("layer", "")
            locked = "YES" if fp.get("is_locked") else "NO"
            print(f"  {ref:<8} {val:<18} {pos_str:<22} {sz_str:<14} {rot:<6} {layer:<8} {locked}")

    print(f"\n[+] Complete state cached at: {res.get('state_file')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())




