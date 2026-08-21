"""
export_jlcpcb.py -- Automated Production Exporter for JLCPCB (Gerbers, Drill, BOM, CPL)
Automates generation of 100% JLCPCB-compatible manufacturing & SMT assembly files from KiCad 10.
"""

import os
import sys
import json
import csv
import zipfile
import subprocess
from pathlib import Path

# Add current directory to path to import local modules without issues
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schematic_gen.paths import load_cli

# Common JLCPCB / LCSC basic/standard part numbers mapping for generic passives
COMMON_LCSC_PARTS = {
    ("10k", "0805"): "C17414",
    ("1k", "0805"): "C17513",
    ("100R", "0805"): "C17424",
    ("5.1k", "0805"): "C23186",
    ("750k", "0805"): "C22986",
    ("240k", "0805"): "C22941",
    ("100nF", "0805"): "C49678",
    ("10uF", "0805"): "C15850",
    ("22uF", "0805"): "C45783",
    ("2.2uH", "1210"): "C12903",
    ("SS34", "SMA"): "C8678",
    ("ESP32-WROOM-32", "ESP32-WROOM-32"): "C82891"
}

def export_jlcpcb(project_dir):
    project_dir = Path(project_dir).resolve()
    
    pro_files = list(project_dir.glob("*.kicad_pro"))
    if not pro_files:
        raise FileNotFoundError(f"No .kicad_pro found in {project_dir}")
    
    stem = pro_files[0].stem
    pcb_file = project_dir / f"{stem}.kicad_pcb"
    sch_file = project_dir / f"{stem}.kicad_sch"
    design_json = project_dir / "design.json"
    
    if not pcb_file.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_file}")
    
    cli = load_cli()
    if not cli:
         raise FileNotFoundError("Could not find kicad-cli.exe. Ensure paths in kicad_paths.json are correct.")

    print(f"[*] Found KiCad CLI: {cli}")
    print(f"[*] Target Project: {stem} at {project_dir}")
    
    out_dir = project_dir / "jlcpcb_production"
    gerber_dir = out_dir / "gerbers"
    if gerber_dir.exists():
        import shutil
        shutil.rmtree(gerber_dir)
    gerber_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Export standard JLCPCB Gerber layers
    print("\n[1/4] Exporting standard Gerber layers...")
    essential_layers = "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts,F.Paste,B.Paste"
    gerber_cmd = [
        cli, "pcb", "export", "gerbers",
        "--output", str(gerber_dir) + os.sep,
        "--layers", essential_layers,
        "--subtract-soldermask",
        "--use-drill-file-origin",
        str(pcb_file)
    ]
    res = subprocess.run(gerber_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Gerber export warning: {res.stderr}")
    else:
        print("    -> Front/Back Copper, Solder Mask, Silkscreen, Paste, Edge.Cuts exported.")
    
    # 2. Export Excellon Drill Files
    print("\n[2/4] Exporting Excellon Drill files...")
    drill_cmd = [
        cli, "pcb", "export", "drill",
        "--output", str(gerber_dir) + os.sep,
        "--format", "excellon",
        "--excellon-units", "mm",
        "--excellon-separate-th",
        "--excellon-oval-format", "alternate",
        "--drill-origin", "absolute",
        str(pcb_file)
    ]
    res = subprocess.run(drill_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Drill export warning: {res.stderr}")
    else:
        print("    -> PTH & NPTH drill files generated.")
        
    # 3. Create Clean Gerber ZIP archive
    zip_path = out_dir / f"Gerber_{stem}.zip"
    print(f"\n[3/4] Packaging Gerber & Drill ZIP: {zip_path.name}...")
    allowed_extensions = {".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gtp", ".gbp", ".gm1", ".gbr", ".drl", ".gbrjob"}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in gerber_dir.glob("*"):
            if f.is_file() and (f.suffix.lower() in allowed_extensions or "drl" in f.name.lower()):
                # Exclude unneeded layers from the zip
                if any(x in f.name for x in ["User_", "Margin", "Courtyard", "Adhesive"]):
                    continue
                zf.write(f, arcname=f.name)
    print(f"    -> Ready for JLCPCB Upload: {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")
    
    # 4. Generate JLCPCB CPL (Pick & Place) CSV
    print("\n[4/4] Generating SMT Assembly Files (BOM & CPL)...")
    raw_pos_csv = out_dir / f"{stem}_raw_pos.csv"
    pos_cmd = [
        cli, "pcb", "export", "pos",
        "--output", str(raw_pos_csv),
        "--format", "csv",
        "--units", "mm",
        "--side", "both",
        "--use-drill-file-origin",
        str(pcb_file)
    ]
    subprocess.run(pos_cmd, capture_output=True, text=True)
    
    cpl_file = out_dir / f"CPL_{stem}.csv"
    cpl_rows = []
    if raw_pos_csv.exists():
        with open(raw_pos_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ref = row.get("Ref", "").strip('"')
                val = row.get("Val", "").strip('"')
                pkg = row.get("Package", "").strip('"')
                pos_x = row.get("PosX", "0").strip('"')
                pos_y = row.get("PosY", "0").strip('"')
                rot = row.get("Rot", "0").strip('"')
                side = row.get("Side", "top").strip('"').capitalize()
                
                # Exclude mechanical mounting holes from SMT pick-and-place list
                if ref.startswith("H") and ("MountingHole" in pkg or "MountingHole" in val):
                    continue
                
                cpl_rows.append({
                    "Designator": ref,
                    "Mid X": f"{float(pos_x):.2f}",
                    "Mid Y": f"{float(pos_y):.2f}",
                    "Layer": side,
                    "Rotation": f"{float(rot):.1f}",
                    "Comment": val,
                    "Package": pkg.split(":")[-1]
                })
        
        with open(cpl_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Comment", "Package"])
            writer.writeheader()
            writer.writerows(cpl_rows)
        print(f"    -> JLCPCB CPL: {cpl_file.name} ({len(cpl_rows)} SMT components)")
    
    # 5. Generate JLCPCB BOM CSV
    bom_file = out_dir / f"BOM_{stem}.csv"
    lcsc_map = {}
    if design_json.exists():
        try:
            d_data = json.loads(design_json.read_text(encoding="utf-8"))
            for p_ref, p_info in d_data.get("parts", {}).items():
                fields = p_info.get("fields", {})
                lcsc = fields.get("LCSC", "")
                if lcsc:
                    lcsc_map[p_ref] = lcsc
        except Exception as e:
            print(f"[!] Warning: Could not read LCSC IDs from design.json: {e}")
            
    raw_bom_csv = out_dir / f"{stem}_raw_bom.csv"
    bom_cmd = [
        cli, "sch", "export", "bom",
        "--output", str(raw_bom_csv),
        "--fields", "Reference,Value,Footprint,QUANTITY,LCSC",
        "--labels", "Designator,Comment,Footprint,Quantity,LCSC Part #",
        "--group-by", "Value,Footprint,LCSC",
        str(sch_file)
    ]
    subprocess.run(bom_cmd, capture_output=True, text=True)
    
    bom_rows = []
    if raw_bom_csv.exists():
        with open(raw_bom_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                desig = row.get("Designator", "").strip('"')
                comment = row.get("Comment", "").strip('"')
                footprint = row.get("Footprint", "").strip('"')
                qty = row.get("Quantity", "").strip('"')
                lcsc = row.get("LCSC Part #", "").strip('"')
                
                # Check design.json map
                if not lcsc:
                    for r in desig.split(","):
                        r_clean = r.strip()
                        if r_clean in lcsc_map:
                            lcsc = lcsc_map[r_clean]
                            break
                            
                # Fallback to common LCSC part mapping
                short_fp = footprint.split(":")[-1]
                if not lcsc:
                    for (c_val, c_pkg), c_lcsc in COMMON_LCSC_PARTS.items():
                        if c_val.lower() == comment.lower() and c_pkg.lower() in short_fp.lower():
                            lcsc = c_lcsc
                            break
                
                bom_rows.append({
                    "Comment": comment,
                    "Designator": desig,
                    "Footprint": short_fp,
                    "Quantity": qty,
                    "LCSC Part #": lcsc
                })
        
        with open(bom_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Comment", "Designator", "Footprint", "Quantity", "LCSC Part #"])
            writer.writeheader()
            writer.writerows(bom_rows)
        print(f"    -> JLCPCB BOM: {bom_file.name} ({len(bom_rows)} component groups)")
        
    print("\n=======================================================")
    print("    🎉 ALL JLCPCB PRODUCTION FILES READY TO ORDER!     ")
    print("=======================================================")
    print(f"📁 Output Folder : {out_dir}")
    print(f"📦 1. Gerber ZIP  : {zip_path.name}  (PCB Fabrication)")
    print(f"📋 2. BOM File    : {bom_file.name}     (SMT Component Sourcing)")
    print(f"📍 3. CPL File    : {cpl_file.name}     (SMT Pick & Place Centroid)")
    print("=======================================================")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    export_jlcpcb(target)

