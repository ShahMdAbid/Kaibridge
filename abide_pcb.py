#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess
from pathlib import Path

def fail(phase, problems, next_action=""):
    print(json.dumps({
        "ok": False,
        "phase": phase,
        "problems": problems,
        "next_action": next_action
    }, indent=2))
    sys.exit(1)

def success(phase, detail=""):
    print(json.dumps({
        "ok": True,
        "phase": phase,
        "detail": detail
    }, indent=2))

def run_bridge_ops(project_dir, ops, commit=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path = os.path.join(script_dir, "Autoplacer", "kicad_agent_bridge.py")
    ops_file = os.path.join(project_dir, "temp_ops.json")
    with open(ops_file, "w") as f:
        json.dump(ops, f)
    
    cmd = [sys.executable, bridge_path, "--json-ops", ops_file]
    if commit:
        cmd.append("--commit")
        
    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(ops_file):
        os.remove(ops_file)
        
    for line in res.stdout.splitlines():
        if line.startswith("ABIDE_RESULT "):
            try:
                return json.loads(line[13:])
            except Exception:
                pass
    return None

def step_place(project_dir, commit=False):
    print(f"Running placement on {project_dir} (commit={commit})", file=sys.stderr)
    ops_path = os.path.join(project_dir, "ops.json")
    ops = []
    if os.path.exists(ops_path):
        try:
            with open(ops_path, "r") as f:
                ops = json.load(f)
        except Exception:
            pass
    res = run_bridge_ops(project_dir, ops, commit=commit)
    if not res:
        fail("place", [{"code": "KICAD_NOT_CONNECTED", "detail": "No response from KiCad"}])
        
    if not res.get("applied"):
        failed = res.get("failed") or {}
        detail = failed.get("error") or res.get("problems") or "Unknown error"
        fail("place", [{"code": "PLACEMENT_REJECTED", "detail": detail}], 
             next_action="Apply fixes returned in placement_report")
    success("place", "Placement is valid.")

def step_route(project_dir):
    print(f"Running routing on {project_dir}", file=sys.stderr)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runner = os.path.join(script_dir, "Autoplacer", "freerouting_runner.py")
    res = subprocess.run([sys.executable, runner, project_dir], capture_output=True, text=True)
    
    for line in res.stdout.splitlines():
        if line.startswith("{") and "ok" in line:
            try:
                data = json.loads(line)
                if data.get("ok"):
                    success("route", data.get("detail"))
                    return
                else:
                    fail("route", data.get("problems", []))
                    return
            except json.JSONDecodeError:
                pass
                
    if res.returncode != 0:
        fail("route", [{"code": "ROUTER_CRASH", "detail": res.stderr or res.stdout}])
    success("route", "Done")

def step_check(project_dir):
    print(f"Running DRC check on {project_dir}", file=sys.stderr)
    # Placeholder for actual DRC check via kicad-cli
    success("check", "DRC not fully implemented in this script yet.")

def step_auto(project_dir):
    # Loop state budget implementation
    loop_file = os.path.join(project_dir, "pcb_brain", "loop_state.json")
    os.makedirs(os.path.dirname(loop_file), exist_ok=True)
    
    budget = 4
    for i in range(budget):
        print(f"Auto iteration {i+1}/{budget}", file=sys.stderr)
        step_place(project_dir, commit=True)
        try:
            step_route(project_dir)
            break
        except SystemExit as e:
            if e.code == 0:
                break
            # if failed, we could try to auto-resolve or give up
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--step", choices=["place", "route", "check", "auto"], required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    
    if args.step == "place":
        step_place(args.project_dir, args.commit)
    elif args.step == "route":
        step_route(args.project_dir)
    elif args.step == "check":
        step_check(args.project_dir)
    elif args.step == "auto":
        step_auto(args.project_dir)
