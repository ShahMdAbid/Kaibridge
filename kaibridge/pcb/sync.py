"""Kaibridge PCB Synchronizer (Programmatic F8):
Binds netlist, instantiates footprints, and attaches all Net connections/ratsnest directly to .kicad_pcb.
"""
from __future__ import annotations

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from ..core.paths import load_cli, load_kicad_python
from ..sourcing.klib import LibIndex


def sync_schematic_to_pcb(project_dir: str | Path) -> Dict[str, Any]:
    """Automates the 'F8' (Update PCB from Schematic) step headlessly with full Net/Ratsnest binding."""
    proj_path = Path(project_dir).resolve()
    if not proj_path.exists():
        return {"success": False, "error": f"Project path does not exist: {project_dir}"}

    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro project found in directory."}

    proj_name = pro_files[0].stem
    sch_file = proj_path / f"{proj_name}.kicad_sch"
    pcb_file = proj_path / f"{proj_name}.kicad_pcb"
    
    # Check kaibridge_dump/design.json then project_dir/design.json
    design_file = proj_path / "kaibridge_dump" / "design.json"
    if not design_file.exists():
        design_file = proj_path / "design.json"

    if not sch_file.exists():
        sch_files = list(proj_path.glob("*.kicad_sch"))
        if sch_files:
            sch_file = sch_files[0]
        else:
            return {"success": False, "error": "No .kicad_sch schematic file found."}

    cli = load_cli()
    if not cli:
        return {"success": False, "error": "kicad-cli not found in system PATH."}

    # 1. Export netlist from schematic
    netlist_file = proj_path / f"{proj_name}.net"
    cmd_net = [str(cli), "sch", "export", "netlist", str(sch_file), "-o", str(netlist_file)]
    res_net = subprocess.run(cmd_net, capture_output=True, text=True)

    # 2. Perform PCB footprint instantiation and Net binding via pcbnew
    try:
        import pcbnew
    except ImportError:
        # If not running in KiCad python, execute via KiCad python subprocess
        kicad_python = load_kicad_python()
        runner = f"""
import sys, json
sys.path.insert(0, r"{str(Path(__file__).resolve().parents[2])}")
from kaibridge.pcb.sync import _execute_pcbnew_sync
res = _execute_pcbnew_sync(r"{str(proj_path)}", r"{str(pcb_file)}", r"{str(design_file)}")
print("PCB_SYNC_RESULT:" + json.dumps(res))
"""
        res_sub = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True)
        for line in res_sub.stdout.splitlines():
            if line.startswith("PCB_SYNC_RESULT:"):
                return json.loads(line.replace("PCB_SYNC_RESULT:", ""))
        return {"success": False, "error": res_sub.stderr.strip() or res_sub.stdout.strip()}

    return _execute_pcbnew_sync(str(proj_path), str(pcb_file), str(design_file))


def _execute_pcbnew_sync(proj_path_str: str, pcb_file_str: str, design_file_str: str) -> Dict[str, Any]:
    import pcbnew
    proj_path = Path(proj_path_str)
    pcb_file = Path(pcb_file_str)
    design_file = Path(design_file_str)

    idx = LibIndex(proj_path)

    if pcb_file.exists():
        board = pcbnew.LoadBoard(str(pcb_file))
    else:
        board = pcbnew.BOARD()
        board.SetFileName(str(pcb_file))

    if not design_file.exists():
        return {"success": False, "error": f"design.json missing at {design_file}"}

    with open(design_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    parts_dict = {}
    if "parts" in data and isinstance(data["parts"], dict):
        parts_dict = data["parts"]
    elif "components" in data and isinstance(data["components"], list):
        for c in data["components"]:
            if c.get("ref"):
                parts_dict[c["ref"]] = c

    existing_fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    # 1. Load and place missing footprints
    col = 0
    row = 0
    added_count = 0
    for ref, pdata in parts_dict.items():
        fp_id = pdata.get("footprint", "")
        val = pdata.get("val") or pdata.get("value", "")

        if ref not in existing_fps and fp_id:
            try:
                parts = fp_id.split(":")
                if len(parts) == 2:
                    lib_name, fp_name = parts[0], parts[1]
                    fp_dir = idx._footprint_dir(lib_name)
                    fp = None
                    if fp_dir:
                        fp = pcbnew.FootprintLoad(str(fp_dir), fp_name)
                    if not fp:
                        fp = pcbnew.FootprintLoad(lib_name, fp_name)

                    if fp:
                        fp.SetReference(ref)
                        fp.SetValue(str(val))
                        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(25 + col * 20), pcbnew.FromMM(25 + row * 20)))
                        board.Add(fp)
                        existing_fps[ref] = fp
                        added_count += 1
                        col += 1
                        if col >= 4:
                            col = 0
                            row += 1
            except Exception as e:
                print(f"Warning loading {ref}: {e}")

    # 2. Bind all Nets and Ratsnest Connections
    nets_data = data.get("nets", {})
    nets_bound = 0
    pads_connected = 0

    net_items = []
    if isinstance(nets_data, dict):
        for nname, nval in nets_data.items():
            if isinstance(nval, dict):
                # Schema 3 canonical format: "GND": {"class": "Power", "connections": ["J1.1", ...]}
                conns = nval.get("connections", nval.get("nodes", []))
                net_items.append((nname, conns))
            elif isinstance(nval, list):
                # Shorthand format: "GND": ["J1.1", "C1.2"]
                net_items.append((nname, nval))
    elif isinstance(nets_data, list):
        for n in nets_data:
            net_items.append((n.get("name", ""), n.get("nodes", n.get("connections", []))))

    for net_name, nodes in net_items:
        if not net_name or not nodes:
            continue

        net_info = board.FindNet(net_name)
        if not net_info:
            net_info = pcbnew.NETINFO_ITEM(board, net_name)
            board.Add(net_info)
            nets_bound += 1

        for node in nodes:
            if isinstance(node, dict):
                ref = str(node.get("ref", ""))
                pad_num = str(node.get("pin", node.get("pad", "")))
            else:
                node_str = str(node).replace(":", ".")
                node_parts = node_str.split(".")
                if len(node_parts) >= 2:
                    ref = ".".join(node_parts[:-1]).strip()
                    pad_num = node_parts[-1].strip()
                else:
                    continue

            fp = existing_fps.get(ref) or board.FindFootprintByReference(ref)
            if fp:
                pad = fp.FindPadByNumber(pad_num)
                if pad:
                    pad.SetNet(net_info)
                    pads_connected += 1

    board.BuildListOfNets()
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb_file), board)

    total_fps = len(list(board.GetFootprints()))
    del board
    import gc
    gc.collect()

    return {
        "success": True,
        "pcb_file": str(pcb_file),
        "total_footprints": total_fps,
        "footprint_count": total_fps,
        "new_footprints": added_count,
        "nets_bound": nets_bound,
        "pads_connected": pads_connected
    }


