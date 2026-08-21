#!/usr/bin/env python3
import os
import sys
import subprocess
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kicad_pins import load_cli

def save_live_board():
    """Forces KiCad to flush the active board to disk using the agent bridge."""
    bridge = os.path.join(os.path.dirname(__file__), "kicad_agent_bridge.py")
    cmd = [
        sys.executable, bridge, 
        "--code", "pcbnew.SaveBoard(pcbnew.GetBoard().GetFileName(), pcbnew.GetBoard())"
    ]
    subprocess.run(cmd, capture_output=True)

def resolve_board(project_dir):
    pros = glob.glob(os.path.join(project_dir, "*.kicad_pro"))
    if not pros:
        return None
    stem = os.path.splitext(os.path.basename(pros[0]))[0]
    return os.path.join(project_dir, f"{stem}.kicad_pcb")

def main():
    if len(sys.argv) < 2:
        print("Usage: python pcb_snapshot.py <PROJECT_DIR>")
        sys.exit(1)
        
    project_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(project_dir):
        print(f"Error: Not a directory: {project_dir}")
        sys.exit(1)
        
    pcb_file = resolve_board(project_dir)
    if not pcb_file or not os.path.exists(pcb_file):
        print(f"Error: No matching .kicad_pcb file found for the project in {project_dir}")
        sys.exit(1)
        
    save_live_board()
        
    base_name = os.path.splitext(os.path.basename(pcb_file))[0]
    out_svg = os.path.join(project_dir, f"{base_name}_board.svg")
    
    kicad_cli = load_cli()
    if not kicad_cli:
        print("Error: kicad-cli not found.")
        sys.exit(1)
        
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

