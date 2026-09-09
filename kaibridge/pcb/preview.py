"""Kaibridge Visual Board Preview & Analytics Engine (preview.py):
Renders vector SVG and top-view PNG snapshots via kicad-cli for multimodal visual AI critique,
and returns structural board metrics (dimensions, footprint positions, track/via stats).
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

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

    # 4. Generate High-Contrast Component HUD Map & Dual-View Inspection Image
    map_png = None
    dual_png = None
    if out_png.exists() and len(analysis.get("footprints", [])) > 0:
        out_map = dump_dir / f"{stem}_component_map.png"
        out_dual = dump_dir / f"{stem}_dual_view.png"
        bb = {
            "x0": analysis.get("origin_x_mm", 0.0),
            "y0": analysis.get("origin_y_mm", 0.0),
            "w": analysis.get("board_width_mm", 1.0),
            "h": analysis.get("board_height_mm", 1.0)
        }
        res_overlay = generate_component_map_overlay(
            top_png_path=out_png,
            footprints=analysis.get("footprints", []),
            board_bounds=bb,
            out_map_path=out_map,
            out_dual_path=out_dual,
            show_values=False
        )
        if res_overlay.get("success"):
            map_png = str(out_map)
            dual_png = str(out_dual)

    return {
        "success": out_svg.exists() or out_png.exists() or len(analysis.get("footprints", [])) > 0,
        "svg_snapshot": str(out_svg) if out_svg.exists() else None,
        "png_snapshot": str(out_png) if out_png.exists() else None,
        "component_map_png": map_png,
        "dual_view_png": dual_png,
        "board_analysis": analysis
    }


def generate_component_map_overlay(
    top_png_path: str | Path,
    footprints: List[Dict[str, Any]],
    board_bounds: Dict[str, float],
    out_map_path: str | Path,
    out_dual_path: Optional[str | Path] = None,
    show_values: bool = False
) -> Dict[str, Any]:
    """Generates a clean, compact HUD overlay with reference designators (e.g. U1, C6, SW1)
    and an optional side-by-side Dual View (Photorealistic PCB on Left, HUD Reference Map on Right).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        top_path = Path(top_png_path)
        if not top_path.exists():
            return {"success": False, "error": f"Base image not found: {top_path}"}

        im = Image.open(top_path).convert("RGBA")
        arr = np.array(im)

        # Detect physical board bounds inside rendered canvas via alpha channel or RGB contrast
        alpha = arr[:, :, 3]
        if np.any(alpha > 10):
            mask = alpha > 10
        else:
            mask = (arr[:, :, 1] > 40) & (arr[:, :, 1] > arr[:, :, 0])
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not np.any(rows) or not np.any(cols):
            rmin, rmax, cmin, cmax = 0, im.height, 0, im.width
        else:
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]

        pw = max(1, cmax - cmin)
        ph = max(1, rmax - rmin)
        pad = 40
        crop_box = (max(0, cmin - pad), max(0, rmin - pad), min(im.width, cmax + pad), min(im.height, rmax + pad))
        board_cropped = im.crop(crop_box)
        annotated = board_cropped.copy()
        draw = ImageDraw.Draw(annotated, "RGBA")

        try:
            font_bold = ImageFont.truetype("arialbd.ttf", 13)
            font_title = ImageFont.truetype("arialbd.ttf", 18)
        except Exception:
            font_bold = ImageFont.load_default()
            font_title = font_bold

        x0 = board_bounds.get("x0", 0.0)
        y0 = board_bounds.get("y0", 0.0)
        w_mm = max(1.0, board_bounds.get("w", 1.0))
        h_mm = max(1.0, board_bounds.get("h", 1.0))

        for fp in footprints:
            ref = fp.get("ref") or fp.get("reference", "")
            val = fp.get("val") or fp.get("value", "")
            pos = fp.get("position_mm") or {}
            x_mm = fp.get("x", pos.get("x", 0.0))
            y_mm = fp.get("y", pos.get("y", 0.0))

            px = pad + (x_mm - x0) / w_mm * pw
            py = pad + (y_mm - y0) / h_mm * ph

            # Category-based color scheme
            if ref.startswith("U"):
                bg = (0, 180, 216, 235)      # Cyan for ICs / MCUs
                border = (255, 255, 255, 255)
                text_c = (0, 0, 0, 255)
            elif ref.startswith("J") or ref.startswith("SW") or ref.startswith("K"):
                bg = (247, 127, 0, 235)     # Orange for Connectors / Switches
                border = (255, 255, 255, 255)
                text_c = (255, 255, 255, 255)
            elif ref.startswith("D"):
                bg = (214, 40, 40, 235)     # Red for Diodes / LEDs
                border = (255, 255, 255, 255)
                text_c = (255, 255, 255, 255)
            elif ref.startswith("R"):
                bg = (252, 191, 73, 235)    # Amber for Resistors
                border = (40, 40, 40, 255)
                text_c = (0, 0, 0, 255)
            elif ref.startswith("C"):
                bg = (138, 201, 38, 235)    # Lime for Capacitors
                border = (40, 40, 40, 255)
                text_c = (0, 0, 0, 255)
            elif ref.startswith("L"):
                bg = (155, 93, 229, 235)    # Purple for Inductors
                border = (255, 255, 255, 255)
                text_c = (255, 255, 255, 255)
            elif ref.startswith("Y"):
                bg = (0, 245, 212, 235)     # Teal for Oscillators
                border = (30, 30, 30, 255)
                text_c = (0, 0, 0, 255)
            else:
                bg = (108, 117, 125, 235)   # Slate for others
                border = (255, 255, 255, 255)
                text_c = (255, 255, 255, 255)

            lbl = f"{ref} [{val}]" if show_values else ref
            bbox = font_bold.getbbox(lbl)
            lw = bbox[2] - bbox[0] + 8
            lh = bbox[3] - bbox[1] + 6

            draw.ellipse([(px - 2, py - 2), (px + 2, py + 2)], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
            lx0 = px - lw / 2
            ly0 = py - lh / 2
            draw.rounded_rectangle([(lx0, ly0), (lx0 + lw, ly0 + lh)], radius=4, fill=bg, outline=border, width=1)
            draw.text((lx0 + 4, ly0 + 2), lbl, font=font_bold, fill=text_c)

        out_map = Path(out_map_path)
        out_map.parent.mkdir(parents=True, exist_ok=True)
        annotated.save(out_map)

        if out_dual_path:
            out_dual = Path(out_dual_path)
            total_w = board_cropped.width + annotated.width + 30
            total_h = max(board_cropped.height, annotated.height) + 60
            dual = Image.new("RGBA", (total_w, total_h), (20, 24, 33, 255))
            d_draw = ImageDraw.Draw(dual)
            dual.paste(board_cropped, (10, 50))
            dual.paste(annotated, (board_cropped.width + 20, 50))
            d_draw.text((20, 16), "1. PHOTOREALISTIC PCB (Physical Board)", font=font_title, fill=(240, 240, 240, 255))
            d_draw.text((board_cropped.width + 30, 16), "2. REFERENCE DESIGNATOR MAP (Call by Ref: U1, C6, SW1...)", font=font_title, fill=(0, 210, 255, 255))
            dual.save(out_dual)

        return {"success": True, "map_path": str(out_map), "dual_path": str(out_dual_path) if out_dual_path else None}
    except Exception as e:
        return {"success": False, "error": str(e)}


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


NINE_VIEWS_CONFIG: Dict[str, Dict[str, Any]] = {
    "top": {
        "desc": "Top Orthogonal View (0°)",
        "args": ["--side", "top", "--zoom", "0.85"]
    },
    "corner_front_left": {
        "desc": "Front-Left (SW) Isometric 45°",
        "args": ["--perspective", "--rotate", "-45,0,45", "--zoom", "0.80"]
    },
    "corner_front_right": {
        "desc": "Front-Right (SE) Isometric 45°",
        "args": ["--perspective", "--rotate", "-45,0,-45", "--zoom", "0.80"]
    },
    "corner_back_right": {
        "desc": "Back-Right (NE) Isometric 45°",
        "args": ["--perspective", "--rotate", "-45,0,-135", "--zoom", "0.80"]
    },
    "corner_back_left": {
        "desc": "Back-Left (NW) Isometric 45°",
        "args": ["--perspective", "--rotate", "-45,0,135", "--zoom", "0.80"]
    },
    "side_front": {
        "desc": "Front (South) Edge Elevation 30°",
        "args": ["--perspective", "--rotate", "-30,0,0", "--zoom", "0.80"]
    },
    "side_right": {
        "desc": "Right (East) Edge Elevation 30°",
        "args": ["--perspective", "--rotate", "-30,0,-90", "--zoom", "0.80"]
    },
    "side_back": {
        "desc": "Back (North) Edge Elevation 30°",
        "args": ["--perspective", "--rotate", "-30,0,180", "--zoom", "0.80"]
    },
    "side_left": {
        "desc": "Left (West) Edge Elevation 30°",
        "args": ["--perspective", "--rotate", "-30,0,90", "--zoom", "0.80"]
    },
}


def render_3d_suite(
    project_dir: str | Path,
    views: Optional[List[str]] = None,
    width: int = 1600,
    height: int = 900
) -> Dict[str, Any]:
    """Renders the comprehensive 9-angle 3D visual inspection suite via kicad-cli.
    Provides calibrated zoom (0.80-0.85) to guarantee unclipped board borders from every angle:
      - 1 Top View (0°)
      - 4 Corner Views (Isometric 45° from SW, SE, NE, NW)
      - 4 Side Views (30° elevation facing Front, Right, Back, Left edges)
    """
    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": f"No .kicad_pro found in {project_dir}"}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    dump_dir = proj_path / "kaibridge_dump" / "3d_views"
    dump_dir.mkdir(parents=True, exist_ok=True)

    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli executable not found"}

    target_views = views if views else list(NINE_VIEWS_CONFIG.keys())
    rendered = {}
    failed = []

    for vname in target_views:
        if vname not in NINE_VIEWS_CONFIG:
            continue
        cfg = NINE_VIEWS_CONFIG[vname]
        out_png = dump_dir / f"{vname}.png"
        if out_png.exists():
            try:
                out_png.unlink()
            except Exception:
                pass

        cmd = [
            str(cli), "pcb", "render",
            "--width", str(width),
            "--height", str(height),
            "-o", str(out_png)
        ] + cfg["args"] + [str(pcb_file)]

        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
        if res.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0:
            rendered[vname] = {
                "path": str(out_png),
                "desc": cfg["desc"]
            }
        else:
            err = res.stderr.strip() or res.stdout.strip() or 'render failed (missing or empty image)'
            failed.append(f"{vname}: {err}")

    return {
        "success": len(rendered) > 0 and len(failed) == 0,
        "total_rendered": len(rendered),
        "views": rendered,
        "failed": failed,
        "output_dir": str(dump_dir)
    }

