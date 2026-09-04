#!/usr/bin/env python3
"""
json2sch.py -- design.json -> KiCad hierarchical schematics.

  python json2sch.py <PROJECT_DIR> [design.json] [-o board.kicad_sch]
                     [--dry-run] [--apply-netclasses] [--erc]

Sub-sheets are written next to the root file as <sheet_id>.kicad_sch.
A sidecar <PROJECT_DIR>/kaibridge_dump/kaibridge_build.json records the resolved design metadata.
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

from kaibridge.schematic.compiler import compile_schematic

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Compile design.json into KiCad hierarchical schematics.")
    ap.add_argument("project_dir", help="folder that holds the .kicad_pro")
    ap.add_argument("design_json", nargs="?",
                    help="default: <project_dir>/kaibridge_dump/design.json or <project_dir>/design.json")
    ap.add_argument("-o", "--out",
                    help="root schematic filename or path")
    ap.add_argument("--dry-run", action="store_true",
                    help="compile and report, write nothing")
    ap.add_argument("--apply-netclasses", action="store_true", default=True,
                    help="also write netclasses into the .kicad_pro (default: true)")
    ap.add_argument("--no-netclasses", action="store_false", dest="apply_netclasses",
                    help="do not modify .kicad_pro netclasses")
    ap.add_argument("--erc", action="store_true",
                    help="run KiCad ERC check automatically and output report")
    ap.add_argument("--svg", action="store_true",
                    help="also export vector SVG schematic preview to kaibridge_dump/")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    res = compile_schematic(
        project_dir=project_dir,
        design_file=args.design_json,
        output_name=args.out,
        apply_netclasses=args.apply_netclasses,
        run_erc=args.erc,
        dry_run=args.dry_run
    )

    if not res.get("success") and not res.get("dry_run"):
        print(f"Error: {res.get('error', 'Compilation failed')}", file=sys.stderr)
        return 1

    pname = res.get("project_name", project_dir.name)
    print(f"\n[*] Kaibridge Schematic Compiler -- Project '{pname}'")

    if res.get("dry_run"):
        print("  Mode: DRY RUN (no files written)")
        sheets = res.get("sheets", [])
        pad = max([len(s["id"]) for s in sheets] + [5]) if sheets else 5
        print(f"  {'sheet'.ljust(pad)}  parts  nets  paper")
        for s in sheets:
            print(f"  {s['id'].ljust(pad)}  {s['parts']:>5}  {s['nets']:>4}  {s['paper']}")
        print(f"\n  Total parts: {res.get('total_parts', 0)}, Total nets: {res.get('total_nets', 0)}")
        return 0

    sch_files = res.get("schematic_files", [])
    print(f"  Generated {len(sch_files)} schematic sheet(s):")
    for f in sch_files:
        print(f"    - {f}")

    if args.erc:
        erc = res.get("erc", {})
        errs = erc.get("errors", 0)
        warns = erc.get("warnings", 0)
        violations = res.get("violations", [])
        print("\n  === ERC Verification Report ===")
        print(f"  Total Errors: {errs}, Total Warnings: {warns}")
        if errs > 0:
            print("  ERRORS:")
            for v in violations[:10]:
                print(f"    - {v}")
            if len(violations) > 10:
                print(f"    ... and {len(violations) - 10} more.")
            return 1
        else:
            print("  Status: PASSED (0 Errors)")

    if args.svg:
        from kaibridge.pcb.preview import render_schematic_preview
        prev_res = render_schematic_preview(project_dir)
        if prev_res.get("success"):
            print("  Preview SVG     : Exported to kaibridge_dump/ (Checkpoint 1 Ready)")

    print("  Next: sync to PCB via headless kicad_pcb_sync.py or KiCad F8\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
