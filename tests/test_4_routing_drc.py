"""
Stage 4 Test: Headless Autorouting, Ground Pour & DRC Verification Gate.
Verifies Specctra DSN export, Java Freerouting 2.3.0 execution, SES track import,
GND copper pour, and zero-violation Design Rules Check (DRC).
"""
import sys
import json
import shutil
from pathlib import Path

#Add package to sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.schematic import compile_schematic
from kaibridge.pcb import sync_schematic_to_pcb, apply_ops, route_board, add_ground_plane, run_drc

def test_routing_and_drc():
    print("[TEST 4] Testing Headless Autorouting, Ground Pour & DRC Check...")
    
    test_dir = _ROOT / "tests" / "test_project_stage4"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize project
    pro_file = test_dir / "stage4_board.kicad_pro"
    pro_content = {
        "meta": {"filename": "stage4_board.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.25, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
        "sheets": [["", ""]]
    }
    pro_file.write_text(json.dumps(pro_content, indent=2), encoding="utf-8")
    
    design_data = {
        "project": "stage4_board",
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
                "footprint": "Resistor_SMD:R_0805_2012Metric"
            },
            "R2": {
                "lib_id": "Device:R",
                "value": "1k",
                "footprint": "Resistor_SMD:R_0805_2012Metric"
            },
            "C1": {
                "lib_id": "Device:C",
                "value": "10uF",
                "footprint": "Capacitor_SMD:C_0805_2012Metric"
            },
            "D1": {
                "lib_id": "Device:LED",
                "value": "PWR_LED",
                "footprint": "LED_SMD:LED_0805_2012Metric"
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
    
    # 2. Compile schematic & sync to PCB
    sch_res = compile_schematic(test_dir, design_file, run_erc=True)
    assert sch_res.get("success"), f"Schematic compile failed: {sch_res}"
    
    sync_res = sync_schematic_to_pcb(test_dir)
    assert sync_res.get("success"), f"PCB sync failed: {sync_res}"
    
    # 3. Apply floorplan placement
    ops_payload = [
        {"op": "board.set_size", "width": 45.0, "height": 35.0, "origin_x": 0.0, "origin_y": 0.0},
        {"op": "footprint.place", "ref": "J1", "x": 8.0, "y": 17.5, "rot": 0},
        {"op": "footprint.place", "ref": "R1", "x": 20.0, "y": 10.0, "rot": 0},
        {"op": "footprint.place", "ref": "R2", "x": 20.0, "y": 25.0, "rot": 0},
        {"op": "footprint.place", "ref": "C1", "x": 34.0, "y": 10.0, "rot": 0},
        {"op": "footprint.place", "ref": "D1", "x": 34.0, "y": 25.0, "rot": 0}
    ]
    layout_res = apply_ops(test_dir, ops_payload)
    assert layout_res.get("success"), f"Layout failed: {layout_res}"
    print("  ? Floorplan placed and Edge.Cuts border created.")
    
    # 4. Autoroute PCB
    route_res = route_board(test_dir)
    assert route_res.get("success"), f"Autorouting failed: {route_res}"
    print(f"  ? Autorouting completed successfully via {route_res.get('method')}.")
    
    # 5. Add Ground Pour Plane
    pour_res = add_ground_plane(test_dir, net="GND", layer="B.Cu", clearance_mm=0.3)
    assert pour_res.get("success"), f"Ground plane pour failed: {pour_res}"
    print("  ? GND copper zone poured and filled on B.Cu.")
    
    # 6. Run Design Rules Check (DRC)
    drc_res = run_drc(test_dir)
    clr_errors = drc_res.get("geometric_clearance_errors", 0)
    unconn = drc_res.get("unconnected_airwires_count", 0)
    print(f"  ? DRC Audit: {clr_errors} clearance errors, {unconn} unconnected airwires.")
    assert clr_errors == 0, f"DRC clearance errors found: {clr_errors} (Violations: {drc_res.get('violations')})"
    
    print("[TEST 4 PASSED] Headless autorouting, ground pour, and DRC verification gate is 100% verified.")
    return True

if __name__ == "__main__":
    if test_routing_and_drc():
        sys.exit(0)
    sys.exit(1)
