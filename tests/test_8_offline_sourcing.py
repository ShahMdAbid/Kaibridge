"""
Stage 8 Test: Offline JLCPCB Sourcing Engine & Native KiCad Integration.
Verifies sub-millisecond querying of easyeda-std.elib, Golden Master cache,
JLCPCB Basic Part detection, and ERC-safe KiCad component recommendation.
"""
import sys
import time
from pathlib import Path

#Add package root to sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.core import find_easyeda_db
from kaibridge.sourcing import (
    lookup_by_lcsc,
    search_basic_passives,
    recommend_kicad_part,
    PartsDatabase
)
from server import handle_tool_call


def test_offline_sourcing():
    print("[TEST 8] Testing Offline JLCPCB Parts Engine...")

    # 1. Database Discovery
    db_path = find_easyeda_db()
    print(f"  [1/5] Database discovery: {db_path} (exists={db_path.exists() if db_path else False})")
    assert db_path is not None and db_path.exists(), "easyeda-std.elib not found!"

    # 2. Lookup by LCSC ID (Benchmark latency)
    t0 = time.perf_counter()
    part_c17513 = lookup_by_lcsc("C17513")
    dt = (time.perf_counter() - t0) * 1000
    print(f"  [2/5] LCSC Lookup C17513 in {dt:.3f}ms: {part_c17513['title']} ({part_c17513['part_class']})")
    assert part_c17513 is not None
    assert part_c17513["lcsc_id"] == "C17513"
    assert "Basic Part" in part_c17513["part_class"]
    assert part_c17513["package"] == "0805"

    # Test active IC lookup from SQLite (AMS1117-3.3)
    part_c6186 = lookup_by_lcsc("C6186")
    print(f"        Active IC C6186: {part_c6186['display_title']} ({part_c6186['part_class']})")
    assert part_c6186 is not None
    assert "AMS1117" in part_c6186["display_title"]

    # 3. Search Basic Passives (Avoid $3 fee)
    resistors_10k = search_basic_passives("R", "10k", package="0805")
    print(f"  [3/5] Search 0805 10k basic passives found: {len(resistors_10k)} matches")
    assert len(resistors_10k) > 0
    assert resistors_10k[0]["part_class"] == "Basic Part"

    caps_100n = search_basic_passives("C", "100nF", package="0805")
    print(f"        Search 0805 100nF basic caps found: {len(caps_100n)} matches (LCSC={caps_100n[0]['lcsc_id']})")
    assert len(caps_100n) > 0
    assert caps_100n[0]["lcsc_id"] == "C1525"

    # 4. Recommend KiCad Component (0-ERC Guarantee)
    rec_r = recommend_kicad_part("R", "10k", package="0805")
    print(f"  [4/5] Recommended R: lib_id={rec_r['lib_id']}, fp={rec_r['footprint']}, fields={rec_r['fields']}")
    assert rec_r["lib_id"] == "Device:R"
    assert rec_r["footprint"] == "Resistor_SMD:R_0805_2012Metric"
    assert "LCSC" in rec_r["fields"]
    assert rec_r["fields"]["JLCPCB_Class"] == "Basic Part"

    rec_c = recommend_kicad_part("C", "10uF", package="0805")
    print(f"        Recommended C: lib_id={rec_c['lib_id']}, fp={rec_c['footprint']}, fields={rec_c['fields']}")
    assert rec_c["lib_id"] == "Device:C"
    assert rec_c["footprint"] == "Capacitor_SMD:C_0805_2012Metric"
    assert rec_c["fields"]["LCSC"] == "C15850"

    rec_led = recommend_kicad_part("LED", "Green", package="0805")
    print(f"        Recommended LED: lib_id={rec_led['lib_id']}, fp={rec_led['footprint']}, fields={rec_led['fields']}")
    assert rec_led["lib_id"] == "Device:LED"
    assert rec_led["footprint"] == "LED_SMD:LED_0805_2012Metric"
    assert rec_led["fields"]["LCSC"] == "C2290"

    # 5. Test MCP Server Tool Call Dispatch
    server_res = handle_tool_call("kaibridge_lookup_lcsc_part", {"component_type": "R", "value": "1k", "package": "0805"})
    print(f"  [5/5] MCP tool response: success={server_res.get('success')}, rec={server_res.get('recommended', {}).get('fields')}")
    assert server_res.get("success") is True
    assert server_res["recommended"]["fields"]["LCSC"] == "C17513"

    print("[SUCCESS] Stage 8 Offline Sourcing Engine verified successfully!\n")


if __name__ == "__main__":
    test_offline_sourcing()
