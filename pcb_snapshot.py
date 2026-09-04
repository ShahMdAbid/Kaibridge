#!/usr/bin/env python3
"""
pcb_snapshot.py -- Export vector SVG render of the board layout.

    python pcb_snapshot.py "<PROJECT_DIR>"
"""

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.core.paths import load_cli

def resolve_board(project_dir: Path):
    pros = sorted(project_dir.glob("*.kicad_pro"))
    if not pros:
        return None
    stem = pros[0].stem
    return project_dir / f"{stem}.kicad_pcb"

def export_snapshot(project_dir: str | Path) -> str:
    pdir = Path(project_dir).expanduser().resolve()
    if not pdir.is_dir():
        raise FileNotFoundError(f"Not a directory: {pdir}")

    pcb_file = resolve_board(pdir)
    if not pcb_file or not pcb_file.exists():
        raise FileNotFoundError(f"No matching .kicad_pcb file found in {pdir}")

    dump_dir = pdir / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    out_svg = dump_dir / f"{pcb_file.stem}_board.svg"

    cli = load_cli()
    if not cli:
        raise RuntimeError("kicad-cli executable not found.")

    cmd = [
        str(cli), "pcb", "export", "svg",
        "--layers", "F.Cu,B.Cu,Edge.Cuts,F.Fab,F.SilkS,F.CrtYd",
        "--page-size-mode", "2",
        "--exclude-drawing-sheet",
        "-o", str(out_svg),
        str(pcb_file)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"kicad-cli SVG export failed:\n{res.stderr}")

    return str(out_svg)

def main():
    ap = argparse.ArgumentParser(description="Export vector SVG snapshot of PCB.")
    ap.add_argument("project_dir", help="KiCad project folder")
    args = ap.parse_args()

    try:
        svg_path = export_snapshot(args.project_dir)
        print(f"[*] Snapshot saved to: {svg_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
