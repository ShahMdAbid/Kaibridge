"""Kaibridge PCB Snapshot & 3D Vision CLI (kaibridge.pcb.snapshot_cli).
Exports vector SVG renders, photorealistic 2D views, HUD component maps,
and the complete 9-angle 3D perspective suite via kicad-cli.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..core.paths import load_cli


def resolve_board(project_dir: Path) -> Optional[Path]:
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


def export_schematic_snapshot(project_dir: str | Path, fmt: str = "svg") -> str:
    from .preview import render_schematic_preview
    res = render_schematic_preview(project_dir, fmt=fmt)
    if not res.get("success"):
        raise RuntimeError(f"Schematic export failed: {res.get('error', 'Unknown error')}")
    return res["schematic_preview_path"]


def export_3d_snapshot(project_dir: str | Path, views: list | None = None) -> dict:
    from .preview import render_3d_suite
    res = render_3d_suite(project_dir, views=views)
    if not res.get("success"):
        raise RuntimeError(f"3D render failed: {res.get('error') or res.get('failed')}")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export vector SVG & 9-angle 3D perspective snapshots of PCB or Schematic.")
    ap.add_argument("project_dir", help="KiCad project folder")
    ap.add_argument("--schematic", action="store_true", help="Export schematic SVG preview instead of PCB layout")
    ap.add_argument("--3d", dest="three_d", action="store_true", help="Export complete 9-angle 3D vision suite (Top, 4 Corners, 4 Sides)")
    ap.add_argument("--all", action="store_true", help="Export both 2D PCB snapshot and complete 9-angle 3D vision suite")
    ap.add_argument("--inspect", "--dual", dest="inspect", action="store_true", help="Export high-contrast Reference Designator HUD map & side-by-side Dual View")
    ap.add_argument("--tag", help="Capture a timestamped board state snapshot with human-readable tag (e.g. pre_sync, pre_route)")
    ap.add_argument("--angle", help="Export a specific 3D angle (e.g. corner_front_left, side_front, top)")
    args = ap.parse_args(argv)

    try:
        executed = False
        if args.tag:
            from .snapshot import snapshot_board
            snap_res = snapshot_board(args.project_dir, tag=args.tag)
            if not snap_res.get("success"):
                raise RuntimeError(f"Snapshot failed: {snap_res.get('error')}")
            print(f"[*] Board snapshot saved: {snap_res.get('snapshot_file')}")
            return 0

        if args.schematic:
            svg_path = export_schematic_snapshot(args.project_dir)
            print(f"[*] Schematic snapshot saved to: {svg_path}")
            executed = True

        if args.inspect:
            from .preview import render_pcb_preview
            res = render_pcb_preview(args.project_dir)
            if not res.get("success"):
                raise RuntimeError(f"Inspect preview failed: {res.get('error')}")
            print(f"[*] Photorealistic PCB : {res.get('png_snapshot')}")
            print(f"[*] Component HUD Map  : {res.get('component_map_png')}")
            print(f"[*] Side-by-Side Dual  : {res.get('dual_view_png')}")
            executed = True

        if args.three_d or args.angle or args.all:
            target_views = [args.angle] if args.angle else None
            res = export_3d_snapshot(args.project_dir, views=target_views)
            print(f"[*] 3D Vision Suite saved ({res['total_rendered']} view(s)) to: {res['output_dir']}")
            for k, v in res["views"].items():
                print(f"    - {k}: {v['desc']}")
            executed = True

        if not executed or args.all:
            svg_path = export_snapshot(args.project_dir)
            print(f"[*] PCB snapshot saved to: {svg_path}")
            print(f"    [Tip] Run with --3d to generate the full 9-angle 3D perspective suite for visual inspection.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
