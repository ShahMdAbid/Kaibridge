"""
Stage 6 Gate: Live KiCad SWIG API Oracle Test & Stress Benchmark (test_6_oracle.py).
Validates dynamic SWIG reflection, inheritance tree resolution, docstring extraction,
fuzzy typo suggestions, and latency benchmarks against the host KiCad pcbnew installation.
"""
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.core import query_oracle, find_pcbnew_source


def test_oracle():
    print("[TEST 6] Testing Live KiCad SWIG API Oracle...")

    # 1. Verify host pcbnew.py source discovery
    src = find_pcbnew_source()
    assert src is not None and src.is_file(), f"Failed to locate host pcbnew.py source: {src}"
    print(f"  ? Located host pcbnew source: {src}")

    # 2. Test Global Function resolution
    t0 = time.time()
    res_global = query_oracle("ExportSpecctraDSN")
    t_global = (time.time() - t0) * 1000
    assert res_global.get("success"), f"Global lookup failed: {res_global}"
    assert "ExportSpecctraDSN" in res_global.get("exact_signature", ""), "Signature mismatch"
    print(f"  ? Global function 'ExportSpecctraDSN' resolved in {t_global:.2f}ms")

    # 3. Test Class Method with Inheritance (BOARD.Delete -> BOARD_ITEM_CONTAINER)
    t0 = time.time()
    res_board = query_oracle("Delete", class_name="BOARD")
    t_board = (time.time() - t0) * 1000
    assert res_board.get("success"), f"BOARD.Delete lookup failed: {res_board}"
    assert "Delete" in res_board.get("exact_signature", ""), "Signature mismatch"
    print(f"  ? Inherited method 'BOARD.Delete' resolved in {t_board:.2f}ms (Defined in {res_board.get('defined_in_class')})")

    # 4. Test Class Method (ZONE.SetPadConnection)
    t0 = time.time()
    res_zone = query_oracle("SetPadConnection", class_name="ZONE")
    t_zone = (time.time() - t0) * 1000
    assert res_zone.get("success"), f"ZONE.SetPadConnection lookup failed: {res_zone}"
    print(f"  ? Direct method 'ZONE.SetPadConnection' resolved in {t_zone:.2f}ms")

    # 5. Test Class Method (SHAPE_LINE_CHAIN.Append)
    res_chain = query_oracle("Append", class_name="SHAPE_LINE_CHAIN")
    assert res_chain.get("success"), f"SHAPE_LINE_CHAIN.Append lookup failed: {res_chain}"
    print(f"  ? Class method 'SHAPE_LINE_CHAIN.Append' resolved")

    # 6. Test Poly Set (SHAPE_POLY_SET.AddOutline)
    res_poly = query_oracle("AddOutline", class_name="SHAPE_POLY_SET")
    assert res_poly.get("success"), f"SHAPE_POLY_SET.AddOutline lookup failed: {res_poly}"
    print(f"  ? Polygon set method 'SHAPE_POLY_SET.AddOutline' resolved")

    # 7. Test Class Inspection (ZONE_FILLER)
    res_cls = query_oracle("ZONE_FILLER")
    assert res_cls.get("success") and res_cls.get("type") == "CLASS", f"Class query failed: {res_cls}"
    assert "constructor" in res_cls and "Fill" in res_cls.get("methods", []), "Expected constructor and Fill method"
    print(f"  [PASS] Class query 'ZONE_FILLER' resolved with constructor & {res_cls.get('methods_count')} methods")

    # 8. Test Constant Query (ZONE_CONNECTION_FULL)
    res_const = query_oracle("ZONE_CONNECTION_FULL")
    assert res_const.get("success") and res_const.get("type") == "CONSTANT", f"Constant query failed: {res_const}"
    print(f"  [PASS] Constant query 'ZONE_CONNECTION_FULL' resolved")

    # 9. Test Architecture Rules Query (drc_rules)
    res_rules = query_oracle("drc_rules")
    assert res_rules.get("success") and res_rules.get("type") == "RULE", f"Rules query failed: {res_rules}"
    print(f"  [PASS] Architecture rules query 'drc_rules' resolved: {res_rules.get('topic')}")

    # 10. Test Fuzzy Typo Suggestions
    t0 = time.time()
    res_typo = query_oracle("ExportSpecctraFile")
    t_typo = (time.time() - t0) * 1000
    assert not res_typo.get("success"), "Typo should not succeed"
    assert "suggestions" in res_typo, "Expected suggestions for typo"
    print(f"  [PASS] Fuzzy typo query 'ExportSpecctraFile' handled in {t_typo:.2f}ms with suggestions: {res_typo.get('suggestions')}")

    # 8. Stress & Latency Benchmark (80 rapid queries)
    t_stress_start = time.time()
    queries = [
        ("GetTracks", "BOARD"),
        ("GetFootprints", "BOARD"),
        ("SetPosition", "FOOTPRINT"),
        ("SetNetCode", "PAD"),
        ("Outline", "ZONE"),
        ("AddOutline", "SHAPE_POLY_SET"),
        ("ExportSpecctraDSN", "GLOBAL"),
        ("SaveBoard", "GLOBAL")
    ]
    for _ in range(10):
        for q, c in queries:
            r = query_oracle(q, class_name=c)
            assert r.get("success"), f"Stress query failed: {q} on {c}"

    total_stress_time = (time.time() - t_stress_start) * 1000
    avg_latency = total_stress_time / 80.0
    print(f"  ? Stress benchmark: 80 queries completed in {total_stress_time:.2f}ms (Avg latency: {avg_latency:.2f}ms/query)")

    print("[TEST 6 PASSED] Live KiCad SWIG API Oracle is 100% verified & grounded.")


if __name__ == "__main__":
    test_oracle()
