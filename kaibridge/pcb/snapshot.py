"""
kaibridge/pcb/snapshot.py ? Board State Snapshot & Structural Diff Engine.

Captures timestamped board state snapshots for deterministic undo/rollback,
saves exact .kicad_pcb binary backups alongside JSON metadata,
and computes UUID-keyed structural diffs between any two snapshots or vs live board.

Aligned with Kaibridge 2.0 headless architecture:
  - Takes project_dir, stores snapshots in kaibridge_dump/snapshots/
  - Returns plain dicts (no SWIG pointer leaks)
"""
from __future__ import annotations

import json
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .inspector import get_board_state


_TOL_MM = 0.001  # 1 micron tolerance for float comparison


def _norm(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return v


def _field_diff(a: dict, b: dict, path: str = "") -> Dict[str, Any]:
    """Compute field-level diff between two dicts, ignoring uuid keys."""
    out = {}
    keys = set(a) | set(b)
    for k in sorted(keys):
        if k in ("uuid", "fingerprint", "state_file", "pcb_file", "snapshot_meta"):
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


def snapshot_board(project_dir: str | Path, tag: str = "") -> Dict[str, Any]:
    """Capture a timestamped board state snapshot and backup .kicad_pcb file.

    Args:
        project_dir: Path to the KiCad project directory.
        tag: Optional human-readable tag for this snapshot (e.g. 'pre_route', 'post_place').

    Returns:
        Dict with snapshot metadata and file paths.
    """
    proj = Path(project_dir).resolve()
    snap_dir = proj / "kaibridge_dump" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Capture full board state
    state = get_board_state(proj, mode="full")
    if not state.get("success"):
        return state

    # Generate timestamped filename
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_str = f"_{tag}" if tag else ""
    filename = f"snapshot_{ts}{tag_str}.json"
    snap_path = snap_dir / filename

    # Add snapshot metadata
    state["snapshot_meta"] = {
        "timestamp": ts,
        "tag": tag or "",
        "fingerprint": state.get("fingerprint", ""),
    }

    snap_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    # Backup physical .kicad_pcb file alongside the JSON snapshot
    pcb_snap_path = None
    pcb_files = list(proj.glob("*.kicad_pcb"))
    if pcb_files and pcb_files[0].exists():
        pcb_snap_path = snap_dir / f"snapshot_{ts}{tag_str}.kicad_pcb"
        try:
            shutil.copyfile(pcb_files[0], pcb_snap_path)
        except Exception:
            pcb_snap_path = None

    return {
        "success": True,
        "snapshot_file": str(snap_path),
        "pcb_backup": str(pcb_snap_path) if pcb_snap_path else None,
        "fingerprint": state.get("fingerprint", ""),
        "tag": tag,
        "timestamp": ts,
        "footprint_count": state.get("footprint_count", 0),
        "track_count": state.get("track_count", 0),
        "zone_count": state.get("zone_count", 0),
    }


def _resolve_snapshot_file(snap_dir: Path, query: str, ext: str = ".json") -> Optional[Path]:
    """Resolves a snapshot path by filename, tag, or partial match."""
    p = Path(query)
    if p.is_file():
        return p
    direct = snap_dir / query
    if direct.is_file():
        return direct
    if not query.endswith(ext):
        with_ext = snap_dir / f"{query}{ext}"
        if with_ext.is_file():
            return with_ext
    # Search by tag match
    matches = sorted(snap_dir.glob(f"*{query}*{ext}"), key=lambda x: x.stat().st_mtime)
    if matches:
        return matches[-1]
    return None


def restore_snapshot(
    project_dir: str | Path,
    tag: Optional[str] = None,
    snapshot_file: Optional[str] = None
) -> Dict[str, Any]:
    """Restores the board .kicad_pcb from a previously captured snapshot.

    Args:
        project_dir: Path to the KiCad project directory.
        tag: Optional human-readable tag (e.g. 'pre_route') to find target snapshot.
        snapshot_file: Optional direct filename or path to snapshot (.kicad_pcb or .json).

    Returns:
        Dict indicating success and restored file details.
    """
    proj = Path(project_dir).resolve()
    snap_dir = proj / "kaibridge_dump" / "snapshots"
    if not snap_dir.exists():
        return {"success": False, "error": f"No snapshots directory found in {proj}"}

    pcb_files = list(proj.glob("*.kicad_pcb"))
    if not pcb_files:
        return {"success": False, "error": f"No .kicad_pcb found in project {proj}"}
    live_pcb = pcb_files[0]

    target_pcb_snap: Optional[Path] = None

    if snapshot_file:
        cand = _resolve_snapshot_file(snap_dir, snapshot_file, ext=".kicad_pcb")
        if not cand:
            # If JSON was provided, look for corresponding .kicad_pcb
            cand_json = _resolve_snapshot_file(snap_dir, snapshot_file, ext=".json")
            if cand_json:
                pcb_peer = cand_json.with_suffix(".kicad_pcb")
                if pcb_peer.is_file():
                    cand = pcb_peer
        target_pcb_snap = cand

    elif tag:
        target_pcb_snap = _resolve_snapshot_file(snap_dir, f"_{tag}", ext=".kicad_pcb")
        if not target_pcb_snap:
            target_pcb_snap = _resolve_snapshot_file(snap_dir, tag, ext=".kicad_pcb")

    else:
        # Most recent .kicad_pcb snapshot
        snaps = sorted(snap_dir.glob("snapshot_*.kicad_pcb"), key=lambda p: p.stat().st_mtime)
        if snaps:
            target_pcb_snap = snaps[-1]

    if not target_pcb_snap or not target_pcb_snap.is_file():
        return {
            "success": False,
            "error": f"No valid .kicad_pcb snapshot found matching tag='{tag}' or file='{snapshot_file}' in {snap_dir}"
        }

    try:
        shutil.copyfile(target_pcb_snap, live_pcb)
        return {
            "success": True,
            "restored_from": str(target_pcb_snap),
            "target_pcb": str(live_pcb),
            "snapshot_name": target_pcb_snap.name
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to restore snapshot: {e}"}


def diff_board(
    project_dir: str | Path,
    snapshot_a: Optional[str] = None,
    snapshot_b: Optional[str] = None,
    tag_a: Optional[str] = None,
    tag_b: Optional[str] = None
) -> Dict[str, Any]:
    """Compute structural diff between two board snapshots or vs live board.

    Args:
        project_dir: Path to the KiCad project directory.
        snapshot_a / tag_a: Before snapshot path or tag.
        snapshot_b / tag_b: After snapshot path or tag. If omitted, diffs vs live board.
    """
    proj = Path(project_dir).resolve()
    snap_dir = proj / "kaibridge_dump" / "snapshots"

    query_a = snapshot_a or tag_a
    query_b = snapshot_b or tag_b

    # Resolve snapshot files
    path_a: Optional[Path] = None
    path_b: Optional[Path] = None

    if query_a:
        path_a = _resolve_snapshot_file(snap_dir, query_a, ext=".json")
        if not path_a:
            return {"success": False, "error": f"Snapshot A '{query_a}' not found in {snap_dir}"}

    if query_b:
        path_b = _resolve_snapshot_file(snap_dir, query_b, ext=".json")
        if not path_b:
            return {"success": False, "error": f"Snapshot B '{query_b}' not found in {snap_dir}"}

    if path_a and path_b:
        old = json.loads(path_a.read_text(encoding="utf-8"))
        new = json.loads(path_b.read_text(encoding="utf-8"))
        return _diff_dicts(old, new)

    elif path_a:
        # Diff against live board
        live = get_board_state(proj, mode="full")
        if not live.get("success"):
            return live
        old = json.loads(path_a.read_text(encoding="utf-8"))
        return _diff_dicts(old, live)

    else:
        # Find two most recent snapshots
        snaps = sorted(snap_dir.glob("snapshot_*.json"), key=lambda p: p.stat().st_mtime)
        if len(snaps) < 2:
            return {"success": False, "error": f"Need at least 2 snapshots in {snap_dir}, found {len(snaps)}"}
        path_a = snaps[-2]
        path_b = snaps[-1]
        old = json.loads(path_a.read_text(encoding="utf-8"))
        new = json.loads(path_b.read_text(encoding="utf-8"))
        return _diff_dicts(old, new)


def _diff_dicts(old: dict, new: dict) -> Dict[str, Any]:
    """Compute structured diff between two board state dicts."""
    report = {
        "success": True,
        "fingerprint_old": old.get("fingerprint"),
        "fingerprint_new": new.get("fingerprint"),
        "identical": old.get("fingerprint") == new.get("fingerprint"),
        "collections": {},
        "summary": {}
    }

    collections = [
        ("footprints", "reference"),
        ("tracks", "uuid"),
        ("vias", "uuid"),
        ("zones", "uuid"),
    ]

    for coll_name, key_field in collections:
        old_items = {item.get(key_field) or item.get("uuid"): item for item in old.get(coll_name, [])}
        new_items = {item.get(key_field) or item.get("uuid"): item for item in new.get(coll_name, [])}

        added = [new_items[k] for k in new_items if k not in old_items]
        removed = [old_items[k] for k in old_items if k not in new_items]
        modified = []

        for k in set(old_items) & set(new_items):
            fd = _field_diff(old_items[k], new_items[k])
            if fd:
                label = new_items[k].get("reference") or new_items[k].get("net_name") or k
                modified.append({"key": k, "label": label, "changes": fd})

        report["collections"][coll_name] = {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "added_items": added[:20],
            "removed_items": removed[:20],
            "modified_items": modified[:20],
        }
        report["summary"][coll_name] = f"+{len(added)} -{len(removed)} ~{len(modified)}"

    return report
