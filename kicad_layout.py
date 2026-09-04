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

from kaibridge.pcb.layout import apply_ops


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
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    ops_path = None
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
        else:
            print(
                f"Error: No ops.json found at {cand1} or {cand2}. Provide path explicitly.",
                file=sys.stderr
            )
            return 1

    with open(ops_path, "r", encoding="utf-8") as f:
        ops_data = json.load(f)

    mode_str = "DRY RUN (In-Memory Simulation)" if args.dry_run else "COMMITTED TO DISK"
    print(f"[*] Applying layout operations from: {ops_path.name} [{mode_str}]")

    res = apply_ops(project_dir, ops_data, dry_run=args.dry_run)

    if not res.get("success") and not args.dry_run:
        print(f"Error: {res.get('error', 'Layout operations failed')}", file=sys.stderr)
        return 1

    applied = res.get("applied_ops_count", 0)
    print("\n=== Layout Operations Result ===")
    print(f"  Operations Applied : {applied}")

    if args.dry_run:
        collisions = res.get("collisions_detected", 0)
        pairs = res.get("collision_pairs", [])
        print(f"  Courtyard Collisions: {collisions}")
        if collisions > 0:
            print("  COLLISIONS DETECTED:")
            for pair in pairs[:10]:
                print(f"    - {pair}")
            if len(pairs) > 10:
                print(f"    ... and {len(pairs) - 10} more.")
            print("\n  [!] Resolve courtyard overlaps in ops.json before committing.\n")
            return 1
        else:
            print("  Status: ZERO COLLISIONS (Geometry Gate Verified)")
    else:
        print("  Status: Successfully updated .kicad_pcb")

    print("\n  Next: Render snapshot via pcb_snapshot.py, or route via kicad_route.py.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
