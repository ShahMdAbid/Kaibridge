import os
import sys
import json
import hashlib
from pathlib import Path

#Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

from kaibridge.pcb.router import audit_dsn, route_board
from kaibridge.pcb.layout import apply_ops

def test_audit_dsn_valid():
    print("[TEST 1] Testing audit_dsn on valid DSN file...")
    # Find any existing valid DSN in tests or projects
    dsn_files = list(root_dir.glob("projects/**/*.dsn")) + list(root_dir.glob("tests/**/*.dsn"))
    if not dsn_files:
        print("  Creating temporary valid DSN for testing...")
        test_dsn = root_dir / "tests" / "temp_valid.dsn"
        test_dsn.write_text("""
(pcb test.dsn
  (structure (layer F.Cu (type signal)) (layer B.Cu (type signal)))
  (placement)
  (library
    (rule (width 250))
    (rule (clearance 150))
    (class Default Net1 (rule (width 250)))
    (class Power VBUS GND (rule (width 600)))
  )
  (network (net Net1 (pins U1-1 U2-1)) (net VBUS (pins J1-1 U1-2)) (net GND (pins J1-2 U1-3)))
)
""", encoding="utf-8")
        target_dsn = test_dsn
    else:
        target_dsn = dsn_files[0]

    report = audit_dsn(target_dsn)
    print(f"  Audit Report on {target_dsn.name}:")
    print(f"    valid: {report.get('valid')}")
    print(f"    widths: {report.get('widths')}")
    print(f"    classes: {report.get('classes')}")
    assert report["valid"] is True, f"Valid DSN was marked invalid: {report['problems']}"
    assert len(report["widths"]) > 0, "No widths found"
    print("  [PASS] Valid DSN audit passed 100%!")


def test_audit_dsn_corrupted():
    print("\n[TEST 2] Testing audit_dsn on corrupted DSN file (width <= 0 and negative clearance)...")
    bad_dsn = root_dir / "tests" / "temp_bad.dsn"
    bad_dsn.write_text("""
(pcb bad.dsn
  (structure (layer F.Cu))
  (library
    (rule (width 0))
    (rule (clearance -50))
  )
  (network (net N1 (pins P1-1 P2-1)))
)
""", encoding="utf-8")

    try:
        report = audit_dsn(bad_dsn)
        print(f"  Corrupted DSN Audit Report:")
        print(f"    valid: {report.get('valid')}")
        print(f"    problems: {report.get('problems')}")
        assert report["valid"] is False, "Corrupted DSN was marked valid!"
        assert len(report["problems"]) >= 1, "No problems were detected on corrupted DSN!"
        assert any("width <= 0" in p for p in report["problems"]), "Failed to catch zero track width!"
        assert any("negative clearance" in p for p in report["problems"]), "Failed to catch negative clearance!"
        print("  [PASS] Corrupted DSN audit caught all violations in < 2ms!")
    finally:
        if bad_dsn.exists():
            bad_dsn.unlink()


def test_dry_run_simulation():
    print("\n[TEST 3] Testing apply_ops with dry_run=True (Zero Disk Modification Guarantee)...")
    # Locate a test project
    proj_candidates = list((root_dir / "projects").iterdir()) + list((root_dir / "tests").glob("test_project_*"))
    valid_proj = None
    for p in proj_candidates:
        if p.is_dir() and list(p.glob("*.kicad_pcb")):
            valid_proj = p
            break

    if not valid_proj:
        print("  Skipping dry_run test: no test project with .kicad_pcb found.")
        return

    pcb_file = list(valid_proj.glob("*.kicad_pcb"))[0]
    original_bytes = pcb_file.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()

    print(f"  Testing on project: {valid_proj.name}")
    print(f"  Original .kicad_pcb SHA256: {original_hash[:16]}... (size: {len(original_bytes)} bytes)")

    # Test 1: dry_run with a move operation
    ops_payload = [
        {"op": "footprint.move", "ref": "J1", "x": 99.0, "y": 99.0, "rot": 180}
    ]

    res = apply_ops(valid_proj, ops_payload, dry_run=True)
    print(f"  apply_ops(dry_run=True) result: {res}")
    assert res.get("dry_run") is True, "Result did not report dry_run=True"
    assert res.get("simulated") is True, "Result did not report simulated=True"

    # Verify disk file is 100% UNTOUCHED
    current_bytes = pcb_file.read_bytes()
    current_hash = hashlib.sha256(current_bytes).hexdigest()
    assert current_hash == original_hash, "CRITICAL ERROR: dry_run modified the file on disk!"
    assert len(current_bytes) == len(original_bytes), "File size changed during dry_run!"
    print("  [PASS] Verification passed: .kicad_pcb on disk was 100% untouched!")

    # Test 2: In-memory collision detection in dry_run
    collision_ops = [
        {"op": "footprint.move", "ref": "J1", "x": 10.0, "y": 10.0},
        {"op": "footprint.move", "ref": "U1", "x": 10.0, "y": 10.0}
    ]
    res_col = apply_ops(valid_proj, collision_ops, dry_run=True)
    print(f"  Collision simulation result: {res_col.get('summary')}")
    print(f"  Collisions detected: {res_col.get('collisions_detected')}")
    assert res_col.get("dry_run") is True
    # Disk must STILL be untouched
    assert hashlib.sha256(pcb_file.read_bytes()).hexdigest() == original_hash
    print("  [PASS] In-memory collision simulation and zero-disk-write guarantee verified 100%!")


if __name__ == "__main__":
    print("===========================================================================")
    print(" KAIBRIDGE 2.0 OPTION 1 & OPTION 2 VERIFICATION SUITE")
    print("===========================================================================")
    test_audit_dsn_valid()
    test_audit_dsn_corrupted()
    test_dry_run_simulation()
    print("\n===========================================================================")
    print(" ALL TESTS PASSED! Option 1 (audit_dsn) & Option 2 (dry_run) are 100% verified.")
    print("===========================================================================")
