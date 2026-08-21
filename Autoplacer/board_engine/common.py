"""
Autoplacer/board_engine/common.py — Safe wrappers, unit conversions, and indexing helpers for KiCad.
"""

import os
import re
import sys
import datetime
import traceback

import pcbnew

SCHEMA_VERSION = "pcb_brain/2.0"

# ----------------------------------------------------------------------------
# SAFE CALL HELPERS
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

def _call_any(obj, method_names, default=None):
    for name in method_names:
        fn = getattr(obj, name, None)
        if fn is not None:
            try:
                return fn()
            except Exception:
                continue
    return default

def _enum(mod_name, default=None):
    return getattr(pcbnew, mod_name, default)

# ----------------------------------------------------------------------------
# BOARD RESOLUTION & SERIALIZATION
# ----------------------------------------------------------------------------

def _ensure_board(b):
    if b is None:
        raise RuntimeError("No board. Open a PCB in the PCB Editor.")
    if hasattr(b, "GetFootprints"):
        return b
    cast = getattr(pcbnew, "Cast_to_BOARD", None)
    if cast is not None:
        b2 = _try(lambda: cast(b))
        if b2 is not None and hasattr(b2, "GetFootprints"):
            _warn_once("cast", "BOARD arrived unwrapped; Cast_to_BOARD recovered it.")
            return b2
    raise RuntimeError(
        "BOARD proxy is corrupt (SwigPyObject). Close and reopen the Kaibridge window. "
        "Do not importlib.reload modules that import pcbnew.")

def resolve_board(board=None, pcb_path=None):
    if board is not None:
        return _ensure_board(board)
    if pcb_path:
        return pcbnew.LoadBoard(pcb_path)
    return _ensure_board(pcbnew.GetBoard())

def safe_json_default(obj):
    s = str(obj)
    if "<Swig Object" in s or "<class" in s:
        return None
    return s

# ----------------------------------------------------------------------------
# VERSION + UNITS
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

def deg(a):
    """EDA_ANGLE (KiCad 7+) or plain number -> float degrees."""
    if a is None:
        return None
    v = _try(lambda: a.AsDegrees())
    if v is None:
        v = _try(lambda: float(a))
    return round(float(v), 4) if v is not None else None

def mk_point(x_mm: float, y_mm: float) -> 'pcbnew.VECTOR2I':
    xi, yi = from_mm(x_mm), from_mm(y_mm)
    return pcbnew.VECTOR2I(xi, yi)

def pt(p):
    if p is None:
        return None
    return {"x": round(to_mm(p.x), 6), "y": round(to_mm(p.y), 6)}

# --- Grid-snap placement aid ---
DEFAULT_GRID_MM = 0.5

def snap_grid(v, grid=None):
    """Quantize a mm coordinate to the nearest grid step.
    grid=0 or grid=None disables snapping and returns the value unchanged.
    Default grid is 0.5 mm — fine enough for mixed-size components,
    coarse enough to eliminate micro-overlap decimal noise.
    """
    if grid is None:
        grid = DEFAULT_GRID_MM
    if grid <= 0:
        return float(v)
    return round(float(v) / grid) * grid

def uuid_of(item):
    return _try(lambda: item.m_Uuid.AsString(),
                _try(lambda: str(item.m_Uuid), None))

def _bbox(o):
    b = _try(lambda: o.GetBoundingBox())
    if b is None:
        return None
    return {"x": round(to_mm(b.GetX()), 4), "y": round(to_mm(b.GetY()), 4),
            "w": round(to_mm(b.GetWidth()), 4), "h": round(to_mm(b.GetHeight()), 4)}

def _box_json(b):
    return {"x0": round(b.x0, 3), "y0": round(b.y0, 3),
            "x1": round(b.x1, 3), "y1": round(b.y1, 3),
            "w": round(b.w, 3), "h": round(b.h, 3),
            "centre": {"x": round(b.cx, 3), "y": round(b.cy, 3)},
            "anchor_offset": list(b.anchor_offset),
            "source": b.source}

def _layers_of(board, item):
    seq = _try(lambda: list(item.GetLayerSet().Seq()))
    if seq:
        return [board.GetLayerName(l) for l in seq]
    single = _try(lambda: item.GetLayerName())
    return [single] if single else []

# ----------------------------------------------------------------------------
# ENUM DECODERS
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
# LIVE INDEX (uuid -> live pcbnew object)
# ----------------------------------------------------------------------------

def build_index(board=None):
    board = resolve_board(board)
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
# OPERATIONAL ERRORS & RESOLVERS
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
