"""Kaibridge Visual Board Preview & Analytics Engine (preview.py):
Renders vector SVG and top-view PNG snapshots via kicad-cli for multimodal visual AI critique,
and returns structural board metrics (dimensions, footprint positions, track/via stats).
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.paths import load_cli, load_kicad_python


def render_pcb_preview(project_dir: str | Path) -> Dict[str, Any]:
    """Generates vector SVG snapshot, top PNG render, and structural geometry analytics."""
    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    dump_dir = proj_path / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)

    out_svg = dump_dir / f"{stem}_board.svg"
    out_png = dump_dir / f"{stem}_top.png"

    cli = load_cli()
    if cli:
        # 1. Export vector SVG with copper, silk, fabrication & courtyards
        cmd_svg = [
            str(cli), "pcb", "export", "svg",
            "--layers", "F.Cu,B.Cu,Edge.Cuts,F.Fab,F.SilkS,F.CrtYd",
            "--page-size-mode", "2",
            "--exclude-drawing-sheet",
            "-o", str(out_svg),
            str(pcb_file)
        ]
        subprocess.run(cmd_svg, capture_output=True, text=True, check=False, errors="replace")

        # 2. Render top visual PNG snapshot
        cmd_png = [
            str(cli), "pcb", "render",
            "--side", "top",
            "--quality", "basic",
            "-o", str(out_png),
            str(pcb_file)
        ]
        subprocess.run(cmd_png, capture_output=True, text=True, check=False, errors="replace")

    # 3. Extract Board Metrics & Footprint Coordinates for AI Critique
    analysis = {}
    try:
        import pcbnew
        import gc
        gc.collect()
        b = pcbnew.LoadBoard(str(pcb_file))
        bbox = b.ComputeBoundingBox()
        fps = [
            {
                "ref": fp.GetReference(),
                "val": fp.GetValue(),
                "x": round(fp.GetPosition().x / 1e6, 2),
                "y": round(fp.GetPosition().y / 1e6, 2),
                "rot": round(fp.GetOrientation().AsDegrees(), 1),
                "layer": "Top" if not fp.IsFlipped() else "Bottom",
                "locked": fp.IsLocked()
            }
            for fp in b.GetFootprints()
        ]
        analysis = {
            "board_width_mm": round(bbox.GetWidth() / 1e6, 2),
            "board_height_mm": round(bbox.GetHeight() / 1e6, 2),
            "origin_x_mm": round(bbox.GetX() / 1e6, 2),
            "origin_y_mm": round(bbox.GetY() / 1e6, 2),
            "total_footprints": len(fps),
            "footprints": fps,
            "total_tracks": len(list(b.GetTracks())),
            "total_vias": len([t for t in b.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]),
            "total_zones": len(list(b.Zones()))
        }
        del b
        gc.collect()
    except Exception:
        try:
            from .inspector import get_board_state
            bs = get_board_state(proj_path, mode="summary")
            if bs.get("success"):
                bb = bs.get("board_bounds") or {}
                fps = [
                    {
                        "ref": fp.get("reference", ""),
                        "val": fp.get("value", ""),
                        "x": fp.get("position_mm", {}).get("x", 0.0),
                        "y": fp.get("position_mm", {}).get("y", 0.0),
                        "rot": fp.get("rotation_deg", 0.0),
                        "layer": fp.get("layer", "Top"),
                        "locked": fp.get("is_locked", False)
                    }
                    for fp in bs.get("footprints", [])
                ]
                analysis = {
                    "board_width_mm": bb.get("w", 0.0),
                    "board_height_mm": bb.get("h", 0.0),
                    "origin_x_mm": bb.get("x0", 0.0),
                    "origin_y_mm": bb.get("y0", 0.0),
                    "total_footprints": len(fps),
                    "footprints": fps,
                    "total_tracks": bs.get("track_count", 0),
                    "total_vias": bs.get("via_count", 0),
                    "total_zones": bs.get("zone_count", 0)
                }
        except Exception as e:
            analysis = {"error": str(e)}

    return {
        "success": out_svg.exists() or out_png.exists() or len(analysis.get("footprints", [])) > 0,
        "svg_snapshot": str(out_svg) if out_svg.exists() else None,
        "png_snapshot": str(out_png) if out_png.exists() else None,
        "board_analysis": analysis
    }


def render_schematic_preview(
    project_dir: str | Path,
    fmt: str = "svg",
    exclude_drawing_sheet: bool = True
) -> Dict[str, Any]:
    """Exports vector SVG or multi-page PDF of the schematic for AI visual critique and human review."""
    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    stem = pro_files[0].stem if pro_files else proj_path.name
    sch_file = proj_path / f"{stem}.kicad_sch"
    if not sch_file.exists():
        cand = list(proj_path.glob("*.kicad_sch"))
        if cand:
            sch_file = cand[0]
        else:
            return {"success": False, "error": f"Schematic file not found in {project_dir}"}

    dump_dir = proj_path / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)

    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli not found"}

    out_file = dump_dir / f"{sch_file.stem}_schematic.{fmt}"

    cmd = [
        str(cli), "sch", "export", fmt,
        "-o", str(out_file),
        str(sch_file)
    ]
    if exclude_drawing_sheet and fmt == "svg":
        cmd.append("--exclude-drawing-sheet")

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "success": out_file.exists() or res.returncode == 0,
        "schematic_preview_path": str(out_file) if out_file.exists() else None,
        "format": fmt,
        "output": res.stdout.strip()
    }
