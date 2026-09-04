"""
Kaibridge 2.0: Clean, Unified, Production-Grade MCP Server.
Direct STDIO JSON-RPC 2.0 hardware design automation engine for KiCad 10.
Exposes complete end-to-end design, placement, visual critique, routing, and manufacturing tools.
"""
from __future__ import annotations

import os
import sys
import json
import time
import re
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List

#Ensure kaibridge package is in sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kaibridge.core import load_paths, load_cli, load_kicad_python, find_freerouting_jar, query_oracle
from kaibridge.sourcing import fetch_lcsc, LibIndex, lookup_by_lcsc, search_by_query, search_basic_passives, recommend_kicad_part
from kaibridge.schematic import compile_schematic
from kaibridge.pcb import (
    sync_schematic_to_pcb,
    apply_ops,
    autoplace_board,
    relax_board,
    render_pcb_preview,
    render_schematic_preview,
    route_board,
    unroute_board,
    add_ground_plane,
    run_drc,
    export_production_files,
    get_board_state,
    placement_audit,
    snapshot_board,
    diff_board,
    restore_snapshot
)

SERVER_INFO = {
    "name": "kaibridge-mcp-server",
    "version": "2.0.1"
}

TOOLS_LIST = [
    {
        "name": "kaibridge_api_oracle",
        "description": "Live SWIG API Oracle: inspects live pcbnew classes, methods, argument types, inheritance trees, and docstrings for the host KiCad version. Eliminates API guessing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Method or function name to inspect (e.g. 'ExportSpecctraDSN', 'Delete', 'SetPadConnection')."},
                "class_name": {"type": "string", "description": "Optional class name (e.g. 'BOARD', 'ZONE', 'FOOTPRINT', 'GLOBAL')."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "kaibridge_fetch_lcsc_component",
        "description": "Download component symbol (.kicad_sym), footprint (.kicad_mod), and 3D model from LCSC / EasyEDA with pacing & retry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "lcsc_id": {"type": "string", "description": "LCSC Part Number (e.g. 'C6186' or 'C6186, C46749')."},
                "lib_name": {"type": "string", "description": "Target library nickname (default: 'kaibridge')."}
            },
            "required": ["project_dir", "lcsc_id"]
        }
    },
    {
        "name": "kaibridge_lookup_lcsc_part",
        "description": "Offline JLCPCB parts resolver: queries 16,607 local parts in <1ms without internet. Resolves LCSC IDs, detects JLCPCB 'Basic Parts' (0-fee), and returns ERC-safe KiCad native component definitions with exact LCSC fields.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Fuzzy search keyword (e.g. 'TCRT5000', 'AMS1117', 'CH340', 'ESP32', 'MOSFET') in local offline database (<1ms)."},
                "lcsc_id": {"type": "string", "description": "Optional LCSC Part Number (e.g. 'C17513', 'C6186') for exact lookup."},
                "component_type": {"type": "string", "description": "Component type ('R', 'C', 'LED', 'D', 'REG')."},
                "value": {"type": "string", "description": "Component value (e.g. '10k', '100nF', 'Green')."},
                "package": {"type": "string", "description": "SMD package size (e.g. '0805', '0603', 'SOD-123', default: '0805')."},
                "basic_only": {"type": "boolean", "description": "Filter strictly for JLCPCB Basic Parts (default: true)."}
            }
        }
    },
    {
        "name": "kaibridge_query_symbol_pins",
        "description": "Extract pin numbers, names, electrical types, and default footprint from a symbol in .kicad_sym or stock KiCad libraries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "lib_id": {"type": "string", "description": "Symbol library ID (e.g. 'Device:R', 'kaibridge:NE555P')."}
            },
            "required": ["project_dir", "lib_id"]
        }
    },
    {
        "name": "kaibridge_build_schematic",
        "description": "Compile design.json into hierarchical KiCad schematics (.kicad_sch) and validate via automated ERC.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "design_json_path": {"type": "string", "description": "Optional path to design.json."},
                "apply_netclasses": {"type": "boolean", "description": "Whether to apply netclasses into .kicad_pro (default: true)."},
                "run_erc_check": {"type": "boolean", "description": "Whether to run Electrical Rules Check (ERC) (default: true)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_render_schematic_preview",
        "description": "Export high-resolution vector SVG or PDF of the schematic for AI visual critique and human inspection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "format": {"type": "string", "enum": ["svg", "pdf"], "description": "Output format ('svg' or 'pdf', default: 'svg')."},
                "exclude_drawing_sheet": {"type": "boolean", "description": "Whether to omit title block and frame (default: true)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_sync_to_pcb",
        "description": "Headless F8: Automatically instantiates footprints in .kicad_pcb and binds nets and ratsnest.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_apply_ops_layout",
        "description": "Execute structured operations payload (ops.json): place footprints, delete parts, unroute, add tracks, add vias, edge cuts, silkscreen text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "ops": {
                    "type": "array",
                    "description": "List of operations (e.g. [{'op': 'footprint.place', 'ref': 'U1', 'x': 25, 'y': 20, 'rot': 0}, {'op': 'board.fit_outline', 'margin': 5.0}])"
                },
                "board": {
                    "type": "object",
                    "description": "Board metadata options."
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, simulates layout operations and collision checks in memory without modifying the board file on disk."
                }
            },
            "required": ["project_dir", "ops"]
        }
    },
    {
        "name": "kaibridge_autoplace_pcb",
        "description": "Smart Geometric Autoplacer with collision avoidance and automatic Edge.Cuts board outline generation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "board_width_mm": {"type": "number", "description": "Target board width in mm (default: 50.0)."},
                "board_height_mm": {"type": "number", "description": "Target board height in mm (default: 40.0)."},
                "pitch_mm": {"type": "number", "description": "Pitch between components in mm (default: 8.0)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_render_pcb_preview",
        "description": "Render vector SVG snapshot, top-view PNG render, and structural board geometry analytics for multimodal visual AI critique.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_route_pcb",
        "description": "Headless Freerouting 2.4.1 Autorouter: Exports Specctra DSN, runs Freerouting 2.4.1 with edge clearance and strict DRC, and imports SES into .kicad_pcb.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "track_width_mm": {"type": "number", "description": "Track width in mm (default: 0.25)."},
                "timeout_sec": {"type": "integer", "description": "Router timeout in seconds (default: 300)."},
                "copper_edge_clearance_um": {"type": "integer", "description": "Board edge outline clearance in micrometers (default: 150 um matching JLCPCB)."},
                "strict_drc": {"type": "boolean", "description": "Enforce strict DRC constraints during routing (default: true)."},
                "max_passes": {"type": "integer", "description": "Optional maximum auto-routing optimization passes (e.g. 10)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_unroute_pcb",
        "description": "Rip-up / delete copper tracks, vias, and optional copper pour zones from the PCB (entire board, specific net, or specific layer).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "net": {"type": "string", "description": "Optional specific net name to rip up (e.g. 'GND'). If omitted, unroutes all nets."},
                "layer": {"type": "string", "description": "Optional specific layer ('F.Cu' or 'B.Cu')."},
                "remove_zones": {"type": "boolean", "description": "Whether to also remove filled copper zones / ground planes matching the net/layer (default: false)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_add_ground_plane",
        "description": "Add and fill copper ground pour zone (GND) across the board with specified clearance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "net": {"type": "string", "description": "Net name (default: 'GND')."},
                "layer": {"type": "string", "description": "Layer ('B.Cu' or 'F.Cu', default: 'B.Cu')."},
                "clearance_mm": {"type": "number", "description": "Clearance in mm (default: 0.3)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_run_drc",
        "description": "Run headless Design Rules Check (DRC) via kicad-cli and return violation reports.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_export_production",
        "description": "Generate 100% JLCPCB-compatible production bundle: Gerber ZIP, Drill, BOM CSV, and CPL CSV.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_get_board_state",
        "description": "Extract complete structured board state: footprints (with pads, nets, courtyards), tracks, vias, zones, design rules, and netclasses as machine-readable JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "mode": {"type": "string", "enum": ["summary", "full"], "description": "'summary' (footprints+nets only) or 'full' (all tracks/vias/zones). Default: 'summary'."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_inspect_board",
        "description": "Extract complete structured board state (alias for kaibridge_get_board_state): footprints, tracks, vias, zones, and rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "mode": {"type": "string", "enum": ["summary", "full"], "description": "'summary' (footprints+nets only) or 'full' (all tracks/vias/zones). Default: 'summary'."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_placement_audit",
        "description": "Pre-placement geometry gate: detects courtyard overlaps, components outside board outline, and netclass validation. Returns route_ready flag.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "clearance": {"type": "number", "description": "Clearance margin in mm (default: 0.25)."},
                "edge_margin": {"type": "number", "description": "Board edge margin in mm (default: 0.5)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_audit_placement",
        "description": "Pre-placement geometry gate (alias for kaibridge_placement_audit): detects courtyard overlaps and out-of-boundary components.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "clearance": {"type": "number", "description": "Clearance margin in mm (default: 0.25)."},
                "edge_margin": {"type": "number", "description": "Board edge margin in mm (default: 0.5)."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_snapshot_board",
        "description": "Capture timestamped board state snapshot and backup .kicad_pcb for undo/rollback and structural diffing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "tag": {"type": "string", "description": "Optional human-readable tag (e.g. 'pre_route', 'post_place')."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_diff_board",
        "description": "Compute structural diff between two board snapshots: added/removed/modified footprints, tracks, vias, and zones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "snapshot_a": {"type": "string", "description": "Path or filename of the 'before' snapshot. If omitted, uses second-most-recent."},
                "snapshot_b": {"type": "string", "description": "Path or filename of the 'after' snapshot. If omitted, diffs against live board."},
                "tag_a": {"type": "string", "description": "Optional tag of the 'before' snapshot."},
                "tag_b": {"type": "string", "description": "Optional tag of the 'after' snapshot."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_restore_snapshot",
        "description": "Restore .kicad_pcb state from a previously captured snapshot checkpoint by tag or filename.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path to the KiCad project directory."},
                "tag": {"type": "string", "description": "Tag used when creating snapshot (e.g. 'pre_route')."},
                "snapshot_file": {"type": "string", "description": "Optional direct path or filename of the snapshot."}
            },
            "required": ["project_dir"]
        }
    },
    {
        "name": "kaibridge_init_project",
        "description": "Bootstrap a new KiCad 10 project headlessly: creates project directory, .kicad_pro, empty .kicad_pcb, library tables, and kaibridge_dump/ folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Absolute path where the new KiCad project will be created."},
                "project_name": {"type": "string", "description": "Name of the project. If omitted, the folder name is used."}
            },
            "required": ["project_dir"]
        }
    }
]


def _init_project(project_dir: str | Path, project_name: Optional[str] = None) -> Dict[str, Any]:
    proj_path = Path(project_dir).resolve()
    proj_path.mkdir(parents=True, exist_ok=True)
    stem = project_name.strip() if project_name and project_name.strip() else proj_path.name

    from kicad_lib_init import init_libraries
    init_res = init_libraries(proj_path, "kaibridge")

    pro_file = proj_path / f"{stem}.kicad_pro"
    pcb_file = proj_path / f"{stem}.kicad_pcb"

    return {
        "success": init_res.get("success", True),
        "project_dir": str(proj_path),
        "project_name": stem,
        "pro_file": str(pro_file),
        "pcb_file": str(pcb_file),
        "symbol_file": init_res.get("symbol_file"),
        "pretty_dir": init_res.get("pretty_dir")
    }


def handle_tool_call(name: str, args: dict) -> dict:
    proj_dir = args.get("project_dir", "")
    proj_path = Path(proj_dir).resolve() if proj_dir else Path.cwd()

    try:
        if name == "kaibridge_api_oracle":
            q = args.get("query", "")
            cls_name = args.get("class_name")
            return query_oracle(query=q, class_name=cls_name)

        elif name == "kaibridge_fetch_lcsc_component":
            raw_ids = args.get("lcsc_id", "")
            lib_name = args.get("lib_name", "kaibridge")
            part_list = [p.strip() for p in raw_ids.split(",") if p.strip()] if isinstance(raw_ids, str) else list(raw_ids)
            delay_sec = float(args.get("delay_sec", 2.0))
            results = []
            for i, part_id in enumerate(part_list):
                if i > 0 and delay_sec > 0:
                    time.sleep(delay_sec)
                results.append(fetch_lcsc(proj_path, part_id, lib_name))
            return {"success": all(r.get("success", False) for r in results), "results": results}

        elif name == "kaibridge_lookup_lcsc_part":
            query = args.get("query") or args.get("search") or args.get("q")
            lcsc_id = args.get("lcsc_id")
            c_type = args.get("component_type")
            val = args.get("value")
            pkg = args.get("package", "0805")
            basic_only = args.get("basic_only", True)

            # 1. Direct fuzzy query search (e.g. 'TCRT5000', 'AMS1117', 'CH340')
            if query:
                results = search_by_query(query, limit=10)
                return {
                    "success": True,
                    "query": query,
                    "count": len(results),
                    "results": results
                }

            # 2. If lcsc_id is not a standard C-number (e.g. user passed 'TCRT5000' as lcsc_id), fallback to fuzzy query
            if lcsc_id and not re.match(r"^C\d+$", str(lcsc_id).strip(), re.IGNORECASE):
                results = search_by_query(str(lcsc_id).strip(), limit=10)
                if results:
                    return {
                        "success": True,
                        "query": lcsc_id,
                        "count": len(results),
                        "results": results
                    }

            # 3. Exact LCSC ID lookup
            if lcsc_id and not c_type:
                part_info = lookup_by_lcsc(lcsc_id)
                if not part_info:
                    # Try fuzzy fallback
                    fuzzy = search_by_query(str(lcsc_id).strip(), limit=5)
                    if fuzzy:
                        return {"success": True, "part": fuzzy[0], "alternatives": fuzzy}
                    return {"success": False, "error": f"Part {lcsc_id} not found in local database."}
                return {"success": True, "part": part_info}

            if c_type and val:
                rec = recommend_kicad_part(c_type, val, package=pkg, preferred_lcsc=lcsc_id)
                alternatives = search_basic_passives(c_type, val, package=pkg)
                return {
                    "success": True,
                    "recommended": rec,
                    "basic_parts_found": len(alternatives),
                    "alternatives": alternatives
                }

            if lcsc_id:
                part_info = lookup_by_lcsc(lcsc_id)
                return {"success": bool(part_info), "part": part_info}

            return {"success": False, "error": "Please provide either 'query', 'lcsc_id' or ('component_type' and 'value')."}

        elif name == "kaibridge_query_symbol_pins":
            lib_id = args.get("lib_id", "")
            idx = LibIndex(proj_path)
            sym = idx.symbol(lib_id)
            
            # Extract default footprint from symbol S-expression properties
            default_fp = ""
            try:
                for c in getattr(sym, "node", [])[2:]:
                    if isinstance(c, list) and len(c) > 2 and c[0] == "property" and c[1] == "Footprint":
                        default_fp = str(c[2]).strip("\"")
                        break
            except Exception:
                pass

            pins_data = {}
            for num, p in sym.pins.items():
                pos_x, pos_y = 0.0, 0.0
                if hasattr(p, "offset") and isinstance(p.offset, (tuple, list)):
                    pos_x = float(p.offset[0]) if len(p.offset) > 0 else 0.0
                    pos_y = float(p.offset[1]) if len(p.offset) > 1 else 0.0
                elif hasattr(p, "x"):
                    pos_x = float(p.x)
                    pos_y = float(getattr(p, "y", 0.0))

                pins_data[num] = {
                    "name": p.name,
                    "type": p.etype,
                    "pos": [pos_x, pos_y],
                    "rot": getattr(p, "rot", 0)
                }
            return {
                "success": True,
                "lib_id": lib_id,
                "symbol_name": sym.name,
                "default_footprint": default_fp,
                "pin_count": len(pins_data),
                "pins": pins_data
            }

        elif name == "kaibridge_build_schematic":
            design_json = args.get("design_json_path")
            apply_nc = args.get("apply_netclasses", True)
            run_erc = args.get("run_erc", args.get("run_erc_check", True))
            return compile_schematic(
                project_dir=proj_path,
                design_file=design_json,
                apply_netclasses=apply_nc,
                run_erc=run_erc
            )

        elif name == "kaibridge_render_schematic_preview":
            fmt = args.get("format", "svg")
            no_sheet = args.get("exclude_drawing_sheet", True)
            return render_schematic_preview(proj_path, fmt=fmt, exclude_drawing_sheet=no_sheet)

        elif name == "kaibridge_sync_to_pcb":
            return sync_schematic_to_pcb(proj_path)

        elif name == "kaibridge_apply_ops_layout":
            ops = args.get("ops", [])
            board_meta = args.get("board", {})
            dry_run = bool(args.get("dry_run", False))
            payload = {"ops": ops, "board": board_meta, "dry_run": dry_run} if (board_meta or dry_run) else ops
            return apply_ops(proj_path, payload, dry_run=dry_run)

        elif name == "kaibridge_autoplace_pcb":
            w = float(args.get("board_width_mm", 50.0))
            h = float(args.get("board_height_mm", 40.0))
            pitch = float(args.get("pitch_mm", 8.0))
            return autoplace_board(proj_path, board_width_mm=w, board_height_mm=h, pitch_mm=pitch)

        elif name == "kaibridge_render_pcb_preview":
            return render_pcb_preview(proj_path)

        elif name == "kaibridge_route_pcb":
            tw = float(args.get("track_width_mm", 0.25))
            timeout = int(args.get("timeout_sec", 300))
            clr_um = int(args.get("copper_edge_clearance_um", 150))
            strict = bool(args.get("strict_drc", True))
            mp = int(args["max_passes"]) if "max_passes" in args and args["max_passes"] is not None else None
            return route_board(proj_path, track_width_mm=tw, timeout_sec=timeout, copper_edge_clearance_um=clr_um, strict_drc=strict, max_passes=mp)

        elif name == "kaibridge_unroute_pcb":
            net = args.get("net")
            layer = args.get("layer")
            rem_zones = args.get("remove_zones", False)
            return unroute_board(proj_path, net=net, layer=layer, remove_zones=rem_zones)

        elif name == "kaibridge_add_ground_plane":
            net = args.get("net", "GND")
            layer = args.get("layer", "B.Cu")
            clr = float(args.get("clearance_mm", 0.3))
            return add_ground_plane(proj_path, net=net, layer=layer, clearance_mm=clr)

        elif name == "kaibridge_run_drc":
            return run_drc(proj_path)

        elif name == "kaibridge_export_production":
            return export_production_files(proj_path)

        elif name in ("kaibridge_get_board_state", "kaibridge_inspect_board"):
            mode = args.get("mode", "summary")
            return get_board_state(proj_path, mode=mode)

        elif name in ("kaibridge_placement_audit", "kaibridge_audit_placement"):
            clr = float(args.get("clearance", 0.25))
            em = float(args.get("edge_margin", 0.5))
            return placement_audit(proj_path, clearance=clr, edge_margin=em)

        elif name == "kaibridge_snapshot_board":
            tag = args.get("tag", "")
            return snapshot_board(proj_path, tag=tag)

        elif name == "kaibridge_diff_board":
            sa = args.get("snapshot_a") or args.get("tag_a")
            sb = args.get("snapshot_b") or args.get("tag_b")
            return diff_board(proj_path, snapshot_a=sa, snapshot_b=sb, tag_a=args.get("tag_a"), tag_b=args.get("tag_b"))

        elif name == "kaibridge_restore_snapshot":
            tag = args.get("tag")
            snap_file = args.get("snapshot_file")
            return restore_snapshot(proj_path, tag=tag, snapshot_file=snap_file)

        elif name == "kaibridge_init_project":
            pname = args.get("project_name")
            return _init_project(proj_path, pname)

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {}}
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS_LIST}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            call_res = handle_tool_call(tool_name, tool_args)
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(call_res, indent=2)}]
                }
            }
        elif method == "ping":
            res = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        else:
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()




