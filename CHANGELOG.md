# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Beta v2.4.1] - 2026-09-08

### Changed & Streamlined
- **Concise & Clean `SKILL.md` Workflow (Up to Schematic Generation):**
  - Reordered procedural workflow: **Step 0 Bootstrap** (`kicad_lib_init.py`) immediately sets up project libraries and tables upon prompt receipt.
  - Postponed formal BOM and netlist generation from Step 1 wishlist to **Step 4 Implementation Plan**, requiring ground-truth pin extraction from downloaded symbols (`kicad_pins.py`) first to eliminate pin-out hallucinations and premature design lock-in.
  - Simplified EasyEDA active component download CLI commands to direct, cross-platform paths without shell-specific `Push-Location` or `$PWD`.
  - Clarified ART-Gate as an adversarial cognitive review protocol applied during planning rather than an external CLI binary.
  - Added **Recommended Default Placement Pipeline** in Step 8 (Anchor Placement → Apply Layout → Planar Optimization → Silkscreen Sanitation).
  - Streamlined Step 8A by removing redundant embedded `ops.json` snippet, linking directly to canonical `ops_template.json` and Appendix A.

### Added
- **Vector Schematic Snapshot CLI (`pcb_snapshot.py --schematic`):** Added `--schematic` flag and `export_schematic_snapshot()` to `pcb_snapshot.py` to directly render vector SVG schematics to `<PROJECT_DIR>/kaibridge_dump/<NAME>_schematic.svg`.
- **Audit Regression Test Suite (`tests/test_audit_fixes.py`):** Added unit tests covering DRC fail-closed behavior, composite pad matching, and LCSC passive disambiguation.

### Fixed & Hardened
- **Fail-Closed DRC Gate (`kaibridge/pcb/drc.py` & `kicad_route.py`):** Fixed potential false-PASS bug by purging stale `drc_report.json` prior to execution and enforcing strict fail-closed validation on missing or unparseable reports.
- **Composite & Stacked Pad Matching (`kaibridge/pcb/sync.py`):** Replaced strict equality with `_matches_pad()`, supporting delimiter-separated aliases (`/`, `,`, `-`, `_`) so multi-pad contacts (e.g. Type-C `A1/B12`) properly connect to copper nets on PCB sync.
- **LCSC Basic Parts & Footprint Mismatches (`references/jlcpcb_basic_parts.md` & `kaibridge/sourcing/parts_db.py`):**
  - Resolved 0805 1µF 50V MLCC C-ID to Samsung `CL21B105KBFNNNE` (`C28323`), preserving `C15849` for 0603.
  - Resolved 0805 5.1kΩ 1% resistor C-ID to UNI-ROYAL `0805W8F5101T5E` (`C27834`), preserving `C23186` for 0603.

---

## [Beta v2.4.0] - 2026-09-07

### Added
- **Proof-Carrying Compiler Architecture (`kaibridge.core.compiler`):** Unified 4-stage constructive hardware compiler (`compile_board`) that eliminates trial-and-error placement/routing loops.
- **Integer Nanometer Domain IR (`kaibridge.core.ir`):** Immutable $1\text{nm} = 1\text{ unit}$ representation (`BoardIR`, `ComponentInstance`, `PadGeometry`, `NetHyperedge`) preventing floating-point geometric drift.
- **Pre-Flight Invariant Proof Gates (E0–E6):**
  - **E0–E2:** Requirements completeness, netlist parity, and fabrication floor verification.
  - **E3 Pad-Pitch Solvability:** Algebraically proves $w_{\text{neck}} \le 2P - a - 2s$ in $<1$ms, halting deadlocks before routing.
  - **E6 Separating Cut Gate:** Calculates exact throat capacity ($B_{\text{required}} = Nw + (N-1)s + b_L + b_R$) with formal deficit certificates.
- **Characterized Electromagnetic Circuit Motifs (`kaibridge.core.motifs`):**
  - Collinear shunt decoupling with solder mask dam preservation ($\ge 0.10$mm).
  - Symmetrical crystal oscillator tanks ($\le 3.5$mm loop) with 4-vertex noise keepout polygons.
  - Procedural necked-down escape stubs for fine-pitch IC pads, pre-routed and locked as `(type fix)`.
- **Topological Channel & Routing Solvers:**
  - $O(KN \log N)$ Fenwick tree inversion counter to eliminate bus braid crossings (`kaibridge.core.bus_order`).
  - Analytical Quadratic Programming (QP) slack solver for corridor widening without coordinate guessing (`kaibridge.core.slack_solver`).
  - Strict 2-layer $B.Cu$ ground return jumper bridge synthesis ($L_{\text{bridge}} \le 3.0$mm) with clearance moats (`kaibridge.core.bridge`).
- **Comprehensive Organic Test Suite:** 23 automated end-to-end unit and integration tests running against live KiCad 10 and real Freerouting 2.4.1 in $<20$s (`tests/test_*.py`).
- **First-Class Live Inspection & API Oracle Tooling:**
  - **Live SWIG Oracle (`kicad_oracle.py`):** Previously internal/dormant reflection logic in `kaibridge.core.oracle` hardened into a first-class, instant (<4ms) CLI tool with exact method signatures, class inheritance trees, constants, and JSON export.
  - **Live Board State Inspector (`kicad_inspect.py`):** Previously silent state extractor in `kaibridge.pcb.inspector` promoted to a canonical CLI tool (`--summary`, `--full`, `--json`), providing sub-second (<0.5s) extraction of live board bounds, footprint coordinates, rotations, locked states, nets, and design rules directly from `.kicad_pcb` for rapid iterative editing.

### Changed
- **System Rules & Protocols:** Overhauled `.agents/AGENTS.md` and `SKILL.md` to establish the Kaibridge 3.0 Proof-Carrying Hardware Compiler protocol over legacy Kaibridge 2.0 visual critique loops.
- **4-Layer Dedicated Plane Inactivity:** Enforced `(layer_rule "In1.Cu" (active off))` and `(layer_rule "In2.Cu" (active off))` in Specctra DSN exports, guaranteeing zero signal tracks on internal power and ground planes.

### Fixed & Hardened
- **Adaptive Router Active Nets Resolution:** Fixed unhandled `NameError` in `route_board` (`len(active_nets)`), restoring Strategy 1 (Fanout-First: 0-signal-vias) and eliminating rogue vias and DRC clearance errors near IC pads.
- **Windows Localhost Socket Resilience:** Added `Connection: close` headers and transient socket retry in `FreeroutingClient` to resolve `WinError 10054` on rapid sequential requests.
- **Fine-Pitch IC Pad Clearance Deadlocks:** Resolved clearance violations across dense MCUs (STM32 LQFP-48 0.5mm pitch, RP2040 QFN-56 0.4mm pitch), achieving 0 DRC violations and 0 unconnected airwires across all production test boards.

---

## [Beta v2.3.0] - 2026-09-06

### Added
- **Freerouting REST Daemon:** Integrated background routing daemon (`freerouting_daemon.py`) to eliminate repeated JVM startup latency.
- **Dynamic Board Sizing:** Updated `kicad_planar_optimizer.py` to parse board dimensions and center offsets directly from layout specifications.

### Fixed & Improved
- **Netclass Width Preservation:** Removed power track clamping in schematic compiler and router; enabled automatic neckdown for fine-pitch IC pads.
- **Decoupling Placement Constraints:** Enforced proximity penalties in planar optimizer to keep bypass capacitors adjacent to IC power pins.
- **DSN Clearance Harmonization:** Aligned signal clearance rules in exported DSN with power netclasses to prevent DRC violations near fanout vias.
- **Layout Parameter Handling:** Fixed coordinate parsing for center offset parameters in `board.set_size`.

---

## [Beta v2.2.1] - 2026-09-05

### Fixed & Improved
- **ERC & DRC Warning Visibility:** Full warning reporting in `json2sch.py` and `kicad_route.py` using `--severity-all`.
- **Pin Type Auto-Healing:** Automatically maps EasyEDA unspecified pins to proper electrical types to resolve `[pin_to_pin]` warnings.
- **Dangling Track Pruning:** Automatically removes $<0.08$mm stubs after routing to ensure 0 DRC warnings.
- **Connector Placement:** Auto-distributes input/output connectors across board edges to prevent courtyard overlap.
- **Silkscreen Sanitization:** Added standalone `--sanitize-silk` flag in `kicad_layout.py`.
- **Component Sourcing Hierarchy:** Explicitly prioritized on-demand active IC downloads via `easyeda2kicad` and native KiCad IPC passives in `AGENTS.md` and `SKILL.md`.

---

## [Beta v2.2.0] - 2026-09-05

### Added
- `kicad_planar_optimizer.py`: In-memory simulated annealing placement using Kruskal's MST and 2D segment intersections to minimize airwire crossings.
- 3-Tier Routing Protocol: Pre-places GND dog-bone vias, routes signals on F.Cu without signal vias, and floods B.Cu ground plane.
- S7A / S7B Placement Flow: Decoupled mathematical placement (`kicad_planar_optimizer.py`) from visual audit (`pcb_snapshot.py`).
- DSN clearance harmonization in `route_board()` to prevent power pad clearance DRC violations.
- Added `kicad_planar_optimizer.py` to root CLI tools (9 tools) and `--fanout-first` flag to `kicad_route.py`.

### Changed
- `kaibridge/pcb/router.py`: Added native `apply_dogbone_fanout()` and `fanout_first` routing support.
- Updated `AGENTS.md` and `SKILL.md` with 9-stage pipeline and 3-Tier routing protocol.

---

## [Beta v2.1.0] - 2026-09-04

### Added
- Root CLI tool suite providing standalone command-line entry points for all design stages:
  - `kicad_lib_init.py`: Project and library table initialization.
  - `kicad_pins.py`: Symbol and footprint pin extraction from `.kicad_sym` files.
  - `json2sch.py`: Schematic compilation and automated Electrical Rules Check (ERC).
  - `kicad_pcb_sync.py`: Headless netlist and footprint synchronization to `.kicad_pcb`.
  - `kicad_layout.py`: Declarative placement with 0.5mm grid snapping and in-memory collision detection (`--dry-run`).
  - `pcb_snapshot.py`: Board layout snapshot export to SVG.
  - `kicad_route.py`: Headless autorouting via Freerouting 2.4.1, B.Cu ground plane pouring, and KiCad DRC verification.
  - `export_jlcpcb.py`: JLCPCB manufacturing bundle generation (Gerbers, drill, BOM, CPL).
- Linear array placement support (`array.place`) in `kaibridge/pcb/layout.py` for multi-channel sensor arrays and repeating circuit blocks.
- Mechanical alignment post auto-sanitization in footprint importer, converting mechanical non-plated through-holes to `np_thru_hole` to prevent zero annular ring DRC violations.
- Mechanical and adversarial DFM checklists in `references/` for design verification.

### Changed
- Refactored `server.py` project initialization to delegate directly to `kicad_lib_init.init_libraries`.
- Synchronized workspace rules (`.agents/AGENTS.md`) and skill definitions (`SKILL.md`) with the root CLI tool suite.
- Standardized all production export output paths to `<PROJECT_DIR>/production_output/`.

### Fixed
- Fixed ERC `[pin_to_pin]` driver collision on active regulator outputs by removing regulator output rails (`+3V3`) from `power_flags` in design templates.
- Fixed stale import paths and function signatures in `references/command_help.md`.

### Removed
- Removed legacy test and temporary scratch files.
- Removed stale 59.4MB binary archive `Kaibridge_v2.0.zip` from repository root.

---

## [Beta v2.0.0] - 2026-09-03

### Added
- Model Context Protocol (MCP) server (`server.py`) exposing discrete tools over STDIO JSON-RPC 2.0.
- Sub-millisecond offline component database lookup using embedded SQLite catalog (`easyeda-std.elib`).
- Upfront LCSC C-Part ID binding during schematic synthesis to guarantee fully populated JLCPCB BOMs.
- Live KiCad SWIG C++ introspection oracle (`kaibridge_api_oracle`) querying host `pcbnew.py` in < 4ms to resolve methods, classes, and constants.
- In-memory layout simulation mode (`dry_run=True`) in `apply_ops` with zero disk modification guarantee.
- Specctra DSN pre-flight auditor (`audit_dsn`) verifying track widths, clearances, and netclasses in < 2ms before launching routing.
- Physics-based 2D spring relaxation solver (`kaibridge_auto_relax_layout`) for resolving courtyard overlaps.
- Automated ground plane pouring on `B.Cu` and `F.Cu` with exact `Edge.Cuts` boundary clipping and solid thermal relief.
- Immutable board snapshots with SHA-256 fingerprints and structural diffing (`kaibridge_diff_board`).
- Headless netlist and footprint synchronization (`kaibridge_sync_to_pcb`).

### Changed
- Migrated from in-GUI wxPython HTTP bridge to 100% headless daemon architecture.
- Upgraded autorouter engine to Freerouting v2.4.1 (Java 25 LTS).
- Enforced 150µm board edge clearance keepout via `--router.copperToEdgeClearanceUm=150` to address KiCad DSN outline omissions.
- Enforced strict DRC verification (`--router.strictDrc=true`) during maze routing.
- Enabled differential netclass routing (0.60mm power rails, 0.25mm signal tracks).
- Switched generic passives to native KiCad symbols and official IPC-7351 footprints (`Device:R`, `Resistor_SMD:R_0805_2012Metric`, etc.).
- Quantized all layout coordinates to a clean 0.5mm grid.

### Fixed
- Fixed `[pin_not_driven]` ERC errors by adding automatic power flag synthesis on switched and fused power rails.
- Fixed passive symbol pin-type mismatches by eliminating raw EasyEDA passive symbols.
- Fixed uniform trace width bug where all nets were routed at 0.25mm by synthesizing `netclass_patterns` into `.kicad_pro`.

### Removed
- Removed legacy in-GUI wxPython plugin and HTTP socket listener (`kicad_agent_bridge.py`).
- Removed deprecated Freerouting v2.3.0 jar.

---

## [Beta v1.0.0] - 2026-08-15

### Added
- Initial release of Kaibridge KiCad bridge.
- Local HTTP REST server running as an in-GUI KiCad plugin.
- Basic schematic compilation from `design.json`.
- Integration with Freerouting 2.3.0.
- Basic geometry collision gate and SVG preview export.
- JLCPCB Gerber, BOM, and CPL export.
