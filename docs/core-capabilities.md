# Core Capabilities

This document outlines the technical capabilities of the Kaibridge plugin. The architecture is modular, defining the boundaries and interactions between autonomous agent execution and required human intervention.

* **Intent Parsing:** Translates abstract requirements into a structured JSON representation (`design.json`).
* **Pin & Net Verification:** Extracts and verifies pin mappings directly from `.kicad_sym` files (`kicad_pins.py`) prior to schematic generation.
* **Component Sourcing:** Fetches footprints and 3D models from LCSC (via `easyeda2kicad`), and resolves native `Device:*` symbols from standard KiCad libraries.
* **Library Management:** Initializes project library tables (`sym-lib-table`, `fp-lib-table`) and constructs the local, project-specific component library.
* **Schematic Compilation:** Generates hierarchical, multi-sheet `.kicad_sch` files based on the JSON specification.
* **Electrical Validation (ERC):** Executes an Electrical Rules Check during schematic generation to validate net connections and power flag assignments.
* **Human-in-the-Loop Alignment:** Halts autonomous execution at primary transition states (Schematic Generation, Component Placement, and Auto-Routing), requiring explicit human review.
* **REST API Bridge:** Provides a local HTTP interface for executing file-lock-safe operations on the in-memory board state without restarting KiCad.
* **Native PCB Operations:** The API supports the following discrete operations: `footprint.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.set_field`, `track.add`, `track.set_width`, `via.add`, `item.delete`, `net.delete_routing`, `board.set_size`, `board.fit_outline`, `board.prep_for_route`, and `board.drc_check`.
* **Geometry Gate & Grid-Snap Placement:** Enforces deterministic, zero-overlap component placement. Coordinates are quantized to a predefined grid (default 0.5mm), and any resulting layout collisions are immediately rejected by the solver.
* **State Extraction & Diffing:** Extracts track, net, and footprint positions directly from KiCad memory, returning spatial diffs and JSON state summaries.
* **Visual Critique Loop:** Exports `.svg` snapshots of the active board state, permitting multimodal agents to evaluate component placement against spatial and thermal engineering constraints.
* **Persistence & Rollback:** Maintains pre-operation backups and snapshots, facilitating state rollback and automatic recovery of corrupted board files.
* **API Grounding:** Utilizes a lookup engine (`oracle.py`) to extract SWIG C++ method signatures from KiCad, mitigating API hallucination during custom scripting.
* **Automated Routing:** Generates board outlines (`Edge.Cuts`), purges unrouted tracks, and orchestrates headless track generation via integration with `Freerouting`.
* **Physical Validation (DRC):** Executes the internal KiCad Design Rules Checker (`kicad-cli`) to report clearance violations and unrouted nets.
* **Production Export:** Compiles manufacturing files, including Gerber ZIP, BOM CSV, and Pick & Place CPL CSV, into a dedicated production directory.
