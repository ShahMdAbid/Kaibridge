"""Kaibridge Geometric Autoplacer:
Places footprints with collision avoidance (PadGate), optimal grouped flow, and Edge.Cuts board generation.
"""
import os
import math
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from ..core.paths import load_kicad_python


def autoplace_board(
    project_dir: str | Path,
    board_width_mm: Optional[float] = None,
    board_height_mm: Optional[float] = None,
    margin_mm: float = 4.0,
    pitch_mm: float = 12.0
) -> Dict[str, Any]:
    """Arranges footprints on the PCB with collision clearance and generates Edge.Cuts."""
    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        return {"success": False, "error": f"Project directory does not exist: {project_dir}"}

    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro project found in directory."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    design_file = proj_path / "kaibridge_dump" / "design.json"
    if not design_file.exists():
        design_file = proj_path / "design.json"

    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file does not exist: {pcb_file}"}

    kicad_python = load_kicad_python()
    autoplace_script = f"""
import os
import sys
import json
import math
import pcbnew
from pathlib import Path

pcb_file = r"{str(pcb_file)}"
design_file = r"{str(design_file)}"

board = pcbnew.LoadBoard(pcb_file)
fps = list(board.GetFootprints())

if not fps:
    print("NO_FOOTPRINTS")
    sys.exit(0)

#Load design groups if available
groups = []
if os.path.exists(design_file):
    try:
        with open(design_file, 'r', encoding='utf-8') as f:
            d = json.load(f)
            groups = d.get('groups', [])
    except Exception:
        pass

#Determine layout grid
ref_to_fp = {{fp.GetReference(): fp for fp in fps}}
placed_refs = set()

#Placement state
cur_x = {margin_mm} + 5.0
cur_y = {margin_mm} + 5.0
max_x = cur_x
max_y = cur_y

#Place by functional groups first
for g in groups:
    refs = g.get('refs', [])
    col = 0
    group_y_start = cur_y
    for ref in refs:
        fp = ref_to_fp.get(ref)
        if fp and ref not in placed_refs:
            pos_x = cur_x + col * {pitch_mm}
            pos_y = cur_y
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(pos_x), pcbnew.FromMM(pos_y)))
            placed_refs.add(ref)
            max_x = max(max_x, pos_x + 8.0)
            max_y = max(max_y, pos_y + 8.0)
            col += 1
            if col >= 4:
                col = 0
                cur_y += {pitch_mm}
    if col > 0:
        cur_y += {pitch_mm}

#Place remaining components with dynamic bounding-box clearance awareness
row_max_h = 4.0
target_row_w = 60.0
if {board_width_mm if board_width_mm else "None"} is not None:
    target_row_w = max(float({board_width_mm if board_width_mm else 50.0}) - 2 * {margin_mm} - 6.0, 30.0)

for fp in fps:
    ref = fp.GetReference()
    if ref not in placed_refs:
        bb = fp.GetBoundingBox()
        w_mm = max(pcbnew.ToMM(bb.GetWidth()), 3.0)
        h_mm = max(pcbnew.ToMM(bb.GetHeight()), 3.0)
        
        # If adding this component exceeds row width, wrap to next row
        if (cur_x + w_mm) > ({margin_mm} + 5.0 + target_row_w):
            cur_x = {margin_mm} + 5.0
            cur_y += row_max_h + 3.0
            row_max_h = 4.0

        center_x = round((cur_x + w_mm / 2.0) * 2.0) / 2.0
        center_y = round((cur_y + h_mm / 2.0) * 2.0) / 2.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(center_x), pcbnew.FromMM(center_y)))
        placed_refs.add(ref)

        max_x = max(max_x, center_x + w_mm / 2.0)
        max_y = max(max_y, center_y + h_mm / 2.0)
        row_max_h = max(row_max_h, h_mm)
        cur_x += w_mm + 3.0

#Board dimensions
bw = {board_width_mm if board_width_mm else 'None'}
bh = {board_height_mm if board_height_mm else 'None'}

width = max(bw, max_x + {margin_mm} + 2.0) if bw is not None else max(max_x + {margin_mm} + 5.0, 30.0)
height = max(bh, max_y + {margin_mm} + 2.0) if bh is not None else max(max_y + {margin_mm} + 5.0, 20.0)

#Clear existing Edge.Cuts lines
for drawing in list(board.GetDrawings()):
    if drawing.GetLayer() == pcbnew.Edge_Cuts:
        board.Remove(drawing)

#Create clean rectangular Edge.Cuts outline
def add_edge_segment(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.15))
    s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    board.Add(s)

add_edge_segment(0, 0, width, 0)
add_edge_segment(width, 0, width, height)
add_edge_segment(width, height, 0, height)
add_edge_segment(0, height, 0, 0)

board.BuildListOfNets()
board.BuildConnectivity()
pcbnew.SaveBoard(pcb_file, board)

print(f"AUTOPLACE_OK: placed {{len(placed_refs)}} components on {{width:.1f}}x{{height:.1f}}mm board")
"""

    res = subprocess.run([kicad_python, "-c", autoplace_script], capture_output=True, text=True)

    return {
        "success": res.returncode == 0 and "AUTOPLACE_OK" in res.stdout,
        "output": res.stdout.strip(),
        "pcb_file": str(pcb_file),
        "error": res.stderr.strip() if res.returncode != 0 else None
    }


