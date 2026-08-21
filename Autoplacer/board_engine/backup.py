"""
Autoplacer/board_engine/backup.py — Snapshots, file backups, and diff calculation engine.
"""

import os
import re
import json
import datetime
import shutil

from .common import (
    resolve_board, _try, safe_json_default
)

_COLLECTIONS = ("footprints", "tracks", "arcs", "vias", "zones", "drawings", "groups")
_TOL_MM = 0.001  # 1 micron

def _store_dir(board):
    base = os.path.dirname(_try(lambda: board.GetFileName(), "") or "") or os.getcwd()
    d = os.path.join(base, "pcb_brain")
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "backups"), exist_ok=True)
    return d

def load_state(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ----------------------------------------------------------------------------
# DIFF ENGINE (uuid-keyed, float-tolerant)
# ----------------------------------------------------------------------------

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

def snapshot(board=None, tag="", write=True, **kw):
    from .fetcher import get_full_board_state
    board = resolve_board(board)
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

def quick_diff(board=None, against=None):
    from .fetcher import get_full_board_state
    board = resolve_board(board)
    d = _store_dir(board)
    old_path = against or os.path.join(d, "state_latest.json")
    if not os.path.exists(old_path):
        print("[pcb_brain] no previous snapshot; creating baseline.")
        return snapshot(board, tag="baseline")
    old = load_state(old_path)
    new = get_full_board_state(board)
    print_diff(diff_states(old, new))
    return new

