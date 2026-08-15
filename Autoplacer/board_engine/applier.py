"""
Autoplacer/board_engine/applier.py — The 16 Board Ops executor and transactional apply_ops engine.
"""

import os
import math
import shutil
import datetime
import traceback
import pcbnew

from .common import (
    resolve_board, build_index, OpError, _need, _resolve_fp,
    _resolve_layer, _resolve_net, mk_point, to_mm, from_mm, pt,
    uuid_of, _try, _enum
)
from .gatekeeper import box_of, placement_report, _geometry_gate
from .backup import _store_dir, diff_states, print_diff
from .fetcher import get_full_board_state

# ----------------------------------------------------------------------------
# 16 BUILT-IN OP HANDLERS
# ----------------------------------------------------------------------------

def _op_fp_place(board, idx, op, dry):
    fp = _resolve_fp(idx, op)
    anchor = op.get("anchor", "centre")
    if dry:
        return "place %s anchor=%s -> (%s, %s) rot=%s" % (
            fp.GetReference(), anchor, op.get("x"), op.get("y"), op.get("rotation"))
    if fp.IsLocked() and not op.get("force"):
        raise OpError("%s is locked (pass force:true)" % fp.GetReference())

    if op.get("rotation") is not None:
        fp.SetOrientationDegrees(float(op["rotation"]))
        _try(lambda: fp.BuildCourtyardCaches())

    box = box_of(fp)
    tx = float(op["x"]) if op.get("x") is not None else box.cx
    ty = float(op["y"]) if op.get("y") is not None else box.cy
    if anchor == "origin":
        nx, ny = tx, ty
    elif anchor == "centre":
        nx, ny = box.origin_for_centre(tx, ty)
    else:
        pad = fp.FindPadByNumber(str(anchor))
        if pad is None:
            raise OpError("%s has no pad '%s'" % (fp.GetReference(), anchor))
        px, py = to_mm(pad.GetPosition().x), to_mm(pad.GetPosition().y)
        nx = to_mm(fp.GetPosition().x) + (tx - px)
        ny = to_mm(fp.GetPosition().y) + (ty - py)
    fp.SetPosition(mk_point(nx, ny))
    return "place %s %s -> centre (%.3f, %.3f)" % (fp.GetReference(), anchor, tx, ty)

def _op_fp_move(board, idx, op, dry):
    fp = _resolve_fp(idx, op)
    _need(op, "x", "y")
    old = pt(fp.GetPosition())
    if not dry:
        if fp.IsLocked() and not op.get("force"):
            raise OpError("%s is locked (pass force:true)" % fp.GetReference())
        fp.SetPosition(mk_point(op["x"], op["y"]))
        if op.get("rotation") is not None:
            fp.SetOrientationDegrees(float(op["rotation"]))
        if op.get("layer"):
            want_back = op["layer"].lower().startswith("b.")
            if bool(fp.IsFlipped()) != want_back:
                fp.Flip(fp.GetPosition(), False)
    return "move %s %s -> (%.3f, %.3f)%s" % (
        fp.GetReference(), old, op["x"], op["y"],
        " rot=%s" % op["rotation"] if op.get("rotation") is not None else "")

def _op_fp_rotate(board, idx, op, dry):
    fp = _resolve_fp(idx, op)
    _need(op, "rotation")
    if not dry:
        fp.SetOrientationDegrees(float(op["rotation"]))
    return "rotate %s -> %s deg" % (fp.GetReference(), op["rotation"])

def _op_fp_lock(board, idx, op, dry):
    fp = _resolve_fp(idx, op)
    val = bool(op.get("locked", True))
    if not dry:
        fp.SetLocked(val)
    return "%s %s" % ("lock" if val else "unlock", fp.GetReference())

def _op_fp_field(board, idx, op, dry):
    fp = _resolve_fp(idx, op)
    _need(op, "name", "value")
    if not dry:
        fp.SetField(op["name"], str(op["value"]))
    return "set field %s.%s = %s" % (fp.GetReference(), op["name"], op["value"])

def _op_track_add(board, idx, op, dry):
    _need(op, "layer", "start", "end", "width")
    layer = _resolve_layer(idx, op["layer"])
    net = _resolve_net(idx, op.get("net"))
    if not dry:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(mk_point(op["start"]["x"], op["start"]["y"]))
        t.SetEnd(mk_point(op["end"]["x"], op["end"]["y"]))
        t.SetWidth(from_mm(op["width"]))
        t.SetLayer(layer)
        if net is not None:
            t.SetNet(net)
        board.Add(t)
        op["_new_uuid"] = uuid_of(t)
    return "add track %s %s->%s w=%s net=%s" % (
        op["layer"], (op["start"]["x"], op["start"]["y"]),
        (op["end"]["x"], op["end"]["y"]), op["width"], op.get("net"))

def _op_via_add(board, idx, op, dry):
    _need(op, "x", "y", "width", "drill")
    net = _resolve_net(idx, op.get("net"))
    top = _resolve_layer(idx, op.get("top_layer", "F.Cu"))
    bot = _resolve_layer(idx, op.get("bottom_layer", "B.Cu"))
    if not dry:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(mk_point(op["x"], op["y"]))
        v.SetWidth(from_mm(op["width"]))
        v.SetDrill(from_mm(op["drill"]))
        v.SetViaType(_enum("VIATYPE_THROUGH"))
        v.SetLayerPair(top, bot)
        if net is not None:
            v.SetNet(net)
        board.Add(v)
        op["_new_uuid"] = uuid_of(v)
    return "add via (%.3f, %.3f) d=%s w=%s net=%s" % (
        op["x"], op["y"], op["drill"], op["width"], op.get("net"))

def _op_set_width(board, idx, op, dry):
    _need(op, "uuid", "width")
    t = idx["by_uuid"].get(op["uuid"])
    if t is None:
        raise OpError("uuid not found: %s" % op["uuid"])
    if not dry:
        t.SetWidth(from_mm(op["width"]))
    return "set width %s -> %s" % (op["uuid"][:8], op["width"])

def _op_delete(board, idx, op, dry):
    _need(op, "uuid")
    item = idx["by_uuid"].get(op["uuid"])
    if item is None:
        raise OpError("uuid not found: %s" % op["uuid"])
    label = _try(lambda: item.GetClass(), "item")
    if not dry:
        board.Remove(item)
    return "delete %s %s" % (label, op["uuid"][:8])

def _op_delete_net_tracks(board, idx, op, dry):
    net_filter = op.get("net")
    if net_filter:
        _resolve_net(idx, net_filter)
    layers = op.get("layers")
    victims = []
    for t in list(board.GetTracks()):
        if net_filter and _try(lambda: t.GetNetname()) != net_filter:
            continue
        if layers and _try(lambda: t.GetLayerName()) not in layers:
            continue
        if t.IsLocked() and not op.get("force"):
            continue
        victims.append(t)
    if not dry:
        for t in victims:
            board.Remove(t)
    return "delete %d routed items%s" % (len(victims), f" on net '{net_filter}'" if net_filter else "")

def _op_zone_refill(board, idx, op, dry):
    if not dry:
        try:
            _try(lambda: board.BuildConnectivity())
            for z in board.Zones():
                z.SetNeedRefill(True)
        except Exception:
            pass
    return "marked all zones for refill (press 'B' in KiCad to render fills)"

def _op_zone_add(board, idx, op, dry):
    _need(op, "net", "layer", "outline")
    net = _resolve_net(idx, op["net"])
    layer = _resolve_layer(idx, op["layer"])
    if len(op["outline"]) < 3:
        raise OpError("zone outline needs at least 3 points")
    if not dry:
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(net)
        z.SetAssignedPriority(int(op.get("priority", 0)))
        z.SetLocalClearance(from_mm(op.get("clearance", 0.3)))
        z.SetMinThickness(from_mm(op.get("min_thickness", 0.25)))
        z.SetZoneName(op.get("name", f"{op['net']}_plane"))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)

        chain = pcbnew.SHAPE_LINE_CHAIN()
        for p in op["outline"]:
            chain.Append(mk_point(p["x"], p["y"]))
        chain.SetClosed(True)
        poly = pcbnew.SHAPE_POLY_SET()
        poly.AddOutline(chain)
        z.SetOutline(poly)

        board.Add(z)
        z.SetNeedRefill(True)
        op["_new_uuid"] = uuid_of(z)
    return f"add zone {op['net']} on {op['layer']} ({len(op['outline'])} pts)"

def _op_prep_for_route(board, idx, op, dry):
    problems, killed = [], 0

    if not dry:
        for t in list(board.GetTracks()):
            board.Remove(t)
            killed += 1
        board.DeleteMARKERs()

    rep = placement_report(board)
    if not rep["route_ready"]:
        if not rep["outline_closed"]:
            problems.append("Edge.Cuts does not form a single closed outline.")
        for o in rep["outside_outline"]:
            problems.append(f"{o['ref']} extends outside Edge.Cuts")
        for p in rep["overlaps"]:
            problems.append(f"{p['a']} and {p['b']} overlap")
        for n in rep["netclasses_without_track_width"]:
            problems.append(f"Netclass {n} has no track width")

    if problems:
        raise OpError("not route-ready:\n  - " + "\n  - ".join(problems))
    return f"route prep OK ({killed} routed items removed)"

def _op_board_set_size(board, idx, op, dry):
    _need(op, "width", "height")
    w, h = float(op["width"]), float(op["height"])
    ox, oy = float(op.get("origin_x", 0.0)), float(op.get("origin_y", 0.0))
    if dry:
        return "outline %gx%g at (%g,%g) -- DELETES every Edge.Cuts item" % (w, h, ox, oy)
    edge = board.GetLayerID("Edge.Cuts")
    if edge == -1:
        raise OpError("Could not resolve the Edge.Cuts layer ID")
    for drw in list(board.GetDrawings()):
        if drw.GetLayer() == edge:
            board.Remove(drw)
    width_iu = from_mm(0.1)
    pts = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    for i in range(4):
        p1, p2 = pts[i], pts[(i + 1) % 4]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(edge)
        seg.SetStart(mk_point(p1[0], p1[1]))
        seg.SetEnd(mk_point(p2[0], p2[1]))
        seg.SetWidth(width_iu)
        board.Add(seg)
    _try(lambda: board.SetOutlinesChainingEpsilon(from_mm(0.01)))
    poly = pcbnew.SHAPE_POLY_SET()
    if not _try(lambda: board.GetBoardPolygonOutlines(poly, True), False) or not poly.OutlineCount():
        raise OpError("Edge.Cuts written but KiCad still will not close it. "
                      "Usual cause: a stray Edge.Cuts graphic inside a footprint. "
                      "Open the Edge.Cuts layer in the PCB editor and look.")
    return "outline %gx%g at (%g,%g) -- closed and verified" % (w, h, ox, oy)

def _op_board_drc(board, idx, op, dry):
    if not dry:
        import subprocess
        from kicad_pins import load_cli
        
        board_path = board.GetFileName()
        if not board_path or not os.path.exists(board_path):
            return "DRC Failed: Board file is not saved to disk yet."

        kicad_cli = load_cli()
        if not kicad_cli:
            return "DRC Failed: kicad-cli not found in paths or PATH."

        try:
            pcbnew.SaveBoard(board_path, board)
            cmd = [kicad_cli, "pcb", "drc", "--all-track-errors", "--exit-code-violations", board_path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            out = res.stdout.strip() or res.stderr.strip()
            if res.returncode == 0:
                return "CLI DRC Check Completed: 0 Violations."
            return f"CLI DRC Check Completed with Violations (code {res.returncode}):\n{out}"
        except Exception as e:
            return f"CLI DRC Failed (execution error): {e}"

    return "drc check requested"

def _op_board_fit_outline(board, idx, op, dry):
    margin = float(op.get("margin", 5.0))
    if dry:
        return "fit board outline to components with margin %.2f mm" % margin
    boxes = [box_of(fp) for fp in board.GetFootprints()]
    if not boxes:
        raise OpError("No footprints to fit outline to")
    x0 = min(b.x0 for b in boxes) - margin
    y0 = min(b.y0 for b in boxes) - margin
    x1 = max(b.x1 for b in boxes) + margin
    y1 = max(b.y1 for b in boxes) + margin
    w = x1 - x0
    h = y1 - y0
    return _op_board_set_size(board, idx, {"width": w, "height": h, "origin_x": x0, "origin_y": y0}, dry)

OPS = {
    "footprint.place": _op_fp_place,
    "footprint.move": _op_fp_move,
    "footprint.rotate": _op_fp_rotate,
    "footprint.lock": _op_fp_lock,
    "footprint.set_field": _op_fp_field,
    "track.add": _op_track_add,
    "track.set_width": _op_set_width,
    "via.add": _op_via_add,
    "item.delete": _op_delete,
    "net.delete_routing": _op_delete_net_tracks,
    "zone.refill": _op_zone_refill,
    "zone.add": _op_zone_add,
    "board.set_size": _op_board_set_size,
    "board.fit_outline": _op_board_fit_outline,
    "board.prep_for_route": _op_prep_for_route,
    "board.drc_check": _op_board_drc,
}

# ----------------------------------------------------------------------------
# APPLY TRANSACTIONS
# ----------------------------------------------------------------------------

def apply_ops(ops, board=None, dry_run=True, save=False, refill=True, verify=True):
    board = resolve_board(board)
    idx = build_index(board)

    # ---- 1. validate ----
    plan, problems = [], []
    for i, op in enumerate(ops):
        name = op.get("op")
        if name not in OPS:
            problems.append((i, "unknown op '%s'. Known: %s" % (name, sorted(OPS))))
            continue
        try:
            plan.append((i, name, OPS[name](board, idx, op, True)))
        except OpError as e:
            problems.append((i, str(e)))
        except Exception as e:
            problems.append((i, "%s: %s" % (type(e).__name__, e)))

    print("--- DRY RUN (%d ops) ---" % len(ops))
    for i, name, desc in plan:
        print("  [%02d] OK   %-22s %s" % (i, name, desc))
    for i, err in problems:
        print("  [%02d] FAIL %s" % (i, err))

    if problems:
        print("!! %d invalid op(s). Nothing applied." % len(problems))
        return {"applied": False, "problems": problems}
    if dry_run:
        print("dry_run=True -> stopping. Call again with dry_run=False to apply.")
        return {"applied": False, "problems": []}

    # ---- 2. backup + pre-state ----
    pre = get_full_board_state(board)
    path = _try(lambda: board.GetFileName(), "")
    backup = None
    if path and os.path.isfile(path):
        backup = os.path.join(_store_dir(board), "backups",
                              "%s_%s.kicad_pcb" % (
                                  os.path.basename(path).replace(".kicad_pcb", ""),
                                  datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
        shutil.copy2(path, backup)
        print("[pcb_brain] backup -> %s" % backup)

    # ---- 3. execute ----
    done, failed = [], None
    for i, op in enumerate(ops):
        try:
            desc = OPS[op["op"]](board, idx, op, False)
            done.append({"index": i, "op": op["op"], "desc": desc,
                         "new_uuid": op.get("_new_uuid")})
            print("  [%02d] APPLIED %s" % (i, desc))
            idx = build_index(board)   # refresh: new items need uuids
        except Exception as e:
            failed = {"index": i, "op": op.get("op"),
                      "error": "%s: %s" % (type(e).__name__, e),
                      "trace": traceback.format_exc()}
            print("  [%02d] RUNTIME FAIL %s" % (i, failed["error"]))
            print("  >>> ABORTED. Board is partially modified. "
                  "Restore backup if needed: %s" % backup)
            break

    # ---- geometry gate ----
    gate_report = None
    if failed is None:
        gate_report, gate_problems = _geometry_gate(
            board, clearance=0.25, edge_margin=0.5, autoresolve=True)
        if gate_problems:
            failed = {"index": -1, "op": "geometry_gate",
                      "error": "; ".join(gate_problems)}
            print("  [gate] %s" % failed["error"])
            print("  >>> NOT SAVED. Board is dirty in memory only -- "
                  "press Ctrl+Z in KiCad or File > Revert to Saved.")

    if refill and failed is None:
        try:
            for z in board.Zones():
                z.SetNeedRefill(True)
        except Exception:
            pass

    _try(lambda: pcbnew.Refresh())

    if save and failed is None and path:
        pcbnew.SaveBoard(path, board)
        print("[pcb_brain] saved -> %s" % path)

    result = {"applied": failed is None, "done": done, "failed": failed,
              "backup": backup, "placement_report": gate_report}

    # ---- 4. verify ----
    if verify:
        post = get_full_board_state(board)
        rep = diff_states(pre, post)
        print_diff(rep)
        result["diff_summary"] = rep["summary"]
        
    # ---- 5. Tangle Score (Ratsnest MST) ----
    if verify and failed is None:
        tangle_score = 0.0
        for net_code, net_info in board.GetNetInfo().NetsByNetcode().items():
            if net_code == 0: continue
            pads = [pad.GetPosition() for pad in board.GetPads() if pad.GetNetCode() == net_code]
            if len(pads) < 2: continue
            
            # simple MST using Prim's algorithm
            connected = [pads.pop(0)]
            while pads:
                best_dist = 1e9
                best_pad_idx = -1
                for i, p in enumerate(pads):
                    for c in connected:
                        dist = math.hypot(to_mm(p.x - c.x), to_mm(p.y - c.y))
                        if dist < best_dist:
                            best_dist = dist
                            best_pad_idx = i
                tangle_score += best_dist
                connected.append(pads.pop(best_pad_idx))
        result["tangle_score"] = round(tangle_score, 2)
        print(f"--- TANGLE SCORE: {result['tangle_score']} mm ---")
    
    return result
