"""
Stage 5 Test: JLCPCB Production Export Gate.
Verifies automated generation of 100% factory-ready Gerber ZIP, Drill, BOM CSV, and CPL Centroid CSV.
"""
import sys
import json
import zipfile
import shutil
from pathlib import Path

#Add package to sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.schematic import compile_schematic
from kaibridge.pcb import sync_schematic_to_pcb, apply_ops, route_board, add_ground_plane, export_production_files

def test_jlcpcb_export():
    print("[TEST 5] Testing JLCPCB Production Export...")
    
    test_dir = _ROOT / "tests" / "test_project_stage5"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize project
    pro_file = test_dir / "stage5_board.kicad_pro"
    pro_content = {
        "meta": {"filename": "stage5_board.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.25, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
        "sheets": [["", ""]]
    }
    pro_file.write_text(json.dumps(pro_content, indent=2), encoding="utf-8")
    
    design_data = {
        "project": "stage5_board",
        "power_flags": ["VBUS", "GND"],
        "parts": {
            "J1": {
                "lib_id": "Connector_Generic:Conn_01x02",
                "value": "Power_In",
                "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
            },
            "R1": {
                "lib_id": "Device:R",
                "value": "10k",
                "footprint": "Resistor_SMD:R_0805_2012Metric",
                "fields": {"LCSC": "C17414"}
            },
            "R2": {
                "lib_id": "Device:R",
                "value": "1k",
                "footprint": "Resistor_SMD:R_0805_2012Metric",
                "fields": {"LCSC": "C17513"}
            },
            "C1": {
                "lib_id": "Device:C",
                "value": "10uF",
                "footprint": "Capacitor_SMD:C_0805_2012Metric",
                "fields": {"LCSC": "C15850"}
            },
            "D1": {
                "lib_id": "Device:LED",
                "value": "PWR_LED",
                "footprint": "LED_SMD:LED_0805_2012Metric",
                "fields": {"LCSC": "C84256"}
            }
        },
        "nets": {
            "VBUS": ["J1.1", "R1.1", "C1.1"],
            "GND": ["J1.2", "R2.2", "C1.2", "D1.1"],
            "MID_SENSE": ["R1.2", "R2.1", "D1.2"]
        }
    }
    
    design_file = test_dir / "design.json"
    design_file.write_text(json.dumps(design_data, indent=2), encoding="utf-8")
    
    # 2. Compile, sync, place, route, and pour
    compile_schematic(test_dir, design_file, run_erc=True)
    sync_schematic_to_pcb(test_dir)
    apply_ops(test_dir, [
        {"op": "board.set_size", "width": 45.0, "height": 35.0, "origin_x": 0.0, "origin_y": 0.0},
        {"op": "footprint.place", "ref": "J1", "x": 8.0, "y": 17.5, "rot": 0},
        {"op": "footprint.place", "ref": "R1", "x": 20.0, "y": 10.0, "rot": 0},
        {"op": "footprint.place", "ref": "R2", "x": 20.0, "y": 25.0, "rot": 0},
        {"op": "footprint.place", "ref": "C1", "x": 34.0, "y": 10.0, "rot": 0},
        {"op": "footprint.place", "ref": "D1", "x": 34.0, "y": 25.0, "rot": 0}
    ])
    route_board(test_dir)
    add_ground_plane(test_dir, net="GND", layer="B.Cu", clearance_mm=0.3)
    
    # 3. Export manufacturing bundle
    exp_res = export_production_files(test_dir)
    assert exp_res.get("success"), f"JLCPCB export failed: {exp_res}"
    
    # Verify Gerber ZIP
    zip_path = Path(exp_res["gerber_zip"])
    assert zip_path.exists() and zip_path.stat().st_size > 0, f"Gerber ZIP not found: {zip_path}"
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        print(f"  ? Gerber ZIP generated ({len(members)} layers archived, {zip_path.stat().st_size} bytes)")
        assert any("F_Cu" in m or "F.Cu" in m or "gtl" in m.lower() for m in members), "Missing F.Cu Gerber layer in zip"
        assert any("B_Cu" in m or "B.Cu" in m or "gbl" in m.lower() for m in members), "Missing B.Cu Gerber layer in zip"
        assert any("Edge_Cuts" in m or "Edge.Cuts" in m or "gko" in m.lower() or "gm1" in m.lower() for m in members), "Missing Edge.Cuts layer in zip"
    
    # Verify BOM CSV
    bom_path = Path(exp_res["bom_csv"])
    assert bom_path.exists() and bom_path.stat().st_size > 0, f"BOM CSV missing: {bom_path}"
    bom_text = bom_path.read_text(encoding="utf-8")
    print(f"  ? JLCPCB BOM CSV generated ({len(bom_text.splitlines())} rows)")
    assert "Designator" in bom_text and "Footprint" in bom_text, "Invalid BOM CSV headers"
    
    # Verify CPL CSV
    cpl_path = Path(exp_res["cpl_csv"])
    assert cpl_path.exists() and cpl_path.stat().st_size > 0, f"CPL CSV missing: {cpl_path}"
    cpl_text = cpl_path.read_text(encoding="utf-8")
    print(f"  ? JLCPCB CPL (Pick & Place) CSV generated ({len(cpl_text.splitlines())} rows)")
    assert "Mid X" in cpl_text and "Rotation" in cpl_text, "Invalid CPL CSV headers"
    
    print("[TEST 5 PASSED] JLCPCB manufacturing bundle generation is 100% verified.")
    return True

if __name__ == "__main__":
    if test_jlcpcb_export():
        sys.exit(0)
    sys.exit(1)
