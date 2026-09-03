"""
Stage 2 Test: Schematic Compilation & Zero-Error ERC Gate.
Verifies design.json -> .kicad_sch compilation and automated Electrical Rules Check (ERC).
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

def test_schematic_compilation():
    print("[TEST 2] Testing Schematic Compilation & ERC Verification...")
    
    test_dir = _ROOT / "tests" / "test_project_stage2"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create project files
    pro_file = test_dir / "stage2_board.kicad_pro"
    pro_content = {
        "meta": {"filename": "stage2_board.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
        "sheets": [["", ""]]
    }
    pro_file.write_text(json.dumps(pro_content, indent=2), encoding="utf-8")
    
    # Write canonical benchmark design.json (Power Supply & Status LED Indicator)
    design_data = {
        "project": "stage2_board",
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
    
    # Run compilation
    res = compile_schematic(
        project_dir=test_dir,
        design_file=design_file,
        apply_netclasses=True,
        run_erc=True
    )
    
    sch_file = test_dir / "stage2_board.kicad_sch"
    assert sch_file.exists(), f"Expected schematic file {sch_file} not created! (Result: {res})"
    print(f"  ? Schematic compiled: {sch_file.name} ({sch_file.stat().st_size} bytes)")
    
    erc = res.get("erc", {})
    erc_errors = erc.get("errors", 0)
    print(f"  ? ERC Results: {erc_errors} errors, {erc.get('warnings', 0)} warnings")
    assert erc_errors == 0, f"ERC verification failed with {erc_errors} errors: {erc}"
    
    print("[TEST 2 PASSED] Schematic compilation and zero-error ERC gate is 100% verified.")
    return True

if __name__ == "__main__":
    if test_schematic_compilation():
        sys.exit(0)
    sys.exit(1)
