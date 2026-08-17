# Core Capabilities

The abIDE platform provides a comprehensive, end-to-end autonomous workflow. Below are the modular capabilities that make up the robust pipeline:

* **Intent Parsing:** Converts natural language prompts into a strict, structurally valid JSON intent representation (`design.json`).
* **Pin & Net Verification:** Extracts and verifies exact pin mappings directly from `.kicad_sym` files (`kicad_pins.py`) to strictly enforce correct wire connections.
* **Component Sourcing:** Automatically fetches and imports real-world footprints and 3D models from LCSC via `easyeda2kicad`, while intelligently resolving native `Device:*` symbols directly from KiCad's standard libraries.
* **Library Management:** Automatically initializes project library tables (`sym-lib-table`, `fp-lib-table`) and curates local, verifiable component libraries for the project.
* **Schematic Compilation:** Translates the abstract JSON intent directly into native, hierarchical, multi-sheet `.kicad_sch` schematic files.
* **Electrical Validation (ERC):** Enforces a strict Electrical Rules Check loop during the schematic phase to validate net connections and power flags before human handoff.
* **Human-in-the-Loop Alignment:** Halts autonomous execution at major checkpoints (Schematic Gen → Placement → Routing), requiring explicit human review and prioritizing specific spatial guidelines (e.g., symmetry, connector locations).
* **Atomic REST API:** Exposes file-lock-safe atomic operations via a local HTTP bridge to execute live layout changes in memory without constantly restarting KiCad.
* **14 Native PCB Operations:** The REST API strictly supports: `footprint.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.set_field`, `track.add`, `track.set_width`, `via.add`, `item.delete`, `net.delete_routing`, `board.set_size`, `board.fit_outline`, `board.prep_for_route`, and `board.drc_check`.
* **Geometry Gate:** Employs an internal 2D Minimum Translation Vector (MTV) collision solver to deterministically prevent component overlaps and enforce courtyard boundaries before committing physical placement.
* **State Extraction & Diffing:** Dynamically reads live KiCad memory (bypassing file locks) to extract track, net, and footprint positions, providing the AI with accurate spatial diffs and JSON state summaries.
* **Visual Critique Loop:** Renders live `.svg` snapshots of the board state so multimodal AI agents can physically "see" decoupling capacitor proximities, oscillator loop areas, and component alignments against strict engineering rules.
* **Persistence & Rollback:** Automatically captures pre-operation backups and snapshots, enabling instant state rollback upon error and automatic recovery of corrupted 0-byte `.kicad_pcb` files.
* **Deterministic Grounding:** Features a multiple-inheritance-aware lookup engine (`oracle.py`) to dynamically extract exact SwigPyObject API method signatures directly from KiCad, strictly preventing AI hallucination during custom Python scripting.
* **Automated Routing:** Automates board outline generation (`Edge.Cuts`), purges unrouted tracks, and orchestrates headless, constraint-aware track laying via seamless integration with the `Freerouting` autorouter engine.
* **Physical Validation (DRC):** Triggers KiCad's internal Design Rules Checker (DRC) via `kicad-cli` to rigorously verify clearance violations and unrouted nets after auto-routing completes.
* **Production Export:** Safely exports JLCPCB-compatible manufacturing files (Gerber ZIP, BOM CSV, and Pick & Place CPL CSV) into a dedicated production folder with a single command.
