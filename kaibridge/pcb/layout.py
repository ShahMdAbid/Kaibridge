"""Kaibridge Operations Engine (layout.py)
Executes structured layout operations on KiCad PCB:
footprint placement, rotation, locking, deletion, Edge.Cuts outlines,
tracks, vias, and copper zones with 0.5mm clean quantization.
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..core.paths import load_kicad_python


def apply_ops(
    project_dir: str | Path,
    ops_data: Dict[str, Any] | List[Dict[str, Any]] | str | Path,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Applies a list of layout operations defined in ops.json or a dictionary/list.
    If dry_run is True, simulates all operations in memory and runs a collision audit without writing to disk.
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
    board_meta = raw.get("board", {}) if isinstance(raw, dict) else {}

    try:
        import pcbnew
        return _execute_in_process(pcb_file, ops_list, board_meta, dry_run=is_dry)
    except ImportError:
        kicad_python = load_kicad_python()
        dump_dir = proj_path / "kaibridge_dump"
        dump_dir.mkdir(parents=True, exist_ok=True)
        temp_ops = dump_dir / "temp_ops_payload.json"
        temp_ops.write_text(json.dumps({"ops": ops_list, "board": board_meta, "dry_run": is_dry}), encoding="utf-8")
        
        runner = f"""
import sys, json, os, traceback
sys.path.insert(0, r"{str(Path(__file__).resolve().parents[2])}")
from kaibridge.pcb.layout import _execute_in_process
try:
    with open(r"{str(temp_ops)}", "r", encoding="utf-8") as f:
        d = json.load(f)
    res = _execute_in_process(r"{str(pcb_file)}", d.get("ops", []), d.get("board", {{}}), dry_run=d.get("dry_run", False))
    print("APPLY_OPS_RESULT:" + json.dumps(res), flush=True)
except Exception as e:
    print("APPLY_OPS_ERROR:" + traceback.format_exc(), flush=True)
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
                return {"success": False, "error": line.replace("APPLY_OPS_ERROR:", "")}
        return {"success": False, "error": res_sub.stderr.strip() or res_sub.stdout.strip()}


def _execute_in_process(
    pcb_path: str | Path,
    ops: List[Dict[str, Any]],
    board_meta: Dict[str, Any],
    dry_run: bool = False
) -> Dict[str, Any]:
    import pcbnew
    b = pcbnew.LoadBoard(str(pcb_path))
    applied = 0
    errors = []

    # Clear options if requested
    if board_meta.get("clear_edge_cuts"):
        for drw in list(b.GetDrawings()):
            if drw.GetLayer() == pcbnew.Edge_Cuts:
                b.Remove(drw)
    if board_meta.get("clear_tracks") or board_meta.get("unroute_all"):
        for t in list(b.GetTracks()):
            b.Remove(t)

    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}

    for op in ops:
        action = op.get("op", "")
        ref = op.get("ref")

        # 1. Place / Move Footprint
        if action in ("footprint.place", "place", "fp_place", "footprint.move", "move"):
            fp = fps.get(ref)
            if fp:
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
                rot = float(op.get("rot", op.get("rotation", op.get("angle", 0.0))))
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
                    # Set or create custom field
                    found = False
                    for fld in fp.GetFields():
                        if fld.GetName() == field_name:
                            fld.SetText(field_value)
                            found = True
                            break
                    if not found:
                        new_field = pcbnew.PCB_FIELD(fp, fp.GetFieldCount(), field_name)
                        new_field.SetText(field_value)
                        new_field.SetVisible(False)
                        fp.AddField(new_field)
                applied += 1

        # 4. Delete Footprint
        elif action in ("item.delete", "delete", "footprint.delete", "fp_delete", "remove_part"):
            fp = fps.get(ref)
            if fp:
                b.Remove(fp)
                del fps[ref]
                applied += 1

        # 5. Set Board Size / Edge Cuts
        elif action in ("board.set_size", "set_size", "add_edge_cuts", "set_board_outline"):
            w = float(op.get("width", op.get("width_mm", 50.0)))
            h = float(op.get("height", op.get("height_mm", 40.0)))
            if "center_x_mm" in op or "center_y_mm" in op or "center_x" in op or "center_y" in op:
                cx = float(op.get("center_x_mm", op.get("center_x", w / 2.0)))
                cy = float(op.get("center_y_mm", op.get("center_y", h / 2.0)))
                ox = cx - w / 2.0
                oy = cy - h / 2.0
            else:
                ox = float(op.get("origin_x", op.get("origin_x_mm", op.get("x", 0.0))))
                oy = float(op.get("origin_y", op.get("origin_y_mm", op.get("y", 0.0))))
            edge = pcbnew.Edge_Cuts
            for drw in list(b.GetDrawings()):
                if drw.GetLayer() == edge:
                    b.Remove(drw)
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
                    b.Remove(drw)
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

        # 7. Unroute / Clear Tracks
        elif action in ("net.delete_routing", "unroute_net", "unroute", "clear_tracks", "ripup"):
            target_net = op.get("net")
            for t in list(b.GetTracks()):
                if not target_net or (t.GetNet() and t.GetNet().GetNetname() == target_net):
                    b.Remove(t)
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
                    b.Remove(z)
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
                    b.Remove(t)
            applied += 1

    b.BuildListOfNets()
    b.BuildConnectivity()

    overlaps = []
    if dry_run:
        # Check component collisions using true physical courtyards in memory without writing to disk
        fps_list = list(b.GetFootprints())
        def _get_crt_bbox(fp):
            for l in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                try:
                    c = fp.GetCourtyard(l)
                    if c and not c.IsEmpty():
                        return c.BBox()
                except Exception:
                    pass
            return fp.GetBoundingBox()

        for i in range(len(fps_list)):
            for j in range(i + 1, len(fps_list)):
                fp_a = fps_list[i]
                fp_b = fps_list[j]
                bb_a = _get_crt_bbox(fp_a)
                bb_b = _get_crt_bbox(fp_b)
                if bb_a.Intersects(bb_b):
                    overlaps.append(f"{fp_a.GetReference()} <-> {fp_b.GetReference()}")
    else:
        pcbnew.SaveBoard(str(pcb_path), b)

    result = {
        "success": applied > 0 or len(ops) == 0,
        "dry_run": dry_run,
        "applied_ops_count": applied,
        "errors": errors
    }
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



