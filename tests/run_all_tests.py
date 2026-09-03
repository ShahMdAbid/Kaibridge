"""
Kaibridge 2.0 Master Automated Test Suite Runner.
Executes all 7 stage gates sequentially and produces a unified audit report.
"""
import sys
import time
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TESTS = [
    ("Stage 1: Sourcing & Pin Extraction Gate", _ROOT / "tests" / "test_1_sourcing.py"),
    ("Stage 2: Schematic Compilation & Zero-Error ERC Gate", _ROOT / "tests" / "test_2_schematic.py"),
    ("Stage 3: Headless PCB Sync & Ops Layout Gate", _ROOT / "tests" / "test_3_pcb_sync_place.py"),
    ("Stage 4: Headless Autorouting, Pour & DRC Gate", _ROOT / "tests" / "test_4_routing_drc.py"),
    ("Stage 5: JLCPCB Production Export Gate", _ROOT / "tests" / "test_5_jlcpcb_export.py"),
    ("Stage 6: Live KiCad SWIG API Oracle & Stress Gate", _ROOT / "tests" / "test_6_oracle.py"),
    ("Stage 7: Board Introspection, Geometry Gate & Snapshot/Diff Gate", _ROOT / "tests" / "test_7_introspection.py"),
]

def main():
    print("=" * 75)
    print(" KAIBRIDGE 2.0 MASTER AUTOMATED TEST SUITE RUNNER")
    print(f"   Target Engine: {_ROOT}")
    print(f"   Python Interpreter: {sys.executable}")
    print("=" * 75)
    
    overall_start = time.time()
    results = []
    
    for idx, (name, test_file) in enumerate(_TESTS, 1):
        print(f"\n[{idx}/7] RUNNING: {name}")
        print("-" * 75)
        
        t0 = time.time()
        res = subprocess.run([sys.executable, str(test_file)], capture_output=True, text=True)
        dur = time.time() - t0
        
        # Clean wx image handler warnings from output display
        lines = [line for line in res.stdout.splitlines() if not line.startswith("Adding duplicate image handler")]
        clean_stdout = "\n".join(lines).strip()
        if clean_stdout:
            print(clean_stdout)
            
        if res.returncode == 0:
            print(f"? PASS ({dur:.2f}s)")
            results.append((name, True, dur, ""))
        else:
            print(f"? FAIL ({dur:.2f}s)")
            if res.stderr.strip():
                print("STDERR:\n" + res.stderr.strip())
            results.append((name, False, dur, res.stderr.strip() or clean_stdout))
            
    total_dur = time.time() - overall_start
    print("\n" + "=" * 75)
    print(" KAIBRIDGE 2.0 TEST SUITE AUDIT REPORT")
    print("=" * 75)
    
    all_passed = True
    for name, ok, dur, err in results:
        status_str = "? PASS" if ok else "? FAIL"
        if not ok:
            all_passed = False
        print(f" {status_str} | {dur:6.2f}s | {name}")
        
    print("-" * 75)
    print(f" Total Execution Time: {total_dur:.2f}s")
    if all_passed:
        print("  ALL 7 STAGE GATES PASSED! Kaibridge 2.0 is 100% verified & production ready.")
        sys.exit(0)
    else:
        print(" ?? SOME GATES FAILED. Please review the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

