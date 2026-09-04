# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-09-04

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

## [2.0.0] - 2026-09-03

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

## [1.0.0] - 2026-08-15

### Added
- Initial release of Kaibridge KiCad bridge.
- Local HTTP REST server running as an in-GUI KiCad plugin.
- Basic schematic compilation from `design.json`.
- Integration with Freerouting 2.3.0.
- Basic geometry collision gate and SVG preview export.
- JLCPCB Gerber, BOM, and CPL export.
