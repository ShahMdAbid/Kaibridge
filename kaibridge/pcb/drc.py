"""Kaibridge Headless Design Rules Check (DRC) Engine.
Runs KiCad 10 DRC CLI headlessly and parses violations JSON.
"""
from __future__ import annotations

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.paths import load_cli


def run_drc(project_dir: str | Path) -> Dict[str, Any]:
    """Runs full DRC check on the PCB and returns parsed violations report."""
    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        return {"success": False, "error": f"Project directory not found: {project_dir}"}

    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    
    # Store in kaibridge_dump/
    dump_dir = proj_path / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    drc_report_file = dump_dir / "drc_report.json"

    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli executable not found."}

    cmd = [
        str(cli), "pcb", "drc",
        "--format", "json",
        "--severity-all",
        "--refill-zones",
        "-o", str(drc_report_file),
        str(pcb_file)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)

    report_data = {}
    if not drc_report_file.exists():
        # Fallback check in project root
        legacy_cand = proj_path / "drc_report.json"
        if legacy_cand.exists():
            drc_report_file = legacy_cand

    if drc_report_file.exists():
        try:
            with open(drc_report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)
        except Exception as e:
            report_data = {"parse_error": str(e)}

    violations = report_data.get("violations", [])
    unconnected = report_data.get("unconnected_items", [])
    schematic_parity = report_data.get("schematic_parity_issues", [])

    clearance_errors = [v for v in violations if v.get("severity") == "error"]
    clearance_warnings = [v for v in violations if v.get("severity") == "warning"]

    passed = len(clearance_errors) == 0 and len(unconnected) == 0

    return {
        "success": passed,
        "passed": passed,
        "drc_report_file": str(drc_report_file),
        "clearance_errors": len(clearance_errors),
        "geometric_clearance_errors": len(clearance_errors),
        "clearance_warnings": len(clearance_warnings),
        "geometric_clearance_warnings": len(clearance_warnings),
        "unconnected": len(unconnected),
        "unconnected_airwires_count": len(unconnected),
        "violations": violations,
        "unconnected_items": unconnected
    }
