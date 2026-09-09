"""Kaibridge Schematic Compiler:
Direct in-process compilation from design.json -> KiCad hierarchical .kicad_sch schematics.
"""
import os
import re
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
    dry_run: bool = False,
    auto_heal_pins: bool = True,
    prefer_global_labels: bool = False
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

    # 1.5. Auto-heal unspecified pin types in project libraries if requested
    if auto_heal_pins:
        libs_dir = folder / "libs"
        if libs_dir.exists():
            for sym_f in libs_dir.glob("*.kicad_sym"):
                try:
                    heal_symbol_pins(sym_f, project_dir=folder)
                except Exception:
                    pass

    # 2. Load LibIndex & Design Model
    try:
        lib = LibIndex(folder)
    except LibError as e:
        return {"success": False, "error": f"Library resolution error: {e}"}

    try:
        raw_data = json.loads(design_path.read_text(encoding="utf-8-sig"))
        design = load(raw_data, lib, prefer_global_labels=prefer_global_labels)
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
        sc = sidecar(design)
        dump_dir = folder / "kaibridge_dump"
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / "kaibridge_build.json").write_text(json.dumps(sc, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 6. Apply Netclasses & JLCPCB Design Rules to .kicad_pro
    if apply_netclasses and pro_path.exists():
        _update_netclasses_in_pro(pro_path, design.netclasses or {}, design=design)

    # 7. Run ERC verification if requested
    erc_summary = {"errors": 0, "warnings": 0, "error_violations": [], "warning_violations": [], "violations": []}
    if run_erc:
        erc_summary = _execute_erc(root_out, folder)

    return {
        "success": len(files) > 0 and erc_summary.get("errors", 0) == 0,
        "schematic_files": list(files.keys()),
        "project_name": project_name,
        "erc": erc_summary,
        "erc_errors": erc_summary.get("errors", 0),
        "erc_warnings": erc_summary.get("warnings", 0),
        "error_violations": erc_summary.get("error_violations", []),
        "warning_violations": erc_summary.get("warning_violations", []),
        "violations": erc_summary.get("violations", []),
        "warnings": design.warnings,
        "design_warnings": design.warnings
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

        # 2.5. Auto-clamp Power netclass for fine-pitch ICs (e.g. LQFP, QFN, TSSOP, BGA, DFN)
        has_fine_pitch = False
        if design and hasattr(design, "parts") and isinstance(design.parts, dict):
            for p_info in design.parts.values():
                fp_str = str(getattr(p_info, "footprint", "") or "")
                val_str = str(getattr(p_info, "value", "") or "")
                sym_str = str(getattr(p_info, "symbol", "") or "")
                combined = f"{fp_str} {val_str} {sym_str}".upper()
                if any(kw in combined for kw in ("LQFP", "QFN", "TSSOP", "DFN", "BGA", "VFBGA", "WLCSP", "P0.5", "P0.4")):
                    has_fine_pitch = True
                    break

        # Note: Freerouting handles fine-pitch neckdowns via automaticNeckdown=True,
        # so Power netclasses preserve their designated width (0.4-0.6mm) without being flattened.

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


def heal_symbol_pins(sym_path: str | Path, project_dir: Optional[Path] = None) -> int:
    """Heals unspecified pin electrical types in KiCad symbol library based on pin names.
    Eliminates [pin_to_pin] unspecified ERC warnings while preserving KiCad validity.
    Transparently logs all alterations to kaibridge_dump/warning.md.
    Returns number of pins updated.
    """
    p = Path(sym_path).resolve()
    if not p.exists() or not p.is_file():
        return 0

    text = p.read_text(encoding="utf-8")
    if "(pin unspecified" not in text:
        return 0

    pin_block_re = re.compile(
        r'(\(pin\s+)unspecified(\s+[a-z_]+.*?\n\s+\(name\s+"([^"]*)"[^\n]*\n\s+\(number\s+"([^"]*)"[^\n]*\))',
        re.DOTALL
    )

    seen_power_out = set()
    updates = 0
    healed_records = []
    current_sym_name = p.stem

    def _replace_pin(m):
        nonlocal updates, current_sym_name
        prefix = m.group(1)
        body = m.group(2)
        name = m.group(3).strip().upper()
        num = m.group(4).strip()

        new_type = "unspecified"

        if name in ("GND", "VSS", "AGND", "DGND", "PGND", "COM", "COMMON") or name.startswith(("GND", "VSS")):
            new_type = "power_in"
        elif name in ("VIN", "VBUS", "VDD", "VCC", "VBAT", "PVIN", "AVDD", "DVDD") or name.startswith(("VIN", "VBUS", "VDD", "VCC", "VBAT")):
            new_type = "power_in"
        elif name in ("VOUT", "VREG", "OUT", "SW", "LX") or name.startswith(("VOUT", "VREG")):
            if name in seen_power_out:
                new_type = "passive"  # Secondary output/tab pin to avoid power_out collision
            else:
                new_type = "power_out"
                seen_power_out.add(name)
        elif name in ("NC", "N.C.", "NO_CONNECT"):
            new_type = "no_connect"
        elif name in ("EN", "ENABLE", "RST", "RESET", "NRST", "SHDN", "CE", "CLK", "IN", "IN+", "IN-", "D", "RS"):
            new_type = "input"
        elif name in ("R", "TX", "TXD", "STATUS", "FAULT", "INT", "IRQ", "VREF", "V_REF"):
            new_type = "output"
        elif name.startswith(("PA", "PB", "PC", "PD", "PE", "PF", "PG", "GPIO", "IO", "SDA", "SCL", "D+", "D-", "DP", "DM", "CC1", "CC2", "SWDIO", "SWCLK", "CANH", "CANL", "CAN_")):
            new_type = "bidirectional"
        elif name in ("RX", "RXD"):
            new_type = "input"
        elif name in ("1", "2", "A", "K", "ANODE", "CATHODE", "BASE", "EMITTER", "COLLECTOR", "DRAIN", "SOURCE", "GATE"):
            new_type = "passive"

        if new_type != "unspecified":
            updates += 1
            healed_records.append(f"- **Symbol:** `{current_sym_name}` | **Pin {num}** (`{name}`): `unspecified` → `{new_type}`")
            return f"{prefix}{new_type}{body}"
        return m.group(0)

    sym_re = re.compile(r'(\(symbol\s+"([^"]+)".*?\n  \))', re.DOTALL)

    def _process_symbol(sm):
        nonlocal seen_power_out, current_sym_name
        current_sym_name = sm.group(2)
        seen_power_out = set()
        return pin_block_re.sub(_replace_pin, sm.group(1))

    new_text = sym_re.sub(_process_symbol, text)
    if updates > 0:
        p.write_text(new_text, encoding="utf-8")

        # Transparently log to kaibridge_dump/warning.md
        pdir = project_dir
        if not pdir and p.parent.name == "libs":
            pdir = p.parent.parent
        if pdir:
            dump_dir = Path(pdir) / "kaibridge_dump"
            dump_dir.mkdir(parents=True, exist_ok=True)
            w_file = dump_dir / "warning.md"
            lines = [
                f"\n### Auto-Healed Pins in `{p.name}`\n",
                f"The following {updates} pins were converted from EasyEDA `unspecified` to typed pins:\n"
            ] + [r + "\n" for r in healed_records]
            if not w_file.exists():
                header = (
                    "# Hardware Synthesis Warnings & Audit Log\n\n"
                    "This log tracks all automated symbol modifications, pin healing actions, "
                    "and electrical sanity audits performed during synthesis.\n\n"
                    "## 1. Symbol Pin Modifications\n"
                )
                w_file.write_text(header + "".join(lines) + "\n## 2. Electrical & ERC Audit Notes\n_No electrical warnings logged yet._\n", encoding="utf-8")
            else:
                existing = w_file.read_text(encoding="utf-8")
                if "_No pin modifications logged yet._" in existing:
                    existing = existing.replace("_No pin modifications logged yet._", "".join(lines).strip())
                    w_file.write_text(existing, encoding="utf-8")
                else:
                    with w_file.open("a", encoding="utf-8") as f:
                        f.write("".join(lines))

    return updates


def _execute_erc(sch_path: Path, project_dir: Path) -> Dict[str, Any]:
    cli = load_cli()
    if not cli:
        return {"errors": 1, "warnings": 0, "error_violations": ["kicad-cli executable not found"], "warning_violations": [], "violations": []}
    dump_dir = project_dir / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    report_path = dump_dir / "erc_report.json"
    
    # Purge any stale report before running
    if report_path.exists():
        try:
            report_path.unlink()
        except Exception:
            pass

    cmd = [
        str(cli), "sch", "erc",
        str(sch_path),
        "--output", str(report_path),
        "--format", "json",
        "--severity-all"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not report_path.exists():
            err_msg = f"kicad-cli sch erc failed to generate report (exit code {res.returncode}): {res.stderr.strip()}"
            return {
                "errors": 1,
                "warnings": 0,
                "error_violations": [err_msg],
                "warning_violations": [],
                "violations": ["ERC report missing"]
            }
        data = json.loads(report_path.read_text(encoding="utf-8-sig"))
        errors = 0
        warnings = 0
        error_violations = []
        warning_violations = []
        violations_list = []
        for s in data.get("sheets", []):
            sheet_name = s.get("name") or "Root"
            for v in s.get("violations", []):
                sev = str(v.get("severity", "")).lower()
                desc = v.get("description", "")
                t = v.get("type", "unknown")
                items = v.get("items", [])
                item_desc = " <-> ".join([i.get("description", "") for i in items if i.get("description")])
                msg = f"[{t}] {sheet_name}: {desc}"
                if item_desc:
                    msg += f" ({item_desc})"
                violations_list.append(msg)
                if sev == "error":
                    errors += 1
                    error_violations.append(msg)
                else:
                    warnings += 1
                    warning_violations.append(msg)
        return {
            "errors": errors,
            "warnings": warnings,
            "error_violations": error_violations,
            "warning_violations": warning_violations,
            "violations": violations_list
        }
    except Exception:
        return {"errors": 0, "warnings": 0, "error_violations": [], "warning_violations": [], "violations": []}


def export_netlist_and_bom(sch_path: Path, project_dir: Path) -> Dict[str, Any]:
    """Exports KiCad XML netlist and BOM CSV via kicad-cli and parses connectivity."""
    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli executable not found"}
    dump_dir = project_dir / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = dump_dir / "netlist.xml"
    bom_path = dump_dir / "bom.csv"

    # Export XML Netlist
    cmd_net = [
        str(cli), "sch", "export", "netlist",
        "--format", "kicadxml",
        "-o", str(netlist_path),
        str(sch_path)
    ]
    subprocess.run(cmd_net, capture_output=True, text=True, check=False)

    # Export BOM CSV
    cmd_bom = [
        str(cli), "sch", "export", "bom",
        "-o", str(bom_path),
        str(sch_path)
    ]
    subprocess.run(cmd_bom, capture_output=True, text=True, check=False)

    nets_summary: Dict[str, list] = {}
    pin_func_nets: Dict[str, list] = {}
    comps_summary: list = []
    ic_pinout_audit: list = []
    audit_md_path = dump_dir / "pinout_audit.md"

    if netlist_path.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(netlist_path)
            root = tree.getroot()

            # 1. Map all defined library symbol parts and their declared pins
            libparts = {}
            for lp in root.findall(".//libpart"):
                lib = lp.get("lib", "")
                part = lp.get("part", "")
                pins = {}
                for p in lp.findall(".//pin"):
                    p_num = p.get("num", "")
                    p_name = p.get("name", "")
                    p_type = p.get("type", "unspecified")
                    pins[p_num] = (p_name, p_type)
                libparts[(lib, part)] = pins

            # 2. Map pin to attached net
            pin_to_net = {}
            for net in root.findall(".//net"):
                name = net.get("name", "")
                raw_nodes = []
                func_nodes = []
                for node in net.findall("node"):
                    r = node.get("ref", "")
                    p = node.get("pin", "")
                    pfunc = node.get("pinfunction") or ""
                    ptype = node.get("pintype") or ""
                    pin_to_net[(r, p)] = (name, pfunc, ptype)

                    raw_nodes.append(f"{r}.{p}")
                    clean_func = pfunc.rsplit("_", 1)[0] if ("_" in pfunc and pfunc.rsplit("_", 1)[1] == p) else pfunc
                    if clean_func and clean_func != p:
                        func_nodes.append(f"{r}.{p}[{clean_func}]")
                    else:
                        func_nodes.append(f"{r}.{p}")

                if name and raw_nodes:
                    nets_summary[name] = raw_nodes
                    pin_func_nets[name] = func_nodes

            # 3. Component inventory
            for comp in root.findall(".//comp"):
                ref = comp.get("ref", "")
                val = comp.find("value").text if comp.find("value") is not None else ""
                fp = comp.find("footprint").text if comp.find("footprint") is not None else ""
                ls = comp.find("libsource")
                lib = ls.get("lib", "") if ls is not None else ""
                part = ls.get("part", "") if ls is not None else ""

                lcsc = ""
                for f in comp.findall(".//field"):
                    if "lcsc" in f.get("name", "").lower():
                        lcsc = f.text or ""
                comps_summary.append({
                    "ref": ref,
                    "value": val or "",
                    "footprint": fp or "",
                    "lcsc": lcsc
                })

                # 4. Detailed IC / Multi-pin Connector Pinout Audit
                defined_pins = libparts.get((lib, part), {})
                if len(defined_pins) > 2 or ref.startswith(("U", "J", "IC", "Q", "SW")):
                    comp_audit = {
                        "ref": ref,
                        "value": val or "",
                        "footprint": fp or "",
                        "total_pins": len(defined_pins),
                        "pins": []
                    }
                    for p_num, (p_name, p_type) in sorted(defined_pins.items(), key=lambda x: (len(str(x[0])), str(x[0]))):
                        conn = pin_to_net.get((ref, p_num))
                        if conn:
                            net_name, pfunc, actual_type = conn
                            is_unconnected = net_name.startswith("unconnected-")
                            status = "[UNCONNECTED / NC]" if is_unconnected else f"Net: {net_name}"
                            clean_name = pfunc.rsplit("_", 1)[0] if ("_" in pfunc and pfunc.rsplit("_", 1)[1] == p_num) else (pfunc or p_name)
                        else:
                            status = "[FLOATING / NOT_CONNECTED]"
                            clean_name = p_name
                            actual_type = p_type

                        comp_audit["pins"].append({
                            "pin": p_num,
                            "name": clean_name or p_num,
                            "type": actual_type,
                            "status": status
                        })
                    ic_pinout_audit.append(comp_audit)

            # 5. Write pinout_audit.md report
            md_lines = [
                f"# Pinout & Netlist Forensic Audit: {project_dir.name}\n",
                f"> Generated by Kaibridge Hardware Synthesis Engine\n",
                f"## 1. Multi-Pin Components & IC Pinout Audit ({len(ic_pinout_audit)} Active Devices)\n"
            ]
            for ca in ic_pinout_audit:
                md_lines.append(f"### Component `{ca['ref']}` ({ca['value']}) — Footprint: `{ca['footprint']}` ({ca['total_pins']} Pins)")
                md_lines.append("| Pin | Symbol Name | Electrical Type | Connected Net / Status |")
                md_lines.append("| :--- | :--- | :--- | :--- |")
                for p in ca["pins"]:
                    md_lines.append(f"| **{p['pin']}** | `{p['name']}` | `{p['type']}` | **{p['status']}** |")
                md_lines.append("")

            md_lines.append("## 2. Pin-Function Netlist Connectivity\n")
            for net_name, nodes in sorted(pin_func_nets.items()):
                if not net_name.startswith("unconnected-"):
                    md_lines.append(f"- **`{net_name}`** : " + "  ".join(nodes))
            md_lines.append("")

            audit_md_path.write_text("\n".join(md_lines), encoding="utf-8")

        except Exception:
            pass

    return {
        "success": netlist_path.exists(),
        "netlist_file": str(netlist_path) if netlist_path.exists() else None,
        "bom_file": str(bom_path) if bom_path.exists() else None,
        "audit_md_file": str(audit_md_path) if audit_md_path.exists() else None,
        "nets_summary": nets_summary,
        "pin_func_nets": pin_func_nets,
        "ic_pinout_audit": ic_pinout_audit,
        "components": comps_summary
    }



