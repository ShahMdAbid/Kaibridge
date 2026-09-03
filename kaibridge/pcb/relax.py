"""Kaibridge Physics-Based Courtyard Relaxation Solver (relax.py):
Iteratively separates colliding footprint bounding boxes while respecting board boundaries
and locked components. Uses true courtyard+pad hull envelopes and preserves pin 1 offsets.
"""
from __future__ import annotations

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..core.paths import load_kicad_python


def relax_board(
    project_dir: str | Path,
    locked_refs: Optional[List[str]] = None,
    passes: int = 300,
    margin: float = 0.5,
    clearance: float = 0.5
) -> Dict[str, Any]:
    """Applies iterative 2D repulsion physics to resolve courtyard collisions."""
    try:
        import pcbnew
    except ImportError:
        kicad_python = load_kicad_python()
        root_pkg = Path(__file__).resolve().parents[2]
        payload = json.dumps({
            "project_dir": str(project_dir),
            "locked_refs": locked_refs,
            "passes": passes,
            "margin": margin,
            "clearance": clearance
        })
        runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.relax import relax_board
kwargs = json.loads(r'''{payload}''')
res = relax_board(**kwargs)
print("RELAX_SUB_RESULT:" + json.dumps(res))
"""
        proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            if line.startswith("RELAX_SUB_RESULT:"):
                return json.loads(line.replace("RELAX_SUB_RESULT:", ""))
        return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}

    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    locked_set = set(locked_refs or [])

    import gc
    gc.collect()
    try:
        b = pcbnew.LoadBoard(str(pcb_file))
        fps = list(b.GetFootprints())
        if not fps:
            del b
            gc.collect()
            return {"success": True, "moved_count": 0, "message": "No footprints on board."}

        # Extract true collision envelope (courtyard + pad hull) without silkscreen text inflation
        boxes = []
        for fp in fps:
            ref = fp.GetReference()
            pos = fp.GetPosition()
            ox, oy = pos.x / 1e6, pos.y / 1e6
            
            crt = None
            for layer_id in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                try:
                    poly = fp.GetCourtyard(layer_id)
                    if poly and poly.OutlineCount() > 0:
                        crt = poly.BBox()
                        break
                except Exception:
                    pass

            if crt:
                w = max(crt.GetWidth() / 1e6, 2.0)
                h = max(crt.GetHeight() / 1e6, 2.0)
                cx = crt.GetCenter().x / 1e6
                cy = crt.GetCenter().y / 1e6
            else:
                pad_boxes = [pad.GetBoundingBox() for pad in fp.Pads()]
                if pad_boxes:
                    x0 = min(pad_b.GetLeft() for pad_b in pad_boxes) / 1e6
                    x1 = max(pad_b.GetRight() for pad_b in pad_boxes) / 1e6
                    y0 = min(pad_b.GetTop() for pad_b in pad_boxes) / 1e6
                    y1 = max(pad_b.GetBottom() for pad_b in pad_boxes) / 1e6
                    w = max(x1 - x0, 2.0)
                    h = max(y1 - y0, 2.0)
                    cx = (x0 + x1) / 2.0
                    cy = (y0 + y1) / 2.0
                else:
                    bb = fp.GetBoundingBox()
                    w = max(bb.GetWidth() / 1e6, 2.0)
                    h = max(bb.GetHeight() / 1e6, 2.0)
                    cx = bb.GetCenter().x / 1e6
                    cy = bb.GetCenter().y / 1e6

            off_x = cx - ox
            off_y = cy - oy

            boxes.append({
                "ref": ref,
                "cx": cx,
                "cy": cy,
                "off_x": off_x,
                "off_y": off_y,
                "w": w,
                "h": h,
                "locked": fp.IsLocked() or (ref in locked_set)
            })

        # Board outline bounds (mm) strictly from Edge.Cuts if available
        poly = pcbnew.SHAPE_POLY_SET()
        has_outline = False
        try:
            has_outline = b.GetBoardPolygonOutlines(poly, True)
        except Exception:
            pass

        if has_outline and poly.OutlineCount() > 0:
            bb = poly.BBox()
            bx_min = (bb.GetLeft() / 1e6) + margin
            by_min = (bb.GetTop() / 1e6) + margin
            bx_max = (bb.GetRight() / 1e6) - margin
            by_max = (bb.GetBottom() / 1e6) - margin
        else:
            board_bbox = b.ComputeBoundingBox()
            bx_min = (board_bbox.GetX() / 1e6) + margin
            by_min = (board_bbox.GetY() / 1e6) + margin
            bx_max = ((board_bbox.GetX() + board_bbox.GetWidth()) / 1e6) - margin
            by_max = ((board_bbox.GetY() + board_bbox.GetHeight()) / 1e6) - margin

        # Run iterative 2D repulsion relaxation
        moved_count = 0
        step_size = 0.5
        initial_overlaps = 0

        for p in range(passes):
            overlap_found = False
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    b1 = boxes[i]
                    b2 = boxes[j]

                    dx = b2["cx"] - b1["cx"]
                    dy = b2["cy"] - b1["cy"]
                    req_x = (b1["w"] + b2["w"]) / 2.0 + clearance
                    req_y = (b1["h"] + b2["h"]) / 2.0 + clearance

                    ox = req_x - abs(dx)
                    oy = req_y - abs(dy)

                    if ox > 0 and oy > 0:
                        if p == 0:
                            initial_overlaps += 1
                        overlap_found = True
                        if ox < oy:
                            push_x = (ox / 2.0) if dx >= 0 else (-ox / 2.0)
                            if not b1["locked"]:
                                b1["cx"] -= push_x * step_size
                            if not b2["locked"]:
                                b2["cx"] += push_x * step_size
                        else:
                            push_y = (oy / 2.0) if dy >= 0 else (-oy / 2.0)
                            if not b1["locked"]:
                                b1["cy"] -= push_y * step_size
                            if not b2["locked"]:
                                b2["cy"] += push_y * step_size

            # Constrain to board boundaries
            for b_item in boxes:
                if not b_item["locked"]:
                    b_item["cx"] = max(bx_min + b_item["w"] / 2.0, min(bx_max - b_item["w"] / 2.0, b_item["cx"]))
                    b_item["cy"] = max(by_min + b_item["h"] / 2.0, min(by_max - b_item["h"] / 2.0, b_item["cy"]))

            if not overlap_found:
                break

        # Apply updated coordinates back to PCB with 0.5mm quantization, preserving pin 1 offset
        fp_map = {fp.GetReference(): fp for fp in fps}
        for b_item in boxes:
            if not b_item["locked"]:
                ref = b_item["ref"]
                fp = fp_map.get(ref)
                if fp:
                    target_ox = b_item["cx"] - b_item["off_x"]
                    target_oy = b_item["cy"] - b_item["off_y"]
                    qx = round(target_ox * 2.0) / 2.0
                    qy = round(target_oy * 2.0) / 2.0
                    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(qx), pcbnew.FromMM(qy)))
                    moved_count += 1

        b.BuildListOfNets()
        b.BuildConnectivity()
        pcbnew.SaveBoard(str(pcb_file), b)
        del b
        gc.collect()

        return {
            "success": True,
            "moved_count": moved_count,
            "initial_overlaps": initial_overlaps,
            "total_footprints": len(fps),
            "passes_executed": p + 1,
            "pcb_file": str(pcb_file)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
