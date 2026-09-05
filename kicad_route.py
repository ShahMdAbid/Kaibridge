#!/usr/bin/env python3
"""
kicad_route.py -- Headless Autorouting, Ground Pour & DRC Execution CLI.
Exports Specctra DSN, executes Freerouting 2.4.1, imports SES, pours solid GND plane, and runs DRC.

    python kicad_route.py "projects/<Project_Name>"
    python kicad_route.py "projects/<Project_Name>" --track-width 0.3 --pour-gnd --drc
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
    ap.add_argument(
        "--strategy",
        choices=["auto", "fanout-first", "dual-layer"],
        default="auto",
        help="Routing strategy: auto (adaptive density detection), fanout-first (Strategy 1), or dual-layer (Strategy 2) (default: auto)"
    )
    ap.add_argument("--fanout-first", action="store_true", default=None, help="Force Dog-Bone GND fanout first protocol (Strategy 1)")
    ap.add_argument("--no-fanout-first", action="store_true", default=None, help="Force Dual-Layer routing protocol (Strategy 2)")
    ap.add_argument("--layers", type=int, choices=[2, 4], default=2, help="Number of copper layers (2 or 4, default: 2)")
    ap.add_argument("--drc", action="store_true", help="Run KiCad DRC check and output violations")
    ap.add_argument("--via-costs", type=int, default=140, help="Via cost penalty for multilayer routing (default: 140)")
    ap.add_argument("--no-daemon", action="store_true", help="Disable persistent REST daemon and force direct CLI execution")
    ap.add_argument("--no-neckdown", action="store_true", help="Disable automatic neckdown entering fine-pitch IC pads")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    # Resolve strategy from flags
    strategy = args.strategy
    if args.no_fanout_first:
        strategy = "dual-layer"
    elif args.fanout_first:
        strategy = "fanout-first"

    print(f"[*] Starting headless routing pipeline for: {project_dir.name}")
    print(f"  Track width     : {args.track_width} mm")
    print(f"  Edge clearance  : {args.edge_clearance_um} um")
    print(f"  Router timeout  : {args.timeout} s")
    print(f"  Strategy        : {strategy}")
    print(f"  Layers          : {args.layers}")
    print(f"  Via cost penalty: {args.via_costs}")
    print(f"  Daemon mode     : {'Disabled' if args.no_daemon else 'Enabled (Port 37864)'}")

    # 1. Execute Freerouting
    route_res = route_board(
        project_dir=project_dir,
        track_width_mm=args.track_width,
        timeout_sec=args.timeout,
        copper_edge_clearance_um=args.edge_clearance_um,
        strict_drc=True,
        max_passes=args.max_passes,
        fanout_first=True if strategy == "fanout-first" else (False if strategy == "dual-layer" else None),
        strategy=strategy,
        via_costs=args.via_costs,
        automatic_neckdown=not args.no_neckdown,
        use_daemon=not args.no_daemon
    )


    if not route_res.get("success"):
        print(f"\nError in routing: {route_res.get('error', 'Routing failed')}", file=sys.stderr)
        return 1

    print("\n=== Autorouting Complete ===")
    print(f"  Method       : {route_res.get('method', 'Freerouting 2.4.1')}")
    print(f"  Tracks/Vias  : SES imported into .kicad_pcb")

    # 2. Add GND plane if requested
    if args.pour_gnd:
        if args.layers == 4:
            print("\n[*] Pouring 4-layer copper planes: In1.Cu (GND), In2.Cu (+3V3/Power), B.Cu (GND)...")
            add_ground_plane(project_dir, net="GND", layer="In1.Cu", clearance_mm=0.3)
            # Check for 3V3 or VCC in design
            design_file = project_dir / "kaibridge_dump" / "design.json"
            if not design_file.exists():
                design_file = project_dir / "design.json"
            power_net = "+3V3"
            if design_file.exists():
                try:
                    d = json.loads(design_file.read_text(encoding="utf-8"))
                    nets = d.get("nets", {})
                    for candidate in ("+3V3", "3V3", "+5V", "5V", "VCC", "VDD", "VBUS", "VIN", "VBAT"):
                        if candidate in nets:
                            power_net = candidate
                            break
                except Exception:
                    pass
            add_ground_plane(project_dir, net=power_net, layer="In2.Cu", clearance_mm=0.3)
            pour_res = add_ground_plane(project_dir, net="GND", layer="B.Cu", clearance_mm=0.3)
        else:
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

        # Auto-fallback: If Strategy 1 left unconnected airwires, automatically recover via Strategy 2
        if unconn > 0 and (strategy == "auto" or route_res.get("fanout_first_used")):
            print(f"\n[!] Strategy 1 left {unconn} unrouted nets. Automatically recovering via Strategy 2 (Dual-Layer Routing)...")
            rules_file = project_dir / f"{project_dir.name}.rules"
            if rules_file.exists():
                try:
                    rules_file.unlink()
                except Exception:
                    pass

            route_res = route_board(
                project_dir=project_dir,
                track_width_mm=args.track_width,
                timeout_sec=args.timeout,
                copper_edge_clearance_um=args.edge_clearance_um,
                strict_drc=True,
                max_passes=args.max_passes or 5,
                fanout_first=False,
                strategy="dual-layer"
            )

            if args.pour_gnd:
                add_ground_plane(project_dir, net="GND", layer="B.Cu", clearance_mm=0.3)

            drc_res = run_drc(project_dir)

        clr_errs = drc_res.get("geometric_clearance_errors", 0)
        unconn = drc_res.get("unconnected_airwires_count", 0)
        warns = drc_res.get("clearance_warnings", 0)
        err_violations = drc_res.get("error_violations", [])
        warn_violations = drc_res.get("warning_violations", [])

        print("\n=== DRC Verification Report ===")
        print(f"  Clearance Errors  : {clr_errs}")
        print(f"  Unconnected Nets  : {unconn}")
        print(f"  Warnings          : {warns}")

        if clr_errs > 0 or unconn > 0:
            print("\n  [!] ERRORS / UNCONNECTED ITEMS:")
            for v in err_violations[:10]:
                print(f"    - {v}")
            for u in drc_res.get("unconnected_items", [])[:10]:
                print(f"    - [unconnected] {u.get('description', str(u))}")
            if len(err_violations) > 10:
                print(f"    ... and {len(err_violations) - 10} more errors.")
            return 1

        if warns > 0:
            print(f"\n  [*] WARNINGS ({warns}):")
            for w in warn_violations[:10]:
                print(f"    - {w}")
            if len(warn_violations) > 10:
                print(f"    ... and {len(warn_violations) - 10} more warnings.")

        if warns > 0:
            print(f"\n  Status: PASSED WITH WARNINGS (0 Clearance Violations, 0 Unconnected Items, {warns} Warnings)")
        else:
            print("\n  Status: PASSED CLEAN (0 Clearance Violations, 0 Unconnected Items, 0 Warnings)")

    print("\n  Next: Export manufacturing files via export_jlcpcb.py.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
