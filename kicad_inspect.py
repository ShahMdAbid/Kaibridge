#!/usr/bin/env python3
"""
kicad_inspect.py -- Live KiCad PCB State Inspector CLI.
Extracts structured board state directly from .kicad_pcb:
Footprints (positions, rotations, courtyards, pads), nets, tracks, vias, zones, and design rules.

Usage:
    python kicad_inspect.py "projects/<Project_Name>" --summary
    python kicad_inspect.py "projects/<Project_Name>" --full
    python kicad_inspect.py "projects/<Project_Name>" --json
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

from kaibridge.pcb.inspector import get_board_state, get_spatial_occupancy


def main():
    ap = argparse.ArgumentParser(description="Live KiCad PCB State Inspector")
    ap.add_argument("project_dir", help="Path to KiCad project directory or .kicad_pcb file")
    ap.add_argument("--summary", action="store_true", default=True, help="Extract summary state (footprints, nets, rules; default)")
    ap.add_argument("--full", action="store_true", help="Extract full state (including all individual tracks, vias, zones)")
    ap.add_argument("--free-space", action="store_true", help="Analyze board spatial occupancy and report maximal free rectangular pockets")
    ap.add_argument("--audit", "--route-ready", dest="audit", action="store_true", help="Execute fail-closed Gatekeeper Route-Readiness Proof (placement audit)")
    ap.add_argument("--json", action="store_true", help="Output raw JSON instead of human-readable summary")
    args = ap.parse_args()

    mode = "full" if args.full else "summary"
    proj_path = Path(args.project_dir).expanduser().resolve()
    
    # If a .kicad_pcb file was passed directly, use its parent directory
    if proj_path.is_file() and proj_path.suffix == ".kicad_pcb":
        proj_dir = proj_path.parent
    else:
        proj_dir = proj_path

    if not proj_dir.is_dir():
        print(f"Error: {proj_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    if args.audit:
        from kaibridge.pcb.gatekeeper import placement_audit
        res = placement_audit(proj_dir)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print("\n================================================================================================")
            print(" [KAIBRIDGE GATEKEEPER ROUTE-READINESS PROOF]")
            print("================================================================================================")
            print(f"  Project           : {proj_dir.name}")
            print(f"  Outline Closed    : {res.get('outline_closed')}")
            print(f"  Overlap Count     : {res.get('overlap_count')}")
            print(f"  Outside Outline   : {res.get('outside_outline_count')}")
            missing_nc = res.get('netclasses_without_track_width', [])
            print(f"  Missing Netclasses: {missing_nc if missing_nc else 'None (All configured)'}")
            ready = res.get('route_ready', False)
            print(f"  Route Readiness   : {'[VERIFIED - ROUTE READY]' if ready else '[FAIL - NOT READY]'}")
            print("================================================================================================\n")
        sys.exit(0 if res.get('route_ready') else 1)

    if args.free_space:
        res = get_spatial_occupancy(proj_dir)
        if not res.get("success"):
            print(f"[-] Error calculating spatial occupancy: {res.get('error')}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(res, indent=2, default=str))
            return

        bounds = res.get("board_bounds_mm") or {}
        stats = res.get("occupancy_stats") or {}
        pockets = res.get("free_pockets") or []
        comps = res.get("components") or {}

        print("\n=======================================================")
        print(f"   KAIBRIDGE 2D SPATIAL OCCUPANCY & FREE SPACE: {proj_dir.name}")
        print("=======================================================")
        print(f"  Board Dimensions : {bounds.get('w', 0.0):.2f} mm x {bounds.get('h', 0.0):.2f} mm")
        print(f"  Total Area       : {stats.get('board_area_mm2', 0.0):.1f} mm²")
        print(f"  Routable Area    : {stats.get('inner_routable_area_mm2', 0.0):.1f} mm²")
        print(f"  Occupied Density : {stats.get('occupied_percentage', 0.0)}% (Courtyards + 0.5mm buffers)")
        print(f"  Free Space Ratio : {stats.get('free_percentage', 0.0)}%")
        print(f"  Total Footprints : {len(comps)}")

        print("\n--- Available Free Rectangular Pockets (Sorted by Area) ---")
        if pockets:
            print(f"  {'#':<3} {'Origin (X, Y) mm':<22} {'Size (W x H) mm':<20} {'Area mm²':<12} {'Fit Guide'}")
            print("  " + "-" * 78)
            for idx, p in enumerate(pockets, 1):
                pos_str = f"({p['x0']:.1f}, {p['y0']:.1f})"
                dim_str = f"{p['width_mm']:.1f} x {p['height_mm']:.1f} mm"
                area_str = f"{p['area_mm2']:.1f} mm²"
                guide = "Large IC / Dense Cluster" if p['area_mm2'] >= 150 else ("Small IC / Passives" if p['area_mm2'] >= 50 else "Local Passives")
                print(f"  {idx:<3} {pos_str:<22} {dim_str:<20} {area_str:<12} {guide}")
        else:
            print("  [!] No large free pockets found (High component density).")

        print("\n--- Component Geometry Catalog ---")
        print(f"  {'Ref':<8} {'Value':<16} {'Size (W x H) mm':<16} {'Pos (X, Y) mm':<18} {'Locked':<8} {'Status'}")
        print("  " + "-" * 80)
        for ref in sorted(comps.keys()):
            c = comps[ref]
            val = str(c.get("value", ""))[:15]
            dim_str = f"{c.get('width_mm', 0.0):.1f} x {c.get('height_mm', 0.0):.1f} mm"
            p = c.get("position_mm") or {}
            pos_str = f"({p.get('x', 0.0):.1f}, {p.get('y', 0.0):.1f})"
            locked = "YES" if c.get("is_locked") else "NO"
            status = "ON BOARD" if c.get("on_board") else "STAGING"
            print(f"  {ref:<8} {val:<16} {dim_str:<16} {pos_str:<18} {locked:<8} {status}")
        print("")
        return

    res = get_board_state(proj_dir, mode=mode)

    if not res.get("success"):
        print(f"[-] Error extracting board state: {res.get('error')}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return

    # Human-Readable Formatted Summary
    bounds = res.get("board_bounds_mm") or {}
    print("\n=======================================================")
    print(f"   KAIBRIDGE LIVE BOARD STATE INSPECTOR: {proj_dir.name}")
    print("=======================================================")
    print(f"  PCB File      : {res.get('pcb_file')}")
    print(f"  Mode          : {res.get('mode', mode).upper()}")
    print(f"  Fingerprint   : {res.get('fingerprint')}")
    if bounds:
        print(f"  Board Size    : {bounds.get('w', 0.0):.2f} mm x {bounds.get('h', 0.0):.2f} mm")
        print(f"  Coordinates   : X=[{bounds.get('x0', 0.0):.2f} .. {bounds.get('x1', 0.0):.2f}], Y=[{bounds.get('y0', 0.0):.2f} .. {bounds.get('y1', 0.0):.2f}]")
    print(f"  Outline Closed: {'YES' if res.get('outline_closed') else 'NO'}")
    print(f"  Footprints    : {res.get('footprint_count', 0)}")
    print(f"  Active Nets   : {res.get('net_count', 0)}")
    print(f"  Tracks        : {res.get('track_count', 0)}")
    if mode == "full":
        print(f"  Vias          : {res.get('via_count', 0)}")
    print(f"  Zones         : {res.get('zone_count', 0)}")

    # Design rules
    rules = res.get("design_rules", {})
    if rules:
        print("\n--- Design Rules ---")
        for k, v in rules.items():
            if v is not None:
                print(f"  {k:25}: {v}")

    # Footprints Table
    fps = res.get("footprints", [])
    if fps:
        print("\n--- Placed Footprints ---")
        print(f"  {'Ref':<8} {'Value':<18} {'Pos (X, Y) mm':<22} {'Size (W x H)':<14} {'Rot':<6} {'Layer':<8} {'Locked'}")
        print("  " + "-" * 90)
        for fp in sorted(fps, key=lambda x: x.get("reference", "")):
            ref = fp.get("reference", "")
            val = fp.get("value", "")[:17]
            pos = fp.get("position_mm") or {}
            pos_str = f"({pos.get('x', 0.0):.2f}, {pos.get('y', 0.0):.2f})"
            c_box = fp.get("courtyard_mm") or {}
            sz_str = f"{c_box.get('w', 0.0):.1f}x{c_box.get('h', 0.0):.1f}" if c_box else "N/A"
            rot = f"{fp.get('rotation_deg', 0.0):.1f}°"
            layer = fp.get("layer", "")
            locked = "YES" if fp.get("is_locked") else "NO"
            print(f"  {ref:<8} {val:<18} {pos_str:<22} {sz_str:<14} {rot:<6} {layer:<8} {locked}")

    print(f"\n[+] Complete state cached at: {res.get('state_file')}\n")


if __name__ == "__main__":
    main()

