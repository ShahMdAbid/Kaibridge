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

from kaibridge.pcb.inspector import get_board_state


def main():
    ap = argparse.ArgumentParser(description="Live KiCad PCB State Inspector")
    ap.add_argument("project_dir", help="Path to KiCad project directory or .kicad_pcb file")
    ap.add_argument("--summary", action="store_true", default=True, help="Extract summary state (footprints, nets, rules; default)")
    ap.add_argument("--full", action="store_true", help="Extract full state (including all individual tracks, vias, zones)")
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
        print(f"  {'Ref':<8} {'Value':<18} {'Pos (X, Y) mm':<22} {'Rot':<6} {'Layer':<8} {'Locked':<7} {'Footprint'}")
        print("  " + "-" * 95)
        for fp in sorted(fps, key=lambda x: x.get("reference", "")):
            ref = fp.get("reference", "")
            val = fp.get("value", "")[:17]
            pos = fp.get("position_mm") or {}
            pos_str = f"({pos.get('x', 0.0):.2f}, {pos.get('y', 0.0):.2f})"
            rot = f"{fp.get('rotation_deg', 0.0):.1f}°"
            layer = fp.get("layer", "")
            locked = "YES" if fp.get("is_locked") else "NO"
            fpid = fp.get("fpid", "")
            # Shorten footprint name for display
            if ":" in fpid:
                fpid = fpid.split(":", 1)[1]
            print(f"  {ref:<8} {val:<18} {pos_str:<22} {rot:<6} {layer:<8} {locked:<7} {fpid}")

    print(f"\n[+] Complete state cached at: {res.get('state_file')}\n")


if __name__ == "__main__":
    main()
