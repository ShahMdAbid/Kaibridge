#!/usr/bin/env python3
"""
kicad_layout.py -- Declarative Component Placement & Layout Engine.
Executes discrete layout operations (ops.json) on .kicad_pcb with 0.5mm grid snap and collision detection.

    python kicad_layout.py "projects/<Project_Name>"
    python kicad_layout.py "projects/<Project_Name>" ops.json
    python kicad_layout.py "projects/<Project_Name>" --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.pcb.layout import apply_ops, sanitize_silkscreen


def main(argv=None):
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

    # Handle dedicated silkscreen sanitation standalone invocations
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


if __name__ == "__main__":
    sys.exit(main())
