#Kaibridge 2.0 Command & Tool Reference

This document describes the **22 dedicated MCP tools** exposed by `server.py` via native STDIO JSON-RPC 2.0. These form the primary autonomous interface for AI agents operating in Antigravity IDE, Claude Desktop, Cursor, or any MCP-compatible environment.

---

##1. Complete MCP Tool Catalog (22 Tools)

All project-level tools accept `project_dir` as their first parameter (absolute path to the KiCad project folder).

###A. Project & Component Sourcing (4 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_init_project` | Create project folder, `.kicad_pro`, empty `.kicad_pcb`, sym-lib/fp-lib tables, and `kaibridge_dump/`. |
| `kaibridge_lookup_lcsc_part` | Fast (<1ms) offline query of JLCPCB Basic Parts catalog from local SQLite DB by query, category, or package. |
| `kaibridge_fetch_lcsc_component` | Download symbol, footprint, and 3D model from EasyEDA/LCSC into local project libraries with retry. |
| `kaibridge_query_symbol_pins` | Extract exact pin numbers, names, electrical types, and default footprints from `.kicad_sym`. |

###B. Schematic Compilation & Preview (2 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_build_schematic` | Compile declarative `design.json` into hierarchical `.kicad_sch` with netclasses, and run headless ERC. |
| `kaibridge_render_schematic_preview` | Export high-resolution vector SVG snapshot of compiled schematic for multimodal visual review. |

###C. Headless PCB Layout & Physics (6 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_sync_to_pcb` | Headless F8: instantiate footprints into `.kicad_pcb` and bind nets/ratsnest. |
| `kaibridge_apply_ops_layout` | Apply discrete placement operations (`ops.json`) with 0.5mm grid snap and in-memory `dry_run` simulation. |
| `kaibridge_autoplace_pcb` | Execute geometric component autoplacement based on net topology and connector perimeters. |
| `kaibridge_auto_relax_layout` | Physics-based 2D spring repulsion solver to iteratively separate overlapping component courtyards. |
| `kaibridge_render_pcb_preview` | Export top-view PNG and vector SVG layout snapshots, returning structural board analytics. |
| `kaibridge_audit_placement` | Audit component boundaries, edge clearance violations, and courtyard collisions against the Geometry Gate. |

###D. Autorouting & Copper Zones (3 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_route_pcb` | Headless Freerouting 2.4.1 autorouting with DSN track width audit, 150µm edge keepout, and strict DRC. |
| `kaibridge_unroute_pcb` | Rip up / delete copper tracks, vias, and optional copper zones. |
| `kaibridge_add_ground_plane` | Add and fill ground copper zones (`B.Cu` / `F.Cu`) with exact `Edge.Cuts` boundary clipping and solid thermal relief (`ZONE_CONNECTION_FULL`). |

###E. Structural Introspection & Rollback (5 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_inspect_board` | Deep structural inspection of footprints, tracks, vias, zones, and layer dimensions in memory. |
| `kaibridge_get_board_state` | Extract lightweight JSON summary of board components, bounding boxes, and routing status. |
| `kaibridge_snapshot_board` | Create timestamped board snapshot with SHA-256 fingerprint for recovery. |
| `kaibridge_diff_board` | Compute spatial and topological diff between two board snapshots or against active board. |
| `kaibridge_restore_snapshot` | Deterministic rollback to a previous snapshot state if layout or routing fails. |

###F. Live API Grounding & Verification (2 Tools)
| Tool | Purpose |
|---|---|
| `kaibridge_api_oracle` | Live introspection of KiCad host `pcbnew.py` C++ SWIG wrapper (<4ms) to query methods, classes, and constants. |
| `kaibridge_run_drc` | Run headless Design Rules Check via `kicad-cli` and parse clearance violations and unrouted airwires. |

###G. Production & Manufacturing (1 Tool)
| Tool | Purpose |
|---|---|
| `kaibridge_export_production` | Generate 100% factory-ready JLCPCB bundle (Gerber ZIP, Drill, BOM CSV with LCSC IDs, and CPL Pick & Place CSV). |

---

##2. Layout Ops Reference (`kaibridge_apply_ops_layout`)

The layout engine accepts a list of discrete operations via `ops.json`. Coordinates are automatically quantized to a **0.5mm grid**.

###Supported Discrete Operations (16 Ops):
```text
footprint.place      footprint.move       footprint.rotate     footprint.lock
footprint.unlock     footprint.set_field  footprint.delete     board.set_size
board.fit_outline    board.prep_for_route track.add            track.set_width
via.add              zone.delete          zone.refill          net.delete_routing
```

###In-Memory Simulation (`dry_run`):
Pass `"dry_run": true` to simulate layout operations in memory and detect courtyard collisions without writing changes to disk:
```json
{
  "dry_run": true,
  "ops": [
    { "op": "footprint.place", "ref": "U1", "x": 25.0, "y": 20.0, "rot": 0 },
    { "op": "footprint.place", "ref": "C1", "x": 22.0, "y": 20.0, "rot": 90 }
  ]
}
```

###Key Rules:
- `board.set_size`: Parameters `width`, `height`, `origin_x`, `origin_y` (all in mm). Creates clean rectangular `Edge.Cuts`.
- `board.fit_outline`: Parameter `margin` (mm). Automatically fits `Edge.Cuts` around placed footprints.
- `footprint.set_field`: Parameters `ref`, `field` (e.g. `"LCSC"`, `"Value"`), and `value`.
- `track.set_width`: Can target by `net`, `netclass`, `uuid`, or globally across all tracks.

---

##3. Python Module Execution (`kaibridge`)

All tools are natively accessible in Python or via MCP server:

```python
from kaibridge.pcb import apply_ops, route_board, add_ground_plane, export_production_files
from kaibridge.schematic import build_schematic
from kaibridge.sourcing import lookup_parts, fetch_lcsc_component

#Build schematic
res = build_schematic(project_dir="C:/projects/demo", design_data=design_json)

#Layout operations with simulation
res = apply_ops(pcb_path="C:/projects/demo/demo.kicad_pcb", ops=ops_list, dry_run=True)

#Headless routing (Freerouting 2.4.1)
res = route_board(project_dir="C:/projects/demo")
```
