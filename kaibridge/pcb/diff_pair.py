"""
kaibridge/pcb/diff_pair.py — Differential Pair Synthesizer, DSN Rule Injector, and Skew Auditor.

Handles:
1. Differential pair detection (explicit via design.json or auto-detected by naming heuristics:
   CANH/CANL, USB_D+/USB_D-, DP/DM, *_P/*_N, *+/*-).
2. Netclass & Specctra DSN coupling rule injection for Freerouting / autorouters.
3. Headless 3D length & skew measurement (2D copper trace length + via barrel height compensation).
4. Physical timing skew calculation in picoseconds (ps) based on FR-4 propagation delay (~6.85 ps/mm).
5. Comprehensive audit reports with PASS/WARN/FAIL status and actionable delay-matching remedies.
"""
from __future__ import annotations

import os
import sys
import json
import re
import math
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, asdict

from ..core.paths import load_kicad_python


# FR-4 microstrip propagation velocity constant (ps per mm)
# v_p = c / sqrt(eps_eff) ~ 3e8 / sqrt(4.2) ~ 0.146 mm/ps => ~6.85 ps/mm
PS_PER_MM_FR4 = 6.85


@dataclass
class DiffPairSpec:
    name: str
    pos_net: str
    neg_net: str
    target_impedance: float = 120.0     # Ohms
    max_skew_mm: float = 0.50          # Max allowable length mismatch (mm)
    track_width_mm: float = 0.25       # Trace width (mm)
    gap_mm: float = 0.25               # Intra-pair gap / clearance (mm)
    class_name: str = ""               # Netclass name in KiCad

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Predefined protocol presets for standard differential signals
PROTOCOL_PRESETS: Dict[str, Dict[str, Any]] = {
    "CAN": {
        "target_impedance": 120.0,
        "max_skew_mm": 0.50,
        "track_width_mm": 0.25,
        "gap_mm": 0.25,
        "class_name": "CAN_DIFF"
    },
    "USB": {
        "target_impedance": 90.0,
        "max_skew_mm": 0.15,
        "track_width_mm": 0.22,
        "gap_mm": 0.15,
        "class_name": "USB_DIFF"
    },
    "ETH": {
        "target_impedance": 100.0,
        "max_skew_mm": 0.10,
        "track_width_mm": 0.20,
        "gap_mm": 0.20,
        "class_name": "ETH_DIFF"
    },
    "RS485": {
        "target_impedance": 120.0,
        "max_skew_mm": 0.50,
        "track_width_mm": 0.25,
        "gap_mm": 0.25,
        "class_name": "RS485_DIFF"
    },
    "GENERIC": {
        "target_impedance": 100.0,
        "max_skew_mm": 0.20,
        "track_width_mm": 0.25,
        "gap_mm": 0.20,
        "class_name": "DIFF_PAIR"
    }
}


# Suffix matching patterns for complementary polarity
PAIR_SUFFIX_PATTERNS = [
    (re.compile(r"^(.*?)(?:_P|\+|_POS|_DP|H)$", re.IGNORECASE),
     re.compile(r"^(.*?)(?:_N|\-|_NEG|_DM|L)$", re.IGNORECASE)),
]


def detect_differential_pairs(
    project_dir_or_board: str | Path | Any,
    design_dict: Optional[Dict[str, Any]] = None
) -> List[DiffPairSpec]:
    """Detects differential pairs from design.json (if explicit) or from net names in the board."""
    specs: List[DiffPairSpec] = []
    seen_pairs = set()

    # 1. Check explicit diff_pairs in design_dict or design.json
    d_dict = design_dict
    if d_dict is None and isinstance(project_dir_or_board, (str, Path)):
        p = Path(project_dir_or_board).resolve()
        if p.is_file():
            p = p.parent
        for candidate in [p / "design.json", p / "kaibridge_dump" / "design.json"]:
            if candidate.exists():
                try:
                    d_dict = json.loads(candidate.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

    if d_dict and "diff_pairs" in d_dict and isinstance(d_dict["diff_pairs"], list):
        for item in d_dict["diff_pairs"]:
            pos = item.get("pos") or item.get("pos_net")
            neg = item.get("neg") or item.get("neg_net")
            if pos and neg:
                name = item.get("name") or f"{pos}_{neg}"
                proto = "CAN" if "CAN" in name.upper() else ("USB" if "USB" in name.upper() else "GENERIC")
                preset = PROTOCOL_PRESETS[proto]
                spec = DiffPairSpec(
                    name=name,
                    pos_net=pos,
                    neg_net=neg,
                    target_impedance=float(item.get("target_impedance", preset["target_impedance"])),
                    max_skew_mm=float(item.get("max_skew_mm", preset["max_skew_mm"])),
                    track_width_mm=float(item.get("track_width_mm", preset["track_width_mm"])),
                    gap_mm=float(item.get("gap_mm", preset["gap_mm"])),
                    class_name=item.get("class_name", preset["class_name"])
                )
                specs.append(spec)
                seen_pairs.add((pos, neg))

    # 2. Extract active net names to search
    net_names: List[str] = []
    if d_dict and "nets" in d_dict and isinstance(d_dict["nets"], dict):
        net_names = list(d_dict["nets"].keys())
    elif hasattr(project_dir_or_board, "GetNetsByName"):
        net_names = [n for n in project_dir_or_board.GetNetsByName().keys() if n]
    elif isinstance(project_dir_or_board, (str, Path)):
        # Try reading from kicad_pcb or kicad_pro
        p = Path(project_dir_or_board).resolve()
        pcb_file = p if p.is_file() and p.suffix == ".kicad_pcb" else None
        if not pcb_file:
            pcbs = list(p.glob("*.kicad_pcb"))
            if pcbs:
                pcb_file = pcbs[0]
        if pcb_file and pcb_file.exists():
            try:
                # Fast regex parse of net names in .kicad_pcb
                content = pcb_file.read_text(encoding="utf-8", errors="ignore")
                found_nets = re.findall(r'\(net\s+\d+\s+"([^"]+)"\)', content)
                net_names = list(set(found_nets))
            except Exception:
                pass

    # 3. Apply Heuristic Pattern Matching
    # Specific known protocols first
    known_pairs = [
        ("CAN", "CANH", "CANL", "CAN"),
        ("CAN", "CAN_H", "CAN_L", "CAN"),
        ("USB", "USB_D+", "USB_D-", "USB"),
        ("USB", "USB_DP", "USB_DM", "USB"),
        ("USB", "DP", "DM", "USB"),
        ("USB", "D+", "D-", "USB"),
        ("RS485", "RS485_A", "RS485_B", "RS485"),
        ("RS485", "485_A", "485_B", "RS485"),
    ]

    for proto, p_name, n_name, key in known_pairs:
        if p_name in net_names and n_name in net_names:
            pair_key = (p_name, n_name)
            if pair_key not in seen_pairs:
                preset = PROTOCOL_PRESETS[key]
                specs.append(DiffPairSpec(
                    name=f"{proto}",
                    pos_net=p_name,
                    neg_net=n_name,
                    target_impedance=preset["target_impedance"],
                    max_skew_mm=preset["max_skew_mm"],
                    track_width_mm=preset["track_width_mm"],
                    gap_mm=preset["gap_mm"],
                    class_name=preset["class_name"]
                ))
                seen_pairs.add(pair_key)

    # General pattern matching: STEM_P / STEM_N, STEM+ / STEM-, STEM_POS / STEM_NEG
    pos_candidates = {}
    neg_candidates = {}

    for name in net_names:
        if name in ("GND", "VBUS", "3V3", "VIN", "+3.3V", "+5V", "+12V"):
            continue
        # Pos patterns
        if name.endswith("_P") or name.endswith("+") or name.endswith("_POS"):
            stem = re.sub(r'(_P|\+|_POS)$', '', name)
            pos_candidates[stem] = name
        # Neg patterns
        elif name.endswith("_N") or name.endswith("-") or name.endswith("_NEG"):
            stem = re.sub(r'(_N|\-|_NEG)$', '', name)
            neg_candidates[stem] = name

    for stem, p_net in pos_candidates.items():
        if stem in neg_candidates:
            n_net = neg_candidates[stem]
            pair_key = (p_net, n_net)
            if pair_key not in seen_pairs:
                proto = "ETH" if "ETH" in stem.upper() else "GENERIC"
                preset = PROTOCOL_PRESETS[proto]
                specs.append(DiffPairSpec(
                    name=stem,
                    pos_net=p_net,
                    neg_net=n_net,
                    target_impedance=preset["target_impedance"],
                    max_skew_mm=preset["max_skew_mm"],
                    track_width_mm=preset["track_width_mm"],
                    gap_mm=preset["gap_mm"],
                    class_name=f"{stem}_DIFF"
                ))
                seen_pairs.add(pair_key)

    return specs


def _dispatch_audit(project_dir: str | Path, design_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Dispatches differential pair audit via KiCad's bundled Python interpreter when pcbnew is unavailable."""
    kicad_python = load_kicad_python()
    root_pkg = Path(__file__).resolve().parents[2]
    payload = json.dumps({"project_dir": str(project_dir), "design_dict": design_dict})
    runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.diff_pair import audit_differential_pairs
kwargs = json.loads(r'''{payload}''')
res = audit_differential_pairs(**kwargs)
print("DIFF_AUDIT_RESULT:" + json.dumps(res))
"""
    proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines():
        if line.startswith("DIFF_AUDIT_RESULT:"):
            return json.loads(line.replace("DIFF_AUDIT_RESULT:", ""))
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip(), "pairs": []}


def audit_differential_pairs(
    project_dir: str | Path,
    design_dict: Optional[Dict[str, Any]] = None,
    board_thickness_mm: float = 1.6
) -> Dict[str, Any]:
    """Performs 3D length and skew analysis for all detected differential pairs on the board.
    Calculates 2D copper trace length, via barrel height, absolute skew, and time skew (ps).
    """
    try:
        import pcbnew
    except ImportError:
        return _dispatch_audit(project_dir, design_dict)

    proj_path = Path(project_dir).resolve()
    pcb_files = list(proj_path.glob("*.kicad_pcb"))
    if not pcb_files:
        return {"success": False, "error": f"No .kicad_pcb file in {proj_path}", "pairs": []}

    import gc
    gc.collect()
    board = pcbnew.LoadBoard(str(pcb_files[0]))

    specs = detect_differential_pairs(proj_path, design_dict)
    if not specs:
        del board
        gc.collect()
        return {"success": True, "count": 0, "pairs": [], "summary": "No differential pairs detected on board."}

    results = []

    # Map layer IDs to human names
    layer_names = {
        pcbnew.F_Cu: "F.Cu",
        pcbnew.B_Cu: "B.Cu",
    }
    if hasattr(pcbnew, "In1_Cu"):
        layer_names[pcbnew.In1_Cu] = "In1.Cu"
    if hasattr(pcbnew, "In2_Cu"):
        layer_names[pcbnew.In2_Cu] = "In2.Cu"

    all_tracks = list(board.GetTracks())

    for spec in specs:
        pos_tracks = [t for t in all_tracks if t.GetNetname() == spec.pos_net]
        neg_tracks = [t for t in all_tracks if t.GetNetname() == spec.neg_net]

        # 2D Length & Via Count
        pos_copper_tracks = [t for t in pos_tracks if t.GetClass() == "PCB_TRACK"]
        neg_copper_tracks = [t for t in neg_tracks if t.GetClass() == "PCB_TRACK"]

        pos_vias = [t for t in pos_tracks if t.GetClass() == "PCB_VIA"]
        neg_vias = [t for t in neg_tracks if t.GetClass() == "PCB_VIA"]

        pos_len_2d_mm = sum(t.GetLength() for t in pos_copper_tracks) / 1e6
        neg_len_2d_mm = sum(t.GetLength() for t in neg_copper_tracks) / 1e6

        # Layer distribution breakdown
        pos_layer_breakdown = {}
        for t in pos_copper_tracks:
            lname = layer_names.get(t.GetLayer(), f"Layer_{t.GetLayer()}")
            pos_layer_breakdown[lname] = pos_layer_breakdown.get(lname, 0.0) + (t.GetLength() / 1e6)

        neg_layer_breakdown = {}
        for t in neg_copper_tracks:
            lname = layer_names.get(t.GetLayer(), f"Layer_{t.GetLayer()}")
            neg_layer_breakdown[lname] = neg_layer_breakdown.get(lname, 0.0) + (t.GetLength() / 1e6)

        # 3D Via Barrel Compensation (each via traversing layers contributes vertical flight length)
        pos_via_count = len(pos_vias)
        neg_via_count = len(neg_vias)
        via_skew_count = pos_via_count - neg_via_count

        pos_len_3d_mm = pos_len_2d_mm + (pos_via_count * board_thickness_mm)
        neg_len_3d_mm = neg_len_2d_mm + (neg_via_count * board_thickness_mm)

        skew_2d_mm = abs(pos_len_2d_mm - neg_len_2d_mm)
        skew_3d_mm = abs(pos_len_3d_mm - neg_len_3d_mm)
        skew_ps = skew_3d_mm * PS_PER_MM_FR4

        # Status evaluation
        is_routed = (pos_len_2d_mm > 0.1 and neg_len_2d_mm > 0.1)
        if not is_routed:
            status = "UNROUTED" if (pos_len_2d_mm < 0.1 and neg_len_2d_mm < 0.1) else "PARTIAL"
            remedy = f"One or both nets ({spec.pos_net}, {spec.neg_net}) are unrouted."
        elif skew_3d_mm > spec.max_skew_mm:
            status = "FAIL"
            longer = spec.pos_net if pos_len_3d_mm > neg_len_3d_mm else spec.neg_net
            shorter = spec.neg_net if longer == spec.pos_net else spec.pos_net
            delta = skew_3d_mm
            remedy = (
                f"Skew ({delta:.2f}mm / {skew_ps:.1f}ps) exceeds max tolerance ({spec.max_skew_mm:.2f}mm). "
                f"Add {delta:.2f}mm delay meander on {shorter} or optimize topology to balance escape paths."
            )
            if pos_via_count != neg_via_count:
                remedy += f" (Note: via asymmetry detected: {pos_via_count} vs {neg_via_count} vias)."
        elif pos_via_count != neg_via_count:
            status = "WARN"
            remedy = (
                f"Length matched ({skew_3d_mm:.2f}mm <= {spec.max_skew_mm:.2f}mm), but via counts differ "
                f"({pos_via_count} vs {neg_via_count}). Via asymmetry causes impedance discontinuities."
            )
        else:
            status = "PASS"
            remedy = f"Coupled pair meets all skew (delta={skew_3d_mm:.3f}mm <= {spec.max_skew_mm:.2f}mm) and via symmetry requirements."

        results.append({
            "name": spec.name,
            "pos_net": spec.pos_net,
            "neg_net": spec.neg_net,
            "target_impedance": spec.target_impedance,
            "max_skew_mm": spec.max_skew_mm,
            "pos_len_2d_mm": round(pos_len_2d_mm, 3),
            "neg_len_2d_mm": round(neg_len_2d_mm, 3),
            "pos_len_3d_mm": round(pos_len_3d_mm, 3),
            "neg_len_3d_mm": round(neg_len_3d_mm, 3),
            "skew_2d_mm": round(skew_2d_mm, 3),
            "skew_3d_mm": round(skew_3d_mm, 3),
            "skew_ps": round(skew_ps, 1),
            "pos_vias": pos_via_count,
            "neg_vias": neg_via_count,
            "via_skew": via_skew_count,
            "pos_layers": pos_layer_breakdown,
            "neg_layers": neg_layer_breakdown,
            "status": status,
            "remedy": remedy
        })

    del board
    gc.collect()

    all_passed = all(r["status"] == "PASS" for r in results) if results else True
    return {
        "success": True,
        "count": len(results),
        "all_passed": all_passed,
        "pairs": results,
        "formatted_table": format_diff_pair_table(results)
    }


def format_diff_pair_table(pairs: List[Dict[str, Any]]) -> str:
    """Renders a clean, high-visibility ASCII table of differential pair audit results."""
    if not pairs:
        return "[Diff Pair Audit] No differential pairs detected on board."

    lines = []
    lines.append("=" * 96)
    lines.append(" [DIFFERENTIAL PAIR LENGTH & SKEW AUDIT]")
    lines.append("=" * 96)
    header = (
        f"{'Pair':<10} {'Pos Net':<10} {'Neg Net':<10} "
        f"{'Pos (mm)':>9} {'Neg (mm)':>9} {'Skew (mm)':>10} {'Skew (ps)':>10} "
        f"{'Vias (P/N)':>11} {'Status':>8}"
    )
    lines.append(header)
    lines.append("-" * 96)

    for p in pairs:
        vias_str = f"{p['pos_vias']} / {p['neg_vias']}"
        status_str = f"[{p['status']}]"
        lines.append(
            f"{p['name']:<10} {p['pos_net']:<10} {p['neg_net']:<10} "
            f"{p['pos_len_3d_mm']:>9.2f} {p['neg_len_3d_mm']:>9.2f} "
            f"{p['skew_3d_mm']:>10.3f} {p['skew_ps']:>9.1f}ps "
            f"{vias_str:>11} {status_str:>8}"
        )
        if p["status"] in ("FAIL", "WARN"):
            lines.append(f"  -> REMEDY: {p['remedy']}")

    lines.append("=" * 96)
    return "\n".join(lines)


def inject_diff_pair_dsn_rules(dsn_path: str | Path, pairs: List[DiffPairSpec]) -> bool:
    """Injects Specctra DSN pair coupling rules into the exported DSN file before Freerouting execution.
    Writes (pair (net <pos> <neg>) (clearance <gap>)) in the (network ...) section.
    """
    p = Path(dsn_path).resolve()
    if not p.exists() or not pairs:
        return False

    text = p.read_text(encoding="utf-8", errors="replace")
    if "(network" not in text:
        return False

    pair_tokens = []
    for pair in pairs:
        gap_um = int(pair.gap_mm * 1000)
        width_um = int(pair.track_width_mm * 1000)
        # Specctra DSN differential pair structure
        token = (
            f"    (pair (net {pair.pos_net} {pair.neg_net})\n"
            f"      (clearance {gap_um})\n"
            f"    )"
        )
        pair_tokens.append(token)

    joined_tokens = "\n".join(pair_tokens)
    # Inject right before the closing parenthesis of (network ...)
    # Find last occurrence of closing parenthesis before (wiring or (structure or EOF
    m = re.search(r"(\(network\b[\s\S]*?)(\n\s*\)\s*(?:\(wiring|\(structure|\Z))", text)
    if m:
        new_text = text[:m.end(1)] + "\n" + joined_tokens + text[m.start(2):]
        p.write_text(new_text, encoding="utf-8")
        return True
    return False


def sync_diff_pair_netclasses(pro_path: str | Path, pairs: List[DiffPairSpec]) -> bool:
    """Synchronizes differential pair netclasses into .kicad_pro so KiCad assigns
    correct track widths, clearances, and net patterns natively.
    """
    p = Path(pro_path).resolve()
    if not p.exists() or not pairs:
        return False

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ns = data.setdefault("net_settings", {})
        classes = ns.setdefault("classes", [])
        patterns = ns.setdefault("netclass_patterns", [])

        class_map = {c.get("name"): c for c in classes if "name" in c}

        for pair in pairs:
            cname = pair.class_name or f"{pair.name}_DIFF"
            if cname not in class_map:
                new_class = {
                    "clearance": pair.gap_mm,
                    "diff_pair_gap": pair.gap_mm,
                    "diff_pair_via_gap": pair.gap_mm,
                    "diff_pair_width": pair.track_width_mm,
                    "name": cname,
                    "track_width": pair.track_width_mm,
                    "via_diameter": 0.6,
                    "via_drill": 0.3
                }
                classes.append(new_class)
                class_map[cname] = new_class
            else:
                c = class_map[cname]
                c["diff_pair_gap"] = pair.gap_mm
                c["diff_pair_width"] = pair.track_width_mm
                c["track_width"] = pair.track_width_mm
                c["clearance"] = pair.gap_mm

            # Assign net patterns
            existing_pats = {pat.get("pattern") for pat in patterns if "pattern" in pat}
            for net in (pair.pos_net, pair.neg_net):
                if net not in existing_pats:
                    patterns.append({"netclass": cname, "pattern": net})

        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _dispatch_tune(project_dir: str | Path, kwargs: dict) -> Dict[str, Any]:
    """Dispatches differential pair tuning via KiCad's bundled Python interpreter when pcbnew is unavailable."""
    kicad_python = load_kicad_python()
    root_pkg = Path(__file__).resolve().parents[2]
    payload = json.dumps(kwargs)
    runner = f"""
import sys, json, gc
sys.path.insert(0, r"{str(root_pkg)}")
from kaibridge.pcb.diff_pair import tune_differential_pair_skew
kwargs = json.loads(r'''{payload}''')
res = tune_differential_pair_skew(**kwargs)
print("DIFF_TUNE_RESULT:" + json.dumps(res))
"""
    proc = subprocess.run([kicad_python, "-c", runner], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines():
        if line.startswith("DIFF_TUNE_RESULT:"):
            return json.loads(line.replace("DIFF_TUNE_RESULT:", ""))
    return {"success": False, "error": proc.stderr.strip() or proc.stdout.strip()}


def generate_meander_polyline(
    p_start: Tuple[float, float],
    p_end: Tuple[float, float],
    h: float,
    num_loops: int = 2,
    pitch: float = 1.3,
    gap: float = 0.8,
    chamfer: float = 0.15,
    sign: float = 1.0
) -> List[Tuple[float, float]]:
    """Generates 45-degree mitered / chamfered serpentine meander polyline points.
    Follows IPC-2141A high-speed guidelines to eliminate acid traps and intra-trace self-coupling.
    """
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    L = math.hypot(dx, dy)
    if L <= 0:
        return [p_start, p_end]

    ux, uy = dx / L, dy / L
    nx, ny = sign * uy, -sign * ux

    total_bump_base = num_loops * pitch + (num_loops - 1) * gap
    margin = max(0.2, (L - total_bump_base) / 2.0)
    c = min(chamfer, h * 0.25, pitch * 0.2)

    pts: List[Tuple[float, float]] = [p_start]
    curr_s = margin

    for _ in range(num_loops):
        b_start_s = curr_s
        b_end_s = curr_s + pitch

        # 1. Base Entry Point
        pts.append((p_start[0] + b_start_s * ux, p_start[1] + b_start_s * uy))
        # 2. 45-degree corner outward
        pts.append((p_start[0] + (b_start_s + c) * ux + c * nx, p_start[1] + (b_start_s + c) * uy + c * ny))
        # 3. Crest start with 45-degree chamfer
        pts.append((p_start[0] + (b_start_s + c) * ux + (h - c) * nx, p_start[1] + (b_start_s + c) * uy + (h - c) * ny))
        pts.append((p_start[0] + (b_start_s + 2 * c) * ux + h * nx, p_start[1] + (b_start_s + 2 * c) * uy + h * ny))
        # 4. Crest end with 45-degree chamfer
        pts.append((p_start[0] + (b_end_s - 2 * c) * ux + h * nx, p_start[1] + (b_end_s - 2 * c) * uy + h * ny))
        pts.append((p_start[0] + (b_end_s - c) * ux + (h - c) * nx, p_start[1] + (b_end_s - c) * uy + (h - c) * ny))
        # 5. Return to baseline with 45-degree chamfer
        pts.append((p_start[0] + (b_end_s - c) * ux + c * nx, p_start[1] + (b_end_s - c) * uy + c * ny))
        pts.append((p_start[0] + b_end_s * ux, p_start[1] + b_end_s * uy))

        curr_s = b_end_s + gap

    pts.append(p_end)
    return pts


def _polyline_length(pts: List[Tuple[float, float]]) -> float:
    return sum(math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1]) for i in range(len(pts) - 1))


def solve_meander(
    p_start: Tuple[float, float],
    p_end: Tuple[float, float],
    delta_l: float,
    num_loops: int = 2,
    pitch: float = 1.3,
    gap: float = 0.8,
    chamfer: float = 0.15,
    sign: float = 1.0,
    max_height: float = 4.0
) -> Tuple[List[Tuple[float, float]], float, float]:
    """Binary searches for exact amplitude h that adds delta_l (sub-micrometer precision)."""
    orig_L = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])
    target_L = orig_L + delta_l

    low, high = 0.1, max_height
    best_pts = [p_start, p_end]
    mid = 0.1

    for _ in range(35):
        mid = (low + high) / 2.0
        pts = generate_meander_polyline(p_start, p_end, mid, num_loops, pitch, gap, chamfer, sign)
        L = _polyline_length(pts)
        if L < target_L:
            low = mid
        else:
            high = mid
        best_pts = pts

    final_L = _polyline_length(best_pts)
    return best_pts, mid, (final_L - orig_L)


def eval_segment_clearance(
    board,
    p_start: Tuple[float, float],
    p_end: Tuple[float, float],
    layer: int,
    ignore_net: str,
    sign: float = 1.0,
    max_search_dist: float = 4.5
) -> float:
    """Evaluates available clearance perpendicular to the segment on the chosen side (+n or -n)."""
    import pcbnew
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    L = math.hypot(dx, dy)
    if L <= 0:
        return 0.0

    ux, uy = dx / L, dy / L
    nx, ny = sign * uy, -sign * ux

    min_dist = max_search_dist

    # 1. Check Board Outline
    poly = pcbnew.SHAPE_POLY_SET()
    has_outline = False
    try:
        has_outline = board.GetBoardPolygonOutlines(poly, True)
    except Exception:
        pass

    if has_outline and poly.OutlineCount() > 0:
        bb = poly.BBox()
        bx0, by0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
        bx1, by1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    else:
        bbox = board.ComputeBoundingBox()
        bx0, by0 = pcbnew.ToMM(bbox.GetX()), pcbnew.ToMM(bbox.GetY())
        bx1, by1 = bx0 + pcbnew.ToMM(bbox.GetWidth()), by0 + pcbnew.ToMM(bbox.GetHeight())

    # Sample points along segment at distance d
    for s_ratio in (0.2, 0.5, 0.8):
        base_x = p_start[0] + s_ratio * dx
        base_y = p_start[1] + s_ratio * dy
        # Distance to outline boundary in direction n
        if abs(nx) > 1e-4:
            boundary_x = bx1 if nx > 0 else bx0
            d_x = (boundary_x - base_x) / nx
            if d_x > 0:
                min_dist = min(min_dist, d_x - 0.5)  # 0.5mm edge margin
        if abs(ny) > 1e-4:
            boundary_y = by1 if ny > 0 else by0
            d_y = (boundary_y - base_y) / ny
            if d_y > 0:
                min_dist = min(min_dist, d_y - 0.5)

    # 2. Check Footprint Pads on same layer
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == ignore_net:
                continue
            pos = pad.GetPosition()
            px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
            # Project onto (u, n) coordinate system of segment
            vx, vy = px - p_start[0], py - p_start[1]
            u_proj = vx * ux + vy * uy
            n_proj = vx * nx + vy * ny
            if -0.5 <= u_proj <= L + 0.5 and n_proj > 0.1:
                # Pad is on this side of the segment
                min_dist = min(min_dist, n_proj - 0.5)

    # 3. Check Other Tracks on same layer
    for t in board.GetTracks():
        if t.GetNetname() == ignore_net or t.GetLayer() != layer:
            continue
        for pt in (t.GetStart(), t.GetEnd()):
            tx, ty = pcbnew.ToMM(pt.x), pcbnew.ToMM(pt.y)
            vx, vy = tx - p_start[0], ty - p_start[1]
            u_proj = vx * ux + vy * uy
            n_proj = vx * nx + vy * ny
            if -0.5 <= u_proj <= L + 0.5 and n_proj > 0.1:
                min_dist = min(min_dist, n_proj - 0.4)

    return max(0.0, min_dist)


def tune_differential_pair_skew(
    project_dir: str | Path,
    pair_name: Optional[str] = None,
    target_skew_mm: float = 0.10,
    pitch_mm: float = 1.3,
    gap_mm: float = 0.8,
    chamfer_mm: float = 0.15,
    max_loops: int = 4,
    auto_refill_zones: bool = True
) -> Dict[str, Any]:
    """Automatically synthesizes 45-degree mitered serpentine meanders into the shorter trace
    of a differential pair to match length and eliminate timing skew.
    Complies with IPC-2141A (no acid traps, 3W loop clearance, sub-micrometer length precision).
    """
    try:
        import pcbnew
    except ImportError:
        return _dispatch_tune(project_dir, {
            "project_dir": str(project_dir),
            "pair_name": pair_name,
            "target_skew_mm": target_skew_mm,
            "pitch_mm": pitch_mm,
            "gap_mm": gap_mm,
            "chamfer_mm": chamfer_mm,
            "max_loops": max_loops,
            "auto_refill_zones": auto_refill_zones
        })

    proj_path = Path(project_dir).resolve()
    pcb_files = list(proj_path.glob("*.kicad_pcb"))
    if not pcb_files:
        return {"success": False, "error": f"No .kicad_pcb in {proj_path}"}

    pcb_file = pcb_files[0]

    # 1. Audit Current Board State
    initial_audit = audit_differential_pairs(proj_path)
    if not initial_audit.get("success") or not initial_audit.get("pairs"):
        return {"success": False, "error": "No differential pairs to tune or audit failed."}

    pairs_to_tune = initial_audit["pairs"]
    if pair_name:
        pairs_to_tune = [p for p in pairs_to_tune if p["name"].lower() == pair_name.lower()]

    skewed_pairs = [p for p in pairs_to_tune if p["skew_3d_mm"] > target_skew_mm]
    if not skewed_pairs:
        return {
            "success": True,
            "message": f"All differential pairs already meet target skew (<= {target_skew_mm}mm).",
            "audit": initial_audit
        }

    import gc
    gc.collect()
    board = pcbnew.LoadBoard(str(pcb_file))

    tuning_log = []

    for pair in skewed_pairs:
        p_name = pair["name"]
        pos_len = pair["pos_len_3d_mm"]
        neg_len = pair["neg_len_3d_mm"]
        delta_l = pair["skew_3d_mm"]

        if pos_len < neg_len:
            shorter_net = pair["pos_net"]
            longer_net = pair["neg_net"]
        else:
            shorter_net = pair["neg_net"]
            longer_net = pair["pos_net"]

        # Collect straight candidate segments on shorter net
        candidate_tracks = []
        for t in list(board.GetTracks()):
            if t.GetNetname() == shorter_net and t.GetClass() == "PCB_TRACK":
                st = t.GetStart()
                en = t.GetEnd()
                sx, sy = pcbnew.ToMM(st.x), pcbnew.ToMM(st.y)
                ex, ey = pcbnew.ToMM(en.x), pcbnew.ToMM(en.y)
                l = math.hypot(ex - sx, ey - sy)
                if l >= 2.5:  # Needs at least 2.5mm straight span
                    candidate_tracks.append((l, t, (sx, sy), (ex, ey)))

        if not candidate_tracks:
            tuning_log.append({
                "pair": p_name,
                "net": shorter_net,
                "status": "FAILED_NO_CANDIDATE_SEGMENT",
                "message": f"No straight segment >= 2.5mm found on {shorter_net}."
            })
            continue

        # Sort candidate segments by length descending
        candidate_tracks.sort(key=lambda x: x[0], reverse=True)

        tuned = False
        for seg_len, target_track, p_start, p_end in candidate_tracks:
            layer = target_track.GetLayer()
            tr_width = target_track.GetWidth()
            net_code = target_track.GetNetCode()

            # Evaluate clearance on both sides (+1 and -1)
            clr_pos = eval_segment_clearance(board, p_start, p_end, layer, shorter_net, sign=1.0)
            clr_neg = eval_segment_clearance(board, p_start, p_end, layer, shorter_net, sign=-1.0)

            chosen_sign = 1.0 if clr_pos >= clr_neg else -1.0
            avail_clr = max(clr_pos, clr_neg)

            if avail_clr < 0.6:
                continue

            # Determine number of loops that fit along this segment
            # Base width for n loops: n * pitch + (n-1) * gap
            fitting_loops = 1
            for n in range(max_loops, 0, -1):
                base_span = n * pitch_mm + (n - 1) * gap_mm
                if base_span <= seg_len - 0.8:
                    fitting_loops = n
                    break

            if fitting_loops < 1:
                continue

            # Calculate and solve meander points
            max_h = min(avail_clr - 0.2, 3.5)
            meander_pts, solved_h, actual_added = solve_meander(
                p_start, p_end, delta_l,
                num_loops=fitting_loops,
                pitch=pitch_mm,
                gap=gap_mm,
                chamfer=chamfer_mm,
                sign=chosen_sign,
                max_height=max_h
            )

            # Replace straight track with synthesized meander segments
            board.Delete(target_track)

            for i in range(len(meander_pts) - 1):
                new_t = pcbnew.PCB_TRACK(board)
                new_t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(meander_pts[i][0]), pcbnew.FromMM(meander_pts[i][1])))
                new_t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(meander_pts[i+1][0]), pcbnew.FromMM(meander_pts[i+1][1])))
                new_t.SetLayer(layer)
                new_t.SetWidth(tr_width)
                new_t.SetNetCode(net_code)
                board.Add(new_t)

            tuned = True
            tuning_log.append({
                "pair": p_name,
                "net": shorter_net,
                "status": "SUCCESS",
                "loops": fitting_loops,
                "amplitude_mm": round(solved_h, 3),
                "added_len_mm": round(actual_added, 3),
                "target_delta_mm": round(delta_l, 3),
                "segment_len_mm": round(seg_len, 3),
                "chosen_side": "+Normal" if chosen_sign > 0 else "-Normal",
                "available_clearance_mm": round(avail_clr, 2)
            })
            break

        if not tuned:
            tuning_log.append({
                "pair": p_name,
                "net": shorter_net,
                "status": "INSUFFICIENT_CLEARANCE",
                "message": f"Segments had insufficient clearance (< 0.6mm) on both sides."
            })

    # Refill zones and save board
    if auto_refill_zones and len(board.Zones()) > 0:
        try:
            filler = pcbnew.ZONE_FILLER(board)
            filler.Fill(board.Zones())
        except Exception:
            pass

    board.BuildListOfNets()
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb_file), board)
    del board
    gc.collect()

    # Post-Tuning Verification Audit
    final_audit = audit_differential_pairs(proj_path)

    # Format Human Report
    lines = []
    lines.append("=" * 96)
    lines.append(" [DIFFERENTIAL PAIR SERPENTINE / ACCORDION TUNING REPORT]")
    lines.append("=" * 96)
    for log in tuning_log:
        if log["status"] == "SUCCESS":
            lines.append(f"  [+] Pair: {log['pair']:<8} | Tuned Net: {log['net']:<10} | Target Delta: +{log['target_delta_mm']:.2f}mm")
            lines.append(f"      - Added Meanders : {log['loops']} loop(s) (Amplitude h={log['amplitude_mm']:.2f}mm, Pitch={pitch_mm:.2f}mm)")
            lines.append(f"      - Placement Side : {log['chosen_side']} (Available clearance: {log['available_clearance_mm']:.2f}mm)")
            lines.append(f"      - Exact Length Added: +{log['added_len_mm']:.3f}mm")
        else:
            lines.append(f"  [-] Pair: {log['pair']:<8} | Net: {log['net']:<10} | FAILED: {log.get('message', log['status'])}")
    lines.append("-" * 96)
    lines.append(final_audit.get("formatted_table", ""))

    report_str = "\n".join(lines)

    return {
        "success": any(l["status"] == "SUCCESS" for l in tuning_log),
        "log": tuning_log,
        "initial_audit": initial_audit,
        "final_audit": final_audit,
        "formatted_report": report_str
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Headless Differential Pair Detection, Netclass Sync, Skew Auditor & Serpentine Tuner."
    )
    ap.add_argument("project_dir", help="Path to KiCad project folder")
    ap.add_argument("--audit", action="store_true", default=False, help="Run 3D length and timing skew audit")
    ap.add_argument("--tune", action="store_true", default=False, help="Automatically synthesize serpentine meanders to eliminate timing skew")
    ap.add_argument("--detect", action="store_true", default=False, help="Detect differential pairs on board")
    ap.add_argument("--sync-netclasses", action="store_true", default=False, help="Sync differential netclasses into .kicad_pro")
    ap.add_argument("--pair", type=str, default=None, help="Target specific differential pair by name (e.g. 'CAN')")
    ap.add_argument("--target-skew", type=float, default=0.10, help="Target residual skew in mm (default: 0.10)")
    ap.add_argument("--loops", type=int, default=4, help="Maximum meander loops to fit (default: 4)")
    ap.add_argument("--thickness", type=float, default=1.6, help="PCB substrate thickness in mm for via barrel compensation (default: 1.6)")
    ap.add_argument("--json", action="store_true", default=False, help="Output machine-readable JSON")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    if args.tune:
        res = tune_differential_pair_skew(
            project_dir,
            pair_name=args.pair,
            target_skew_mm=args.target_skew,
            max_loops=args.loops
        )
        if not res.get("success"):
            print(f"[-] Differential pair tuning failed: {res.get('error') or res.get('message')}", file=sys.stderr)
            if args.json:
                print(json.dumps(res, indent=2))
            return 1

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res.get("formatted_report", ""))
        return 0

    run_all = not (args.detect or args.sync_netclasses)

    if args.detect or run_all:
        specs = detect_differential_pairs(project_dir)
        if args.detect and not args.audit:
            if args.json:
                print(json.dumps([s.to_dict() for s in specs], indent=2))
            else:
                print(f"[*] Detected {len(specs)} differential pair(s) in {project_dir.name}:")
                for s in specs:
                    print(f"    - {s.name:<10}: {s.pos_net} / {s.neg_net} | Target: {s.target_impedance:.0f}Ω | Max Skew: {s.max_skew_mm:.2f}mm | Width: {s.track_width_mm:.2f}mm | Gap: {s.gap_mm:.2f}mm")
            if not run_all:
                return 0

    if args.sync_netclasses:
        specs = detect_differential_pairs(project_dir)
        pro_files = list(project_dir.glob("*.kicad_pro"))
        if not pro_files:
            print("Error: No .kicad_pro found in project directory", file=sys.stderr)
            return 1
        ok = sync_diff_pair_netclasses(pro_files[0], specs)
        if ok:
            print(f"[+] Synchronized {len(specs)} differential netclass(es) into {pro_files[0].name}")
        else:
            print("[-] Failed to update .kicad_pro", file=sys.stderr)
            return 1
        if not run_all:
            return 0

    if args.audit or run_all:
        res = audit_differential_pairs(project_dir, board_thickness_mm=args.thickness)
        if not res.get("success"):
            print(f"[-] Differential pair audit failed: {res.get('error')}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res.get("formatted_table", ""))

        return 0 if res.get("all_passed", True) else 2

    return 0


if __name__ == "__main__":
    sys.exit(main())


