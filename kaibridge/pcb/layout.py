"""Kaibridge Operations Engine (layout.py)
Executes structured layout operations on KiCad PCB:
footprint placement, rotation, locking, deletion, Edge.Cuts outlines,
tracks, vias, and copper zones with 0.5mm clean quantization.
"""
import os
import sys
import json
import math
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from ..core.paths import load_kicad_python


def apply_ops(
    project_dir: str | Path,
    ops_data: Dict[str, Any] | List[Dict[str, Any]] | str | Path,
    dry_run: bool = False,
    shove: bool = False
) -> Dict[str, Any]:
    """Applies a list of layout operations defined in ops.json or a dictionary/list.
    If dry_run is True, simulates all operations in memory and runs a collision audit without writing to disk.
    If shove is True, automatically activates elastic Component Push-and-Shove collision relaxation.
    """
    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        return {"success": False, "error": f"Project directory not found: {project_dir}"}

    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    if isinstance(ops_data, (str, Path)):
        ops_path = Path(ops_data)
        if ops_path.exists():
            with open(ops_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        else:
            raw = json.loads(str(ops_data))
    elif isinstance(ops_data, dict):
        raw = ops_data
    elif isinstance(ops_data, list):
        raw = {"ops": ops_data}
    else:
        return {"success": False, "error": "Invalid ops data format."}

    is_dry = dry_run or (isinstance(raw, dict) and bool(raw.get("dry_run", False)))
    ops_list = raw.get("ops", raw.get("operations", [])) if isinstance(raw, dict) else raw
    board_meta = dict(raw.get("board", {})) if isinstance(raw, dict) and isinstance(raw.get("board"), dict) else {}
    if isinstance(raw, dict):
        for key in ("clear_tracks", "unroute_all", "delete_all_tracks", "clear_all_tracks", "unroute", "clear_zones", "remove_zones"):
            if raw.get(key) is not None and key not in board_meta:
                board_meta[key] = raw[key]
    is_shove = shove or (isinstance(raw, dict) and bool(raw.get("shove", False))) or (isinstance(board_meta, dict) and bool(board_meta.get("shove", False)))
    if not is_shove and isinstance(ops_list, list):
        is_shove = any(isinstance(op, dict) and bool(op.get("shove", False)) for op in ops_list)

    try:
        import pcbnew
        return _execute_in_process(pcb_file, ops_list, board_meta, dry_run=is_dry, shove=is_shove)
    except ImportError:
        kicad_python = load_kicad_python()
        dump_dir = proj_path / "kaibridge_dump"
        dump_dir.mkdir(parents=True, exist_ok=True)
        temp_ops = dump_dir / "temp_ops_payload.json"
        temp_ops.write_text(json.dumps({"ops": ops_list, "board": board_meta, "dry_run": is_dry, "shove": is_shove}), encoding="utf-8")
        
        runner = f"""
import sys, json, os, traceback
sys.path.insert(0, r"{str(Path(__file__).resolve().parents[2])}")
from kaibridge.pcb.layout import _execute_in_process
try:
    with open(r"{str(temp_ops)}", "r", encoding="utf-8") as f:
        d = json.load(f)
    res = _execute_in_process(r"{str(pcb_file)}", d.get("ops", []), d.get("board", {{}}), dry_run=d.get("dry_run", False), shove=d.get("shove", False))
    print("APPLY_OPS_RESULT:" + json.dumps(res), flush=True)
except Exception as e:
    print("APPLY_OPS_ERROR:" + json.dumps({{"error": traceback.format_exc()}}), flush=True)
finally:
    os._exit(0)
"""
        res_sub = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True)
        if temp_ops.exists():
            try:
                temp_ops.unlink()
            except Exception:
                pass
        for line in res_sub.stdout.splitlines():
            if line.startswith("APPLY_OPS_RESULT:"):
                return json.loads(line.replace("APPLY_OPS_RESULT:", ""))
            if line.startswith("APPLY_OPS_ERROR:"):
                try:
                    err_payload = json.loads(line.replace("APPLY_OPS_ERROR:", ""))
                    return {"success": False, "error": err_payload.get("error", "Unknown subprocess error")}
                except Exception:
                    return {"success": False, "error": line.replace("APPLY_OPS_ERROR:", "")}
        return {"success": False, "error": res_sub.stderr.strip() or res_sub.stdout.strip()}


def _get_board_bounds(board) -> Tuple[float, float, float, float]:
    """Returns (origin_x_mm, origin_y_mm, width_mm, height_mm) from Edge.Cuts drawings."""
    import pcbnew
    edge_drawings = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    if edge_drawings:
        x0 = min(d.GetBoundingBox().GetLeft() for d in edge_drawings) / 1e6
        y0 = min(d.GetBoundingBox().GetTop() for d in edge_drawings) / 1e6
        x1 = max(d.GetBoundingBox().GetRight() for d in edge_drawings) / 1e6
        y1 = max(d.GetBoundingBox().GetBottom() for d in edge_drawings) / 1e6
        return (x0, y0, x1 - x0, y1 - y0)
    bb = board.ComputeBoundingBox()
    x0 = bb.GetX() / 1e6
    y0 = bb.GetY() / 1e6
    x1 = (bb.GetX() + bb.GetWidth()) / 1e6
    y1 = (bb.GetY() + bb.GetHeight()) / 1e6
    return (x0, y0, max(10.0, x1 - x0), max(10.0, y1 - y0))


def apply_component_push_and_shove(
    board,
    moved_refs: List[str],
    clearance: float = 0.5,
    margin: float = 1.5,
    max_iterations: int = 50
) -> Dict[str, Any]:
    """Elastic Component Push-and-Shove Collision Relaxation.
    When component A is placed/moved and collides with unlocked component B,
    B is elastically shoved along the minimum penetration vector into free space.
    If B collides with C, the shove cascades to C (ripple effect).
    Components with locked=True are immovable bedrock and cannot be displaced.
    All shoved positions are clamped inside board margins and snapped to the 0.5mm grid.
    """
    import pcbnew

    edge_drawings = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    if edge_drawings:
        x0 = min(d.GetBoundingBox().GetLeft() for d in edge_drawings) / 1e6
        y0 = min(d.GetBoundingBox().GetTop() for d in edge_drawings) / 1e6
        x1 = max(d.GetBoundingBox().GetRight() for d in edge_drawings) / 1e6
        y1 = max(d.GetBoundingBox().GetBottom() for d in edge_drawings) / 1e6
    else:
        bb = board.ComputeBoundingBox()
        x0 = bb.GetX() / 1e6
        y0 = bb.GetY() / 1e6
        x1 = (bb.GetX() + bb.GetWidth()) / 1e6
        y1 = (bb.GetY() + bb.GetHeight()) / 1e6

    min_x = x0 + margin
    max_x = x1 - margin
    min_y = y0 + margin
    max_y = y1 - margin

    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if not fps:
        return {"shove_applied": False, "displaced_count": 0, "displaced": []}

    def _extract_box(fp):
        pos = fp.GetPosition()
        ox = pos.x / 1e6
        oy = pos.y / 1e6
        c_box = None
        if hasattr(fp, "GetCourtyard"):
            for l in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                try:
                    poly = fp.GetCourtyard(l)
                    if poly and not poly.IsEmpty():
                        c_box = poly.BBox()
                        break
                except Exception:
                    pass
        if c_box:
            bw = c_box.GetWidth() / 1e6
            bh = c_box.GetHeight() / 1e6
            cx = c_box.GetCenter().x / 1e6
            cy = c_box.GetCenter().y / 1e6
        else:
            pad_boxes = [pad.GetBoundingBox() for pad in fp.Pads()]
            if pad_boxes:
                px0 = min(pad_b.GetLeft() for pad_b in pad_boxes) / 1e6
                px1 = max(pad_b.GetRight() for pad_b in pad_boxes) / 1e6
                py0 = min(pad_b.GetTop() for pad_b in pad_boxes) / 1e6
                py1 = max(pad_b.GetBottom() for pad_b in pad_boxes) / 1e6
                bw = max(px1 - px0, 1.2)
                bh = max(py1 - py0, 1.2)
                cx = (px0 + px1) / 2.0
                cy = (py0 + py1) / 2.0
            else:
                bb = fp.GetBoundingBox()
                bw = bb.GetWidth() / 1e6
                bh = bb.GetHeight() / 1e6
                cx = bb.GetCenter().x / 1e6
                cy = bb.GetCenter().y / 1e6
        bw = max(bw, 1.2)
        bh = max(bh, 1.2)
        off_x = cx - ox
        off_y = cy - oy
        return {
            "ox": ox, "oy": oy,
            "cx": cx, "cy": cy,
            "off_x": off_x, "off_y": off_y,
            "w": bw, "h": bh,
            "locked": bool(fp.IsLocked())
        }

    state = {ref: _extract_box(fp) for ref, fp in fps.items()}
    initial_positions = {ref: (d["ox"], d["oy"]) for ref, d in state.items()}

    active_shove_occurred = False
    def _is_on_board(b_box, ref_name):
        if ref_name in moved_refs:
            return True
        return (b_box["cx"] >= x0 - 1.0 and b_box["cx"] <= x1 + 1.0 and
                b_box["cy"] >= y0 - 1.0 and b_box["cy"] <= y1 + 1.0)

    for iteration in range(max_iterations):
        overlap_found = False
        refs = list(state.keys())

        for i in range(len(refs)):
            rA = refs[i]
            bA = state[rA]
            if not _is_on_board(bA, rA):
                continue
            for j in range(i + 1, len(refs)):
                rB = refs[j]
                bB = state[rB]
                if not _is_on_board(bB, rB):
                    continue

                dx = bB["cx"] - bA["cx"]
                dy = bB["cy"] - bA["cy"]
                pen_x = (bA["w"] / 2.0 + bB["w"] / 2.0 + clearance) - abs(dx)
                pen_y = (bA["h"] / 2.0 + bB["h"] / 2.0 + clearance) - abs(dy)

                if pen_x > 0.05 and pen_y > 0.05:
                    overlap_found = True
                    active_shove_occurred = True

                    lockA = bA["locked"]
                    lockB = bB["locked"]
                    if lockA and lockB:
                        continue

                    push_axis_x = pen_x < pen_y

                    if lockA:
                        shove_ref = rB
                        push_dir_x = 1.0 if dx >= 0 else -1.0
                        push_dir_y = 1.0 if dy >= 0 else -1.0
                    elif lockB:
                        shove_ref = rA
                        push_dir_x = -1.0 if dx >= 0 else 1.0
                        push_dir_y = -1.0 if dy >= 0 else 1.0
                    else:
                        if rA in moved_refs and rB not in moved_refs:
                            shove_ref = rB
                            push_dir_x = 1.0 if dx >= 0 else -1.0
                            push_dir_y = 1.0 if dy >= 0 else -1.0
                        elif rB in moved_refs and rA not in moved_refs:
                            shove_ref = rA
                            push_dir_x = -1.0 if dx >= 0 else 1.0
                            push_dir_y = -1.0 if dy >= 0 else 1.0
                        else:
                            shove_ref = None
                            sign_x = 1.0 if dx >= 0 else -1.0
                            sign_y = 1.0 if dy >= 0 else -1.0
                            shift_x = (pen_x / 2.0 + 0.25) * sign_x
                            shift_y = (pen_y / 2.0 + 0.25) * sign_y
                            if push_axis_x:
                                bB["cx"] += shift_x
                                bA["cx"] -= shift_x
                            else:
                                bB["cy"] += shift_y
                                bA["cy"] -= shift_y

                    if shove_ref:
                        target = state[shove_ref]
                        dist_x = (pen_x + 0.4) * push_dir_x
                        dist_y = (pen_y + 0.4) * push_dir_y

                        if push_axis_x:
                            test_x = target["cx"] + dist_x
                            if test_x - target["w"] / 2.0 < min_x or test_x + target["w"] / 2.0 > max_x:
                                push_axis_x = False

                        if push_axis_x:
                            target["cx"] += dist_x
                        else:
                            target["cy"] += dist_y

                    for r in (rA, rB):
                        if not state[r]["locked"]:
                            state[r]["cx"] = max(min_x + state[r]["w"] / 2.0, min(max_x - state[r]["w"] / 2.0, state[r]["cx"]))
                            state[r]["cy"] = max(min_y + state[r]["h"] / 2.0, min(max_y - state[r]["h"] / 2.0, state[r]["cy"]))

        if not overlap_found:
            break

    displaced_summary = []
    for ref, b_data in state.items():
        if b_data["locked"]:
            continue
        init_ox, init_oy = initial_positions[ref]
        # Reconstruct footprint origin from displaced courtyard center
        new_ox = b_data["cx"] - b_data["off_x"]
        new_oy = b_data["cy"] - b_data["off_y"]
        qx = round(new_ox * 2.0) / 2.0
        qy = round(new_oy * 2.0) / 2.0

        if abs(qx - init_ox) > 0.05 or abs(qy - init_oy) > 0.05:
            fp = fps[ref]
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(qx), pcbnew.FromMM(qy)))
            displaced_summary.append({
                "ref": ref,
                "from": [round(init_ox, 2), round(init_oy, 2)],
                "to": [round(qx, 2), round(qy, 2)],
                "delta_mm": [round(qx - init_ox, 2), round(qy - init_oy, 2)]
            })

    return {
        "shove_applied": active_shove_occurred,
        "displaced_count": len(displaced_summary),
        "displaced": displaced_summary
    }



def _execute_in_process(
    pcb_path: str | Path,
    ops: List[Dict[str, Any]],
    board_meta: Dict[str, Any],
    dry_run: bool = False,
    shove: bool = False
) -> Dict[str, Any]:
    import pcbnew
    b = pcbnew.LoadBoard(str(pcb_path))
    applied = 0
    errors = []
    moved_refs = []

    # Clear options if requested (use b.Delete to avoid SWIG type table corruption)
    if board_meta.get("clear_edge_cuts"):
        for drw in list(b.GetDrawings()):
            if drw.GetLayer() == pcbnew.Edge_Cuts:
                b.Delete(drw)
                applied += 1
    if any(board_meta.get(k) for k in ("clear_tracks", "unroute_all", "delete_all_tracks", "clear_all_tracks", "unroute")):
        for t in list(b.GetTracks()):
            b.Delete(t)
            applied += 1
    if any(board_meta.get(k) for k in ("clear_zones", "remove_zones")):
        for z in list(b.Zones()):
            b.Delete(z)
            applied += 1

    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}

    for op in ops:
        action = op.get("op", op.get("action", ""))
        ref = op.get("ref", "")

        # 1. Place / Move Footprint
        if action in ("footprint.place", "place", "fp_place", "footprint.move", "move", "item.place", "item.move", "set_pos"):
            fp = fps.get(ref)
            if fp:
                if op.get("shove"):
                    shove = True
                if ref:
                    moved_refs.append(ref)
                if "pos" in op and isinstance(op["pos"], (list, tuple)) and len(op["pos"]) >= 2:
                    x = float(op["pos"][0])
                    y = float(op["pos"][1])
                else:
                    x = float(op.get("x", op.get("x_mm", 0.0)))
                    y = float(op.get("y", op.get("y_mm", 0.0)))
                # 0.5mm clean quantization
                x = round(x * 2.0) / 2.0
                y = round(y * 2.0) / 2.0
                fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))

                # Set rotation ONLY if explicitly requested (preserves existing rotation otherwise)
                if "rot" in op or "rotation" in op or "angle" in op:
                    rot = float(op.get("rot", op.get("rotation", op.get("angle", 0.0))))
                    fp.SetOrientationDegrees(rot)

                # Flip layer if specified (e.g. B.Cu vs F.Cu)
                if op.get("layer"):
                    want_back = str(op["layer"]).lower().startswith("b.")
                    if bool(fp.IsFlipped()) != want_back:
                        fp.Flip(fp.GetPosition(), False)

                if "locked" in op:
                    fp.SetLocked(bool(op["locked"]))
                applied += 1
            else:
                errors.append(f"Footprint {ref} not found on board")

        # 1.5. Array Placement (Linear sequence of footprints along X or Y axis)
        elif action in ("array.place", "footprint.array", "place_array", "array"):
            refs = op.get("refs", [])
            start_x = float(op.get("start_x", op.get("x", 0.0)))
            start_y = float(op.get("start_y", op.get("y", 0.0)))
            pitch_x = float(op.get("pitch_x", 0.0))
            pitch_y = float(op.get("pitch_y", 0.0))
            axis = str(op.get("axis", "X")).upper()
            pitch = float(op.get("pitch", 0.0))
            if pitch != 0.0:
                if axis == "X":
                    pitch_x = pitch
                else:
                    pitch_y = pitch
            rot = float(op.get("rot", op.get("rotation", op.get("angle", 0.0)))) if ("rot" in op or "rotation" in op or "angle" in op) else None
            locked = bool(op.get("locked", False))

            for i, r in enumerate(refs):
                fp = fps.get(r)
                if fp:
                    cur_x = round((start_x + i * pitch_x) * 2.0) / 2.0
                    cur_y = round((start_y + i * pitch_y) * 2.0) / 2.0
                    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cur_x), pcbnew.FromMM(cur_y)))
                    if rot is not None:
                        fp.SetOrientationDegrees(rot)
                    if "locked" in op:
                        fp.SetLocked(locked)
                    applied += 1
                else:
                    errors.append(f"Footprint {r} not found on board")

        # 2. Rotate Footprint
        elif action in ("footprint.rotate", "rotate", "fp_rotate"):
            fp = fps.get(ref)
            if fp:
                rot = float(op.get("rot", op.get("rotation", op.get("angle", op.get("deg", 0.0)))))
                if op.get("relative", False):
                    cur_rot = fp.GetOrientationDegrees()
                    fp.SetOrientationDegrees(cur_rot + rot)
                else:
                    fp.SetOrientationDegrees(rot)
                applied += 1

        # 3. Lock / Unlock Footprint
        elif action in ("footprint.lock", "lock"):
            fp = fps.get(ref)
            if fp:
                fp.SetLocked(bool(op.get("locked", True)))
                applied += 1
        elif action in ("footprint.unlock", "unlock"):
            fp = fps.get(ref)
            if fp:
                fp.SetLocked(False)
                applied += 1

        # 3.5. Set Footprint Field (value, LCSC, etc.)
        elif action in ("footprint.field", "set_field", "fp_field"):
            fp = fps.get(ref)
            if fp:
                field_name = op.get("field", op.get("name", ""))
                field_value = str(op.get("value", ""))
                if field_name.lower() == "value":
                    fp.SetValue(field_value)
                elif field_name.lower() == "reference":
                    fp.SetReference(field_value)
                else:
                    if hasattr(fp, "SetField"):
                        fp.SetField(field_name, field_value)
                    else:
                        found = False
                        for fld in fp.GetFields():
                            if fld.GetName() == field_name:
                                fld.SetText(field_value)
                                found = True
                                break
                applied += 1

        # 4. Delete Footprint
        elif action in ("item.delete", "delete", "footprint.delete", "fp_delete", "remove_part"):
            fp = fps.get(ref)
            if fp:
                b.Delete(fp)
                del fps[ref]
                applied += 1

        # 5. Set Board Size / Edge Cuts
        elif action in ("board.set_size", "set_size", "add_edge_cuts", "set_board_outline"):
            w = float(op.get("width", op.get("width_mm", 50.0)))
            h = float(op.get("height", op.get("height_mm", 40.0)))
            if any(k in op for k in ("center_x_mm", "center_y_mm", "center_x", "center_y", "cx", "cy")):
                cx = float(op.get("center_x_mm", op.get("center_x", op.get("cx", w / 2.0))))
                cy = float(op.get("center_y_mm", op.get("center_y", op.get("cy", h / 2.0))))
                ox = cx - w / 2.0
                oy = cy - h / 2.0
            else:
                ox = float(op.get("origin_x", op.get("origin_x_mm", op.get("x", 0.0))))
                oy = float(op.get("origin_y", op.get("origin_y_mm", op.get("y", 0.0))))
            edge = pcbnew.Edge_Cuts
            for drw in list(b.GetDrawings()):
                if drw.GetLayer() == edge:
                    b.Delete(drw)
            def add_edge_seg(x1, y1, x2, y2):
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                s.SetLayer(edge)
                s.SetWidth(pcbnew.FromMM(0.15))
                s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                b.Add(s)
            add_edge_seg(ox, oy, ox + w, oy)
            add_edge_seg(ox + w, oy, ox + w, oy + h)
            add_edge_seg(ox + w, oy + h, ox, oy + h)
            add_edge_seg(ox, oy + h, ox, oy)
            applied += 1

        # 6. Fit Outline to Footprints
        elif action in ("board.fit_outline", "fit_outline"):
            margin = float(op.get("margin", 5.0))
            edge = pcbnew.Edge_Cuts
            for drw in list(b.GetDrawings()):
                if drw.GetLayer() == edge:
                    b.Delete(drw)
            all_fps = list(b.GetFootprints())
            if all_fps:
                x0 = min(fp.GetBoundingBox().GetLeft() / 1e6 for fp in all_fps) - margin
                y0 = min(fp.GetBoundingBox().GetTop() / 1e6 for fp in all_fps) - margin
                x1 = max(fp.GetBoundingBox().GetRight() / 1e6 for fp in all_fps) + margin
                y1 = max(fp.GetBoundingBox().GetBottom() / 1e6 for fp in all_fps) + margin
                x0 = round(x0 * 2.0) / 2.0
                y0 = round(y0 * 2.0) / 2.0
                x1 = round(x1 * 2.0) / 2.0
                y1 = round(y1 * 2.0) / 2.0
                w = x1 - x0
                h = y1 - y0
                def add_edge_seg(x1, y1, x2, y2):
                    s = pcbnew.PCB_SHAPE(b)
                    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                    s.SetLayer(edge)
                    s.SetWidth(pcbnew.FromMM(0.15))
                    s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                    s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                    b.Add(s)
                add_edge_seg(x0, y0, x0 + w, y0)
                add_edge_seg(x0 + w, y0, x0 + w, y0 + h)
                add_edge_seg(x0 + w, y0 + h, x0, y0 + h)
                add_edge_seg(x0, y0 + h, x0, y0)
                applied += 1

        # 7. Unroute / Clear Tracks / Delete All Tracks / Clear Zones
        elif action in (
            "track.delete_all", "tracks.delete_all", "delete_all_tracks", "clear_all_tracks",
            "tracks.clear", "track.clear", "clear_tracks", "unroute_all", "board.unroute",
            "board.clear_tracks", "net.delete_routing", "unroute_net", "unroute", "ripup",
            "track.delete", "tracks.delete", "zone.delete_all", "zones.delete_all",
            "zone.clear", "zones.clear", "clear_zones", "remove_zones", "zone.delete"
        ):
            target_net = op.get("net")
            target_layer = op.get("layer")
            layer_id = None
            if target_layer == "B.Cu":
                layer_id = pcbnew.B_Cu
            elif target_layer == "F.Cu":
                layer_id = pcbnew.F_Cu
            elif target_layer:
                try:
                    layer_id = b.GetLayerID(target_layer)
                except Exception:
                    layer_id = None

            def _matches_net(item, net_name):
                if not net_name:
                    return True
                try:
                    if hasattr(item, "GetNetname") and item.GetNetname():
                        return item.GetNetname() == net_name
                    if hasattr(item, "GetNet") and item.GetNet():
                        return item.GetNet().GetNetname() == net_name
                    if hasattr(item, "GetNetCode"):
                        nc = item.GetNetCode()
                        net_obj = b.FindNet(nc)
                        if net_obj:
                            return net_obj.GetNetname() == net_name
                except Exception:
                    pass
                return False

            is_zone_only = action in (
                "zone.delete_all", "zones.delete_all", "zone.clear", "zones.clear",
                "clear_zones", "remove_zones", "zone.delete"
            )

            deleted_tracks = 0
            if not is_zone_only:
                for t in list(b.GetTracks()):
                    if _matches_net(t, target_net) and (layer_id is None or t.GetLayer() == layer_id):
                        b.Delete(t)
                        deleted_tracks += 1

            deleted_zones = 0
            if is_zone_only or op.get("remove_zones", False) or op.get("clear_zones", False):
                for z in list(b.Zones()):
                    if _matches_net(z, target_net) and (layer_id is None or z.GetLayer() == layer_id):
                        b.Delete(z)
                        deleted_zones += 1

            applied += 1

        # 8. Add Copper Track
        elif action in ("track.add", "add_track", "track_add"):
            x1 = float(op.get("x1", op.get("start", [0.0, 0.0])[0]))
            y1 = float(op.get("y1", op.get("start", [0.0, 0.0])[1]))
            x2 = float(op.get("x2", op.get("end", [0.0, 0.0])[0]))
            y2 = float(op.get("y2", op.get("end", [0.0, 0.0])[1]))
            width = float(op.get("width", 0.25))
            layer_name = op.get("layer", "F.Cu")
            layer_id = pcbnew.B_Cu if layer_name == "B.Cu" else pcbnew.F_Cu
            track = pcbnew.PCB_TRACK(b)
            track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
            track.SetWidth(pcbnew.FromMM(width))
            track.SetLayer(layer_id)
            if op.get("net"):
                net_obj = b.FindNet(op["net"])
                if net_obj:
                    track.SetNet(net_obj)
            b.Add(track)
            applied += 1

        # 9. Add Via
        elif action in ("via.add", "add_via", "via_add"):
            vx = float(op.get("x", 0.0))
            vy = float(op.get("y", 0.0))
            dia = float(op.get("diameter", op.get("size", 0.6)))
            drill = float(op.get("drill", 0.3))
            via = pcbnew.PCB_VIA(b)
            via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
            via.SetWidth(pcbnew.FromMM(dia))
            via.SetDrill(pcbnew.FromMM(drill))
            if op.get("net"):
                net_obj = b.FindNet(op["net"])
                if net_obj:
                    via.SetNet(net_obj)
            b.Add(via)
            applied += 1

        # 10. Delete Zone
        elif action in ("zone.delete", "zone.remove", "delete_zone", "remove_zone"):
            target_net = op.get("net")
            target_layer = op.get("layer")
            layer_id = pcbnew.B_Cu if target_layer == "B.Cu" else (pcbnew.F_Cu if target_layer == "F.Cu" else None)
            for z in list(b.Zones()):
                z_netname = z.GetNetname() if hasattr(z, "GetNetname") else (z.GetNet().GetNetname() if z.GetNet() else "")
                match_net = not target_net or (z_netname == target_net) or (z.GetNet() and z.GetNet().GetNetname() == target_net)
                match_layer = layer_id is None or z.GetLayer() == layer_id
                if match_net and match_layer:
                    b.Delete(z)
                    applied += 1

        # 11. Refill Zones
        elif action in ("zone.refill", "refill_zones", "refill"):
            try:
                filler = pcbnew.ZONE_FILLER(b)
                filler.Fill(b.Zones())
                applied += 1
            except Exception:
                pass

        # 12. Adjust Track Width
        elif action in ("track.set_width", "set_track_width", "set_width"):
            width = float(op.get("width", op.get("track_width_mm", 0.25)))
            target_net = op.get("net")
            target_netclass = op.get("netclass")
            target_uuid = op.get("uuid")

            target_nets = set()
            if target_net:
                target_nets.add(target_net)
            if target_netclass:
                for nc_code, net in b.GetNetsByNetcode().items():
                    n_obj = b.FindNet(nc_code)
                    if n_obj and hasattr(n_obj, "GetNetClassName") and n_obj.GetNetClassName() == target_netclass:
                        target_nets.add(net.GetNetname())

            for t in list(b.GetTracks()):
                if isinstance(t, pcbnew.PCB_VIA):
                    continue
                t_netname = t.GetNet().GetNetname() if t.GetNet() else ""
                if target_uuid and hasattr(t, "m_Uuid") and str(t.m_Uuid.AsString()) == target_uuid:
                    t.SetWidth(pcbnew.FromMM(width))
                    applied += 1
                elif target_nets and t_netname in target_nets:
                    t.SetWidth(pcbnew.FromMM(width))
                    applied += 1
                elif not target_uuid and not target_nets:
                    t.SetWidth(pcbnew.FromMM(width))
                    applied += 1

        # 13. Prep for Route (Clean orphaned tracks)
        elif action in ("board.prep_for_route", "prep_for_route"):
            for t in list(b.GetTracks()):
                if not t.GetNet() or t.GetNet().GetNetCode() == 0:
                    b.Delete(t)
            applied += 1

        # 14. Silkscreen Sanitation / Clean-up
        elif action in ("silkscreen.sanitize", "sanitize_silk", "silkscreen.hide_all", "silkscreen.hide_values", "clean_silk"):
            silk_mode = op.get("mode", "hide_all" if "hide_all" in action else ("hide_values" if "hide_values" in action else "sanitize"))
            target_ref = op.get("ref")
            target_fps = [fps[target_ref]] if target_ref and target_ref in fps else list(b.GetFootprints())
            for fp in target_fps:
                if silk_mode == "hide_all":
                    fp.Reference().SetVisible(False)
                    fp.Value().SetVisible(False)
                elif silk_mode == "hide_values":
                    fp.Value().SetVisible(False)
                elif silk_mode == "sanitize":
                    fp.Value().SetVisible(False)
                    ref_text = fp.Reference()
                    ref_text.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
                    ref_text.SetTextThickness(pcbnew.FromMM(0.15))
                    ref_bbox = ref_text.GetBoundingBox()
                    collides = False
                    for other_fp in b.GetFootprints():
                        for pad in other_fp.Pads():
                            if ref_bbox.Intersects(pad.GetBoundingBox()):
                                collides = True
                                break
                        if collides:
                            break
                    if collides:
                        ref_text.SetVisible(False)
            applied += 1

        # 15. Hole / Mounting Holes (Single hole or 4 corners)
        elif action in ("hole.add", "add_hole", "mounting_hole.add", "board.mounting_holes", "mounting_holes"):
            drill = float(op.get("drill", op.get("diameter", 3.2)))
            radius = drill / 2.0
            layer_name = op.get("layer", "Edge.Cuts")
            layer_id = pcbnew.Edge_Cuts if "edge" in str(layer_name).lower() else pcbnew.Dwgs_User
            is_corners = bool(op.get("corners", False))
            margin = float(op.get("margin", 3.5))

            hole_coords = []
            if is_corners:
                bx, by, bw, bh = _get_board_bounds(b)
                hole_coords = [
                    (bx + margin, by + margin),
                    (bx + bw - margin, by + margin),
                    (bx + bw - margin, by + bh - margin),
                    (bx + margin, by + bh - margin)
                ]
            else:
                hx = float(op.get("x", op.get("cx", 0.0)))
                hy = float(op.get("y", op.get("cy", 0.0)))
                hole_coords = [(hx, hy)]

            for hx, hy in hole_coords:
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_CIRCLE)
                s.SetLayer(layer_id)
                s.SetCenter(pcbnew.VECTOR2I(pcbnew.FromMM(hx), pcbnew.FromMM(hy)))
                s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(hx), pcbnew.FromMM(hy)))
                s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(hx + radius), pcbnew.FromMM(hy)))
                s.SetWidth(pcbnew.FromMM(0.15))
                b.Add(s)
                applied += 1

        # 16. Board Corner Fillet (Smooth rounded corners on Edge.Cuts)
        elif action in ("board.fillet", "fillet", "board.rounded_corners", "rounded_corners"):
            r = float(op.get("radius", op.get("r", 2.0)))
            edge = pcbnew.Edge_Cuts
            bx, by, bw, bh = _get_board_bounds(b)
            # Delete existing Edge.Cuts segments
            for drw in list(b.GetDrawings()):
                if drw.GetLayer() == edge:
                    b.Delete(drw)

            def add_line(x1, y1, x2, y2):
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                s.SetLayer(edge)
                s.SetWidth(pcbnew.FromMM(0.15))
                s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                b.Add(s)

            def add_corner_arc(start_x, start_y, mid_x, mid_y, end_x, end_y):
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_ARC)
                s.SetLayer(edge)
                s.SetWidth(pcbnew.FromMM(0.15))
                s.SetArcGeometry(
                    pcbnew.VECTOR2I(pcbnew.FromMM(start_x), pcbnew.FromMM(start_y)),
                    pcbnew.VECTOR2I(pcbnew.FromMM(mid_x), pcbnew.FromMM(mid_y)),
                    pcbnew.VECTOR2I(pcbnew.FromMM(end_x), pcbnew.FromMM(end_y))
                )
                b.Add(s)

            d = r * 0.70710678
            # 1. Top segment
            add_line(bx + r, by, bx + bw - r, by)
            # 2. Top-Right Arc
            add_corner_arc(bx + bw - r, by, bx + bw - r + d, by + r - d, bx + bw, by + r)
            # 3. Right segment
            add_line(bx + bw, by + r, bx + bw, by + bh - r)
            # 4. Bottom-Right Arc
            add_corner_arc(bx + bw, by + bh - r, bx + bw - r + d, by + bh - r + d, bx + bw - r, by + bh)
            # 5. Bottom segment
            add_line(bx + bw - r, by + bh, bx + r, by + bh)
            # 6. Bottom-Left Arc
            add_corner_arc(bx + r, by + bh, bx + r - d, by + bh - r + d, bx, by + bh - r)
            # 7. Left segment
            add_line(bx, by + bh - r, bx, by + r)
            # 8. Top-Left Arc
            add_corner_arc(bx, by + r, bx + r - d, by + r - d, bx + r, by)
            applied += 8

        # 17. Slot / Isolation Cutout
        elif action in ("slot.add", "add_slot", "board.cutout", "cutout"):
            edge = pcbnew.Edge_Cuts
            w = float(op.get("width", 1.2))
            if "start" in op or "x1" in op:
                x1 = float(op.get("x1", op.get("start", [0, 0])[0]))
                y1 = float(op.get("y1", op.get("start", [0, 0])[1]))
                x2 = float(op.get("x2", op.get("end", [0, 0])[0]))
                y2 = float(op.get("y2", op.get("end", [0, 0])[1]))
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                s.SetLayer(edge)
                s.SetWidth(pcbnew.FromMM(w))
                s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                b.Add(s)
                applied += 1
            elif "x" in op and ("h" in op or "height" in op):
                cx = float(op.get("x", 0.0))
                cy = float(op.get("y", 0.0))
                cw = float(op.get("w", op.get("width", 5.0)))
                ch = float(op.get("h", op.get("height", 2.0)))
                def add_cut_seg(sx1, sy1, sx2, sy2):
                    seg = pcbnew.PCB_SHAPE(b)
                    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
                    seg.SetLayer(edge)
                    seg.SetWidth(pcbnew.FromMM(0.15))
                    seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(sx1), pcbnew.FromMM(sy1)))
                    seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(sx2), pcbnew.FromMM(sy2)))
                    b.Add(seg)
                add_cut_seg(cx, cy, cx + cw, cy)
                add_cut_seg(cx + cw, cy, cx + cw, cy + ch)
                add_cut_seg(cx + cw, cy + ch, cx, cy + ch)
                add_cut_seg(cx, cy + ch, cx, cy)
                applied += 4

        # 18. Add Silkscreen or Graphic Text
        elif action in ("text.add", "add_text", "silkscreen.add_text", "text"):
            txt_str = str(op.get("text", op.get("str", "")))
            tx = float(op.get("x", 0.0))
            ty = float(op.get("y", 0.0))
            layer_name = str(op.get("layer", "F.SilkS"))
            layer_id = pcbnew.B_SilkS if "b.silk" in layer_name.lower() else (
                pcbnew.F_Cu if "f.cu" in layer_name.lower() else (
                    pcbnew.B_Cu if "b.cu" in layer_name.lower() else pcbnew.F_SilkS
                )
            )
            size = float(op.get("size", 1.0))
            thick = float(op.get("thickness", 0.15))
            rot = float(op.get("rot", op.get("angle", 0.0)))

            t = pcbnew.PCB_TEXT(b)
            t.SetText(txt_str)
            t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(tx), pcbnew.FromMM(ty)))
            t.SetLayer(layer_id)
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
            t.SetTextThickness(pcbnew.FromMM(thick))
            if rot != 0.0:
                t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
            b.Add(t)
            applied += 1

        # 19. Connector Pinout Automatic Labels
        elif action in ("connector.pinout_labels", "pinout_labels", "label_pins"):
            target_ref = op.get("ref")
            offset_dist = float(op.get("offset", 1.5))
            txt_size = float(op.get("size", 0.8))
            txt_thick = float(op.get("thickness", 0.12))
            layer_id = pcbnew.F_SilkS

            fp = fps.get(target_ref)
            if fp:
                fcx = pcbnew.ToMM(fp.GetPosition().x)
                fcy = pcbnew.ToMM(fp.GetPosition().y)
                labeled_count = 0
                for pad in fp.Pads():
                    raw_net = pad.GetNetname()
                    if not raw_net or raw_net.strip() == "":
                        continue
                    clean_name = raw_net.split("/")[-1].replace("+", "").strip()
                    if clean_name in ("NC", "unconnected", ""):
                        continue
                    ppos = pad.GetPosition()
                    px = pcbnew.ToMM(ppos.x)
                    py = pcbnew.ToMM(ppos.y)
                    dx = px - fcx
                    dy = py - fcy
                    if abs(dx) >= abs(dy):
                        lx = px + (offset_dist if dx >= 0 else -offset_dist)
                        ly = py
                    else:
                        lx = px
                        ly = py + (offset_dist if dy >= 0 else -offset_dist)

                    t = pcbnew.PCB_TEXT(b)
                    t.SetText(clean_name)
                    t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(lx), pcbnew.FromMM(ly)))
                    t.SetLayer(layer_id)
                    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(txt_size), pcbnew.FromMM(txt_size)))
                    t.SetTextThickness(pcbnew.FromMM(txt_thick))
                    b.Add(t)
                    labeled_count += 1
                applied += labeled_count
            else:
                errors.append(f"Connector footprint '{target_ref}' not found for pinout labelling.")

        # 20. Dimension Markings on Fabrication Layer
        elif action in ("dimension.add", "add_dimension", "board.dimension"):
            layer_name = str(op.get("layer", "Dwgs.User"))
            layer_id = pcbnew.Cmts_User if "cmts" in layer_name.lower() else pcbnew.Dwgs_User
            offset = float(op.get("offset", 4.0))
            bx, by, bw, bh = _get_board_bounds(b)

            # Horizontal dimension across top edge
            dim_h = pcbnew.PCB_DIM_ALIGNED(b)
            dim_h.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(bx), pcbnew.FromMM(by)))
            dim_h.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx + bw), pcbnew.FromMM(by)))
            dim_h.SetHeight(pcbnew.FromMM(offset))
            dim_h.SetLayer(layer_id)
            b.Add(dim_h)

            # Vertical dimension along right edge
            dim_v = pcbnew.PCB_DIM_ALIGNED(b)
            dim_v.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(bx + bw), pcbnew.FromMM(by)))
            dim_v.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx + bw), pcbnew.FromMM(by + bh)))
            dim_v.SetHeight(pcbnew.FromMM(offset))
            dim_v.SetLayer(layer_id)
            b.Add(dim_v)
            applied += 2

        # 21. Add Copper Zone / Ground Pour
        elif action in ("zone.add", "add_zone", "copper_pour", "plane.add"):
            net_name = str(op.get("net", "GND"))
            layer_name = str(op.get("layer", "B.Cu"))
            layer_id = pcbnew.F_Cu if "f.cu" in layer_name.lower() else pcbnew.B_Cu
            conn_mode = str(op.get("connection", "full")).lower()
            min_thick = float(op.get("min_thickness", 0.15))
            margin = float(op.get("margin", 0.2))

            z = pcbnew.ZONE(b)
            z.SetLayer(layer_id)
            net_obj = b.FindNet(net_name)
            if net_obj:
                z.SetNet(net_obj)
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if conn_mode == "full" else pcbnew.ZONE_CONNECTION_THERMAL)
            z.SetMinThickness(pcbnew.FromMM(min_thick))

            chain = pcbnew.SHAPE_LINE_CHAIN()
            if "corners" in op and isinstance(op["corners"], list) and len(op["corners"]) >= 3:
                for c in op["corners"]:
                    chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(float(c[0])), pcbnew.FromMM(float(c[1]))))
            else:
                bx, by, bw, bh = _get_board_bounds(b)
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(bx + margin), pcbnew.FromMM(by + margin)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(bx + bw - margin), pcbnew.FromMM(by + margin)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(bx + bw - margin), pcbnew.FromMM(by + bh - margin)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(bx + margin), pcbnew.FromMM(by + bh - margin)))

            chain.SetClosed(True)
            z.AddPolygon(chain)
            b.Add(z)
            try:
                filler = pcbnew.ZONE_FILLER(b)
                filler.Fill(b.Zones())
            except Exception:
                pass
            applied += 1

        # 22. Rule Area / Keepout Zone (e.g. Antenna / High-Voltage)
        elif action in ("rule_area.add", "add_rule_area", "zone.keepout", "keepout"):
            z = pcbnew.ZONE(b)
            z.SetIsRuleArea(True)
            z.SetDoNotAllowZoneFills(bool(op.get("no_copper", op.get("no_zone", True))))
            z.SetDoNotAllowTracks(bool(op.get("no_tracks", True)))
            z.SetDoNotAllowVias(bool(op.get("no_vias", True)))
            z.SetDoNotAllowFootprints(bool(op.get("no_footprints", False)))
            layer_name = str(op.get("layer", "F.Cu"))
            z.SetLayer(pcbnew.B_Cu if "b.cu" in layer_name.lower() else pcbnew.F_Cu)

            chain = pcbnew.SHAPE_LINE_CHAIN()
            if "corners" in op and isinstance(op["corners"], list) and len(op["corners"]) >= 3:
                for c in op["corners"]:
                    chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(float(c[0])), pcbnew.FromMM(float(c[1]))))
            else:
                kx = float(op.get("x", 0.0))
                ky = float(op.get("y", 0.0))
                kw = float(op.get("w", op.get("width", 10.0)))
                kh = float(op.get("h", op.get("height", 10.0)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(kx), pcbnew.FromMM(ky)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(kx + kw), pcbnew.FromMM(ky)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(kx + kw), pcbnew.FromMM(ky + kh)))
                chain.Append(pcbnew.VECTOR2I(pcbnew.FromMM(kx), pcbnew.FromMM(ky + kh)))

            chain.SetClosed(True)
            z.AddPolygon(chain)
            b.Add(z)
            applied += 1

        # 23. Via Matrix / Thermal Pad Array
        elif action in ("via.matrix", "via.array", "thermal_vias"):
            net_name = str(op.get("net", "GND"))
            net_obj = b.FindNet(net_name)
            rows = int(op.get("rows", 3))
            cols = int(op.get("cols", 3))
            pitch_x = float(op.get("pitch_x", op.get("pitch", 1.2)))
            pitch_y = float(op.get("pitch_y", op.get("pitch", 1.2)))
            drill = float(op.get("drill", 0.3))
            size = float(op.get("size", op.get("diameter", 0.6)))

            if "ref" in op and op["ref"] in fps:
                fp = fps[op["ref"]]
                cx = pcbnew.ToMM(fp.GetPosition().x)
                cy = pcbnew.ToMM(fp.GetPosition().y)
            else:
                cx = float(op.get("center_x", op.get("cx", op.get("x", 0.0))))
                cy = float(op.get("center_y", op.get("cy", op.get("y", 0.0))))

            start_x = cx - ((cols - 1) * pitch_x) / 2.0
            start_y = cy - ((rows - 1) * pitch_y) / 2.0
            v_count = 0
            for r_idx in range(rows):
                for c_idx in range(cols):
                    vx = start_x + c_idx * pitch_x
                    vy = start_y + r_idx * pitch_y
                    via = pcbnew.PCB_VIA(b)
                    via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
                    via.SetWidth(pcbnew.FromMM(size))
                    via.SetDrill(pcbnew.FromMM(drill))
                    if net_obj:
                        via.SetNet(net_obj)
                    b.Add(via)
                    v_count += 1
            applied += v_count

        # 24. Via Fence / Perimeter Ground Shielding
        elif action in ("via.fence", "perimeter_vias", "ground_fence"):
            net_name = str(op.get("net", "GND"))
            net_obj = b.FindNet(net_name)
            pitch = float(op.get("pitch", 3.0))
            offset = float(op.get("offset", 1.5))
            drill = float(op.get("drill", 0.3))
            size = float(op.get("size", 0.6))

            bx, by, bw, bh = _get_board_bounds(b)
            x_min = bx + offset
            x_max = bx + bw - offset
            y_min = by + offset
            y_max = by + bh - offset

            fence_coords = []
            curr_x = x_min
            while curr_x <= x_max:
                fence_coords.append((curr_x, y_min))
                curr_x += pitch
            curr_y = y_min + pitch
            while curr_y <= y_max:
                fence_coords.append((x_max, curr_y))
                curr_y += pitch
            curr_x = x_max - pitch
            while curr_x >= x_min:
                fence_coords.append((curr_x, y_max))
                curr_x -= pitch
            curr_y = y_max - pitch
            while curr_y >= y_min + pitch:
                fence_coords.append((x_min, curr_y))
                curr_y -= pitch

            for fx, fy in fence_coords:
                via = pcbnew.PCB_VIA(b)
                via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(fx), pcbnew.FromMM(fy)))
                via.SetWidth(pcbnew.FromMM(size))
                via.SetDrill(pcbnew.FromMM(drill))
                if net_obj:
                    via.SetNet(net_obj)
                b.Add(via)
            applied += len(fence_coords)

        # 25. Footprint Align & Uniform Distribution
        elif action in ("footprint.align", "align", "distribute", "fp_align"):
            target_refs = op.get("refs", [])
            valid_fps = [fps[r] for r in target_refs if r in fps]
            align_mode = str(op.get("align", "top")).lower()
            dist_val = op.get("distribute")

            if valid_fps:
                if align_mode == "top":
                    target_y = min(pcbnew.ToMM(fp.GetPosition().y) for fp in valid_fps)
                    for fp in valid_fps:
                        px = pcbnew.ToMM(fp.GetPosition().x)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(px * 2.0) / 2.0), pcbnew.FromMM(round(target_y * 2.0) / 2.0)))
                elif align_mode == "bottom":
                    target_y = max(pcbnew.ToMM(fp.GetPosition().y) for fp in valid_fps)
                    for fp in valid_fps:
                        px = pcbnew.ToMM(fp.GetPosition().x)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(px * 2.0) / 2.0), pcbnew.FromMM(round(target_y * 2.0) / 2.0)))
                elif align_mode == "left":
                    target_x = min(pcbnew.ToMM(fp.GetPosition().x) for fp in valid_fps)
                    for fp in valid_fps:
                        py = pcbnew.ToMM(fp.GetPosition().y)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(target_x * 2.0) / 2.0), pcbnew.FromMM(round(py * 2.0) / 2.0)))
                elif align_mode == "right":
                    target_x = max(pcbnew.ToMM(fp.GetPosition().x) for fp in valid_fps)
                    for fp in valid_fps:
                        py = pcbnew.ToMM(fp.GetPosition().y)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(target_x * 2.0) / 2.0), pcbnew.FromMM(round(py * 2.0) / 2.0)))
                elif align_mode in ("center_x", "center"):
                    target_x = sum(pcbnew.ToMM(fp.GetPosition().x) for fp in valid_fps) / len(valid_fps)
                    for fp in valid_fps:
                        py = pcbnew.ToMM(fp.GetPosition().y)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(target_x * 2.0) / 2.0), pcbnew.FromMM(round(py * 2.0) / 2.0)))
                elif align_mode == "center_y":
                    target_y = sum(pcbnew.ToMM(fp.GetPosition().y) for fp in valid_fps) / len(valid_fps)
                    for fp in valid_fps:
                        px = pcbnew.ToMM(fp.GetPosition().x)
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(px * 2.0) / 2.0), pcbnew.FromMM(round(target_y * 2.0) / 2.0)))

                if dist_val is not None:
                    step = float(dist_val)
                    axis = str(op.get("axis", "X" if align_mode in ("top", "bottom", "center_y") else "Y")).upper()
                    if axis == "X":
                        sorted_fps = sorted(valid_fps, key=lambda f: pcbnew.ToMM(f.GetPosition().x))
                        base_x = pcbnew.ToMM(sorted_fps[0].GetPosition().x)
                        for idx, fp in enumerate(sorted_fps):
                            new_x = round((base_x + idx * step) * 2.0) / 2.0
                            cur_y = pcbnew.ToMM(fp.GetPosition().y)
                            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(new_x), pcbnew.FromMM(cur_y)))
                    else:
                        sorted_fps = sorted(valid_fps, key=lambda f: pcbnew.ToMM(f.GetPosition().y))
                        base_y = pcbnew.ToMM(sorted_fps[0].GetPosition().y)
                        for idx, fp in enumerate(sorted_fps):
                            cur_x = pcbnew.ToMM(fp.GetPosition().x)
                            new_y = round((base_y + idx * step) * 2.0) / 2.0
                            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cur_x), pcbnew.FromMM(new_y)))

                applied += len(valid_fps)
            else:
                errors.append("No valid footprints found to align.")

        else:
            errors.append(f"Unknown layout operation: '{action}'")

    shove_info = None
    if shove:
        shove_info = apply_component_push_and_shove(b, moved_refs)

    b.BuildListOfNets()
    b.BuildConnectivity()

    overlaps = []
    if dry_run:
        # Check component collisions using true physical courtyards in memory without writing to disk
        fps_list = list(b.GetFootprints())
        def _get_crt_bbox(fp):
            if hasattr(fp, "GetCourtyard"):
                for l in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                    try:
                        c = fp.GetCourtyard(l)
                        if c and not c.IsEmpty():
                            return c.BBox()
                    except Exception:
                        pass
            if hasattr(fp, "GetBoundingBox"):
                try:
                    return fp.GetBoundingBox()
                except Exception:
                    pass
            return None

        for i in range(len(fps_list)):
            for j in range(i + 1, len(fps_list)):
                fp_a = fps_list[i]
                fp_b = fps_list[j]
                bb_a = _get_crt_bbox(fp_a)
                bb_b = _get_crt_bbox(fp_b)
                if bb_a and bb_b and bb_a.Intersects(bb_b):
                    ref_a = fp_a.GetReference() if hasattr(fp_a, "GetReference") else f"fp_{i}"
                    ref_b = fp_b.GetReference() if hasattr(fp_b, "GetReference") else f"fp_{j}"
                    overlaps.append(f"{ref_a} <-> {ref_b}")
    else:
        can_commit = (applied > 0 or len(ops) == 0) and len(errors) == 0
        if can_commit:
            pcbnew.SaveBoard(str(pcb_path), b)

    can_commit = (applied > 0 or len(ops) == 0) and len(errors) == 0
    result = {
        "success": can_commit,
        "dry_run": dry_run,
        "applied_ops_count": applied if can_commit else 0,
        "errors": errors
    }
    if shove_info:
        result["push_and_shove"] = shove_info

    if dry_run:
        result["simulated"] = True
        result["collisions_detected"] = len(overlaps)
        result["collision_pairs"] = overlaps
        result["summary"] = f"Simulated {applied} layout operations in memory. {len(overlaps)} collisions detected. 0 bytes written to disk."

    # Explicitly release SWIG objects and trigger garbage collection
    # to avoid false-positive SWIG teardown warnings on process exit
    del fps
    del b
    import gc
    gc.collect()

    return result


def sanitize_silkscreen(
    project_dir: str | Path,
    mode: str = "sanitize",
    target_ref: Optional[str] = None
) -> Dict[str, Any]:
    """Sanitizes silkscreen text across footprints:
    - 'sanitize': Hides bulky values and auto-hides reference designators that collide with copper pads.
    - 'hide_all': Hides all silkscreen reference designators and values (for dense boards / clean aesthetic).
    - 'hide_values': Hides all bulky component values, preserving reference designators.
    """
    return apply_ops(project_dir, [{"op": "silkscreen.sanitize", "mode": mode, "ref": target_ref}])


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Apply ops.json layout operations (placement, rotation, locking, boundaries) to PCB."
    )
    ap.add_argument("project_dir", help="Path to KiCad project folder")
    ap.add_argument(
        "ops_file",
        nargs="?",
        help="Path to ops.json (default: <project_dir>/kaibridge_dump/ops.json or <project_dir>/ops.json)"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate placement in memory and audit courtyard collisions without writing to disk"
    )
    ap.add_argument(
        "--sanitize-silk",
        action="store_true",
        help="Sanitize silkscreen: hide bulky values and auto-hide references that collide with copper pads"
    )
    ap.add_argument(
        "--hide-silk",
        action="store_true",
        help="Hide all silkscreen reference designators and values (for dense boards / clean aesthetic)"
    )
    ap.add_argument(
        "--hide-values",
        action="store_true",
        help="Hide all component values from silkscreen, preserving reference designators"
    )
    ap.add_argument(
        "--shove",
        action="store_true",
        help="Enable elastic Component Push-and-Shove collision relaxation: gently displace unlocked colliding parts into free space"
    )
    ap.add_argument(
        "--clear-tracks",
        "--unroute",
        action="store_true",
        dest="clear_tracks",
        help="Clear/unroute all copper tracks and vias from the board"
    )
    ap.add_argument(
        "--clear-zones",
        action="store_true",
        help="Clear all copper zones/pours from the board"
    )
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    if args.sanitize_silk or args.hide_silk or args.hide_values:
        mode = "hide_all" if args.hide_silk else ("hide_values" if args.hide_values else "sanitize")
        print(f"[*] Sanitizing silkscreen for: {project_dir.name} [Mode: {mode}]")
        s_res = sanitize_silkscreen(project_dir, mode=mode)
        if s_res.get("success"):
            print("  Status: Silkscreen successfully cleaned and updated in .kicad_pcb.")
        else:
            print(f"  Warning: Silkscreen sanitation reported: {s_res.get('error', 'unknown error')}")
        if not args.ops_file and not (args.clear_tracks or args.clear_zones):
            return 0

    ops_path = None
    ops_data = None
    ops_name = "in-memory ops"

    if args.ops_file:
        ops_path = Path(args.ops_file).expanduser().resolve()
        if not ops_path.exists():
            print(f"Error: Ops file not found: {ops_path}", file=sys.stderr)
            return 1
    else:
        cand1 = project_dir / "kaibridge_dump" / "ops.json"
        cand2 = project_dir / "ops.json"
        if cand1.exists():
            ops_path = cand1
        elif cand2.exists():
            ops_path = cand2
        elif args.clear_tracks or args.clear_zones:
            ops_data = {"board": {"clear_tracks": args.clear_tracks, "clear_zones": args.clear_zones}, "ops": []}
            ops_name = "CLI flags (--clear-tracks / --clear-zones)"
        else:
            print(
                f"Error: No ops.json found at {cand1} or {cand2}. Provide path explicitly.",
                file=sys.stderr
            )
            return 1

    if ops_path:
        with open(ops_path, "r", encoding="utf-8") as f:
            ops_data = json.load(f)
        if args.clear_tracks:
            if isinstance(ops_data, dict):
                ops_data.setdefault("board", {})["clear_tracks"] = True
            elif isinstance(ops_data, list):
                ops_data.insert(0, {"op": "track.delete_all"})
        if args.clear_zones:
            if isinstance(ops_data, dict):
                ops_data.setdefault("board", {})["clear_zones"] = True
            elif isinstance(ops_data, list):
                ops_data.insert(0, {"op": "zone.delete_all"})
        ops_name = ops_path.name

    mode_str = "DRY RUN (In-Memory Simulation)" if args.dry_run else "COMMITTED TO DISK"
    if args.shove:
        mode_str += " + PUSH-AND-SHOVE RELAXATION"
    print(f"[*] Applying layout operations from: {ops_name} [{mode_str}]")

    res = apply_ops(project_dir, ops_data, dry_run=args.dry_run, shove=args.shove)

    if not res.get("success"):
        err_msg = res.get("error") or "; ".join(res.get("errors", [])) or "Layout operations failed"
        print(f"Error: {err_msg}", file=sys.stderr)
        return 1

    applied = res.get("applied_ops_count", 0)
    print("\n=== Layout Operations Result ===")
    print(f"  Operations Applied : {applied}")

    shove_info = res.get("push_and_shove")
    if shove_info and shove_info.get("shove_applied"):
        print(f"  Push-and-Shove     : {shove_info.get('displaced_count', 0)} colliding part(s) elastically relocated into free space:")
        for disp in shove_info.get("displaced", [])[:8]:
            print(f"    - {disp['ref']}: {disp['from']} -> {disp['to']} (delta: {disp['delta_mm']} mm)")

    if args.dry_run:
        if "collisions_detected" not in res:
            print("Error: Backend dry-run failed to return collision audit data", file=sys.stderr)
            return 1
        collisions = res.get("collisions_detected", 0)
        pairs = res.get("collision_pairs", [])
        print(f"  Courtyard Collisions: {collisions}")
        if collisions > 0:
            print("  COLLISIONS DETECTED:")
            for pair in pairs[:10]:
                print(f"    - {pair}")
            if len(pairs) > 10:
                print(f"    ... and {len(pairs) - 10} more.")
            print("\n  [!] Resolve courtyard overlaps in ops.json or use --shove to relax.\n")
            return 1
        else:
            print("  Status: ZERO COLLISIONS (Geometry Gate Verified)")
    else:
        print("  Status: Successfully updated .kicad_pcb")

    print("\n  Next: Render snapshot via pcb_snapshot.py, or route via kicad_route.py.\n")
    return 0

