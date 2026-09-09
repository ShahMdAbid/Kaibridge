#!/usr/bin/env python3
"""CLI for the physics-preserving ISRRO-X post-placement optimizer."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.pcb.swap_optimizer import OptimizerConfig, optimize_placement


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic isomorphic swap/rotate placement refinement for KiCad.")
    ap.add_argument("project_dir", help="KiCad project directory")
    ap.add_argument("--commit", action="store_true", help="Commit the verified result; default is audit-only")
    ap.add_argument("--allow-routed-board", action="store_true", help="Explicitly permit moving footprints on a board containing tracks")
    ap.add_argument("--clearance", type=float, default=0.25, help="Minimum component-envelope clearance in mm")
    ap.add_argument("--grid", type=float, default=0.1, help="Placement grid in mm")
    ap.add_argument("--passes", type=int, default=8, help="Maximum accepted best-improvement passes")
    ap.add_argument("--max-evaluations", type=int, default=12000, help="Maximum virtual states to score")
    ap.add_argument("--time-limit", type=float, default=20.0, help="Search time limit in seconds")
    ap.add_argument("--max-pairs-per-class", type=int, default=250, help="Candidate pair cap per equivalence class")
    ap.add_argument("--no-three-cycles", action="store_true", help="Disable bounded 3-cycle escape neighborhood")
    ap.add_argument("--relaxed-anchor", action="store_true", help="Permit same-class candidates with different anchors")
    ap.add_argument("--relaxed-group", action="store_true", help="Permit same-class candidates across functional groups")
    ap.add_argument("--include-plane-nets", action="store_true", help="Include GND/reference-plane nets in placement proxies")
    ap.add_argument("--lock", action="append", default=[], help="Additional reference to lock; repeatable")
    ap.add_argument("--json", action="store_true", help="Print the complete JSON report")
    args = ap.parse_args(argv)

    cfg = OptimizerConfig(
        clearance_mm=args.clearance,
        grid_mm=args.grid,
        max_passes=args.passes,
        max_evaluations=args.max_evaluations,
        max_pairs_per_class=args.max_pairs_per_class,
        time_limit_s=args.time_limit,
        strict_same_anchor=not args.relaxed_anchor,
        preserve_group=not args.relaxed_group,
        enable_three_cycles=not args.no_three_cycles,
        ignore_plane_nets=not args.include_plane_nets,
        allow_routed_board=args.allow_routed_board,
        commit=args.commit,
        locked_refs=tuple(args.lock),
    )
    result = optimize_placement(Path(args.project_dir), cfg)
    if args.json or not result.get("success"):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        before, after = result.get("before", {}), result.get("after", {})
        print(f"Algorithm: {result.get('algorithm')}")
        print(f"Accepted moves: {result.get('accepted_move_count', 0)}")
        print(f"Crossings: {before.get('crossings')} -> {after.get('crossings')}")
        print(f"Blocked escapes: {before.get('blocked_escapes')} -> {after.get('blocked_escapes')}")
        print(f"RUDY overflow: {before.get('rudy_overflow')} -> {after.get('rudy_overflow')}")
        print(f"Weighted HPWL: {before.get('weighted_hpwl')} -> {after.get('weighted_hpwl')}")
        print(f"Committed: {result.get('committed', False)}")
        print(f"Report: {result.get('report_file')}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
