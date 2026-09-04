"""Kaibridge Schematic Compiler:
Direct in-process compilation from design.json -> KiCad hierarchical .kicad_sch schematics.
"""
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.model import load, sidecar, DesignError
from ..core.paths import load_cli
from ..sourcing.klib import LibIndex, LibError
from .place import plan
from .render import build, write, VERSION, existing_uuid, uid


def compile_schematic(
    project_dir: str | Path,
    design_file: Optional[str | Path] = None,
    output_name: Optional[str] = None,
    apply_netclasses: bool = True,
    run_erc: bool = True,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Compiles design.json into full hierarchical .kicad_sch schematics in-process."""
    folder = Path(project_dir).resolve()
    if not folder.exists():
        return {"success": False, "error": f"Project directory does not exist: {project_dir}"}

    # 1. Detect project files
    pros = sorted(folder.glob("*.kicad_pro"))
    project_name = pros[0].stem if pros else folder.name
    pro_path = pros[0] if pros else folder / f"{project_name}.kicad_pro"

    if design_file is None:
        cand = folder / "kaibridge_dump" / "design.json"
        if not cand.exists():
            cand = folder / "design.json"
        if not cand.exists():
            return {"success": False, "error": f"No design.json found in {folder} or kaibridge_dump/"}
        design_path = cand
    else:
        design_path = Path(design_file).resolve()
        if not design_path.exists():
            return {"success": False, "error": f"Design file not found: {design_path}"}

    root_out = folder / (output_name or f"{project_name}.kicad_sch")

    # 2. Load LibIndex & Design Model
    try:
        lib = LibIndex(folder)
    except LibError as e:
        return {"success": False, "error": f"Library resolution error: {e}"}

    try:
        raw_data = json.loads(design_path.read_text(encoding="utf-8-sig"))
        design = load(raw_data, lib)
    except DesignError as e:
        return {"success": False, "error": f"Design error: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Invalid JSON file: {e}"}

    # 3. Layout & Build S-expression files in-process (supports multi-sheet / multipage automatically)
    try:
        layout = plan(design)
        files = build(design, layout, lib, project_name, root_out.stem, version=VERSION)
    except Exception as e:
        return {"success": False, "error": f"Compilation error: {e}"}

    if dry_run:
        sheet_info = [
            {
                "id": s.id,
                "parts": len(design.sheet_parts(s.id)),
                "nets": len([n for n in design.nets.values() if s.id in n.sheets]),
                "paper": s.paper
            }
            for s in design.sheets
        ]
        return {
            "success": True,
            "dry_run": True,
            "project_name": project_name,
            "schematic_files": list(files.keys()),
            "sheets": sheet_info,
            "total_parts": len(design.parts),
            "total_nets": len(design.nets),
            "warnings": design.warnings
        }

    # 4. Write schematics to disk
    written, orphaned = write(files, folder, backup=False)

    # 5. Write sidecar build metadata
    try:
        sc = sidecar(design, lib)
        dump_dir = folder / "kaibridge_dump"
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / "kaibridge_build.json").write_text(json.dumps(sc, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 6. Apply Netclasses & JLCPCB Design Rules to .kicad_pro
    if apply_netclasses and pro_path.exists():
        _update_netclasses_in_pro(pro_path, design.netclasses or {}, design=design)

    # 7. Run ERC verification if requested
    erc_summary = {"errors": 0, "warnings": 0, "violations": []}
    if run_erc:
        erc_summary = _execute_erc(root_out, folder)

    return {
        "success": len(files) > 0 and erc_summary.get("errors", 0) == 0,
        "schematic_files": list(files.keys()),
        "project_name": project_name,
        "erc": erc_summary,
        "erc_errors": erc_summary.get("errors", 0),
        "erc_warnings": erc_summary.get("warnings", 0),
        "violations": erc_summary.get("violations", []),
        "warnings": design.warnings
    }


def _update_netclasses_in_pro(pro_path: Path, netclasses: Dict[str, Any], design: Any = None):
    try:
        pro_data = json.loads(pro_path.read_text(encoding="utf-8-sig"))
        ns = pro_data.setdefault("net_settings", {})
        classes = ns.setdefault("classes", [])
        existing = {c.get("name"): c for c in classes if isinstance(c, dict) and "name" in c}

        # 1. Ensure Default class exists with standard 0.25mm width
        if "Default" not in existing:
            def_entry = {
                "name": "Default",
                "track_width": 0.25,
                "clearance": 0.2,
                "via_diameter": 0.6,
                "via_drill": 0.3
            }
            classes.append(def_entry)
            existing["Default"] = def_entry

        # 2. Add or update specified netclasses
        for name, spec in (netclasses or {}).items():
            entry = existing.get(name, {"name": name})
            for k, v in spec.items():
                if k != "nets":
                    entry[k] = v
            if name not in existing:
                classes.append(entry)
                existing[name] = entry

        # 3. Synthesize netclass_patterns to bind nets to netclasses in KiCad & DSN exporter
        patterns = []
        assigned_nets = set()

        # From netclasses spec 'nets' array (e.g. "Power": {"nets": ["VBUS", "GND"]})
        for name, spec in (netclasses or {}).items():
            if name != "Default" and isinstance(spec, dict) and "nets" in spec:
                for pat in spec["nets"]:
                    patterns.append({"netclass": name, "pattern": str(pat)})
                    assigned_nets.add(str(pat))

        # From design.nets netclass attribute
        if design and hasattr(design, "nets") and isinstance(design.nets, dict):
            for net_name, net_obj in design.nets.items():
                nc = getattr(net_obj, "netclass", None)
                if nc and nc != "Default" and net_name not in assigned_nets:
                    patterns.append({"netclass": nc, "pattern": net_name})
                    assigned_nets.add(net_name)

        # Auto-infer Power netclass for power_flags and common power nets if 'Power' exists
        if "Power" in existing:
            pflags = getattr(design, "power_flags", []) if design else []
            for pf in (pflags or []):
                if pf not in assigned_nets:
                    patterns.append({"netclass": "Power", "pattern": pf})
                    assigned_nets.add(pf)

            if design and hasattr(design, "nets") and isinstance(design.nets, dict):
                for net_name in design.nets:
                    if net_name not in assigned_nets:
                        upper_n = net_name.upper()
                        if upper_n in ("GND", "VBUS", "VIN", "+5V", "+3V3", "3V3", "5V", "VCC", "VDD") or \
                           upper_n.startswith(("VBUS", "VIN", "+", "PWR_")) or upper_n.endswith(("_PWR", "VBUS", "_GND")):
                            patterns.append({"netclass": "Power", "pattern": net_name})
                            assigned_nets.add(net_name)

        if patterns:
            ns["netclass_patterns"] = patterns

        # 4. Inject JLCPCB production DRC constraints into .kicad_pro
        board_settings = pro_data.setdefault("board", {}).setdefault("design_settings", {})
        rules = board_settings.setdefault("rules", {})
        if "min_copper_edge_clearance" not in rules or rules["min_copper_edge_clearance"] > 0.15:
            rules["min_copper_edge_clearance"] = 0.15
        if "min_clearance" not in rules:
            rules["min_clearance"] = 0.15
        if "min_track_width" not in rules:
            rules["min_track_width"] = 0.15
        if "min_hole_clearance" not in rules:
            rules["min_hole_clearance"] = 0.25
        if "min_hole_to_hole" not in rules:
            rules["min_hole_to_hole"] = 0.25
        if "min_via_diameter" not in rules:
            rules["min_via_diameter"] = 0.5
        if "min_through_hole_clearance" not in rules:
            rules["min_through_hole_clearance"] = 0.2

        pro_path.write_text(json.dumps(pro_data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _execute_erc(sch_path: Path, project_dir: Path) -> Dict[str, int]:
    cli = load_cli()
    if not cli:
        return {"errors": 0, "warnings": 0}
    dump_dir = project_dir / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    report_path = dump_dir / "erc_report.json"
    cmd = [str(cli), "sch", "erc", str(sch_path), "--output", str(report_path), "--format", "json"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not report_path.exists():
            return {"errors": 0, "warnings": 0}
        data = json.loads(report_path.read_text(encoding="utf-8-sig"))
        errors = 0
        warnings = 0
        violations_list = []
        for s in data.get("sheets", []):
            sheet_name = s.get("name") or "Root"
            for v in s.get("violations", []):
                sev = v.get("severity")
                desc = v.get("description")
                t = v.get("type")
                items = v.get("items", [])
                item_desc = " <-> ".join([i.get("description", "") for i in items]) if items else ""
                msg = f"[{t}] {sheet_name}: {desc}"
                if item_desc:
                    msg += f" ({item_desc})"
                violations_list.append(msg)
                if sev == "error":
                    errors += 1
                else:
                    warnings += 1
        return {"errors": errors, "warnings": warnings, "violations": violations_list}
    except Exception:
        return {"errors": 0, "warnings": 0, "violations": []}

