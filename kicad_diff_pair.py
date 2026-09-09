#!/usr/bin/env python3
"""
kicad_diff_pair.py -- Differential Pair Synthesizer, Netclass Sync & Length/Skew Auditor CLI.
Detects differential pairs, inspects physical 3D copper lengths, calculates timing skew (ps),
and verifies compliance against high-speed tolerances.

Usage:
    python kicad_diff_pair.py "projects/<Project_Name>" --audit
    python kicad_diff_pair.py "projects/<Project_Name>" --detect
    python kicad_diff_pair.py "projects/<Project_Name>" --sync-netclasses
    python kicad_diff_pair.py "projects/<Project_Name>" --json
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

from kaibridge.pcb.diff_pair import (
    detect_differential_pairs,
    audit_differential_pairs,
    tune_differential_pair_skew,
    sync_diff_pair_netclasses,
    format_diff_pair_table
)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Headless Differential Pair Detection, Netclass Sync, Skew Auditor & Serpentine Tuner."
    )
    ap.add_argument("project_dir", help="Path to KiCad project folder")
    ap.add_argument("--audit", action="store_true", default=False, help="Run 3D length and timing skew audit")
    ap.add_argument("--tune", action="store_true", default=False, help="Automatically synthesize serpentine meanders to eliminate timing skew")
    ap.add_argument("--detect", action="store_true", default=False, help="Detect differential pairs on board")
    ap.add_argument("--sync-netclasses", action="store_true", default=False, help="Sync differential netclasses into .kicad_pro")
    ap.add_argument("--pair", type=str, default=None, help="Target specific differential pair by name (e.g. 'CAN')")
    ap.add_argument("--target-skew", type=float, default=0.10, help="Target residual skew in mm (default: 0.10)")
    ap.add_argument("--loops", type=int, default=4, help="Maximum meander loops to fit (default: 4)")
    ap.add_argument("--thickness", type=float, default=1.6, help="PCB substrate thickness in mm for via barrel compensation (default: 1.6)")
    ap.add_argument("--json", action="store_true", default=False, help="Output machine-readable JSON")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    # If --tune requested: run serpentine tuning
    if args.tune:
        res = tune_differential_pair_skew(
            project_dir,
            pair_name=args.pair,
            target_skew_mm=args.target_skew,
            max_loops=args.loops
        )
        if not res.get("success"):
            print(f"[-] Differential pair tuning failed: {res.get('error') or res.get('message')}", file=sys.stderr)
            if args.json:
                print(json.dumps(res, indent=2))
            return 1

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res.get("formatted_report", ""))
        return 0

    # Default action: run audit if no specific flag passed
    run_all = not (args.detect or args.sync_netclasses)

    # 1. Detect
    if args.detect or run_all:
        specs = detect_differential_pairs(project_dir)
        if args.detect and not args.audit:
            if args.json:
                print(json.dumps([s.to_dict() for s in specs], indent=2))
            else:
                print(f"[*] Detected {len(specs)} differential pair(s) in {project_dir.name}:")
                for s in specs:
                    print(f"    - {s.name:<10}: {s.pos_net} / {s.neg_net} | Target: {s.target_impedance:.0f}Ω | Max Skew: {s.max_skew_mm:.2f}mm | Width: {s.track_width_mm:.2f}mm | Gap: {s.gap_mm:.2f}mm")
            if not run_all:
                return 0

    # 2. Sync Netclasses
    if args.sync_netclasses:
        specs = detect_differential_pairs(project_dir)
        pro_files = list(project_dir.glob("*.kicad_pro"))
        if not pro_files:
            print("Error: No .kicad_pro found in project directory", file=sys.stderr)
            return 1
        ok = sync_diff_pair_netclasses(pro_files[0], specs)
        if ok:
            print(f"[+] Synchronized {len(specs)} differential netclass(es) into {pro_files[0].name}")
        else:
            print("[-] Failed to update .kicad_pro", file=sys.stderr)
            return 1
        if not run_all:
            return 0

    # 3. Audit
    if args.audit or run_all:
        res = audit_differential_pairs(project_dir, board_thickness_mm=args.thickness)
        if not res.get("success"):
            print(f"[-] Differential pair audit failed: {res.get('error')}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res.get("formatted_table", ""))

        # Exit code reflects whether all differential pairs passed tolerance check
        return 0 if res.get("all_passed", True) else 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
