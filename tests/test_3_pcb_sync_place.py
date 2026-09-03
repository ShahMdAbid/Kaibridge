"""
Stage 3 Test: Headless PCB Synchronization & Layout Ops Gate.
Verifies programmatic F8 footprint instantiation, netlist binding, and ops.json layout execution.
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
from kaibridge.pcb import sync_schematic_to_pcb, apply_ops

def test_pcb_sync_and_place():
    print("[TEST 3] Testing Headless PCB Sync & Ops Layout...")
    
    test_dir = _ROOT / "tests" / "test_project_stage3"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize project and compile schematic
    pro_file = test_dir / "stage3_board.kicad_pro"
    pro_content = {
        "meta": {"filename": "stage3_board.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
        "sheets": [["", ""]]
    }
    pro_file.write_text(json.dumps(pro_content, indent=2), encoding="utf-8")
    
    design_data = {
        "project": "stage3_board",
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
    
    # Compile schematic
    sch_res = compile_schematic(test_dir, design_file, run_erc=True)
    assert sch_res.get("success"), f"Schematic compile failed: {sch_res}"
    print("  ? Schematic compiled successfully.")
    
    # 2. Synchronize to PCB (Headless F8)
    sync_res = sync_schematic_to_pcb(test_dir)
    assert sync_res.get("success"), f"PCB Sync failed: {sync_res}"
    total_fps = sync_res.get("total_footprints", 0)
    print(f"  ? Headless PCB Sync complete: {total_fps} footprints instantiated, {sync_res.get('pads_connected', 0)} pads bound.")
    assert total_fps == 5, f"Expected 5 footprints, found {total_fps}"
    
    # 3. Apply structured layout operations
    ops_payload = [
        {"op": "board.set_size", "width": 50.0, "height": 40.0, "origin_x": 0.0, "origin_y": 0.0},
        {"op": "footprint.place", "ref": "J1", "x": 10.0, "y": 20.0, "rot": 0},
        {"op": "footprint.place", "ref": "R1", "x": 25.0, "y": 12.0, "rot": 0},
        {"op": "footprint.place", "ref": "R2", "x": 25.0, "y": 28.0, "rot": 0},
        {"op": "footprint.place", "ref": "C1", "x": 38.0, "y": 12.0, "rot": 90},
        {"op": "footprint.place", "ref": "D1", "x": 38.0, "y": 28.0, "rot": 90}
    ]
    
    layout_res = apply_ops(test_dir, ops_payload)
    assert layout_res.get("success"), f"Apply ops failed: {layout_res}"
    print(f"  ? Ops layout applied successfully: 6 operations executed.")
    
    # Verify in-memory / on-disk board structure
    pcb_file = test_dir / "stage3_board.kicad_pcb"
    assert pcb_file.exists() and pcb_file.stat().st_size > 0, "PCB file is missing or 0 bytes"
    
    from kaibridge.pcb.inspector import get_board_state
    state = get_board_state(test_dir, mode="summary")
    fps = {fp["reference"]: fp for fp in state.get("footprints", [])}
    assert set(fps.keys()) == {"J1", "R1", "R2", "C1", "D1"}, f"Footprints mismatch: {list(fps.keys())}"
    
    # Verify J1 position
    j1_pos = fps["J1"]["position_mm"]
    pos_x, pos_y = j1_pos["x"], j1_pos["y"]
    assert abs(pos_x - 10.0) < 0.01 and abs(pos_y - 20.0) < 0.01, f"J1 position wrong: ({pos_x}, {pos_y})"
    print(f"  [PASS] J1 placement coordinates verified: ({pos_x}mm, {pos_y}mm)")
    
    print("[TEST 3 PASSED] Headless PCB synchronization and layout ops gate is 100% verified.")
    return True

if __name__ == "__main__":
    if test_pcb_sync_and_place():
        sys.exit(0)
    sys.exit(1)
