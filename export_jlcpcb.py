#!/usr/bin/env python3
"""
export_jlcpcb.py -- Automated Production Exporter for JLCPCB (Gerbers, Drill, BOM, CPL)
Automates generation of 100% JLCPCB-compatible manufacturing & SMT assembly files from KiCad 10.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.pcb.export import export_production_files

def main():
    ap = argparse.ArgumentParser(description="Export JLCPCB manufacturing bundle (Gerbers, Drill, BOM, CPL).")
    ap.add_argument("project_dir", help="KiCad project folder")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: Not a directory: {project_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Exporting JLCPCB production files for: {project_dir}")
    res = export_production_files(project_dir)

    if not res.get("success"):
        print(f"Error: {res.get('error')}", file=sys.stderr)
        sys.exit(1)

    print("\n=== JLCPCB Production Export Successful ===")
    print(f"  Gerber ZIP : {res.get('gerber_zip') or res.get('gerbers_zip')}")
    print(f"  BOM CSV    : {res.get('bom_csv')}")
    print(f"  CPL CSV    : {res.get('cpl_csv')}")
    print(f"  Total Parts: {res.get('bom_rows') or res.get('total_bom_items')}")

if __name__ == "__main__":
    main()
