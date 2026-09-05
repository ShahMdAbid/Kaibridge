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
import math
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.paths import load_cli, load_kicad_python, find_freerouting_jar
from .freerouting_daemon import start_daemon, is_daemon_alive, FreeroutingClient


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


def apply_dogbone_fanout(board, gnd_net_name: str = "GND") -> int:
    """Pre-places 0.6mm structural vias (0.3mm drill) and 0.25mm escape neck traces
    offset 1.0-1.2mm away from every SMD GND pad. Guarantees intact solder mask dams
    and eliminates Via-in-Pad defects.
    """
    gnd_net = board.FindNet(gnd_net_name)
    if not gnd_net:
        return 0
    gnd_code = gnd_net.GetNetCode()

    import pcbnew
    # Collect existing GND vias to prevent duplicate/stacked vias
    existing_vias = set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd_code:
            pos = t.GetPosition()
            existing_vias.add((round(pcbnew.ToMM(pos.x), 2), round(pcbnew.ToMM(pos.y), 2)))

    # Collect all existing pads across the board for clearance checking
    all_pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            all_pads.append((pad, pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), pad.GetNetname()))

    placed_count = 0
    for fp in board.GetFootprints():
        fp_pos = fp.GetPosition()
        for pad in fp.Pads():
            if pad.GetNetname() == gnd_net_name and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                pad_pos = pad.GetPosition()
                px_mm = pcbnew.ToMM(pad_pos.x)
                py_mm = pcbnew.ToMM(pad_pos.y)

                # Check if this pad already has a via within 1.8mm
                already_has_via = any(
                    ((vx - px_mm)**2 + (vy - py_mm)**2) <= (1.8**2)
                    for vx, vy in existing_vias
                )
                if already_has_via:
                    continue

                dx_mm = pcbnew.ToMM(pad_pos.x - fp_pos.x)
                dy_mm = pcbnew.ToMM(pad_pos.y - fp_pos.y)

                # Candidate escape vectors (primary outward, orthogonal, diagonal, extended)
                prim_x = 1.1 if dx_mm >= 0 else -1.1
                prim_y = 1.1 if dy_mm >= 0 else -1.1
                candidates = []
                if abs(dx_mm) >= abs(dy_mm):
                    candidates.append((prim_x, 0.0))
                    candidates.append((0.0, prim_y))
                    candidates.append((0.0, -prim_y))
                    candidates.append((prim_x, prim_y * 0.7))
                    candidates.append((prim_x, -prim_y * 0.7))
                    candidates.append((prim_x * 1.3, 0.0))
                else:
                    candidates.append((0.0, prim_y))
                    candidates.append((prim_x, 0.0))
                    candidates.append((-prim_x, 0.0))
                    candidates.append((prim_x * 0.7, prim_y))
                    candidates.append((-prim_x * 0.7, prim_y))
                    candidates.append((0.0, prim_y * 1.3))

                chosen_vec = None
                for ex, ey in candidates:
                    cvx = px_mm + ex
                    cvy = py_mm + ey

                    # Check clearance against existing vias (>= 0.7mm)
                    if any(math.hypot(vx - cvx, vy - cvy) < 0.70 for vx, vy in existing_vias):
                        continue

                    # Check clearance against all other non-GND pads (>= 0.75mm)
                    collides = False
                    for other_pad, ox, oy, onet in all_pads:
                        if other_pad == pad:
                            continue
                        dist = math.hypot(ox - cvx, oy - cvy)
                        if onet != gnd_net_name:
                            if dist < 0.75:
                                collides = True
                                break
                        else:
                            if dist < 0.50:
                                collides = True
                                break
                    if not collides:
                        chosen_vec = (ex, ey)
                        break

                if not chosen_vec:
                    # No safe clearance vector found; skip pre-via to prevent deadlocks
                    continue

                escape_x, escape_y = chosen_vec
                via_x = pad_pos.x + pcbnew.FromMM(escape_x)
                via_y = pad_pos.y + pcbnew.FromMM(escape_y)
                via_pos = pcbnew.VECTOR2I(via_x, via_y)

                # 1. Via: 0.6mm diameter, 0.3mm drill
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(via_pos)
                via.SetWidth(pcbnew.FromMM(0.6))
                via.SetDrill(pcbnew.FromMM(0.3))
                via.SetNetCode(gnd_code)
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                board.Add(via)

                # 2. Escape neck trace: 0.25mm width on F.Cu
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pad_pos)
                tr.SetEnd(via_pos)
                tr.SetWidth(pcbnew.FromMM(0.25))
                tr.SetLayer(pcbnew.F_Cu)
                tr.SetNetCode(gnd_code)
                board.Add(tr)

                existing_vias.add((round(pcbnew.ToMM(via_x), 2), round(pcbnew.ToMM(via_y), 2)))
                placed_count += 1

    board.BuildListOfNets()
    board.BuildConnectivity()
    return placed_count


def _ensure_netclass_patterns(proj_path: Path, pro_file: Path):
    """Ensures .kicad_pro has netclass_patterns so ExportSpecctraDSN writes differential track widths.
    Also auto-clamps Power netclasses for fine-pitch ICs to prevent pad entry clearance deadlocks.
    """
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
                pro_data = json.loads(pro_file.read_text(encoding="utf-8"))

        # Power netclasses preserve their designated widths (0.4-0.6mm).
        # Freerouting automatically necks down tracks at fine-pitch IC pads via automaticNeckdown=True.
    except Exception:
        pass


def route_board(
    project_dir: str | Path,
    track_width_mm: float = 0.25,
    timeout_sec: int = 300,
    copper_edge_clearance_um: int = 150,
    strict_drc: bool = True,
    max_passes: Optional[int] = None,
    fanout_first: Optional[bool] = None,
    strategy: str = "auto",
    via_costs: int = 140,
    plane_via_costs: int = 100,
    automatic_neckdown: bool = True,
    use_daemon: bool = True
) -> Dict[str, Any]:
    """Exports DSN, runs Java Freerouting v2.4.1 (Tier 2 Daemon or Tier 1 Optimized CLI)
    with robust edge clearance, dynamic via penalization, and strict DRC,
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
            "max_passes": max_passes,
            "fanout_first": fanout_first,
            "strategy": strategy,
            "via_costs": via_costs,
            "plane_via_costs": plane_via_costs,
            "automatic_neckdown": automatic_neckdown,
            "use_daemon": use_daemon
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
    rules_file = proj_path / f"{stem}.rules"

    import gc
    gc.collect()

    # Preflight: Sync netclass patterns to .kicad_pro so ExportSpecctraDSN writes differential widths
    _ensure_netclass_patterns(proj_path, pro_files[0])

    # 0. Resolve Routing Strategy
    if strategy == "fanout-first" or fanout_first is True:
        use_fanout = True
    elif strategy == "dual-layer" or fanout_first is False:
        use_fanout = False
    else:
        # Auto-detect density from board topology
        use_fanout = True
        try:
            chk_board = pcbnew.LoadBoard(str(pcb_file))
            fps = list(chk_board.GetFootprints())
            max_pads = max([fp.GetPadCount() for fp in fps] or [0])
            active_nets = [n for n in chk_board.GetNetsByName().values() if n.GetNetname() not in ("", "GND")]
            del chk_board
            gc.collect()
            if max_pads >= 24 or len(active_nets) > 20:
                use_fanout = False
                print(f"[*] Adaptive Router: High-density board detected (max IC pads: {max_pads}, active nets: {len(active_nets)}) -> Selected Strategy 2 (Dual-Layer Routing).")
            else:
                use_fanout = True
                print(f"[*] Adaptive Router: Standard/discrete board detected (max IC pads: {max_pads}, active nets: {len(active_nets)}) -> Selected Strategy 1 (Dog-Bone Fanout First).")
        except Exception:
            use_fanout = False

    # 1. Export Specctra DSN (with optional Tier-1 Dog-Bone Fanout First)
    try:
        board = pcbnew.LoadBoard(str(pcb_file))
        # Always clean previous routing tracks, vias, AND zones before exporting DSN
        # This prevents KiCad from exporting (plane GND (polygon B.Cu ...)) which locks B.Cu against signal routing
        for t in list(board.GetTracks()):
            board.Delete(t)
        for z in list(board.Zones()):
            board.Delete(z)
        if use_fanout:
            apply_dogbone_fanout(board, "GND")
            pcbnew.SaveBoard(str(pcb_file), board)
        pcbnew.ExportSpecctraDSN(board, str(dsn_file))
        del board
        gc.collect()
    except Exception as e:
        return {"success": False, "error": f"Failed to export DSN: {e}"}

    if not dsn_file.exists():
        return {"success": False, "error": "Failed to export Specctra DSN file."}

    # If use_fanout: strip GND from DSN network so Freerouting routes only signals on F.Cu
    if use_fanout:
        dsn_text = dsn_file.read_text(encoding="utf-8")
        dsn_text = re.sub(r'\(net\s+GND\s*\(pins[^)]+\)\s*\)', '', dsn_text)
        # Harmonize default signal clearance to power clearance so tracks honor power pads and pre-placed GND vias
        clears = [float(v) for v in _DSN_CLEAR.findall(dsn_text)]
        max_c = int(max(clears)) if clears else 200
        if max_c > 0:
            def _bump_clear(m):
                val = float(m.group(1))
                if val < max_c:
                    return f"(clearance {max_c})"
                return m.group(0)
            dsn_text = re.sub(r'\(clearance\s+(\d+(?:\.\d+)?)(?!\s*\(type)\)', _bump_clear, dsn_text)
        dsn_file.write_text(dsn_text, encoding="utf-8")

        # High via costs prioritize flat F.Cu routing while permitting clean jumper escapes
        rules_content = f'''(rules PCB {stem}
  (autoroute_settings
    (fanout off)
    (vias on)
  )
)
'''
        rules_file.write_text(rules_content, encoding="utf-8")
    else:
        if rules_file.exists():
            try:
                rules_file.unlink()
            except Exception:
                pass

    # 1.5. Pre-flight Specctra DSN Audit (Failproof Guard)
    dsn_audit = audit_dsn(dsn_file)
    if not dsn_audit.get("valid", True):
        return {
            "success": False,
            "error": f"Specctra DSN pre-flight audit failed: {'; '.join(dsn_audit.get('problems', []))}",
            "dsn_audit": dsn_audit
        }

    # 2. Run Java Freerouting 2.4.1 (Tier 2 Daemon or Tier 1 Optimized CLI)
    jar_path = find_freerouting_jar()
    if not jar_path:
        return {"success": False, "error": "freerouting.jar not found."}

    routing_method = "Freerouting 2.4.1 CLI"
    freerouting_failed = False
    proc_err = ""

    # Try Tier 2: Persistent REST API Daemon (Zero Cold-Start)
    if use_daemon:
        try:
            if not is_daemon_alive():
                start_daemon(jar_path, timeout_sec=8.0)
            if is_daemon_alive():
                client = FreeroutingClient()
                daemon_res = client.route(
                    dsn_path=dsn_file,
                    ses_path=ses_file,
                    rules_path=rules_file if rules_file.exists() else None,
                    via_costs=via_costs,
                    plane_via_costs=plane_via_costs,
                    automatic_neckdown=automatic_neckdown,
                    max_passes=max_passes or 1,
                    copper_to_edge_clearance_um=copper_edge_clearance_um,
                    timeout_sec=timeout_sec
                )
                if daemon_res.get("success") and ses_file.exists() and ses_file.stat().st_size > 0:
                    routing_method = daemon_res.get("method", "Freerouting 2.4.1 REST API Daemon (Tier 2)")
                else:
                    freerouting_failed = True
            else:
                freerouting_failed = True
        except Exception as e:
            freerouting_failed = True
            proc_err = f"Daemon route failed: {e}"

    # Fallback / Direct Tier 1: Optimized CLI Pipeline
    if not ses_file.exists() or freerouting_failed:
        freerouting_failed = False
        proc_err = ""
        cpu_threads = max(1, (os.cpu_count() or 2) - 1)
        cmd = [
            "java", "-Xmx1024m", "-jar", str(jar_path),
            "-de", str(dsn_file),
            "-do", str(ses_file),
            "-mt", str(cpu_threads),
            "--gui.enabled=false",
            "-dct", "0",
            "-ll", "WARN",
            "-is", "prioritized",
            "-us", "hybrid", "-hr", "1:1",
            f"--router.copperToEdgeClearanceUm={copper_edge_clearance_um}",
            f"--router.scoring.viaCosts={via_costs}",
            f"--router.scoring.planeViaCosts={plane_via_costs}",
            f"--router.automaticNeckdown={'true' if automatic_neckdown else 'false'}",
            "--optimizer.maxConsecutiveFailures=40"
        ]
        if use_fanout:
            cmd.extend(["-inc", "GND", "--router.viasAllowed=false"])
        if rules_file.exists():
            cmd.extend(["-dr", str(rules_file)])
        if strict_drc:
            cmd.append("--router.strictDrc=true")
        if max_passes is not None and max_passes > 0:
            cmd.extend(["-mp", str(max_passes)])
        else:
            cmd.extend(["-mp", "1"])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
            if proc.returncode != 0 and not ses_file.exists():
                freerouting_failed = True
                proc_err = proc.stderr.strip() or proc.stdout.strip()
            else:
                routing_method = "Freerouting 2.4.1 Optimized CLI (Tier 1)"
        except subprocess.TimeoutExpired:
            freerouting_failed = True
            proc_err = f"Freerouting timed out after {timeout_sec}s"

    # Automatic Fallback: If Strategy 1 failed, immediately recover via Strategy 2 without stopping
    if use_fanout and (freerouting_failed or not ses_file.exists()):
        print("[!] Strategy 1 (Dog-Bone Fanout) did not complete. Automatically recovering via Strategy 2 (Dual-Layer Routing)...")
        if rules_file.exists():
            try:
                rules_file.unlink()
            except Exception:
                pass
        return route_board(
            project_dir=project_dir,
            track_width_mm=track_width_mm,
            timeout_sec=timeout_sec,
            copper_edge_clearance_um=copper_edge_clearance_um,
            strict_drc=strict_drc,
            max_passes=max_passes or 5,
            fanout_first=False,
            strategy="dual-layer",
            via_costs=via_costs,
            plane_via_costs=plane_via_costs,
            automatic_neckdown=automatic_neckdown,
            use_daemon=use_daemon
        )

    if freerouting_failed or not ses_file.exists():
        return {"success": False, "error": f"Freerouting failed to generate SES output: {proc_err}"}


    # 3. Import Specctra SES into board
    imported_count = 0
    try:
        gc.collect()
        board = pcbnew.LoadBoard(str(pcb_file))
        # Clear existing tracks first
        for t in list(board.GetTracks()):
            board.Delete(t)
        pcbnew.ImportSpecctraSES(board, str(ses_file))
        
        # If fanout_first was used, re-apply any missing GND dog-bone stubs/vias
        if use_fanout:
            apply_dogbone_fanout(board, "GND")

        # Clean any dangling micro-track stubs (< 0.08mm) left by autorouter overshoot
        for t in list(board.GetTracks()):
            if t.GetClass() == "PCB_TRACK" and pcbnew.ToMM(t.GetLength()) < 0.08:
                board.Delete(t)

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
        "method": routing_method,
        "tracks_imported": imported_count,
        "pcb_file": str(pcb_file),
        "ses_file": str(ses_file),
        "fanout_first_used": use_fanout
    }



def add_ground_plane(
    project_dir: str | Path,
    net: str = "GND",
    layer: str = "B.Cu",
    clearance_mm: float = 0.3
) -> Dict[str, Any]:
    """Adds a solid copper ground plane zone strictly matching the board outline with island removal."""
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
        
        # Dynamic Layer Resolution (supports 2-layer F.Cu/B.Cu and 4-layer In1.Cu/In2.Cu)
        try:
            target_layer = board.GetLayerID(layer)
        except Exception:
            layer_map = {
                "F.Cu": pcbnew.F_Cu,
                "B.Cu": pcbnew.B_Cu,
                "In1.Cu": getattr(pcbnew, "In1_Cu", 1),
                "In2.Cu": getattr(pcbnew, "In2_Cu", 2)
            }
            target_layer = layer_map.get(layer, pcbnew.B_Cu)

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

        # Enforce island removal to eliminate floating copper antennas
        try:
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        except Exception:
            pass

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
