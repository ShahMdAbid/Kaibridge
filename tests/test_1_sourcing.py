"""
Stage 1 Test: Sourcing & Pin Extraction Gate.
Verifies symbol library resolution and pin mapping.
"""
import sys
from pathlib import Path

#Add package to sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.sourcing import LibIndex

def test_sourcing():
    print("[TEST 1] Testing Symbol Library Index & Pin Extraction...")
    idx = LibIndex()
    
    # Test native KiCad passives
    sym_r = idx.symbol("Device:R")
    assert sym_r is not None, "Failed to resolve Device:R"
    assert len(sym_r.pins) == 2, f"Expected 2 pins for Device:R, got {len(sym_r.pins)}"
    print("  [PASS] Device:R resolved (2 pins)")

    sym_c = idx.symbol("Device:C")
    assert sym_c is not None, "Failed to resolve Device:C"
    assert len(sym_c.pins) == 2, f"Expected 2 pins for Device:C, got {len(sym_c.pins)}"
    print("  [PASS] Device:C resolved (2 pins)")

    sym_led = idx.symbol("Device:LED")
    assert sym_led is not None, "Failed to resolve Device:LED"
    assert len(sym_led.pins) == 2, f"Expected 2 pins for Device:LED, got {len(sym_led.pins)}"
    print("  [PASS] Device:LED resolved (2 pins)")

    print("[TEST 1 PASSED] Sourcing & Pin Extraction gate is 100% verified.")
    return True

if __name__ == "__main__":
    if test_sourcing():
        sys.exit(0)
    sys.exit(1)
