# Core Capabilities (v2.2.0)

This document outlines the technical capabilities of the Kaibridge hardware automation bridge. The architecture is modular, defining the boundaries and interactions between autonomous agent execution and human engineering review.

* **Modular Execution Modes:** Supports both Model Context Protocol (MCP) server integration (`server.py`) and standalone command-line utilities for headless KiCad execution.
* **Standalone CLI Suite (9 Canonical Tools):** Dedicated command-line utilities (`kicad_lib_init.py`, `kicad_pins.py`, `json2sch.py`, `kicad_pcb_sync.py`, `kicad_planar_optimizer.py`, `kicad_layout.py`, `pcb_snapshot.py`, `kicad_route.py`, `export_jlcpcb.py`) for automated execution across all 9 pipeline stages.
* **In-Memory Planar Optimizer (`kicad_planar_optimizer.py`):** Simulated annealing placement engine using Kruskal's MST and 2D segment intersections to minimize airwire crossings in memory.
* **Two-Stage Placement (S7A / S7B):** Stage 7A executes mathematical placement via `kicad_planar_optimizer.py`; Stage 7B executes visual audit via `pcb_snapshot.py`.
* **3-Tier Routing Protocol:** Pre-places GND dogbone vias, routes signals on F.Cu without signal vias, and floods B.Cu ground plane with 0 DRC violations.
* **DSN Clearance Harmonization:** Matches default signal clearance to power pad clearance to prevent false DRC violations.
* **Intent Parsing:** Translates abstract natural language requirements into a structured JSON circuit netlist (`design.json`).
* **Pin & Net Verification:** Extracts and verifies exact pin mappings directly from `.kicad_sym` files prior to schematic generation via `kicad_pins.py`.
* **Component Sourcing & Offline Search:** Fetches footprints and 3D models from LCSC (via `easyeda2kicad`), resolves native `Device:*` symbols from standard KiCad libraries, and queries an offline SQLite database (`easyeda-std.elib`) in < 1ms with upfront LCSC C-Part ID binding.
* **Mechanical Footprint Auto-Sanitization:** When fetching footprints from EasyEDA/LCSC, the engine automatically detects unnumbered mechanical alignment post holes where pad size equals drill diameter (`size == drill`) and converts them from `thru_hole` to `np_thru_hole` with `*.Mask` layers, preventing 0-annular ring width DRC violations.
* **Library Management:** Initializes project library tables (`sym-lib-table`, `fp-lib-table`) and constructs the local, project-specific component library.
* **Schematic Compilation:** Generates hierarchical, multi-sheet `.kicad_sch` files based on the JSON specification.
* **Electrical Validation (ERC):** Executes an Electrical Rules Check during schematic generation to validate net connections and power flag assignments.
* **Headless F8 PCB Synchronization:** Programmatically instantiates footprints, assigns references/values, and attaches all net connections & ratsnest directly into `.kicad_pcb` without launching the KiCad GUI.
* **Human-in-the-Loop Alignment:** Halts autonomous execution at primary transition checkpoints (Implementation Plan, Schematic Review, Component Placement, and Auto-Routing), requiring explicit human review.
* **Adversarial Red-Team Engineering Gate (ART-Gate):** Executes a bounded adversarial engineering verification pipeline: Design Contract extraction (STATED / INFERRED / UNKNOWN requirement classification with impact rating), followed by a 3-layer attack (Requirement Attack, Universal EE & DFM Gate, and Domain-Specific Scenario Analysis).
* **MCP Server (23 Dedicated Tools):** Exposes a Model Context Protocol (MCP) server over STDIO JSON-RPC 2.0 providing 23 specialized tools that give AI agents complete programmatic control over circuit design, sourcing, simulation, routing, and fabrication.
* **Discrete Layout Operations (17 Primitives in `apply_ops`):** Within the layout tool (`kaibridge_apply_ops_layout`), the engine executes 17 discrete, board-level primitives with 0.5mm grid snapping and in-memory dry-run collision checks: `footprint.place`, `array.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.unlock`, `footprint.set_field`, `footprint.delete` (or `item.delete`), `board.set_size`, `board.fit_outline`, `board.prep_for_route`, `track.add`, `track.set_width`, `via.add`, `zone.delete`, `zone.refill`, and `net.delete_routing`.
* **Linear Array Placement (`array.place`):** Synthesizes multi-channel repeating component arrays (sensor arrays, LED clusters, resistor packs) in a single declarative command with exact pitch, axis, and 0.5mm quantization.
* **Geometry Gate & Grid-Snap Placement:** Enforces deterministic, zero-overlap component placement. Coordinates are quantized to a clean 0.5mm grid, and any resulting layout collisions are rejected by the solver.
* **In-Memory Simulation (`dry_run`):** Simulates layout operations and evaluates bounding-box collisions in memory with a zero-disk-write guarantee before writing changes to disk.
* **Critical Component & RF/Crystal Locking Protocol (`LCK-01`):** Mandates pre-routing locking (`footprint.lock` or `"locked": true`) of crystal oscillators, RF matching networks, and edge connectors, ensuring Freerouting never displaces sensitive analog and high-frequency geometries.
* **State Extraction & Diffing:** Extracts track, net, and footprint positions directly from KiCad memory, returning spatial diffs and JSON state summaries.
* **Visual Critique Loop:** Exports `.svg` and `.png` snapshots of the active board state, permitting multimodal agents to evaluate component placement against spatial and thermal engineering constraints.
* **Persistence & Rollback:** Maintains timestamped board snapshots with SHA-256 fingerprints, facilitating state rollback and automatic recovery of corrupted board files.
* **Live API Grounding (Oracle):** Directly introspects KiCad's host `pcbnew.py` C++ SWIG wrapper in < 4ms to resolve exact method signatures, classes, and constants (`ZONE_CONNECTION_FULL`), mitigating API hallucination during custom scripting.
* **Pre-Flight DSN Audit:** Audits Specctra `.dsn` files in < 2ms to verify track widths, netclasses, and clearances before launching autorouting.
* **Automated Routing:** Generates board outlines (`Edge.Cuts`), enforces differential netclass widths (power vs signal) and 150µm edge clearance, purges unrouted tracks, and orchestrates headless track generation via integration with Freerouting 2.4.1.
* **Ground Copper Pouring:** Pours and fills ground planes on `B.Cu` and `F.Cu` with exact `Edge.Cuts` boundary clipping and solid thermal pad connections.
* **Physical Validation (DRC):** Executes the internal KiCad Design Rules Checker (`kicad-cli`) to report clearance violations and unrouted nets.
* **Production Export:** Compiles manufacturing files, including Gerber ZIP, BOM CSV (with upfront LCSC IDs), and Pick & Place CPL CSV, into `<PROJECT_DIR>/production_output/`.
