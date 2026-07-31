"""
pcb_brain.py — KiCad PCB state extraction / diff / batch-apply toolkit
Tested-shape for KiCad 6, 7, 8, 9, 10. Every version-fragile call goes through
_try() or _call_any() so a missing API degrades to None instead of crashing.
"""

import os
import re
import json
import math
import time
import shutil
import hashlib
import datetime
import traceback

import pcbnew

def safe_json_default(obj):
    s = str(obj)
    if "<Swig Object" in s or "<class" in s:
        return None
    return s

SCHEMA_VERSION = "pcb_brain/2.0"

# ----------------------------------------------------------------------------
# 0. SAFE CALL HELPERS
# ----------------------------------------------------------------------------

_WARNED = set()

def _warn_once(key, msg):
    if key not in _WARNED:
        _WARNED.add(key)
        print("[pcb_brain][warn] %s" % msg)

def _try(fn, default=None, key=None):
    """Run fn(); on ANY exception return default. Never let extraction die."""
    try:
        return fn()
    except Exception as e:
        if key:
            _warn_once(key, "%s -> %s: %s" % (key, type(e).__name__, e))
        return default


def _enum(mod_name, default=None):
    return getattr(pcbnew, mod_name, default)

# ----------------------------------------------------------------------------
# 1. VERSION + UNITS
# ----------------------------------------------------------------------------

BUILD_VERSION = _try(lambda: pcbnew.GetBuildVersion(), "unknown")
_MAJOR = _try(lambda: int(re.search(r"(\d+)", BUILD_VERSION).group(1)), 0)

def to_mm(v):
    """internal units -> mm (float)."""
    if v is None:
        return None
    try:
        return float(pcbnew.ToMM(v))
    except Exception:
        return float(v) / 1000000.0  # IU_PER_MM fallback

def from_mm(v):
    return pcbnew.FromMM(float(v))

def mk_point(x_mm: float, y_mm: float) -> 'pcbnew.VECTOR2I':
    xi, yi = from_mm(x_mm), from_mm(y_mm)
    return pcbnew.VECTOR2I(xi, yi)

def pt(p):
    if p is None:
        return None
    return {"x": round(to_mm(p.x), 6), "y": round(to_mm(p.y), 6)}

def uuid_of(item):
    return _try(lambda: item.m_Uuid.AsString(),
                _try(lambda: str(item.m_Uuid), None))

def _bbox(o):
    b = _try(lambda: o.GetBoundingBox())
    if b is None:
        return None
    return {"x": round(to_mm(b.GetX()), 4), "y": round(to_mm(b.GetY()), 4),
            "w": round(to_mm(b.GetWidth()), 4), "h": round(to_mm(b.GetHeight()), 4)}

def _layers_of(board, item):
    seq = _try(lambda: list(item.GetLayerSet().Seq()))
    if seq:
        return [board.GetLayerName(l) for l in seq]
    single = _try(lambda: item.GetLayerName())
    return [single] if single else []

# ----------------------------------------------------------------------------
# 2. ENUM DECODERS
# ----------------------------------------------------------------------------

_VIA_TYPES = {}
for _n, _label in (("VIATYPE_THROUGH", "through"),
                   ("VIATYPE_BLIND_BURIED", "blind_buried"),
                   ("VIATYPE_MICROVIA", "microvia")):
    _v = _enum(_n)
    if _v is not None:
        _VIA_TYPES[int(_v)] = _label

_PAD_ATTRS = {}
for _n, _label in (("PAD_ATTRIB_PTH", "pth"), ("PAD_ATTRIB_SMD", "smd"),
                   ("PAD_ATTRIB_CONN", "connector"), ("PAD_ATTRIB_NPTH", "npth")):
    _v = _enum(_n)
    if _v is not None:
        _PAD_ATTRS[int(_v)] = _label

_ZONE_CONN = {0: "none", 1: "thermal_relief", 2: "solid", 3: "thru_hole_only"}

def _fp_attributes(fp):
    a = _try(lambda: int(fp.GetAttributes()), 0)

    def bit(name):
        v = _enum(name)
        return bool(a & int(v)) if v is not None else None

    return {
        "smd": bit("FP_SMD"),
        "through_hole": bit("FP_THROUGH_HOLE"),
        "exclude_from_bom": bit("FP_EXCLUDE_FROM_BOM"),
        "exclude_from_pos": bit("FP_EXCLUDE_FROM_POS_FILES"),
        "board_only": bit("FP_BOARD_ONLY"),
        "dnp": _try(lambda: bool(fp.IsDNP()), None),
    }

def _fp_fields(fp):
    """All user fields/properties across v6..v9 naming."""
    out = {}
    d = _try(lambda: dict(fp.GetFieldsShownText()))
    if isinstance(d, dict) and d:
        out.update({str(k): str(v) for k, v in d.items()})
    d = _try(lambda: dict(fp.GetProperties()))
    if isinstance(d, dict) and d:
        out.update({str(k): str(v) for k, v in d.items()})
    flds = _try(lambda: list(fp.GetFields()))
    if flds:
        for f in flds:
            k = _try(lambda: f.GetName())
            v = _try(lambda: f.GetText())
            if k:
                out[str(k)] = str(v) if v is not None else ""
    return out

# ----------------------------------------------------------------------------
# 3. EXTRACTORS (one per entity kind)
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
        "courtyard_area_mm2": _try(
            lambda: round(to_mm(to_mm(fp.GetCourtyard(fp.GetLayer()).Area())), 4)),
        "models_3d": _try(lambda: [m.m_Filename for m in fp.Models()], []),
        "pads": [_extract_pad(board, p) for p in fp.Pads()],
        "graphics": [],
    }
    if include_fp_graphics:
        for g in _try(lambda: list(fp.GraphicalItems()), []) or []:
            d["graphics"].append(_extract_drawing(board, g, shallow=True))
    return d

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
            "arc_angle_deg": _try(lambda: d.GetArcAngleStart()),
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
            "copper_pour": bool(z.GetDoNotAllowCopperPour()),
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
            "angle_deg": _try(lambda: t.GetAngle()),
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
# 4. DESIGN RULES / STACKUP
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
        layers = []
        for it in su.GetList():
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
# 5. MAIN EXTRACTOR
# ----------------------------------------------------------------------------

def get_full_board_state(board=None,
                         include_tracks=True,
                         include_zone_outlines=True,
                         include_fp_graphics=True,
                         net_filter=None):
    """
    net_filter: optional list/set of net names. If given, tracks/vias/zones are
                limited to those nets (useful for huge boards).
    """
    board = board or pcbnew.GetBoard()
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

def _section(state, name, fn):
    try:
        fn()
    except Exception:
        state["errors"].append({"section": name, "trace": traceback.format_exc()})
        print("[pcb_brain][error] section %s failed (see state['errors'])" % name)

def _fingerprint(state):
    """Stable hash of geometry-relevant content (ignores timestamps)."""
    clone = {k: v for k, v in state.items()
             if k not in ("meta", "fingerprint", "errors", "stats")}
    blob = json.dumps(clone, sort_keys=True, default=safe_json_default).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]

# ----------------------------------------------------------------------------
# 6. SNAPSHOT STORE
# ----------------------------------------------------------------------------

def _store_dir(board):
    base = os.path.dirname(_try(lambda: board.GetFileName(), "") or "") or os.getcwd()
    d = os.path.join(base, "pcb_brain")
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "backups"), exist_ok=True)
    return d

def snapshot(board=None, tag="", write=True, **kw):
    board = board or pcbnew.GetBoard()
    st = get_full_board_state(board, **kw)
    if write:
        d = _store_dir(board)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", tag)[:40]
        name = "state_%s%s.json" % (ts, ("_" + safe_tag) if safe_tag else "")
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, default=safe_json_default)
        with open(os.path.join(d, "state_latest.json"), "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, default=safe_json_default)
        st["meta"]["saved_to"] = path
        print("[pcb_brain] snapshot -> %s  (fp=%s)" % (path, st["fingerprint"]))
    return st

def load_state(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ----------------------------------------------------------------------------
# 7. DIFF ENGINE (uuid-keyed, float-tolerant)
# ----------------------------------------------------------------------------

_COLLECTIONS = ("footprints", "tracks", "arcs", "vias", "zones", "drawings", "groups")
_TOL_MM = 0.001  # 1 micron

def _norm(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return v

def _field_diff(a, b, path=""):
    out = {}
    keys = set(a) | set(b)
    for k in sorted(keys):
        if k == "uuid":
            continue
        va, vb = a.get(k), b.get(k)
        if isinstance(va, dict) and isinstance(vb, dict):
            sub = _field_diff(va, vb, path + k + ".")
            out.update(sub)
            continue
        if isinstance(va, float) and isinstance(vb, float):
            if abs(va - vb) > _TOL_MM:
                out[path + k] = {"old": round(va, 4), "new": round(vb, 4)}
            continue
        if _norm(va) != _norm(vb):
            out[path + k] = {"old": _norm(va), "new": _norm(vb)}
    return out

def diff_states(old, new, verbose_fields=True):
    """Returns added / removed / modified per collection, keyed by uuid."""
    report = {
        "fingerprint": {"old": old.get("fingerprint"), "new": new.get("fingerprint")},
        "identical": old.get("fingerprint") == new.get("fingerprint"),
        "collections": {},
        "summary": {},
    }
    for coll in _COLLECTIONS:
        a = {i.get("uuid"): i for i in old.get(coll, []) if i.get("uuid")}
        b = {i.get("uuid"): i for i in new.get(coll, []) if i.get("uuid")}
        added = [b[u] for u in b if u not in a]
        removed = [a[u] for u in a if u not in b]
        modified = []
        for u in set(a) & set(b):
            fd = _field_diff(a[u], b[u])
            if fd:
                modified.append({
                    "uuid": u,
                    "label": b[u].get("reference") or b[u].get("net_name") or b[u].get("name") or coll,
                    "changes": fd if verbose_fields else sorted(fd.keys()),
                })
        report["collections"][coll] = {
            "added": added, "removed": removed, "modified": modified}
        report["summary"][coll] = {
            "added": len(added), "removed": len(removed), "modified": len(modified)}

    # net-level diff
    on, nn = old.get("nets", {}), new.get("nets", {})
    report["nets"] = {
        "added": sorted(set(nn) - set(on)),
        "removed": sorted(set(on) - set(nn)),
    }
    return report

def print_diff(report):
    print("=" * 60)
    print("PCB DIFF  %s -> %s  %s" % (
        report["fingerprint"]["old"], report["fingerprint"]["new"],
        "(IDENTICAL)" if report["identical"] else ""))
    for coll, s in report["summary"].items():
        if any(s.values()):
            print("  %-11s +%-4d -%-4d ~%-4d" % (coll, s["added"], s["removed"], s["modified"]))
    for coll, c in report["collections"].items():
        for m in c["modified"][:40]:
            print("   ~ [%s] %s" % (coll, m["label"]))
            for k, v in list(m["changes"].items())[:6]:
                print("       %s: %s -> %s" % (k, v["old"], v["new"]))
    if report["nets"]["added"] or report["nets"]["removed"]:
        print("  nets +%s -%s" % (report["nets"]["added"], report["nets"]["removed"]))
    print("=" * 60)

# ----------------------------------------------------------------------------
# 8. LIVE INDEX (uuid -> live pcbnew object)
# ----------------------------------------------------------------------------

def build_index(board=None):
    board = board or pcbnew.GetBoard()
    idx = {"by_uuid": {}, "by_ref": {}, "pads": {}, "nets": {}, "layers": {}}

    for fp in board.GetFootprints():
        u = uuid_of(fp)
        idx["by_uuid"][u] = fp
        ref = _try(lambda: fp.GetReference())
        if ref:
            idx["by_ref"][ref] = fp
        for p in fp.Pads():
            pu = uuid_of(p)
            idx["by_uuid"][pu] = p
            idx["pads"]["%s.%s" % (ref, _call_any(p, ["GetNumber", "GetPadName"], ""))] = p
    for t in board.GetTracks():
        idx["by_uuid"][uuid_of(t)] = t
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        idx["by_uuid"][uuid_of(z)] = z
    for d in board.Drawings():
        idx["by_uuid"][uuid_of(d)] = d
    for g in _try(lambda: list(board.Groups()), []) or []:
        idx["by_uuid"][uuid_of(g)] = g

    for name, ni in board.GetNetsByName().items():
        if str(name):
            idx["nets"][str(name)] = ni
    for l in _try(lambda: list(board.GetEnabledLayers().Seq()), []) or []:
        idx["layers"][board.GetLayerName(l)] = l
    return idx

# ----------------------------------------------------------------------------
# 9. OPERATIONS
# ----------------------------------------------------------------------------

class OpError(Exception):
    pass

def _need(op, *keys):
    for k in keys:
        if k not in op or op[k] is None:
            raise OpError("op '%s' missing required field '%s'" % (op.get("op"), k))

def _resolve_fp(idx, op):
    if op.get("uuid"):
        o = idx["by_uuid"].get(op["uuid"])
        if o is None:
            raise OpError("uuid not found: %s" % op["uuid"])
        return o
    if op.get("ref"):
        o = idx["by_ref"].get(op["ref"])
        if o is None:
            raise OpError("reference not found: %s" % op["ref"])
        return o
    raise OpError("need 'uuid' or 'ref'")

def _resolve_layer(idx, name):
    if name not in idx["layers"]:
        raise OpError("layer '%s' not enabled. Available: %s"
                      % (name, sorted(idx["layers"])))
    return idx["layers"][name]

def _resolve_net(idx, name):
    if name in (None, ""):
        return None
    if name not in idx["nets"]:
        raise OpError("net '%s' does not exist on this board" % name)
    return idx["nets"][name]

# --- individual op handlers: fn(board, idx, op, dry) -> description string ---

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
    _need(op, "net")
    _resolve_net(idx, op["net"])
    layers = op.get("layers")
    victims = []
    for t in list(board.GetTracks()):
        if _try(lambda: t.GetNetname()) != op["net"]:
            continue
        if layers and _try(lambda: t.GetLayerName()) not in layers:
            continue
        if t.IsLocked() and not op.get("force"):
            continue
        victims.append(t)
    if not dry:
        for t in victims:
            board.Remove(t)
    return "delete %d routed items on net '%s'" % (len(victims), op["net"])

def _op_zone_refill(board, idx, op, dry):
    if not dry:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
    return "refill all zones"

OPS = {
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
}

# ----------------------------------------------------------------------------
# 10. APPLY (validate-all -> backup -> execute -> verify)
# ----------------------------------------------------------------------------

def apply_ops(ops, board=None, dry_run=True, save=False, refill=True, verify=True):
    board = board or pcbnew.GetBoard()
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

    if refill and failed is None:
        _try(lambda: pcbnew.ZONE_FILLER(board).Fill(board.Zones()), key="refill")

    _try(lambda: pcbnew.Refresh())

    if save and failed is None and path:
        pcbnew.SaveBoard(path, board)
        print("[pcb_brain] saved -> %s" % path)

    result = {"applied": True, "done": done, "failed": failed, "backup": backup}

    # ---- 4. verify ----
    if verify:
        post = get_full_board_state(board)
        rep = diff_states(pre, post)
        print_diff(rep)
        result["diff_summary"] = rep["summary"]
    return result

# ----------------------------------------------------------------------------
# 11. DRC SNAPSHOT
# ----------------------------------------------------------------------------
def run_drc(board=None, report_path=None):
    # Disabled for KiCad 10 stability: WriteDRCReport can segfault.
    print("[pcb_brain] DRC explicitly disabled to prevent KiCad 10 crash.")
    return None

# ----------------------------------------------------------------------------
# 12. DESIGN INTENT (the part geometry can never tell you)
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
    board = board or pcbnew.GetBoard()
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
# 13. AI CONTEXT BUNDLE
# ----------------------------------------------------------------------------

def ai_context(board=None, mode="summary", net_filter=None):
    """
    mode = "summary" -> compact (no track geometry). Give this first.
    mode = "full"    -> everything. Can be huge.
    """
    board = board or pcbnew.GetBoard()
    st = get_full_board_state(
        board,
        include_tracks=(mode == "full"),
        include_zone_outlines=(mode == "full"),
        include_fp_graphics=(mode == "full"),
        net_filter=net_filter)
    bundle = {
        "state": st,
        "intent": _try(lambda: load_intent(board), {}),
        "op_schema": {
            "available_ops": sorted(OPS),
            "example": [
                {"op": "footprint.move", "ref": "U1", "x": 50.0, "y": 40.0, "rotation": 90},
                {"op": "net.delete_routing", "net": "GND", "layers": ["F.Cu"]},
                {"op": "track.add", "net": "VBUS", "layer": "F.Cu", "width": 0.6,
                 "start": {"x": 10, "y": 10}, "end": {"x": 20, "y": 10}},
                {"op": "via.add", "net": "GND", "x": 15, "y": 12,
                 "width": 0.6, "drill": 0.3},
                {"op": "zone.refill"},
            ],
            "rules": [
                "Always target items by 'uuid' from state; 'ref' only for footprints.",
                "All coordinates in mm, KiCad Y axis points DOWN.",
                "Never invent net names or layer names; use only those in state.",
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

# ----------------------------------------------------------------------------
# 14. CLI
# ----------------------------------------------------------------------------

def quick_diff(board=None, against=None):
    board = board or pcbnew.GetBoard()
    d = _store_dir(board)
    old_path = against or os.path.join(d, "state_latest.json")
    if not os.path.exists(old_path):
        print("[pcb_brain] no previous snapshot; creating baseline.")
        return snapshot(board, tag="baseline")
    old = load_state(old_path)
    new = get_full_board_state(board)
    print_diff(diff_states(old, new))
    return new

if __name__ == "__main__":
    _b = pcbnew.GetBoard()
    print(json.dumps(get_full_board_state(_b), indent=2, default=safe_json_default))
