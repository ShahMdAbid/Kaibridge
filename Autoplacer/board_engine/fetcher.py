"""
Autoplacer/board_engine/fetcher.py — KiCad board state extractor, full board state, and AI context generator.
"""

import os
import json
import hashlib
import datetime
import traceback
import pcbnew

from .common import (
    SCHEMA_VERSION, BUILD_VERSION, _MAJOR,
    resolve_board, safe_json_default, to_mm, from_mm, deg, pt,
    uuid_of, _bbox, _box_json, _layers_of, _try, _call_any, _enum,
    _VIA_TYPES, _PAD_ATTRS, _ZONE_CONN, _fp_attributes, _fp_fields
)
from .gatekeeper import box_of, placement_report
from .backup import _store_dir

# ----------------------------------------------------------------------------
# DRAWING / SHAPE EXTRACTORS
# ----------------------------------------------------------------------------

def _shape_polygon(shape):
    """Points for POLY shapes (custom board outlines, logos)."""
    def go():
        ps = shape.GetPolyShape()
        rings = []
        for i in range(ps.OutlineCount()):
            r = ps.Outline(i)
            rings.append([{"x": round(to_mm(r.CPoint(k).x), 5),
                           "y": round(to_mm(r.CPoint(k).y), 5)}
                          for k in range(r.PointCount())])
        return rings or None
    return _try(go)

def _extract_drawing(board, d, shallow=False):
    cls = _try(lambda: d.GetClass(), type(d).__name__)
    item = {
        "uuid": uuid_of(d),
        "class": cls,
        "layer": _try(lambda: d.GetLayerName()),
        "locked": _try(lambda: bool(d.IsLocked()), False),
    }
    if hasattr(pcbnew, "PCB_SHAPE") and isinstance(d, pcbnew.PCB_SHAPE) or \
       hasattr(pcbnew, "FP_SHAPE") and isinstance(d, getattr(pcbnew, "FP_SHAPE", ())):
        item.update({
            "shape": _try(lambda: d.GetShapeStr()),
            "start_mm": pt(_try(lambda: d.GetStart())),
            "end_mm": pt(_try(lambda: d.GetEnd())),
            "center_mm": pt(_try(lambda: d.GetCenter())),
            "radius_mm": _try(lambda: round(to_mm(d.GetRadius()), 5)),
            "arc_angle_deg": deg(_try(lambda: d.GetArcAngleStart())),
            "stroke_width_mm": _try(lambda: round(to_mm(
                _try(lambda: d.GetWidth(), 0)), 5)),
            "filled": _try(lambda: bool(d.IsFilled())),
            "polygon_mm": _shape_polygon(d),
        })
    elif "TEXT" in str(cls).upper():
        item.update({
            "text": _try(lambda: d.GetText(), ""),
            "position_mm": pt(_try(lambda: d.GetPosition())),
            "rotation_deg": _try(lambda: d.GetTextAngleDegrees()),
            "visible": _try(lambda: bool(d.IsVisible()), True),
            "mirrored": _try(lambda: bool(d.IsMirrored())),
        })
    elif "DIM" in str(cls).upper():
        item.update({
            "text": _try(lambda: d.GetText(), ""),
            "start_mm": pt(_try(lambda: d.GetStart())),
            "end_mm": pt(_try(lambda: d.GetEnd())),
        })
    return item

# ----------------------------------------------------------------------------
# PAD / FOOTPRINT EXTRACTORS
# ----------------------------------------------------------------------------

def _extract_pad(board, pad):
    sz = _try(lambda: pad.GetSize())
    dr = _try(lambda: pad.GetDrillSize())
    off = _try(lambda: pad.GetOffset())
    attr = _try(lambda: int(pad.GetAttribute()))
    lc = _try(lambda: pad.GetLocalClearance())
    return {
        "uuid": uuid_of(pad),
        "number": _try(lambda: pad.GetNumber(), ""),
        "pin_function": _try(lambda: pad.GetPinFunction()),
        "net_name": _try(lambda: pad.GetNetname(), ""),
        "net_code": _try(lambda: pad.GetNetCode(), 0),
        "attr": _PAD_ATTRS.get(attr, attr),
        "shape": _try(lambda: pad.GetShapeStr()),
        "position_mm": pt(_try(lambda: pad.GetPosition())),
        "offset_mm": pt(off) if off else None,
        "size_mm": {"w": round(to_mm(sz.x), 5), "h": round(to_mm(sz.y), 5)} if sz else None,
        "drill_mm": {"w": round(to_mm(dr.x), 5), "h": round(to_mm(dr.y), 5)} if dr else None,
        "drill_shape": _try(lambda: int(pad.GetDrillShape())),
        "orientation_deg": _call_any(pad, ["GetOrientationDegrees"], None),
        "layers": _layers_of(board, pad),
        "roundrect_ratio": _try(lambda: round(pad.GetRoundRectRadiusRatio(), 4)),
        "chamfer_ratio": _try(lambda: round(pad.GetChamferRectRatio(), 4)),
        "local_clearance_mm": to_mm(lc) if lc else None,
        "solder_mask_margin_mm": _try(
            lambda: to_mm(pad.GetLocalSolderMaskMargin()) or None),
        "solder_paste_margin_mm": _try(
            lambda: to_mm(pad.GetLocalSolderPasteMargin()) or None),
        "zone_connection": _try(lambda: int(pad.GetZoneConnection())),
        "is_on_copper": _try(lambda: pad.IsOnCopperLayer()),
    }

def _extract_footprint(board, fp, include_fp_graphics=True):
    d = {
        "uuid": uuid_of(fp),
        "sheet_path": _try(lambda: fp.GetPath().AsString()) if _try(lambda: fp.GetPath()) else None,
        "reference": _try(lambda: fp.GetReference(), ""),
        "value": _try(lambda: fp.GetValue(), ""),
        "fpid": _try(lambda: fp.GetFPIDAsString()) or _try(lambda: fp.GetFPID().GetUniStringLibId()),
        "description": _try(lambda: fp.GetLibDescription()),
        "layer": _try(lambda: fp.GetLayerName()),
        "flipped": _try(lambda: bool(fp.IsFlipped())),
        "position_mm": pt(_try(lambda: fp.GetPosition())),
        "rotation_deg": _try(lambda: fp.GetOrientationDegrees()),
        "is_locked": _try(lambda: bool(fp.IsLocked()), False),
        "attributes": _fp_attributes(fp),
        "fields": _fp_fields(fp),
        "bbox_mm": _bbox(fp),
        "courtyard_mm": _try(lambda: _box_json(box_of(fp))),
        "models_3d": _try(lambda: [m.m_Filename for m in fp.Models()], []),
        "pads": [_extract_pad(board, p) for p in fp.Pads()],
        "graphics": [],
    }
    if include_fp_graphics:
        for g in _try(lambda: list(fp.GraphicalItems()), []) or []:
            d["graphics"].append(_extract_drawing(board, g, shallow=True))
    return d

# ----------------------------------------------------------------------------
# ZONE & TRACK EXTRACTORS
# ----------------------------------------------------------------------------

def _extract_zone(board, z):
    def outline():
        o = z.Outline()
        rings = []
        for i in range(o.OutlineCount()):
            r = o.Outline(i)
            rings.append([{"x": round(to_mm(r.CPoint(k).x), 5),
                           "y": round(to_mm(r.CPoint(k).y), 5)}
                          for k in range(r.PointCount())])
        return rings
    conn = _try(lambda: int(z.GetPadConnection()))
    return {
        "uuid": uuid_of(z),
        "name": _try(lambda: z.GetZoneName(), ""),
        "net_name": _try(lambda: z.GetNetname(), ""),
        "net_code": _try(lambda: z.GetNetCode(), 0),
        "layers": _layers_of(board, z),
        "is_filled": _try(lambda: bool(z.IsFilled()), False),
        "priority": _try(lambda: z.GetAssignedPriority(), 0),
        "is_rule_area": _try(lambda: bool(z.GetIsRuleArea()), False),
        "keepout": _try(lambda: {
            "tracks": bool(z.GetDoNotAllowTracks()),
            "vias": bool(z.GetDoNotAllowVias()),
            "pads": bool(z.GetDoNotAllowPads()),
            "copper_pour": bool(_call_any(z, ["GetDoNotAllowZoneFills", "GetDoNotAllowCopperPour"], False)),
            "footprints": bool(z.GetDoNotAllowFootprints()),
        }),
        "clearance_mm": _try(lambda: to_mm(z.GetLocalClearance())),
        "min_thickness_mm": _try(lambda: to_mm(z.GetMinThickness())),
        "thermal_gap_mm": _try(lambda: to_mm(z.GetThermalReliefGap())),
        "thermal_spoke_mm": _try(lambda: to_mm(z.GetThermalReliefSpokeWidth())),
        "pad_connection": _ZONE_CONN.get(conn, conn),
        "fill_mode": _try(lambda: int(z.GetFillMode())),
        "locked": _try(lambda: bool(z.IsLocked()), False),
        "outline_mm": _try(outline, []),
        "area_mm2": _try(lambda: round(to_mm(to_mm(z.GetOutlineArea())), 4)),
    }

def _extract_track(board, t):
    base = {
        "uuid": uuid_of(t),
        "net_name": _try(lambda: t.GetNetname(), ""),
        "net_code": _try(lambda: t.GetNetCode(), 0),
        "width_mm": round(to_mm(_try(lambda: t.GetWidth(), 0)), 5),
        "locked": _try(lambda: bool(t.IsLocked()), False),
    }
    VIA = getattr(pcbnew, "PCB_VIA", None)
    ARC = getattr(pcbnew, "PCB_ARC", None)

    if VIA and isinstance(t, VIA):
        vt = _try(lambda: int(t.GetViaType()))
        base.update({
            "kind": "via",
            "position_mm": pt(_try(lambda: t.GetPosition())),
            "drill_mm": round(to_mm(_try(lambda: t.GetDrillValue(), 0)), 5),
            "via_type": _VIA_TYPES.get(vt, vt),
            "top_layer": _try(lambda: board.GetLayerName(t.TopLayer())),
            "bottom_layer": _try(lambda: board.GetLayerName(t.BottomLayer())),
            "is_tented": _try(lambda: t.IsTented(t.TopLayer())),
        })
    elif ARC and isinstance(t, ARC):
        base.update({
            "kind": "arc",
            "layer": _try(lambda: t.GetLayerName()),
            "start_mm": pt(_try(lambda: t.GetStart())),
            "mid_mm": pt(_try(lambda: t.GetMid())),
            "end_mm": pt(_try(lambda: t.GetEnd())),
            "radius_mm": _try(lambda: round(to_mm(t.GetRadius()), 5)),
            "angle_deg": deg(_try(lambda: t.GetAngle())),
        })
    else:
        base.update({
            "kind": "track",
            "layer": _try(lambda: t.GetLayerName()),
            "start_mm": pt(_try(lambda: t.GetStart())),
            "end_mm": pt(_try(lambda: t.GetEnd())),
            "length_mm": _try(lambda: round(to_mm(t.GetLength()), 5)),
        })
    return base

# ----------------------------------------------------------------------------
# DESIGN RULES & STACKUP
# ----------------------------------------------------------------------------

def _extract_design_rules(board):
    bds = _try(lambda: board.GetDesignSettings())
    if bds is None:
        return {}
    out = {
        "board_thickness_mm": _try(lambda: to_mm(bds.GetBoardThickness())),
        "aux_origin_mm": pt(_try(lambda: bds.GetAuxOrigin())),
        "grid_origin_mm": pt(_try(lambda: bds.GetGridOrigin())),
        "min_clearance_mm": _try(lambda: to_mm(bds.m_MinClearance)),
        "track_width_list_mm": _try(
            lambda: [round(to_mm(w), 5) for w in bds.m_TrackWidthList]),
        "via_dimensions": _try(lambda: [
            {"diameter_mm": round(to_mm(v.m_Diameter), 5),
             "drill_mm": round(to_mm(v.m_Drill), 5)} for v in bds.m_ViasDimensionsList]),
        "netclasses": {},
    }

    def netclasses():
        res = {}
        try:
            items = board.GetAllNetClasses().items()
        except Exception:
            return res
        for name, nc in items:
            if nc is None:
                continue
            res[str(name)] = {
                "track_width_mm": _try(lambda: to_mm(nc.GetTrackWidth())),
                "clearance_mm": _try(lambda: to_mm(nc.GetClearance())),
                "via_diameter_mm": _try(lambda: to_mm(nc.GetViaDiameter())),
                "via_drill_mm": _try(lambda: to_mm(nc.GetViaDrill())),
                "uvia_diameter_mm": _try(lambda: to_mm(nc.GetuViaDiameter())),
                "diff_pair_width_mm": _try(lambda: to_mm(nc.GetDiffPairWidth())),
                "diff_pair_gap_mm": _try(lambda: to_mm(nc.GetDiffPairGap())),
            }
        return res

    out["netclasses"] = _try(netclasses, {}, key="netclasses") or {}
    return out

def _extract_stackup(board):
    def go():
        su = board.GetDesignSettings().GetStackupDescriptor()
        try:
            items = su.GetList()
        except AttributeError:
            return []
        layers = []
        for it in items:
            layers.append({
                "type": _try(lambda: int(it.GetType())),
                "layer_name": _try(lambda: board.GetLayerName(it.GetBrdLayerId())),
                "thickness_mm": _try(lambda: to_mm(it.GetThickness())),
                "material": _try(lambda: it.GetMaterial()),
                "epsilon_r": _try(lambda: it.GetEpsilonR()),
            })
        return layers
    return _try(go, [], key="stackup") or []

# ----------------------------------------------------------------------------
# MAIN EXTRACTOR
# ----------------------------------------------------------------------------

def _fingerprint(state):
    """Stable hash of geometry-relevant content (ignores timestamps)."""
    clone = {k: v for k, v in state.items()
             if k not in ("meta", "fingerprint", "errors", "stats")}
    blob = json.dumps(clone, sort_keys=True, default=safe_json_default).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]

def _section(state, name, fn):
    try:
        fn()
    except Exception:
        state["errors"].append({"section": name, "trace": traceback.format_exc()})
        print("[pcb_brain][error] section %s failed (see state['errors'])" % name)

def get_full_board_state(board=None,
                         include_tracks=True,
                         include_zone_outlines=True,
                         include_fp_graphics=True,
                         net_filter=None):
    board = resolve_board(board)
    if board is None:
        raise RuntimeError("No board. Open a PCB or pass board=pcbnew.LoadBoard(path).")

    bbox = _try(lambda: board.GetBoardEdgesBoundingBox())

    state = {
        "schema": SCHEMA_VERSION,
        "meta": {
            "kicad_version": BUILD_VERSION,
            "extracted_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "units": "mm",
            "coord_note": "KiCad Y axis points DOWN; angles CCW degrees",
            "include_tracks": include_tracks,
            "net_filter": sorted(net_filter) if net_filter else None,
        },
        "board_info": {
            "file_name": _try(lambda: board.GetFileName(), ""),
            "copper_layers": _try(lambda: board.GetCopperLayerCount(), 0),
            "enabled_layers": _try(
                lambda: [board.GetLayerName(l) for l in board.GetEnabledLayers().Seq()], []),
            "bbox_mm": ({"x": round(to_mm(bbox.GetX()), 4),
                         "y": round(to_mm(bbox.GetY()), 4),
                         "w": round(to_mm(bbox.GetWidth()), 4),
                         "h": round(to_mm(bbox.GetHeight()), 4)} if bbox else None),
        },
        "design_rules": _extract_design_rules(board),
        "stackup": _extract_stackup(board),
        "nets": {},
        "footprints": [],
        "tracks": [],
        "arcs": [],
        "vias": [],
        "zones": [],
        "drawings": [],
        "groups": [],
        "errors": [],
    }

    # NETS
    def nets():
        for name, ni in board.GetNetsByName().items():
            name = str(name)
            if not name:
                continue
            state["nets"][name] = {
                "net_code": _try(lambda: ni.GetNetCode(), 0),
                "node_count": _try(lambda: ni.GetNodesCount(), 0),
                "netclass": _try(lambda: ni.GetNetClass().GetName()),
            }
    _section(state, "nets", nets)

    # FOOTPRINTS
    def fps():
        for fp in board.GetFootprints():
            state["footprints"].append(
                _extract_footprint(board, fp, include_fp_graphics))
    _section(state, "footprints", fps)

    # TRACKS / ARCS / VIAS
    if include_tracks:
        def tr():
            for t in board.GetTracks():
                d = _extract_track(board, t)
                if net_filter and d.get("net_name") not in net_filter:
                    continue
                state[{"via": "vias", "arc": "arcs", "track": "tracks"}[d["kind"]]].append(d)
        _section(state, "tracks", tr)

    # ZONES
    def zs():
        for i in range(board.GetAreaCount()):
            z = _extract_zone(board, board.GetArea(i))
            if net_filter and z.get("net_name") and z["net_name"] not in net_filter:
                continue
            if not include_zone_outlines:
                z.pop("outline_mm", None)
            state["zones"].append(z)
    _section(state, "zones", zs)

    # DRAWINGS
    def dr():
        for d in board.Drawings():
            state["drawings"].append(_extract_drawing(board, d))
    _section(state, "drawings", dr)

    # GROUPS
    def gr():
        for g in _try(lambda: list(board.Groups()), []) or []:
            state["groups"].append({
                "uuid": uuid_of(g),
                "name": _try(lambda: g.GetName(), ""),
                "members": [uuid_of(m) for m in _try(lambda: list(g.GetItems()), []) or []],
            })
    _section(state, "groups", gr)

    state["stats"] = {
        "footprints": len(state["footprints"]),
        "pads": sum(len(f["pads"]) for f in state["footprints"]),
        "nets": len(state["nets"]),
        "tracks": len(state["tracks"]),
        "arcs": len(state["arcs"]),
        "vias": len(state["vias"]),
        "zones": len(state["zones"]),
        "drawings": len(state["drawings"]),
        "unfilled_zones": [z["name"] or z["net_name"]
                           for z in state["zones"] if not z["is_filled"]],
    }
    state["fingerprint"] = _fingerprint(state)
    return state

# ----------------------------------------------------------------------------
# DESIGN INTENT
# ----------------------------------------------------------------------------

INTENT_TEMPLATE = {
    "schema": "pcb_brain.intent/1.0",
    "project": "",
    "goal": "",
    "constraints": {
        "board_outline": "",
        "keepouts": [],
        "thermal": [],
        "mechanical": []
    },
    "net_roles": {},
    "placement_rules": [],
    "manual_edits_log": [],
    "do_not_modify_uuids": []
}

def ensure_intent(board=None):
    board = resolve_board(board)
    p = os.path.join(_store_dir(board), "intent.json")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(INTENT_TEMPLATE, f, indent=2)
        print("[pcb_brain] created %s — fill this in, it's your real brain." % p)
    return p

def load_intent(board=None):
    p = ensure_intent(board)
    return json.load(open(p, encoding="utf-8"))

# ----------------------------------------------------------------------------
# AI CONTEXT BUNDLE
# ----------------------------------------------------------------------------

def ai_context(board=None, mode="summary", net_filter=None):
    """
    mode = "summary" -> compact (no track geometry). Give this first.
    mode = "full"    -> everything. Can be huge.
    """
    from .applier import OPS
    board = resolve_board(board)
    st = get_full_board_state(
        board,
        include_tracks=(mode == "full"),
        include_zone_outlines=(mode == "full"),
        include_fp_graphics=(mode == "full"),
        net_filter=net_filter)
    bundle = {
        "placement_report": _try(lambda: placement_report(board), {}),
        "state": st,
        "intent": _try(lambda: load_intent(board), {}),
        "op_schema": {
            "available_ops": sorted(OPS),
            "example": [
                {"op": "board.fit_outline", "margin": 5.0},
                {"op": "footprint.place", "anchor": "centre",
                 "ref": "U1", "x": 50.0, "y": 40.0, "rotation": 90},
                {"op": "zone.refill"},
            ],
            "rules": [
                "position_mm is the footprint ORIGIN (pin 1 on most connectors), NOT the centre. Never place using position_mm.",
                "Use footprint.place with anchor='centre' and let the code do the arithmetic.",
                "courtyard_mm is the real physical extent. bbox_mm includes silkscreen text and is too big -- ignore it for clearance.",
                "Overlap truth comes from placement_report.overlaps. The SVG is aesthetics only.",
                "If a batch is rejected, apply the returned move_b_by vectors verbatim. Do not recompute them.",
                "Always target items by 'uuid'; 'ref' only for footprints.",
                "Never invent net or layer names; use only those in state.",
                "Respect intent.do_not_modify_uuids and is_locked=true items.",
            ],
        },
    }
    d = _store_dir(board)
    p = os.path.join(d, "ai_context_%s.json" % mode)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, default=safe_json_default)
    size_kb = os.path.getsize(p) / 1024.0
    print("[pcb_brain] ai_context(%s) -> %s  (%.1f KB)" % (mode, p, size_kb))
    if size_kb > 900:
        print("  !! large. Use mode='summary' or net_filter=[...] for the AI prompt.")
    return bundle

