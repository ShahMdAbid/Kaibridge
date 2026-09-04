#!/usr/bin/env python3
"""
kicad_pcb_sync.py -- Headless Schematic-to-PCB Synchronization (Programmatic F8).
Binds netlist, instantiates footprints, and attaches all net connections & ratsnest directly into .kicad_pcb.

    python kicad_pcb_sync.py "projects/<Project_Name>"
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

from kaibridge.pcb.sync import sync_schematic_to_pcb


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Headless F8 synchronization: update KiCad PCB from schematic & design.json."
    )
    ap.add_argument("project_dir", help="Path to KiCad project folder")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"[*] Synchronizing schematic netlist to PCB for: {project_dir.name}")
    res = sync_schematic_to_pcb(project_dir)

    if not res.get("success"):
        print(f"Error: {res.get('error', 'PCB synchronization failed')}", file=sys.stderr)
        return 1

    print("\n=== PCB Synchronization Successful (F8) ===")
    print(f"  PCB File        : {res.get('pcb_file')}")
    print(f"  Total Footprints: {res.get('total_footprints') or res.get('footprint_count')}")
    print(f"  New Footprints  : {res.get('new_footprints')}")
    print(f"  Nets Bound      : {res.get('nets_bound')}")
    print(f"  Pads Connected  : {res.get('pads_connected')}")
    print("\n  Next: Place components with ops.json via kicad_layout.py or apply_ops_layout.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
