"""Kaibridge Production Exporter (Hallmark 6):
Generates 100% JLCPCB-compatible Gerbers, Drill files, Gerber ZIP, BOM CSV, and CPL Pick & Place CSV.
"""
from __future__ import annotations

import os
import sys
import json
import csv
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.paths import load_cli, load_kicad_python


def export_production_files(project_dir: str | Path) -> Dict[str, Any]:
    """Generates complete JLCPCB manufacturing bundle: Gerber ZIP, Drill, BOM CSV, and CPL CSV."""
    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        return {"success": False, "error": f"Project directory does not exist: {project_dir}"}

    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro project found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    
    # Check kaibridge_dump/design.json then project_dir/design.json
    design_file = proj_path / "kaibridge_dump" / "design.json"
    if not design_file.exists():
        design_file = proj_path / "design.json"

    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file does not exist: {pcb_file}"}

    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli executable not found."}

    out_dir = proj_path / "production_output"
    gerber_dir = out_dir / "gerbers"
    if gerber_dir.exists():
        import shutil
        shutil.rmtree(gerber_dir)
    gerber_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export standard Gerbers
    cmd_gerber = [
        str(cli), "pcb", "export", "gerbers",
        "--output", gerber_dir.as_posix() + "/",
        "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask",
        "--use-drill-file-origin",
        str(pcb_file)
    ]
    subprocess.run(cmd_gerber, capture_output=True, text=True, check=False)

    # 2. Export Drill files
    cmd_drill = [
        str(cli), "pcb", "export", "drill",
        "--output", gerber_dir.as_posix() + "/",
        "--format", "excellon",
        "--drill-origin", "plot",
        "--excellon-separate-th",
        "--generate-map",
        "--map-format", "pdf",
        str(pcb_file)
    ]
    subprocess.run(cmd_drill, capture_output=True, text=True, check=False)

    # 3. Create Gerber ZIP archive
    zip_path = out_dir / f"{stem}_gerbers.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in gerber_dir.glob("*.*"):
            zf.write(f, arcname=f.name)

    # 4. Generate BOM & CPL via pcbnew & design.json
    kicad_python = load_kicad_python()
    bom_cpl_script = f"""
import os
import sys
import json
import csv
import pcbnew
from pathlib import Path

pcb_file = r"{str(pcb_file)}"
design_file = r"{str(design_file)}"
out_dir = r"{str(out_dir)}"
root_dir = r"{str(Path(__file__).resolve().parents[2])}"
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

board = pcbnew.LoadBoard(pcb_file)
design_parts = {{}}
if os.path.exists(design_file):
    try:
        with open(design_file, 'r', encoding='utf-8-sig') as f:
            d = json.load(f)
            design_parts = d.get('parts', {{}})
            if not design_parts and 'components' in d:
                for c in d.get('components', []):
                    if c.get('ref'):
                        design_parts[c['ref']] = c
    except Exception:
        pass

#1. BOM Generation
grouped_bom = {{}}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    val = fp.GetValue()
    fpid = str(fp.GetFPID().GetLibItemName())
    pdata = design_parts.get(ref, {{}})
    fields = pdata.get('fields', {{}}) if isinstance(pdata, dict) else {{}}
    
    # Check fields dict, top-level keys, and live KiCad footprint field
    lcsc_id = fields.get('LCSC') or fields.get('lcsc') or pdata.get('lcsc') or pdata.get('lcsc_id') or ''
    if not lcsc_id:
        try:
            fld = fp.GetFieldByName('LCSC')
            if fld and fld.GetText():
                lcsc_id = fld.GetText()
        except Exception:
            pass

    # Auto-healing fallback from parts_db if LCSC was omitted for standard passives
    if not lcsc_id and fpid:
        try:
            from kaibridge.sourcing.parts_db import recommend_kicad_part
            prefix = ''.join([ch for ch in ref if ch.isalpha()]).upper()
            ctype = 'R' if prefix == 'R' else ('C' if prefix == 'C' else ('LED' if prefix in ('D', 'LED') and 'LED' in fpid.upper() else ''))
            if ctype and val:
                pkg = '0805' if '0805' in fpid else ('0603' if '0603' in fpid else ('0402' if '0402' in fpid else '1206' if '1206' in fpid else ''))
                if pkg:
                    rec = recommend_kicad_part(ctype, val, package=pkg)
                    lcsc_id = rec.get('fields', {{}}).get('LCSC', '')
        except Exception:
            pass
            
    key = (val, fpid, lcsc_id)
    if key not in grouped_bom:
        grouped_bom[key] = []
    grouped_bom[key].append(ref)

bom_file = os.path.join(out_dir, "{stem}_bom_jlcpcb.csv")
with open(bom_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (val, fpid, lcsc_id), refs in sorted(grouped_bom.items()):
        refs.sort()
        writer.writerow([val, ",".join(refs), fpid, lcsc_id])

#2. CPL (Pick & Place) Generation with True Footprint Centers & Plain Floats (No 'mm' suffix)
cpl_file = os.path.join(out_dir, "{stem}_cpl_jlcpcb.csv")
with open(cpl_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        val = fp.GetValue()
        pkg = str(fp.GetFPID().GetLibItemName())
        pos = fp.GetPosition()
        
        # Calculate true physical center from courtyard or pads
        cx, cy = pos.x, pos.y
        try:
            crt = fp.GetCourtyard(pcbnew.F_CrtYd)
            if crt and crt.OutlineCount() > 0:
                c_pt = crt.BBox().GetCenter()
                cx, cy = c_pt.x, c_pt.y
            else:
                pad_boxes = [pad.GetBoundingBox() for pad in fp.Pads()]
                if pad_boxes:
                    x0 = min(pad_b.GetLeft() for pad_b in pad_boxes)
                    x1 = max(pad_b.GetRight() for pad_b in pad_boxes)
                    y0 = min(pad_b.GetTop() for pad_b in pad_boxes)
                    y1 = max(pad_b.GetBottom() for pad_b in pad_boxes)
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                else:
                    c_pt = fp.GetBoundingBox().GetCenter()
                    cx, cy = c_pt.x, c_pt.y
        except Exception:
            pass

        mid_x = f"{{pcbnew.ToMM(cx):.4f}}"
        mid_y = f"{{pcbnew.ToMM(-cy):.4f}}"
        rot = f"{{fp.GetOrientation().AsDegrees():.1f}}"
        layer = "Top" if not fp.IsFlipped() else "Bottom"
        writer.writerow([ref, val, pkg, mid_x, mid_y, rot, layer])

del board
import gc
gc.collect()

print("BOM_CPL_OK")
"""
    res_bom = subprocess.run([kicad_python, "-c", bom_cpl_script], capture_output=True, text=True)

    bom_count = len(list(csv.reader(open(out_dir / f"{stem}_bom_jlcpcb.csv", encoding="utf-8")))) if (out_dir / f"{stem}_bom_jlcpcb.csv").exists() else 0
    return {
        "success": zip_path.exists() and "BOM_CPL_OK" in res_bom.stdout,
        "output_directory": str(out_dir),
        "gerber_zip": str(zip_path),
        "gerbers_zip": str(zip_path),
        "bom_csv": str(out_dir / f"{stem}_bom_jlcpcb.csv"),
        "cpl_csv": str(out_dir / f"{stem}_cpl_jlcpcb.csv"),
        "bom_rows": bom_count,
        "total_bom_items": bom_count
    }

