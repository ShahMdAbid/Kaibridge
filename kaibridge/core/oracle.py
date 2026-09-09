"""
Kaibridge Live SWIG API & Architecture Oracle (oracle.py):
Reflection, static inspection, and architectural constraint engine for KiCad pcbnew SWIG bindings.
Provides zero-hallucination ground-truth API method signatures, argument types,
class constructor inspection, module constants, and production rules directly from host pcbnew.
"""
from __future__ import annotations

import os
import sys
import json
import re
import difflib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

_PCBNEW_CACHE: Optional[str] = None
_PCBNEW_SOURCE_PATH: Optional[Path] = None

# Ground-truth architectural knowledge base for Kaibridge / KiCad 10 / JLCPCB production
_RULES_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "drc_rules": {
        "topic": "JLCPCB Production DRC Rules & Constraints",
        "description": "Standard JLCPCB manufacturing capabilities to embed in .kicad_pro design_settings.rules",
        "values": {
            "min_copper_edge_clearance": "0.15mm (prevents false DRC errors on USB-C & edge connectors; default KiCad 0.50mm is too strict)",
            "min_clearance": "0.15mm (6 mil standard)",
            "min_track_width": "0.15mm (6 mil standard)",
            "min_hole_clearance": "0.25mm",
            "min_hole_to_hole": "0.25mm",
            "min_via_diameter": "0.5mm",
            "min_via_drill": "0.3mm",
            "min_through_hole_clearance": "0.2mm",
            "min_text_height": "0.8mm",
            "min_text_thickness": "0.08mm"
        },
        "kicad_pro_snippet": {
            "board": {
                "design_settings": {
                    "rules": {
                        "min_clearance": 0.15,
                        "min_track_width": 0.15,
                        "min_copper_edge_clearance": 0.15,
                        "min_hole_clearance": 0.25,
                        "min_hole_to_hole": 0.25,
                        "min_via_diameter": 0.5
                    }
                }
            }
        }
    },
    "jlcpcb_rules": {
        "topic": "JLCPCB PCB Manufacturing Capabilities & DFM Constraints",
        "description": "Comprehensive DFM engineering limits for JLCPCB 2-layer and 4-layer standard PCB fabrication",
        "values": {
            "min_track_width_clearance": "0.127mm (5 mil) for standard; 0.15mm (6 mil) recommended for 100% yield",
            "min_via_hole_diameter": "0.3mm drill / 0.5mm pad diameter (0.1mm annular ring)",
            "min_plated_hole": "0.3mm; min non-plated hole: 0.5mm",
            "board_outline_clearance": "0.20mm (copper to board edge clearance; default KiCad 0.5mm creates false edge-connector errors)",
            "solder_mask_bridge": "min 0.1mm (4 mil) between adjacent SMD pads",
            "silk_to_pad_clearance": "min 0.15mm (6 mil) to prevent legend bleeding onto solder pads",
            "min_silkscreen_text": "height 0.8mm, stroke thickness 0.08mm (smaller will be unreadable)",
            "board_thickness": "1.6mm (standard), 1.0mm, 1.2mm, 2.0mm",
            "copper_weight": "1oz (35µm) outer layers, 0.5oz (17.5µm) inner layers"
        },
        "rules": [
            "1. Set copper-to-edge clearance in .kicad_pro to 0.15mm-0.2mm so edge-straddling connectors (USB-C, pin headers) pass DRC.",
            "2. Maintain 0.25mm minimum spacing between vias to prevent drill bit slippage or breakout.",
            "3. Never place silkscreen text over unmasked copper or exposed pads.",
            "4. Keep annular ring on vias >= 0.1mm to avoid open circuits caused by drilling tolerances."
        ]
    },
    "swig_memory": {
        "topic": "KiCad pcbnew SWIG Memory Lifecycle & Safety",
        "description": "Rules to avoid SwigPyObject pointer invalidation and memory leaks in Python",
        "rules": [
            "1. Always run gc.collect() before and after calling pcbnew.LoadBoard().",
            "2. Always explicitly delete the board variable (del board) at the end of functions to release C++ pointers.",
            "3. Never keep a module-level or global board reference across multiple tool calls or operations.",
            "4. Verify hasattr(board, 'GetFootprints') before accessing board attributes.",
            "5. For heavy batch operations, run them in an isolated subprocess via load_kicad_python() to ensure clean OS process teardown."
        ],
        "example_pattern": "import gc, pcbnew\ngc.collect()\nboard = pcbnew.LoadBoard(pcb_path)\ntry:\n    # operations\n    pcbnew.SaveBoard(pcb_path, board)\nfinally:\n    del board\n    gc.collect()"
    },
    "zone_filling": {
        "topic": "Ground Plane Pouring & Post-Routing Refill Protocol",
        "description": "Mandatory steps for DRC-clean copper zones in KiCad 10",
        "rules": [
            "1. Exact Outline: Use zone.SetOutline(poly) where poly is obtained from board.GetBoardPolygonOutlines(poly, True) to avoid edge overflow.",
            "2. Thermal Connections: Use zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL) for solid connections to prevent starved_thermal DRC errors.",
            "3. Mandatory Refill: Immediately after importing tracks from Freerouting (SES), MUST instantiate pcbnew.ZONE_FILLER(board) and call filler.Fill(board.Zones()).",
            "4. Connectivity: Always call board.BuildListOfNets() and board.BuildConnectivity() after zone operations."
        ],
        "example_pattern": "filler = pcbnew.ZONE_FILLER(board)\nfiller.Fill(board.Zones())\nboard.BuildListOfNets()\nboard.BuildConnectivity()"
    },
    "power_flags": {
        "topic": "Power Flags & Switched Rail ERC Rules",
        "description": "Prevention of [pin_not_driven] ERC errors on power ingest and switched nets",
        "rules": [
            "1. KiCad ERC requires every power net connected to a power_in pin to have a power driver (power_out pin or PWR_FLAG).",
            "2. Switched rails (e.g. VBUS_SW after a switch, VIN after a series diode) have NO power_out pin because switches/diodes are passive.",
            "3. In design.json, declare all such nets in 'power_flags': ['VBUS', 'VBUS_SW', 'VIN', 'GND'].",
            "4. Never put power_flags on actively driven regulator output pins (e.g. AMS1117 VOUT) to avoid pin_to_pin collision errors."
        ]
    },
    "freerouting_limits": {
        "topic": "Freerouting 2.4.1 Headless Auto-Router Limits & Execution Protocol",
        "description": "Production limits, keepout handling, and CLI invocation rules for Freerouting JAR engine",
        "values": {
            "max_passes": "100 passes (optimal convergence; >150 has diminishing returns)",
            "via_cost": "50 (balances track length vs via count; lower causes via explosion)",
            "router_grid": "0.05mm (high precision; 0.025mm for dense BGAs)",
            "java_heap_allocation": "-Xmx4g (minimum 2GB for small boards, 4GB for multi-layer)",
            "timeout_seconds": "300s (5 minutes safety watchdog per routing job)"
        },
        "rules": [
            "1. Specctra DSN Export: Always invoke board.ExportSpecctraDSN() with all SMD footprints locked and board boundary closed.",
            "2. Headless Invocation: Execute via 'java -Djava.awt.headless=true -jar freerouting-2.4.1.jar -de <DSN> -do <SES> -mp 100'.",
            "3. SES Post-Processing: After importing .ses into KiCad, ALWAYS refill copper planes with ZONE_FILLER(board).Fill(board.Zones()).",
            "4. Keepouts: Route keepouts on F.SilkS or F.Courtyard are NOT respected by DSN unless explicitly converted to pcbnew.ZONE with is_rule_area=True."
        ],
        "example_pattern": "java -Djava.awt.headless=true -jar freerouting-2.4.1.jar -de project.dsn -do project.ses -mp 100"
    },
    "stackup_4layer": {
        "topic": "JLCPCB JLC04161H-7628 4-Layer Controlled Impedance Stackup",
        "description": "Standard 1.6mm 4-layer PCB stackup with dielectric constants and trace geometries for 50Ω / 90Ω differential pairs",
        "values": {
            "total_thickness": "1.6mm (+/- 10%)",
            "layer_1_top": "F.Cu: 0.035mm (1oz) - High-speed signal routing & component placement",
            "dielectric_1": "Prepreg 7628 (thickness 0.2104mm, Er 4.6 @ 1GHz)",
            "layer_2_in1": "In1.Cu: 0.0175mm (0.5oz) - Solid GND Plane (unbroken ground return)",
            "core": "FR4 Core (thickness 1.065mm, Er 4.5 @ 1GHz)",
            "layer_3_in2": "In2.Cu: 0.0175mm (0.5oz) - Power Planes (3V3, 5V, VBUS copper pours)",
            "dielectric_2": "Prepreg 7628 (thickness 0.2104mm, Er 4.6 @ 1GHz)",
            "layer_4_bottom": "B.Cu: 0.035mm (1oz) - Low-speed signals, passives, and secondary ground fill",
            "single_ended_50_ohm": "Trace width: 0.35mm (13.8 mil) referencing In1.Cu GND",
            "differential_90_ohm_usb": "Trace width: 0.22mm (8.7 mil), Gap: 0.15mm (6 mil) referencing In1.Cu GND",
            "differential_120_ohm_can": "Trace width: 0.25mm (9.8 mil), Gap: 0.25mm (9.8 mil) referencing In1.Cu GND"
        },
        "rules": [
            "1. In1.Cu MUST remain an unbroken, solid GND copper pour without signal cutouts beneath high-speed signals (USB D+/D-, CAN, SPI).",
            "2. Stitch GND vias around high-speed trace vias when switching from Top to Bottom layer to maintain return path continuity.",
            "3. Never route differential traces over splits or voids in the In1.Cu ground plane."
        ]
    },
    "track_clearance": {
        "topic": "IPC-2221 Track Spacing, Voltage Breakdown & Net Class Clearances",
        "description": "Safety clearances and net class isolation rules across digital, analog, power, and differential signals",
        "values": {
            "digital_low_voltage_0_15v": "0.15mm (6 mil) min clearance",
            "analog_sensitive_signals": "0.25mm (10 mil) clearance to prevent crosstalk",
            "power_rail_15_30v": "0.25mm (10 mil) min clearance; trace width >= 0.50mm per 1A current",
            "industrial_bus_30_50v": "0.40mm (16 mil) min clearance",
            "usb_diff_pair_90ohm": "Trace width 0.22mm, intra-pair gap 0.15mm, clearance to other traces >= 0.30mm (3W rule)",
            "can_diff_pair_120ohm": "Trace width 0.25mm, intra-pair gap 0.25mm, clearance to other traces >= 0.40mm",
            "mains_high_voltage_230vac": "3.0mm min clearance; 6.3mm creepage distance or physical isolation routing slot"
        },
        "rules": [
            "1. Follow the 3W Rule: Keep spacing between high-speed signal tracks and unrelated tracks >= 3x trace width to suppress 70% crosstalk.",
            "2. Current Capacity Rule: For 1oz copper with 10°C temp rise, trace width must be at least 0.3mm per 1A on outer layers (1mm for 2A).",
            "3. Power Ingest Traces: VBUS, VIN, and Battery traces should be at least 0.5mm to 1.0mm wide with thermal vias."
        ]
    }
}

# Curated, production-tested KiCad 10 Python SWIG usage patterns
_SWIG_CODE_PATTERNS: Dict[str, Dict[str, str]] = {
    "loadboard": {
        "title": "Load KiCad Board Safely",
        "code": "import gc, pcbnew\ngc.collect()\nboard = pcbnew.LoadBoard('path/to/board.kicad_pcb')"
    },
    "saveboard": {
        "title": "Save KiCad Board with Pointer Release",
        "code": "pcbnew.SaveBoard('path/to/board.kicad_pcb', board)\ndel board\ngc.collect()"
    },
    "frommm": {
        "title": "Convert Millimeters to KiCad Internal Units (nanometers)",
        "code": "coord_iu = pcbnew.FromMM(12.5)  # 12.5 mm -> 12,500,000 nm"
    },
    "tomm": {
        "title": "Convert KiCad Internal Units to Millimeters",
        "code": "coord_mm = pcbnew.ToMM(coord_iu)  # 12,500,000 nm -> 12.5 mm"
    },
    "vector2i": {
        "title": "Create KiCad 2D Integer Vector Point",
        "code": "pos = pcbnew.VECTOR2I(pcbnew.FromMM(50.0), pcbnew.FromMM(30.0))"
    },
    "eda_angle": {
        "title": "Create KiCad Exact Rotation Angle",
        "code": "angle = pcbnew.EDA_ANGLE(90.0, pcbnew.DEGREES_T)\nfootprint.SetOrientation(angle)"
    },
    "findfootprintbyreference": {
        "title": "Locate Component Footprint by Reference",
        "code": "fp = board.FindFootprintByReference('U1')\nif fp is not None:\n    pos = fp.GetPosition()\n    print(f'U1 at X={pcbnew.ToMM(pos.x)}mm, Y={pcbnew.ToMM(pos.y)}mm')"
    },
    "getfootprints": {
        "title": "Iterate Over Board Footprints",
        "code": "for fp in board.GetFootprints():\n    ref = fp.GetReference()\n    print(f'{ref}: {pcbnew.ToMM(fp.GetPosition().x)}, {pcbnew.ToMM(fp.GetPosition().y)}')"
    },
    "footprints": {
        "title": "Iterate Over Board Footprints",
        "code": "for fp in board.GetFootprints():\n    ref = fp.GetReference()\n    print(f'{ref}: {pcbnew.ToMM(fp.GetPosition().x)}, {pcbnew.ToMM(fp.GetPosition().y)}')"
    },
    "setposition": {
        "title": "Set Footprint Coordinates",
        "code": "new_pos = pcbnew.VECTOR2I(pcbnew.FromMM(25.4), pcbnew.FromMM(18.0))\nfootprint.SetPosition(new_pos)"
    },
    "setorientation": {
        "title": "Rotate Footprint by Degrees",
        "code": "footprint.SetOrientation(pcbnew.EDA_ANGLE(180.0, pcbnew.DEGREES_T))"
    },
    "pads": {
        "title": "Inspect Footprint Pads and Nets",
        "code": "for pad in footprint.Pads():\n    pad_name = pad.GetName() or pad.GetNumber()\n    net_name = pad.GetNetname()\n    pad_pos = pad.GetPosition()"
    },
    "exportspecctradsn": {
        "title": "Export Specctra DSN File for Freerouting",
        "code": "success = pcbnew.ExportSpecctraDSN(board, 'project.dsn')"
    },
    "importspecctrases": {
        "title": "Import Specctra SES File from Freerouting",
        "code": "success = pcbnew.ImportSpecctraSES(board, 'project.ses')"
    },
    "zone_filler": {
        "title": "Instantiate Zone Filler and Refill Copper Pours",
        "code": "filler = pcbnew.ZONE_FILLER(board)\nfiller.Fill(board.Zones())\nboard.BuildListOfNets()\nboard.BuildConnectivity()"
    },
    "buildconnectivity": {
        "title": "Rebuild Board Connectivity and Ratsnest",
        "code": "board.BuildListOfNets()\nboard.BuildConnectivity()"
    },
    "buildlistofnets": {
        "title": "Rebuild Net Index",
        "code": "board.BuildListOfNets()\nboard.BuildConnectivity()"
    },
    "zone_connection_full": {
        "title": "Set Zone Pad Connection to Solid Full Pour",
        "code": "zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)"
    },
    "setpadconnection": {
        "title": "Configure Zone Thermal vs Solid Relief",
        "code": "zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)"
    },
    "pcb_track": {
        "title": "Create and Add a PCB Copper Track Segment",
        "code": "track = pcbnew.PCB_TRACK(board)\ntrack.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(10.0), pcbnew.FromMM(10.0)))\ntrack.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(20.0), pcbnew.FromMM(10.0)))\ntrack.SetWidth(pcbnew.FromMM(0.25))\ntrack.SetLayer(pcbnew.F_Cu)\nboard.Add(track)"
    },
    "pcb_via": {
        "title": "Create and Add a Through-Hole Via",
        "code": "via = pcbnew.PCB_VIA(board)\nvia.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(15.0), pcbnew.FromMM(15.0)))\nvia.SetWidth(pcbnew.FromMM(0.5))  # Pad diameter\nvia.SetDrill(pcbnew.FromMM(0.3))  # Hole diameter\nvia.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)\nboard.Add(via)"
    }
}


def find_pcbnew_source() -> Optional[Path]:
    """Locates the live pcbnew.py file installed on the host machine across Windows, Linux, and macOS."""
    global _PCBNEW_SOURCE_PATH
    if _PCBNEW_SOURCE_PATH and _PCBNEW_SOURCE_PATH.is_file():
        return _PCBNEW_SOURCE_PATH

    # 1. Try active imported pcbnew module
    try:
        import pcbnew
        mod_file = getattr(pcbnew, "__file__", None)
        if mod_file:
            p = Path(mod_file)
            if p.suffix in (".pyc", ".pyo"):
                p = p.with_suffix(".py")
            if p.is_file():
                _PCBNEW_SOURCE_PATH = p
                return p
    except Exception:
        pass

    # 2. Derive from load_kicad_python()
    try:
        from .paths import load_kicad_python
        kpython = load_kicad_python()
        if kpython and kpython != "python":
            py_path = Path(kpython)
            for sub in (py_path.parent / "Lib" / "site-packages" / "pcbnew.py",
                        py_path.parent.parent / "share" / "kicad" / "plugins" / "pcbnew.py",
                        py_path.parent / "pcbnew.py"):
                if sub.is_file():
                    _PCBNEW_SOURCE_PATH = sub
                    return sub
    except Exception:
        pass

    # 3. Comprehensive multi-drive Windows paths (C:, D:, E:, F:)
    candidates: List[Path] = []
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    for ver in ("10.0", "9.0", "8.0", "7.0"):
        candidates.append(Path(f"{prog_files}/KiCad/{ver}/bin/Lib/site-packages/pcbnew.py"))
        candidates.append(Path(f"{prog_files}/KiCad/{ver}/lib/python3/dist-packages/pcbnew.py"))
        candidates.append(Path(f"{prog_files}/KiCad/{ver}/bin/pcbnew.py"))

    for drive in ("C", "D", "E", "F"):
        for ver in ("10.0", "9.0", "8.0", "7.0"):
            candidates.append(Path(f"{drive}:/Program Files/KiCad/{ver}/bin/Lib/site-packages/pcbnew.py"))
            candidates.append(Path(f"{drive}:/Program Files/KiCad/{ver}/lib/python3/dist-packages/pcbnew.py"))
            candidates.append(Path(f"{drive}:/Program Files/KiCad/{ver}/bin/pcbnew.py"))

    # 4. Standard Linux paths
    candidates.extend([
        Path("/usr/lib/kicad/lib/python3/dist-packages/pcbnew.py"),
        Path("/usr/lib/python3/dist-packages/pcbnew.py"),
        Path("/usr/share/kicad/plugins/pcbnew.py"),
        Path("/usr/local/lib/python3/dist-packages/pcbnew.py"),
    ])

    # 5. Standard macOS paths
    for py_ver in ("3.9", "3.10", "3.11", "3.12"):
        candidates.append(Path(f"/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python{py_ver}/site-packages/pcbnew.py"))
    candidates.append(Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/plugins/pcbnew.py"))

    for cand in candidates:
        try:
            if cand.is_file():
                _PCBNEW_SOURCE_PATH = cand
                return cand
        except Exception:
            continue

    return None


def _load_pcbnew_content() -> str:
    """Loads and caches the contents of pcbnew.py."""
    global _PCBNEW_CACHE
    if _PCBNEW_CACHE is not None:
        return _PCBNEW_CACHE

    src = find_pcbnew_source()
    if not src or not src.is_file():
        return ""

    try:
        _PCBNEW_CACHE = src.read_text(encoding="utf-8", errors="replace")
    except Exception:
        _PCBNEW_CACHE = ""
    return _PCBNEW_CACHE


def _extract_docstring(method_body: str) -> str:
    """Extracts def line, signature, and attached docstrings/aliases from a method block."""
    doc_match = re.search(
        r"^[ \t]*def[^\n]+:\s*r?(?:\"\"\"|\'\'\')[\s\S]*?(?:\"\"\"|\'\'\')",
        method_body,
        re.MULTILINE
    )
    if doc_match:
        return doc_match.group(0).strip()

    lines = method_body.strip().splitlines()
    if len(lines) > 2:
        return "\n".join(lines[:3]).strip()
    return lines[0].strip() if lines else ""


def _find_similar_names(all_names: List[str], query: str, limit: int = 6) -> List[str]:
    """Finds fuzzy suggestions for misspelled or partially matched names."""
    q_lower = query.lower().replace("-", "_")
    exact_substr = [n for n in all_names if q_lower in n.lower()]
    if exact_substr:
        return sorted(exact_substr, key=len)[:limit]
    
    # Case-insensitive difflib matching
    lower_map: Dict[str, str] = {}
    for n in all_names:
        n_low = n.lower().replace("-", "_")
        if n_low not in lower_map:
            lower_map[n_low] = n

    close_lowers = difflib.get_close_matches(q_lower, list(lower_map.keys()), n=limit, cutoff=0.45)
    return [lower_map[cl] for cl in close_lowers]


_QUERY_CACHE: Dict[Tuple[str, Optional[str], Optional[str]], Dict[str, Any]] = {}


def query_oracle(query: str, class_name: Optional[str] = None, filter_str: Optional[str] = None) -> Dict[str, Any]:
    """Queries the KiCad pcbnew SWIG oracle for exact signatures, docstrings, classes, constants, and rules.
    
    Args:
        query: Method name, class name, constant name, rule topic, or 'topics'/'rules' for directory.
        class_name: Optional class name (e.g. 'BOARD', 'ZONE', 'FOOTPRINT', 'GLOBAL').
        filter_str: Optional keyword filter for class methods (e.g. 'track', 'pad').
    """
    q_clean = query.strip()
    c_clean = class_name.strip() if class_name else None
    f_clean = filter_str.strip() if filter_str else None

    cache_key = (q_clean, c_clean, f_clean)
    if cache_key in _QUERY_CACHE:
        return _QUERY_CACHE[cache_key]

    res = _query_oracle_uncached(q_clean, c_clean, f_clean)
    _QUERY_CACHE[cache_key] = res
    return res


def _query_oracle_uncached(q_clean: str, c_clean: Optional[str], f_clean: Optional[str]) -> Dict[str, Any]:
    if not q_clean:
        return {
            "success": False,
            "error": "Empty query string provided.",
            "source_path": str(_PCBNEW_SOURCE_PATH) if _PCBNEW_SOURCE_PATH else None
        }

    q_lower = q_clean.lower()

    # 1. Topics Listing Query
    if q_lower in ("topics", "rules", "list", "all_topics", "all_rules", "--list", "help"):
        topics_list = [
            {
                "key": k,
                "topic": v.get("topic"),
                "description": v.get("description")
            }
            for k, v in _RULES_KNOWLEDGE_BASE.items()
        ]
        return {
            "success": True,
            "type": "TOPICS_LIST",
            "count": len(topics_list),
            "topics": topics_list
        }

    # 2. Architectural & Production Rules Knowledge Base Match
    # Match rule if exact key, or if no class was requested and rule key matches
    q_rule_key = q_lower.replace("-", "_").replace(" ", "_")
    if q_rule_key in _RULES_KNOWLEDGE_BASE:
        data = _RULES_KNOWLEDGE_BASE[q_rule_key]
        return {
            "success": True,
            "type": "RULE",
            "topic": data.get("topic"),
            "description": data.get("description"),
            "details": data
        }
    
    content = _load_pcbnew_content()
    if not content:
        # If KiCad pcbnew is not on host, allow fuzzy partial rule matching
        if not c_clean:
            for key, data in _RULES_KNOWLEDGE_BASE.items():
                if len(q_rule_key) >= 4 and (key in q_rule_key or q_rule_key in key):
                    return {
                        "success": True,
                        "type": "RULE",
                        "topic": data.get("topic"),
                        "description": data.get("description"),
                        "details": data
                    }
        return {
            "success": False,
            "error": "pcbnew.py source file could not be located on host system.",
            "source_path": None
        }

    # Collect top-level functions and classes
    global_func_names = list(set(re.findall(r"\ndef\s+([A-Za-z0-9_]+)\s*\(", content)))
    class_names = list(set(re.findall(r"\nclass\s+([A-Za-z0-9_]+)\b", content)))

    # Case-insensitive maps
    class_map = {c.lower(): c for c in class_names}
    global_func_map = {f.lower(): f for f in global_func_names}

    # If not a class or function, check partial rule substring
    if not c_clean and q_clean not in class_names and q_lower not in class_map:
        for key, data in _RULES_KNOWLEDGE_BASE.items():
            if len(q_rule_key) >= 4 and (key in q_rule_key or q_rule_key in key):
                return {
                    "success": True,
                    "type": "RULE",
                    "topic": data.get("topic"),
                    "description": data.get("description"),
                    "details": data
                }

    # 3. Class Query (when query matches a class name or class_name is requested without method)
    is_class_query = (
        (q_clean in class_names or q_lower in class_map) and not c_clean
    ) or (
        c_clean and q_lower in ("class", "overview", "__init__", "", "all")
    )

    if is_class_query:
        raw_target = c_clean if c_clean else q_clean
        target_cls = class_map.get(raw_target.lower(), raw_target)
        cls_pat = rf"\nclass\s+{re.escape(target_cls)}\b(?:\(([^)]+)\))?:([\s\S]*?)(?=\nclass |\Z)"
        cls_match = re.search(cls_pat, content)
        if cls_match:
            parents = cls_match.group(1) or "object"
            body = cls_match.group(2)
            
            # Extract class docstring
            doc_m = re.search(r"^[ \t]*r?(?:\"\"\"|\'\'\')([\s\S]*?)(?:\"\"\"|\'\'\')", body.strip(), re.MULTILINE)
            class_doc = doc_m.group(1).strip() if doc_m else f"Proxy of C++ {target_cls} class."
            
            # Extract __init__ constructor
            init_m = re.search(r"\n[ \t]+def\s+__init__\s*\([\s\S]*?(?=(?:\n[ \t]+def |\Z))", body)
            ctor_sig = _extract_docstring(init_m.group(0)) if init_m else "def __init__(self, *args):"
            
            # Extract public methods
            methods = sorted(set(m for m in re.findall(r"\n[ \t]+def\s+([A-Za-z0-9_]+)\s*\(", body) if not m.startswith("_")))
            
            # Apply keyword filter if requested
            filtered_methods = methods
            if f_clean:
                f_kw = f_clean.lower()
                filtered_methods = [m for m in methods if f_kw in m.lower()]

            code_pat = _find_code_pattern(target_cls)
            res_cls = {
                "success": True,
                "type": "CLASS",
                "class": target_cls,
                "parents": parents.strip(),
                "constructor": ctor_sig,
                "docstring": class_doc,
                "methods_count": len(methods),
                "filtered_count": len(filtered_methods) if f_clean else len(methods),
                "methods": filtered_methods[:80],
                "filter": f_clean,
                "source_path": str(_PCBNEW_SOURCE_PATH)
            }
            if code_pat:
                res_cls["code_example"] = code_pat
            return res_cls

    # 4. Constant or Enum Query (Exact and Case-Insensitive)
    const_pat = rf"(?:^|\n)[ \t]*{re.escape(q_clean)}\s*=\s*([^\n]+)"
    const_match = re.search(const_pat, content)
    if not const_match:
        # Case-insensitive constant search
        ci_const_pat = rf"(?:^|\n)[ \t]*([A-Za-z0-9_]*{re.escape(q_clean)}[A-Za-z0-9_]*)\s*=\s*([^\n]+)"
        ci_match = re.search(ci_const_pat, content, re.IGNORECASE)
        if ci_match and ci_match.group(1).lower() == q_lower:
            const_match = ci_match
            q_clean = ci_match.group(1)

    if const_match:
        val_expr = const_match.group(1 if const_match.re.groups == 1 else 2).strip()
        code_pat = _find_code_pattern(q_clean)
        res_data: Dict[str, Any] = {
            "success": True,
            "type": "CONSTANT",
            "name": q_clean,
            "assignment": f"{q_clean} = {val_expr}",
            "source_path": str(_PCBNEW_SOURCE_PATH)
        }
        if code_pat:
            res_data["code_example"] = code_pat
        return res_data

    # 5. Global Function Query (Exact and Case-Insensitive)
    resolved_global = q_clean if q_clean in global_func_names else global_func_map.get(q_lower)
    if resolved_global and (not c_clean or c_clean.upper() in ("GLOBAL", "NONE", "")):
        pat = rf"(?:^|\n)def\s+{re.escape(resolved_global)}\s*\([\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |\Z))"
        m = re.search(pat, content)
        if m:
            sig = _extract_docstring(m.group(0))
            code_pat = _find_code_pattern(resolved_global)
            res_data = {
                "success": True,
                "type": "FUNCTION",
                "scope": f"GLOBAL.{resolved_global}",
                "exact_signature": sig,
                "class": "GLOBAL",
                "method": resolved_global,
                "source_path": str(_PCBNEW_SOURCE_PATH)
            }
            if code_pat:
                res_data["code_example"] = code_pat
            return res_data

    # 6. Class Method Query with Inheritance Resolution and Case-Insensitive Matching
    raw_cls = c_clean if c_clean and c_clean.upper() not in ("GLOBAL", "NONE") else None
    target_class = class_map.get(raw_cls.lower(), raw_cls) if raw_cls else "BOARD"

    queue = [target_class]
    visited = set()
    class_method_names = set()

    while queue:
        curr_cls = queue.pop(0)
        if curr_cls in visited or curr_cls in ("object", ""):
            continue
        visited.add(curr_cls)

        cls_pat = rf"\nclass\s+{re.escape(curr_cls)}\b(?:\(([^)]+)\))?:"
        cls_match = re.search(cls_pat, content)
        if not cls_match:
            continue

        parents_raw = cls_match.group(1)
        if parents_raw:
            parents = [p.strip().split(".")[-1] for p in parents_raw.split(",") if p.strip()]
            for p in parents:
                if p not in visited:
                    queue.append(p)

        cls_start = cls_match.start()
        next_cls = content.find("\nclass ", cls_start + 6)
        cls_block = content[cls_start:next_cls] if next_cls != -1 else content[cls_start:]

        # Collect methods and build case-insensitive map
        meth_ci_map = {}
        for meth in re.findall(r"\n[ \t]+def\s+([A-Za-z0-9_]+)\s*\(", cls_block):
            class_method_names.add(meth)
            meth_ci_map[meth.lower()] = meth

        # Match exact or case-insensitive method
        target_meth = q_clean if q_clean in meth_ci_map.values() else meth_ci_map.get(q_lower)
        if target_meth:
            meth_pat = rf"\n[ \t]+def\s+{re.escape(target_meth)}\s*\([\s\S]*?(?=(?:\n[ \t]+def |\nclass |\Z))"
            meth_match = re.search(meth_pat, cls_block)
            if meth_match:
                sig = _extract_docstring(meth_match.group(0))
                code_pat = _find_code_pattern(target_meth)
                res_data = {
                    "success": True,
                    "type": "METHOD",
                    "scope": f"{target_class}.{target_meth}" if curr_cls == target_class else f"{target_class}.{target_meth} (inherited from {curr_cls})",
                    "exact_signature": sig,
                    "class": target_class,
                    "defined_in_class": curr_cls,
                    "method": target_meth,
                    "source_path": str(_PCBNEW_SOURCE_PATH)
                }
                if code_pat:
                    res_data["code_example"] = code_pat
                return res_data

    # If class was not specified, search across all classes for this method
    if not c_clean:
        for cls_match in re.finditer(r"\nclass\s+([A-Za-z0-9_]+)\b(?:\(([^)]+)\))?:", content):
            cls_name = cls_match.group(1)
            cls_start = cls_match.start()
            next_cls = content.find("\nclass ", cls_start + 6)
            cls_block = content[cls_start:next_cls] if next_cls != -1 else content[cls_start:]
            for m_name in re.findall(r"\n[ \t]+def\s+([A-Za-z0-9_]+)\s*\(", cls_block):
                if m_name.lower() == q_lower:
                    return query_oracle(query=m_name, class_name=cls_name)

    # 7. Not Found -> Compute Fuzzy Suggestions across methods, classes, and global defs
    if c_clean:
        all_candidates = list(class_method_names)
    else:
        all_candidates = sorted(set(list(class_method_names) + global_func_names + class_names))
    suggestions = _find_similar_names(all_candidates, q_clean, limit=6)

    return {
        "success": False,
        "scope": f"{target_class}.{q_clean}" if c_clean else q_clean,
        "error": f"Symbol, method, class, or constant '{q_clean}' not found in {target_class if c_clean else 'pcbnew'}.",
        "suggestions": suggestions,
        "source_path": str(_PCBNEW_SOURCE_PATH)
    }


def _find_code_pattern(query: str) -> Optional[Dict[str, str]]:
    """Looks up matching production code snippets for a SWIG method or symbol."""
    q_norm = query.lower().replace("_", "")
    for k, pat in _SWIG_CODE_PATTERNS.items():
        k_norm = k.lower().replace("_", "")
        if k_norm == q_norm or k_norm in q_norm or q_norm in k_norm:
            return pat
    return None
