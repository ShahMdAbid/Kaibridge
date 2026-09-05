#!/usr/bin/env python3
"""
kicad_route.py -- Headless Autorouting, Ground Pour & DRC Execution CLI.
Exports Specctra DSN, executes Freerouting 2.4.1, imports SES, pours solid GND plane, and runs DRC.

    python kicad_route.py "projects/<Project_Name>"
    python kicad_route.py "projects/<Project_Name>" --track-width 0.3 --pour-gnd --drc
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.pcb.router import route_board, add_ground_plane
from kaibridge.pcb.drc import run_drc


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Headless Freerouting autorouter, GND plane pour, and DRC verification gate."
    )
    ap.add_argument("project_dir", help="Path to KiCad project folder")
    ap.add_argument("--track-width", type=float, default=0.25, help="Default track width in mm (default: 0.25)")
    ap.add_argument("--timeout", type=int, default=300, help="Router timeout in seconds (default: 300)")
    ap.add_argument("--edge-clearance-um", type=int, default=150, help="Board edge clearance in um (default: 150)")
    ap.add_argument("--max-passes", type=int, default=None, help="Maximum Freerouting optimization passes")
    ap.add_argument("--pour-gnd", action="store_true", default=True, help="Pour solid GND copper zone on B.Cu after routing (default: true)")
    ap.add_argument("--no-pour-gnd", action="store_false", dest="pour_gnd", help="Do not pour ground plane")
    ap.add_argument("--fanout-first", action="store_true", default=True, help="Pre-place Dog-Bone GND fanouts and route signals on F.Cu (default: true)")
    ap.add_argument("--no-fanout-first", action="store_false", dest="fanout_first", help="Disable Dog-Bone fanout first protocol")
    ap.add_argument("--drc", action="store_true", help="Run KiCad DRC check and output violations")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"[*] Starting headless routing pipeline for: {project_dir.name}")
    print(f"  Track width     : {args.track_width} mm")
    print(f"  Edge clearance  : {args.edge_clearance_um} um")
    print(f"  Router timeout  : {args.timeout} s")
    print(f"  Fanout First    : {args.fanout_first}")

    # 1. Execute Freerouting
    route_res = route_board(
        project_dir=project_dir,
        track_width_mm=args.track_width,
        timeout_sec=args.timeout,
        copper_edge_clearance_um=args.edge_clearance_um,
        strict_drc=True,
        max_passes=args.max_passes,
        fanout_first=args.fanout_first
    )

    if not route_res.get("success"):
        print(f"\nError in routing: {route_res.get('error', 'Routing failed')}", file=sys.stderr)
        return 1

    print("\n=== Autorouting Complete ===")
    print(f"  Method       : {route_res.get('method', 'Freerouting 2.4.1')}")
    print(f"  Tracks/Vias  : SES imported into .kicad_pcb")

    # 2. Add GND plane if requested
    if args.pour_gnd:
        print("\n[*] Pouring solid GND copper plane on B.Cu...")
        pour_res = add_ground_plane(project_dir, net="GND", layer="B.Cu", clearance_mm=0.3)
        if pour_res.get("success"):
            print("  Status: GND copper zone filled with 0.3mm clearance")
        else:
            print(f"  Warning: Ground pour failed: {pour_res.get('error')}")

    # 3. Run DRC if requested
    if args.drc:
        print("\n[*] Running Design Rules Check (DRC)...")
        drc_res = run_drc(project_dir)
        clr_errs = drc_res.get("geometric_clearance_errors", 0)
        unconn = drc_res.get("unconnected_airwires_count", 0)
        violations = drc_res.get("violations", [])

        print("=== DRC Verification Report ===")
        print(f"  Clearance Errors  : {clr_errs}")
        print(f"  Unconnected Nets  : {unconn}")

        if clr_errs > 0 or unconn > 0:
            print("  VIOLATIONS:")
            for v in violations[:10]:
                print(f"    - {v}")
            if len(violations) > 10:
                print(f"    ... and {len(violations) - 10} more.")
            return 1
        else:
            print("  Status: PASSED (0 Clearance Violations, 0 Unconnected Items)")

    print("\n  Next: Export manufacturing files via export_jlcpcb.py.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
