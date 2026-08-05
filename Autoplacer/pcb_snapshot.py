#!/usr/bin/env python3
import os
import sys
import subprocess
import glob

def main():
    if len(sys.argv) < 2:
        print("Usage: python pcb_snapshot.py <PROJECT_DIR>")
        sys.exit(1)
        
    project_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(project_dir):
        print(f"Error: Not a directory: {project_dir}")
        sys.exit(1)
        
    pcb_files = glob.glob(os.path.join(project_dir, "*.kicad_pcb"))
    if not pcb_files:
        print(f"Error: No .kicad_pcb file found in {project_dir}")
        sys.exit(1)
        
    pcb_file = pcb_files[0]
    base_name = os.path.splitext(os.path.basename(pcb_file))[0]
    out_svg = os.path.join(project_dir, f"{base_name}_board.svg")
    
    kicad_cli = "kicad-cli"
    alt_cli = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
    if os.path.exists(alt_cli):
        kicad_cli = alt_cli
        
    cmd = [
        kicad_cli, "pcb", "export", "svg",
        "--layers", "F.Cu,B.Cu,Edge.Cuts,F.Fab,F.SilkS,F.CrtYd",
        "--page-size-mode", "2",
        "--exclude-drawing-sheet",
        "-o", out_svg,
        pcb_file
    ]
    
    print(f"Taking snapshot of PCB: {pcb_file}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Snapshot saved to: {out_svg}")
    except subprocess.CalledProcessError as e:
        print(f"Error exporting SVG:\n{e.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    main()
