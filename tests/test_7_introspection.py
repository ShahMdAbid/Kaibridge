"""
Stage 7 Gate: Board Introspection, Geometry Gate, Snapshot & Diff Test (test_7_introspection.py).
Validates all ported features from Kaibridge 2.0 ? 3.0 architecture alignment.
"""
import sys
import time
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.pcb import get_board_state, placement_audit, snapshot_board, diff_board

PROJ = _ROOT / "projects" / "usbc_power_hub"


def test_introspection():
    print("[TEST 7] Testing Board Introspection, Geometry Gate & Snapshot/Diff...")

    # 1. Board State Introspection (Summary Mode)
    t0 = time.time()
    state = get_board_state(PROJ, mode="summary")
    dt = (time.time() - t0) * 1000
    assert state.get("success"), f"Board state failed: {state.get('error')}"
    assert state.get("footprint_count", 0) > 0, "No footprints found"
    assert state.get("net_count", 0) > 0, "No nets found"
    assert state.get("fingerprint"), "Missing fingerprint"
    assert state.get("outline_closed"), "Board outline not closed"
    print(f"  ? Board state (summary): {state['footprint_count']} footprints, {state['net_count']} nets, {state['track_count']} tracks ({dt:.1f}ms)")

    # 2. Board State Introspection (Full Mode)
    t0 = time.time()
    full = get_board_state(PROJ, mode="full")
    dt = (time.time() - t0) * 1000
    assert full.get("success"), f"Full state failed: {full.get('error')}"
    assert len(full.get("tracks", [])) > 0, "No tracks in full mode"
    assert len(full.get("footprints", [])) > 0, "No footprints in full mode"
    # Validate footprint structure
    fp0 = full["footprints"][0]
    assert "reference" in fp0, "Missing reference field"
    assert "position_mm" in fp0, "Missing position_mm field"
    assert "pads" in fp0, "Missing pads field"
    print(f"  ? Board state (full): {len(full['tracks'])} tracks, {len(full.get('vias', []))} vias, {len(full.get('zones', []))} zones ({dt:.1f}ms)")

    # 3. Placement Audit (Geometry Gate)
    t0 = time.time()
    audit = placement_audit(PROJ)
    dt = (time.time() - t0) * 1000
    assert audit.get("success"), f"Placement audit failed: {audit.get('error')}"
    assert audit.get("outline_closed"), "Outline not closed"
    assert audit.get("footprint_count", 0) > 0, "No footprints in audit"
    assert "overlaps" in audit, "Missing overlaps field"
    assert "route_ready" in audit, "Missing route_ready flag"
    assert "footprint_boxes" in audit, "Missing footprint_boxes"
    print(f"  ? Placement audit: {audit['overlap_count']} overlaps, {audit['outside_outline_count']} outside, route_ready={audit['route_ready']} ({dt:.1f}ms)")

    # 4. Snapshot Board
    t0 = time.time()
    snap1 = snapshot_board(PROJ, tag="test_pre")
    dt = (time.time() - t0) * 1000
    assert snap1.get("success"), f"Snapshot failed: {snap1}"
    assert Path(snap1["snapshot_file"]).exists(), "Snapshot file not created"
    print(f"  ? Snapshot 'test_pre': {snap1['footprint_count']} fps, {snap1['track_count']} tracks ({dt:.1f}ms)")

    # 5. Second Snapshot (to enable diff)
    snap2 = snapshot_board(PROJ, tag="test_post")
    assert snap2.get("success"), f"Second snapshot failed: {snap2}"
    print(f"  ? Snapshot 'test_post': fingerprint={snap2['fingerprint'][:10]}...")

    # 6. Diff Between Two Snapshots
    t0 = time.time()
    d = diff_board(PROJ, snapshot_a=snap1["snapshot_file"], snapshot_b=snap2["snapshot_file"])
    dt = (time.time() - t0) * 1000
    assert d.get("success"), f"Diff failed: {d}"
    assert d.get("identical") == True, f"Same board should produce identical diff, got: {d.get('summary')}"
    print(f"  ? Diff (same board): identical={d['identical']}, summary={d.get('summary')} ({dt:.1f}ms)")

    # 7. Diff Against Live Board
    t0 = time.time()
    d_live = diff_board(PROJ, snapshot_a=snap1["snapshot_file"])
    dt = (time.time() - t0) * 1000
    assert d_live.get("success"), f"Live diff failed: {d_live}"
    print(f"  ? Diff (vs live): identical={d_live['identical']} ({dt:.1f}ms)")

    print("[TEST 7 PASSED] Board introspection, geometry gate, snapshot & diff verified.")


if __name__ == "__main__":
    test_introspection()
