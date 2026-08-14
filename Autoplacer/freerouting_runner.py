import os
import sys
import json
import subprocess
import argparse
import re
from pathlib import Path

_WIDTH = re.compile(r"\(width\s+(-?[\d.]+)\)")
_CLEAR = re.compile(r"\(clearance\s+(-?[\d.]+)")

def fail(code, detail, **kwargs):
    print(json.dumps({"ok": False, "phase": "route", "problems": [{"code": code, "detail": detail, **kwargs}]}))
    sys.exit(1)

def success(detail):
    print(json.dumps({"ok": True, "phase": "route", "detail": detail}))
    sys.exit(0)

def audit_dsn(path):
    """Turn 'Freerouting silently routed 0 nets' into a sentence you can act on."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    widths = [float(v) for v in _WIDTH.findall(text)]
    clears = [float(v) for v in _CLEAR.findall(text)]
    problems = []
    if "(network" not in text:
        problems.append("DSN has no (network ...) section -- nothing to route")
    if not widths:
        problems.append("DSN contains no (width ...) rule at all")
    elif min(widths) <= 0:
        problems.append(
            "%d rule(s) have width <= 0 (min %s). Freerouting will route 0 nets. "
            "Cause: netclasses defined but not assigned. Re-run json2sch.py "
            "--apply-netclasses with KiCad closed, then F8."
            % (sum(1 for w in widths if w <= 0), min(widths)))
    if clears and min(clears) < 0:
        problems.append("DSN has clearance < 0 (min %s)" % min(clears))
    return problems

def run_freerouting(project_dir, jar_path=None, heap_mb=2048, route_timeout=900):
    autoplacer_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path = os.path.join(autoplacer_dir, "kicad_agent_bridge.py")
    plugin_root = os.path.dirname(autoplacer_dir)
    
    if not jar_path or not os.path.exists(jar_path):
        candidates = [
            os.path.join(autoplacer_dir, "freerouting.jar"),
            os.path.expanduser("~/Downloads/freerouting-2.3.0.jar"),
            os.path.expanduser("~/Downloads/freerouting-2.2.4.jar"),
            os.path.expanduser("~/Downloads/freerouting.jar"),
        ]
        jar_path = next((c for c in candidates if os.path.exists(c)), None)
        
    if not jar_path or not os.path.exists(jar_path):
        return fail("MISSING_FREEROUTING", f"freerouting.jar not found (checked Autoplacer/ and Downloads/)")
    
    dsn_path = os.path.join(project_dir, "board.dsn")
    ses_path = os.path.join(project_dir, "board.ses")
    
    for old_file in [dsn_path, ses_path]:
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
            except Exception:
                pass
    
    # 0. Prep for route
    prep_code = (
        "import pcbnew, json, sys\n"
        "from currentboardfetcher import apply_ops\n"
        "res = apply_ops([{'op': 'board.prep_for_route'}], dry_run=False, save=True, refill=False, verify=False)\n"
        "if res.get('failed'):\n"
        "    print(json.dumps({'PREP_FAILED': True, 'problems': res.get('problems') or res.get('failed')}))\n"
        "else:\n"
        "    print(json.dumps({'PREP_SUCCESS': True}))\n"
    )
    res0 = subprocess.run([sys.executable, bridge_path, "--code", prep_code, "--timeout", "120"], capture_output=True, text=True)
    if "PREP_FAILED" in res0.stdout:
        return fail("PREP_FAILED", "Error preparing for route", stdout=res0.stdout)
    
    # 1. Export DSN
    export_code = (
        "import pcbnew\n"
        "board = pcbnew.GetBoard()\n"
        f"success = pcbnew.ExportSpecctraDSN(board, r'{dsn_path}')\n"
        "print('DSN Export:', 'SUCCESS' if success else 'FAILED')\n"
    )
    res = subprocess.run([sys.executable, bridge_path, "--code", export_code, "--timeout", "120"], capture_output=True, text=True)
    if "FAILED" in res.stdout or not os.path.exists(dsn_path):
        return fail("DSN_EXPORT_FAILED", "Error exporting DSN", stdout=res.stdout)

    if os.path.getsize(dsn_path) < 2048:
        return fail("DSN_TOO_SMALL", f"DSN file is too small ({os.path.getsize(dsn_path)} bytes).")
        
    dsn_issues = audit_dsn(dsn_path)
    if dsn_issues:
        return fail("DSN_BAD_RULE", "DSN audit failed", issues=dsn_issues)

    # 2. Run FreeRouting
    cmd = ["java", f"-Xmx{heap_mb}m", "-jar", jar_path, "-de", dsn_path, "-do", ses_path, "--gui.enabled=false"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=route_timeout)
    except subprocess.TimeoutExpired:
        return fail("ROUTER_TIMEOUT", f"Freerouting exceeded {route_timeout}s. Reduce passes or simplify placement.")
    except FileNotFoundError:
        return fail("JAVA_NOT_FOUND", "Java executable not found.")
        
    if "OutOfMemory" in (proc.stderr or "") + (proc.stdout or ""):
        return fail("ROUTER_OOM", f"Freerouting ran out of heap at -Xmx{heap_mb}m. Retry higher.")
        
    if proc.returncode != 0:
        return fail("ROUTER_FAILED", (proc.stderr or proc.stdout or "").strip()[-2000:])

    # 3. Import SES
    ses = Path(ses_path)
    if not ses.exists() or ses.read_text(errors="replace").count("(wire") == 0:
        return fail("ROUTER_ROUTED_NOTHING", "SES contains zero wires.", dsn_audit=audit_dsn(dsn_path))
        
    pcb_path = None
    for f in os.listdir(project_dir):
        if f.endswith('.kicad_pcb'):
            pcb_path = os.path.join(project_dir, f)
            break
            
    if not pcb_path:
        return fail("NO_PCB_FILE", "No .kicad_pcb file found to import SES into.")
        
    # Import SES in a plain python process to avoid corrupting GUI
    import_code = (
        "import pcbnew, sys\n"
        f"b = pcbnew.LoadBoard(r'{pcb_path}')\n"
        f"if not pcbnew.ImportSpecctraSES(b, r'{ses_path}'):\n"
        "    sys.exit(1)\n"
        f"pcbnew.SaveBoard(r'{pcb_path}', b)\n"
        "print('SUCCESS')\n"
    )
    import_proc = subprocess.run([sys.executable, bridge_path, "--code", import_code, "--timeout", "60"], capture_output=True, text=True)
    if "SUCCESS" not in import_proc.stdout:
        return fail("SES_IMPORT_FAILED", "SES import script failed.", stderr=import_proc.stderr, stdout=import_proc.stdout)

    return success("Routing completed successfully. Please reload the PCB in KiCad Editor (File -> Revert to Saved).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Headless FreeRouting for KiCad via Bridge")
    parser.add_argument("project_dir", help="Directory of the KiCad project")
    parser.add_argument("--jar", default=None, help="Path to freerouting.jar")
    parser.add_argument("--heap", type=int, default=2048, help="Java heap size in MB")
    parser.add_argument("--timeout", type=int, default=900, help="Router timeout in seconds")
    args = parser.parse_args()
    
    run_freerouting(args.project_dir, jar_path=args.jar, heap_mb=args.heap, route_timeout=args.timeout)
