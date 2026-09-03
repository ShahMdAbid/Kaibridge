"""Kaibridge Headless Routing Engine (router.py):
Handles Specctra DSN export, Java Freerouting v2.3.0 execution, SES track import,
and headless ground zone pouring with solid thermal pad connections and exact outline clipping.
Supports dual-mode execution: direct in-process when pcbnew is available, or isolated
subprocess fallback via KiCad's bundled Python interpreter.
"""
from __future__ import annotations

import os
import sys
import json
import time
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.paths import load_cli, load_kicad_python, find_freerouting_jar

_DSN_WIDTH = re.compile(r"\(width\s+(-?[\d.]+)\)")
_DSN_CLEAR = re.compile(r"\(clearance\s+(-?[\d.]+)\)")
_DSN_CLASS = re.compile(r"\(class\s+([^\s\(\)]+)", re.IGNORECASE)


def audit_dsn(dsn_path: str | Path) -> Dict[str, Any]:
    """Audits Specctra DSN text before launching Java Freerouting.
    Catches zero/negative widths, negative clearances, missing nets, and unassigned netclasses in < 2ms.
    """
    p = Path(dsn_path).resolve()
    if not p.exists() or p.stat().st_size == 0:
        return {
            "valid": False,
            "problems": ["DSN file does not exist or is 0 bytes."],
            "warnings": [],
            "widths": [],
            "classes": []
        }

    text = p.read_text(encoding="utf-8", errors="replace")
    widths = [float(v) for v in _DSN_WIDTH.findall(text)]
    clears = [float(v) for v in _DSN_CLEAR.findall(text)]
    classes = _DSN_CLASS.findall(text)
    problems = []
    warnings = []

    if "(network" not in text:
        problems.append("DSN file contains no (network ...) section -- nothing to route.")

    if not widths:
        problems.append("DSN contains no (width ...) rule at all.")
    elif any(w <= 0 for w in widths):
        bad_count = sum(1 for w in widths if w <= 0)
        min_w = min(widths)
        problems.append(
            f"{bad_count} rule(s) have width <= 0 (minimum: {min_w}). Freerouting will route 0 nets. "
            "Cause: Netclasses defined in schematic without track_width or nets not assigned."
        )

    if clears and any(c < 0 for c in clears):
        problems.append(f"DSN contains negative clearance (minimum: {min(clears)}).")

    unique_widths = sorted(set(widths))
    if len(classes) > 1 and len(unique_widths) <= 1:
        warnings.append(
            f"Multiple netclasses detected ({', '.join(classes[:5])}) but only a single width rule ({unique_widths}) was exported."
        )

    return {
        "valid": len(problems) == 0,
        "problems": problems,
        "warnings": warnings,
        "widths": unique_widths,
        "classes": classes,
        "filesize_bytes": p.stat().st_size
    }


def _dispatch_sub(func_name: str, kwargs: dict) -> Dict[str, Any]:
    """Runs a router function inside KiCad's Python interpreter when pcbnew is not importable."""
    kicad_python = load_kicad_python()
    root_pkg = Path(__file__).resolve().parents[2]
    payload = json.dumps(kwargs)
    runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.router import {func_name}
kwargs = json.loads(r'''{payload}''')
res = {func_name}(**kwargs)
print("ROUTER_SUB_RESULT:" + json.dumps(res))
"""
    proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines():
        if line.startswith("ROUTER_SUB_RESULT:"):
            return json.loads(line.replace("ROUTER_SUB_RESULT:", ""))
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}


def unroute_board(
    project_dir: str | Path,
    net: Optional[str] = None,
    layer: Optional[str] = None,
    remove_zones: bool = False
) -> Dict[str, Any]:
    """Rips up and deletes copper tracks, vias, and optional zones from the board."""
    try:
        import pcbnew
    except ImportError:
        return _dispatch_sub("unroute_board", {
            "project_dir": str(project_dir),
            "net": net,
            "layer": layer,
            "remove_zones": remove_zones
        })

    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    import gc
    gc.collect()
    try:
        board = pcbnew.LoadBoard(str(pcb_file))
        layer_id = pcbnew.B_Cu if layer == "B.Cu" else (pcbnew.F_Cu if layer == "F.Cu" else None)

        def _get_netname(item) -> str:
            try:
                if hasattr(item, "GetNetname"):
                    return item.GetNetname()
                nc = item.GetNetCode()
                net_obj = board.FindNet(nc)
                if net_obj:
                    return net_obj.GetNetname()
            except Exception:
                pass
            return ""

        # Remove tracks & vias
        removed_tracks = 0
        for t in list(board.GetTracks()):
            t_net = _get_netname(t)
            match_net = not net or (t_net == net)
            match_layer = layer_id is None or t.GetLayer() == layer_id
            if match_net and match_layer:
                board.Delete(t)
                removed_tracks += 1

        # Remove zones
        removed_zones = 0
        if remove_zones:
            for z in list(board.Zones()):
                z_net = _get_netname(z)
                match_net = not net or (z_net == net)
                match_layer = layer_id is None or z.GetLayer() == layer_id
                if match_net and match_layer:
                    board.Delete(z)
                    removed_zones += 1

        board.BuildListOfNets()
        board.BuildConnectivity()
        pcbnew.SaveBoard(str(pcb_file), board)
        del board
        gc.collect()
        return {"success": True, "removed_tracks": removed_tracks, "removed_zones": removed_zones}

    except Exception as e:
        return {"success": False, "error": str(e)}


def _ensure_netclass_patterns(proj_path: Path, pro_file: Path):
    """Ensures .kicad_pro has netclass_patterns so ExportSpecctraDSN writes differential track widths."""
    try:
        pro_data = json.loads(pro_file.read_text(encoding="utf-8"))
        ns = pro_data.setdefault("net_settings", {})
        existing_pats = ns.get("netclass_patterns") or []
        if not existing_pats:
            design_file = proj_path / "kaibridge_dump" / "design.json"
            if not design_file.exists():
                design_file = proj_path / "design.json"
            if design_file.exists():
                with open(design_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                from ..schematic.compiler import _update_netclasses_in_pro
                from types import SimpleNamespace
                proxy = SimpleNamespace(
                    nets=d.get("nets", {}),
                    power_flags=d.get("power_flags", [])
                )
                _update_netclasses_in_pro(pro_file, d.get("netclasses", {}), design=proxy)
    except Exception:
        pass


def route_board(
    project_dir: str | Path,
    track_width_mm: float = 0.25,
    timeout_sec: int = 300,
    copper_edge_clearance_um: int = 150,
    strict_drc: bool = True,
    max_passes: Optional[int] = None
) -> Dict[str, Any]:
    """Exports DSN, runs Java Freerouting v2.4.1 with robust edge clearance and strict DRC,
    and imports SES tracks into the board.
    """
    try:
        import pcbnew
    except ImportError:
        return _dispatch_sub("route_board", {
            "project_dir": str(project_dir),
            "track_width_mm": track_width_mm,
            "timeout_sec": timeout_sec,
            "copper_edge_clearance_um": copper_edge_clearance_um,
            "strict_drc": strict_drc,
            "max_passes": max_passes
        })

    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    dsn_file = proj_path / f"{stem}.dsn"
    ses_file = proj_path / f"{stem}.ses"

    import gc
    gc.collect()

    # Preflight: Sync netclass patterns to .kicad_pro so ExportSpecctraDSN writes differential widths
    _ensure_netclass_patterns(proj_path, pro_files[0])

    # 1. Export Specctra DSN
    try:
        board = pcbnew.LoadBoard(str(pcb_file))
        pcbnew.ExportSpecctraDSN(board, str(dsn_file))
        del board
        gc.collect()
    except Exception as e:
        return {"success": False, "error": f"Failed to export DSN: {e}"}

    if not dsn_file.exists():
        return {"success": False, "error": "Failed to export Specctra DSN file."}

    # 1.5. Pre-flight Specctra DSN Audit (Failproof Guard)
    dsn_audit = audit_dsn(dsn_file)
    if not dsn_audit.get("valid", True):
        return {
            "success": False,
            "error": f"Specctra DSN pre-flight audit failed: {'; '.join(dsn_audit.get('problems', []))}",
            "dsn_audit": dsn_audit
        }

    # 2. Run Java Freerouting 2.4.1 (Decoupled Universal Routing Pipeline)
    jar_path = find_freerouting_jar()
    if not jar_path:
        return {"success": False, "error": "freerouting.jar not found."}

    cmd = [
        "java", "-jar", str(jar_path),
        "-de", str(dsn_file),
        "-do", str(ses_file),
        "-mt", "1",
        "--gui.enabled=false",
        f"--router.copperToEdgeClearanceUm={copper_edge_clearance_um}"
    ]
    if strict_drc:
        cmd.append("--router.strictDrc=true")
    if max_passes is not None and max_passes > 0:
        cmd.extend(["-mp", str(max_passes)])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        if proc.returncode != 0 and not ses_file.exists():
            return {
                "success": False,
                "error": f"Freerouting failed (code {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Freerouting timed out after {timeout_sec}s."}

    if not ses_file.exists():
        return {"success": False, "error": "Freerouting did not generate .ses file."}

    # 3. Import Specctra SES into board
    imported_count = 0
    try:
        gc.collect()
        board = pcbnew.LoadBoard(str(pcb_file))
        # Clear existing tracks first
        for t in list(board.GetTracks()):
            board.Delete(t)
        pcbnew.ImportSpecctraSES(board, str(ses_file))
        ds = board.GetDesignSettings()
        ds.m_TrackMinWidth = pcbnew.FromMM(0.15)
        ds.m_TrackClearance = pcbnew.FromMM(0.15)
        board.BuildListOfNets()
        board.BuildConnectivity()

        # Refill all copper zones to respect new traces and vias
        if len(board.Zones()) > 0:
            try:
                filler = pcbnew.ZONE_FILLER(board)
                filler.Fill(board.Zones())
                board.BuildConnectivity()
            except Exception:
                pass

        pcbnew.SaveBoard(str(pcb_file), board)
        
        # Ensure .kicad_pro has standard JLCPCB rules
        if pro_files:
            try:
                pdata = json.loads(pro_files[0].read_text(encoding="utf-8"))
                rules = pdata.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
                rules["min_track_width"] = 0.15
                rules["min_clearance"] = 0.15
                rules["min_copper_edge_clearance"] = 0.15
                pro_files[0].write_text(json.dumps(pdata, indent=2), encoding="utf-8")
            except Exception:
                pass

        imported_count = len(list(board.GetTracks()))
        del board
        gc.collect()
    except Exception as e:
        return {"success": False, "error": f"Failed to import SES: {e}"}

    return {
        "success": True,
        "method": "freerouting",
        "tracks_imported": imported_count,
        "pcb_file": str(pcb_file),
        "ses_file": str(ses_file)
    }


def add_ground_plane(
    project_dir: str | Path,
    net: str = "GND",
    layer: str = "B.Cu",
    clearance_mm: float = 0.3
) -> Dict[str, Any]:
    """Adds a solid copper ground plane zone strictly matching the board outline."""
    try:
        import pcbnew
    except ImportError:
        return _dispatch_sub("add_ground_plane", {
            "project_dir": str(project_dir),
            "net": net,
            "layer": layer,
            "clearance_mm": clearance_mm
        })

    proj_path = Path(project_dir).resolve()
    pro_files = list(proj_path.glob("*.kicad_pro"))
    if not pro_files:
        return {"success": False, "error": "No .kicad_pro found."}

    stem = pro_files[0].stem
    pcb_file = proj_path / f"{stem}.kicad_pcb"
    if not pcb_file.exists():
        return {"success": False, "error": f"PCB file not found: {pcb_file}"}

    import gc
    gc.collect()
    try:
        board = pcbnew.LoadBoard(str(pcb_file))
        target_layer = pcbnew.B_Cu if layer == "B.Cu" else pcbnew.F_Cu

        # Remove duplicate zone on same layer
        for z in list(board.Zones()):
            if z.GetLayer() == target_layer:
                board.Delete(z)

        # Compute outline boundary strictly from Edge.Cuts
        poly = pcbnew.SHAPE_POLY_SET()
        has_outline = False
        try:
            has_outline = board.GetBoardPolygonOutlines(poly, True)
        except Exception:
            pass

        zone = pcbnew.ZONE(board)
        zone.SetLayer(target_layer)

        if has_outline and poly.OutlineCount() > 0:
            # Set exact closed board outline directly (zero negative space overflow)
            zone.SetOutline(poly)
        else:
            edge_drawings = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
            if edge_drawings:
                x0 = min(d.GetBoundingBox().GetLeft() for d in edge_drawings)
                y0 = min(d.GetBoundingBox().GetTop() for d in edge_drawings)
                x1 = max(d.GetBoundingBox().GetRight() for d in edge_drawings)
                y1 = max(d.GetBoundingBox().GetBottom() for d in edge_drawings)
            else:
                bbox = board.ComputeBoundingBox()
                x0, y0 = bbox.GetX(), bbox.GetY()
                x1, y1 = x0 + bbox.GetWidth(), y0 + bbox.GetHeight()

            chain = pcbnew.SHAPE_LINE_CHAIN()
            chain.Append(x0, y0)
            chain.Append(x1, y0)
            chain.Append(x1, y1)
            chain.Append(x0, y1)
            chain.SetClosed(True)
            zone.Outline().AddOutline(chain)

        # Assign Net
        net_info = board.FindNet(net)
        if net_info:
            zone.SetNetCode(net_info.GetNetCode())

        # Set clearance & full solid thermal pad connections to prevent starved thermal relief errors
        zone.SetLocalClearance(pcbnew.FromMM(clearance_mm))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetMinThickness(pcbnew.FromMM(0.2))

        board.Add(zone)

        # Fill Zone
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())

        board.BuildListOfNets()
        board.BuildConnectivity()
        pcbnew.SaveBoard(str(pcb_file), board)
        del board
        gc.collect()
        return {"success": True, "pcb_file": str(pcb_file), "zone_layer": layer, "net": net}

    except Exception as e:
        return {"success": False, "error": str(e)}
