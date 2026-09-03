#Core Capabilities

This document outlines the technical capabilities of the Kaibridge engine. The architecture is modular, defining the boundaries and interactions between autonomous agent execution and required human intervention.

* **Intent Parsing:** Translates abstract requirements into a structured JSON representation (`design.json`).
* **Pin & Net Verification:** Extracts and verifies pin mappings directly from `.kicad_sym` files prior to schematic generation.
* **Component Sourcing:** Fetches footprints and 3D models from LCSC (via `easyeda2kicad`), resolves native `Device:*` symbols from standard KiCad libraries, and queries an offline SQLite database (`easyeda-std.elib`) in < 1ms with upfront LCSC C-Part ID binding.
* **Library Management:** Initializes project library tables (`sym-lib-table`, `fp-lib-table`) and constructs the local, project-specific component library.
* **Schematic Compilation:** Generates hierarchical, multi-sheet `.kicad_sch` files based on the JSON specification.
* **Electrical Validation (ERC):** Executes an Electrical Rules Check during schematic generation to validate net connections and power flag assignments.
* **Human-in-the-Loop Alignment:** Halts autonomous execution at primary transition states (Implementation Plan, Schematic Generation, Component Placement, and Auto-Routing), requiring explicit human review.
* **Headless MCP Bridge (22 Dedicated Tools):** Exposes a Model Context Protocol (MCP) server over STDIO JSON-RPC 2.0 providing 22 specialized tools that give AI agents complete programmatic control over circuit design, sourcing, simulation, routing, and fabrication without requiring the KiCad GUI.
* **Discrete Layout Operations (16 Primitives in `apply_ops`):** Within the layout tool (`kaibridge_apply_ops_layout`), the engine executes 16 discrete, board-level primitives with 0.5mm grid snapping and in-memory dry-run collision checks: `footprint.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.unlock`, `footprint.set_field`, `footprint.delete` (or `item.delete`), `board.set_size`, `board.fit_outline`, `board.prep_for_route`, `track.add`, `track.set_width`, `via.add`, `zone.delete`, `zone.refill`, and `net.delete_routing`.
* **Geometry Gate & Grid-Snap Placement:** Enforces deterministic, zero-overlap component placement. Coordinates are quantized to a predefined grid (default 0.5mm), and any resulting layout collisions are rejected by the solver.
* **In-Memory Simulation (`dry_run`):** Simulates layout operations and evaluates bounding-box collisions in memory with a zero-disk-write guarantee before writing changes to disk.
* **Physics-Based Relaxation:** Iteratively separates colliding component courtyards using a 2D spring repulsion solver (`kaibridge_auto_relax_layout`).
* **State Extraction & Diffing:** Extracts track, net, and footprint positions directly from KiCad memory, returning spatial diffs and JSON state summaries.
* **Visual Critique Loop:** Exports `.svg` and `.png` snapshots of the active board state, permitting multimodal agents to evaluate component placement against spatial and thermal engineering constraints.
* **Persistence & Rollback:** Maintains timestamped board snapshots with SHA-256 fingerprints, facilitating state rollback and automatic recovery of corrupted board files.
* **Live API Grounding (Oracle):** Directly introspects KiCad's host `pcbnew.py` C++ SWIG wrapper in < 4ms to resolve exact method signatures, classes, and constants (`ZONE_CONNECTION_FULL`), mitigating API hallucination during custom scripting.
* **Pre-Flight DSN Audit:** Audits Specctra `.dsn` files in < 2ms to verify track widths, netclasses, and clearances before launching autorouting.
* **Automated Routing:** Generates board outlines (`Edge.Cuts`), enforces differential netclass widths (power vs signal) and 150µm edge clearance, purges unrouted tracks, and orchestrates headless track generation via integration with Freerouting 2.4.1.
* **Ground Copper Pouring:** Pours and fills ground planes on `B.Cu` and `F.Cu` with exact `Edge.Cuts` boundary clipping and solid thermal pad connections.
* **Physical Validation (DRC):** Executes the internal KiCad Design Rules Checker (`kicad-cli`) to report clearance violations and unrouted nets.
* **Production Export:** Compiles manufacturing files, including Gerber ZIP, BOM CSV (with upfront LCSC IDs), and Pick & Place CPL CSV, into a dedicated production directory.
