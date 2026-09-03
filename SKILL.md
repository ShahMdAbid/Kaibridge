---
name: KiCad Kaibridge 2.0 Hardware Automation Engine & MCP Protocol
description: Guidelines, tool reference, and execution protocol for Kaibridge 2.0 — the autonomous, headless KiCad 10 hardware design automation engine with MCP integration, closed-loop visual critique, live SWIG API Oracle, structural board introspection, snapshot diffing, offline LCSC sourcing, and 100% factory-ready JLCPCB production export.
---

#Kaibridge 2.0 Autonomous Hardware Engineering Protocol

STRICT instructions. Zero hallucination. If a rule and your instinct disagree, the rule wins.

---

### RULE 0 — Session Contract & Project Directory Resolution

1. **Project Directory Handling:**
   - If the user provides `<PROJECT_DIR>` or points to an existing KiCad project folder, use that path directly.
   - If the user has **NOT** specified a project directory: The agent **MUST NOT** make silent assumptions. Propose creating a dedicated project directory (e.g. `<workspace>/<Project_Name>`) and confirm before initializing files.
2. **Headless New Project Bootstrapping (`kaibridge_init_project`):**
   - If starting a brand-new project from scratch, call `kaibridge_init_project` with `project_dir` and `project_name`.
   - This automatically creates the project directory, `<name>.kicad_pro` (KiCad 10 JSON format), empty `<name>.kicad_pcb`, `sym-lib-table`, `fp-lib-table`, and `kaibridge_dump/` folder in one step without requiring KiCad GUI.
3. `<LIB_NAME>` is `kaibridge` everywhere. `kicad_lib_init.py -n kaibridge` and `easyeda2kicad --output "$PWD/libs/kaibridge"` must use the same library nickname.
4. Confirm `kicad_paths.json` exists in the plugin directory and points to valid KiCad 10 binaries and libraries.
5. **Intermediate Artifacts & Clean Workspace Rule (`kaibridge_dump/`):**
   - Store all intermediate compiler specifications (`design.json`, `ops.json`, `erc_report.json`, `drc_report.json`, `board.dsn`, `board.ses`, schematic SVGs, board state dumps) inside `<PROJECT_DIR>/kaibridge_dump/`.
   - The Kaibridge compiler and tooling natively resolve `<PROJECT_DIR>/kaibridge_dump/design.json`.

---

### RULE 1 — Mandatory Implementation Plan & Human Alignment Gate

1. **Mandatory Planning Gate (Start of Every Design Task):**
   - When a user asks to design a circuit, create a board, or generate PCB files, the agent **MUST NOT** immediately begin creating or modifying files without approval.
   - The agent **MUST** first enter planning mode and create an `implementation_plan.md` artifact outlining:
     - Circuit Architecture & Sub-blocks (Power, MCU, Sensors, Connectors)
     - Component BOM with target LCSC C-Part numbers and footprint packages (e.g. 0603, 0805, QFP-32, SOT-223)
     - Proposed Board Dimensions, Connector Orientations & Spatial Placement Flow
     - Verification Plan (ERC, DRC, Visual Render checkpoints)
   - The agent **MUST HALT / STOP** calling tools, present the implementation plan with `RequestFeedback: true`, and explicitly wait for the user to approve (`"Proceed"` / `"Approved"`) before creating/modifying any files or executing the pipeline.

2. **Sequential Human Checkpoints (Review & Approval Gates):**
   - **Checkpoint 1 (Post-Schematic Review):** After generating `.kicad_sch` with 0 ERC errors, call `kaibridge_render_schematic_preview`, present the vector SVG preview path (`kaibridge_dump/schematic_svg/`), stop calling tools, and ask: *"Schematic is ready and verified (0 ERC errors). Shall I proceed to PCB synchronization and component placement?"*
   - **Checkpoint 2 (Post-Placement & Visual Critique Review):** After placing components with `kaibridge_apply_ops_layout`, export the board SVG with `kaibridge_render_pcb_preview`, present the snapshot path & board analytics (dimensions, component positions), stop calling tools, and ask: *"Component placement is verified (0 courtyard overlaps). Shall I proceed to auto-routing?"*
   - **Checkpoint 3 (Post-Routing & DRC Review):** After routing with `kaibridge_route_pcb` and adding ground planes, run `kaibridge_run_drc`, report violation status (0 errors, 0 unrouted nets), stop calling tools, and ask before generating production files.

3. **User Overrides & Directives (Top Priority - Tier 0):**
   - If the user provides specific placement guidelines, symmetry rules, connector orientations, or form-factor constraints, the agent **MUST** prioritize the user's instructions over all generic heuristics.

4. **Manual Human Edits in KiCad:**
   - The user is always free to open KiCad, inspect the schematic or PCB, make manual tweaks, and save (`Ctrl+S`).
   - If the user makes manual edits in KiCad GUI:
     - *Headless Resumption:* User saves (`Ctrl+S`) and closes KiCad so the headless engine can continue without file locks.
     - *Live Visual Sync:* User keeps KiCad open with the Kaibridge window active.
5. **Resumption:** When the user gives feedback or approves with *"proceed" / "continue"*, the agent seamlessly resumes from the current checkpoint without re-running completed work.

---

### RULE 2 — Tool & Core Engine Map (22 Integrated MCP Tools)

When operating via MCP (e.g. Antigravity IDE), use these 22 dedicated Kaibridge 2.0 tools:

| # | MCP Tool Name | Purpose | Key Parameters |
|---|---|---|---|
| 1 | `kaibridge_init_project` | **Headless Bootstrapper:** Create project folder, `.kicad_pro`, empty `.kicad_pcb`, library tables, and `kaibridge_dump/` | `project_dir`, `project_name` |
| 2 | `kaibridge_lookup_lcsc_part` | **Instant Offline DB Sourcing:** Query local `easyeda-std.elib` & Golden Cache in < 1ms for MPN, basic/extended class, and footprint mapping | `lcsc_id`, `component_type`, `value`, `package` |
| 3 | `kaibridge_fetch_lcsc_component` | Download symbol (.kicad_sym), footprint (.kicad_mod), and 3D model from LCSC with sequential pacing & retry | `project_dir`, `lcsc_id`, `lib_name`, `delay_sec` |
| 4 | `kaibridge_query_symbol_pins` | Extract pin numbers, names, electrical types, and footprint from `.kicad_sym` (smart fuzzy & case fallback) | `project_dir`, `lib_id` |
| 5 | `kaibridge_build_schematic` | Compile `design.json` into hierarchical `.kicad_sch` and run ERC validation (handles UTF-8 BOM) | `project_dir`, `apply_netclasses`, `run_erc_check` |
| 6 | `kaibridge_render_schematic_preview` | Export high-resolution vector SVG or multi-page PDF of compiled schematic for AI visual verification | `project_dir`, `format`, `pages`, `exclude_drawing_sheet` |
| 7 | `kaibridge_sync_to_pcb` | **Headless F8:** Instantiate footprints on `.kicad_pcb` and bind nets/ratsnest | `project_dir` |
| 8 | `kaibridge_apply_ops_layout` | Execute `ops.json` layout payload (place, move, rotate, lock, unlock, add tracks, vias, delete, edge cuts) in <100ms with 0.5mm grid snap | `project_dir`, `ops` |
| 9 | `kaibridge_autoplace_pcb` | Smart Geometric Autoplacer with collision avoidance and automatic Edge.Cuts board generation | `project_dir`, `board_width_mm`, `board_height_mm`, `pitch_mm` |
| 10 | `kaibridge_render_pcb_preview` | Export vector SVG snapshot, top PNG render, and structural board analytics (dimensions, positions, track/via count) | `project_dir` |
| 11 | `kaibridge_route_pcb` | Headless Freerouting 2.4.1 autorouter with 150um edge clearance & strict DRC + automatic zone refilling | `project_dir`, `track_width_mm`, `timeout_sec`, `copper_edge_clearance_um`, `strict_drc`, `max_passes` |
| 12 | `kaibridge_unroute_pcb` | Rip up / delete copper tracks, vias, & optional copper zones (entire board, net, or layer) | `project_dir`, `net`, `layer`, `remove_zones` |
| 13 | `kaibridge_add_ground_plane` | Add and fill copper ground pour zone (`GND` on `B.Cu` or `F.Cu`) with 0.3mm clearance | `project_dir`, `net`, `layer`, `clearance_mm` |
| 14 | `kaibridge_run_drc` | Run headless Design Rules Check (DRC) via `kicad-cli` with `--refill-zones` and parse JSON violations | `project_dir` |
| 15 | `kaibridge_export_production` | Generate 100% JLCPCB-compatible bundle (`Gerber_*.zip`, Drill, `BOM_*.csv`, `CPL_*.csv`) with auto-healing BOM fallback | `project_dir` |
| 16 | `kaibridge_auto_relax_layout` | Physics-based geometry engine to automatically resolve courtyard collisions by pushing components apart | `project_dir`, `locked_refs`, `passes`, `margin` |
| 17 | `kaibridge_api_oracle` | Live KiCad SWIG signature, class, constant & rules oracle; queries host `pcbnew.py` in < 4ms | `query`, `class_name` |
| 18 | `kaibridge_inspect_board` | Structural board state introspection (alias: `kaibridge_get_board_state`; mode='summary' or 'full') | `project_dir`, `mode` |
| 19 | `kaibridge_audit_placement` | Geometry Gate evaluation (alias: `kaibridge_placement_audit`): detect courtyard overlaps & boundary | `project_dir` |
| 20 | `kaibridge_snapshot_board` | Save an immutable board state checkpoint and backup `.kicad_pcb` tagged before major operations | `project_dir`, `tag` |
| 21 | `kaibridge_diff_board` | Compute structural delta (added/removed/moved parts, tracks, vias) between two snapshots or vs live board | `project_dir`, `snapshot_a`, `snapshot_b`, `tag_a`, `tag_b` |
| 22 | `kaibridge_restore_snapshot` | Restore `.kicad_pcb` state from a previous snapshot checkpoint by tag or filename | `project_dir`, `tag`, `snapshot_file` |

---

### File Map & Core Modular Engines

| File | Purpose | Invocation / Import |
|---|---|---|
| `kaibridge/core/paths.py` | Centralized path resolver: `load_cli()`, `load_kicad_python()`, `find_easyeda_db()`, `env_dirs()` | Core module |
| `kaibridge/core/oracle.py` | Live SWIG signature, class, constant, and architectural rules oracle | `kaibridge.core` |
| `kaibridge/oracle/swig_oracle.py` | Live SWIG signature, class, constant & rules oracle alias | `kaibridge.oracle` |
| `kaibridge/sourcing/parts_db.py` | Offline parts database: SQLite query on `easyeda-std.elib`, Golden Cache, `recommend_kicad_part()` | `kaibridge.sourcing` |
| `kaibridge/sourcing/lcsc_runner.py` | EasyEDA API runner for downloading active IC symbols and footprints | `kaibridge.sourcing` |
| `kaibridge/schematic/compiler.py` | `design.json` -> `.kicad_sch` compiler with netclasses, hierarchical sheets & headless ERC | `kaibridge.schematic` |
| `kaibridge/pcb/sync.py` | Headless F8 netlist and footprint binder directly into `.kicad_pcb` | `kaibridge.pcb` |
| `kaibridge/pcb/layout.py` | Board state engine: 16 layout ops, geometry gate, 0.5mm grid snap, physics relaxation | `kaibridge.pcb` |
| `kaibridge/pcb/router.py` | Specctra DSN export -> Java Freerouting 2.4.1 -> SES import + automatic zone refilling | `kaibridge.pcb` |
| `kaibridge/pcb/export.py` | Gerber ZIP, Excellon drill, JLCPCB BOM CSV (with auto-healing), and CPL CSV export | `kaibridge.pcb` |
| `kaibridge/pcb/snapshot.py` | Timestamped `.kicad_pcb` backups, deterministic rollback, and structural diffing | `kaibridge.pcb` |
| `references/pcb_placement_rules.md` | 80-rule comprehensive PCB floorplanning rulebook | Reference documentation |
| `references/trackwidth_clearence_viasize.md` | Netclasses specifications and trace current guidelines | Reference documentation |
| `references/failure_recovery_matrix.md` | Exhaustive ERC/DRC/Freerouting/SWIG deterministic recovery matrix | Reference documentation |
| `server.py` | STDIO JSON-RPC 2.0 MCP server exposing all 22 tools | Standalone process |

---

### RULE 3 — Component Sourcing, Native IPC Footprints & Upfront LCSC BOM Binding (Zero ERC Guarantee)

1. **Two-Tier Sourcing Doctrine**:
   - **Generic Passives (Resistors, Capacitors, Inductors, LEDs, Diodes, Headers):**
     - **Symbols:** ALWAYS use native KiCad symbols:
       - Resistors: `Device:R`
       - Capacitors: `Device:C` (ceramic/unpolarized) or `Device:C_Polarized` (electrolytic/tantalum)
       - LEDs: `Device:LED`
       - Diodes: `Device:D` or `Device:D_Schottky`
       - Inductors: `Device:L`
       - Pin Headers: `Connector_Generic:Conn_01x<N>`
       *(NEVER use raw EasyEDA passive symbols that declare pins as "Input", which trigger `[pin_not_driven]` ERC errors).*
     - **Footprints:** ALWAYS use native KiCad official IPC-7351 footprints (`Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`, `LED_SMD:LED_0805_2012Metric`, `Diode_SMD:D_SOD-123`, `Connector_PinHeader_2.54mm:PinHeader_1x*`). **NEVER download passive footprints from EasyEDA!** KiCad IPC footprints guarantee zero silkscreen overlaps, correct courtyards, and 100% JLCPCB SMT compatibility.
     - ** UPFRONT LCSC ID BINDING (MANDATORY BEFORE SCHEMATIC COMPILATION):**
       You MUST attach the JLCPCB LCSC C-Part ID directly during `design.json` synthesis inside `fields: {"LCSC": "Cxxxx", "JLCPCB_Class": "Basic Part"}` for EVERY component. Do NOT wait until BOM export! Sourcing the LCSC ID upfront ensures it travels automatically into the schematic, netlist, PCB footprint fields, and exports a 100% populated JLCPCB BOM CSV without missing part numbers.
     - **Instant Resolution & Reference Catalog:**
       - Use `kaibridge_lookup_lcsc_part` (<1ms) to query any part dynamically.
       -  **Complete Basic Parts Directory:** See [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) for the verified catalog of JLCPCB Basic Parts (resistors, capacitors, LEDs, diodes, transistors, MOSFETs, LDOs) with exact LCSC IDs and KiCad IPC footprint mappings.
   - **Active ICs, Sensors, Microcontrollers, USB Sockets:**
     - Download via `kaibridge_fetch_lcsc_component`.
     - Query exact pin numbers, pin names, and electrical types via `kaibridge_query_symbol_pins`.
     - Copy exact pin numbers (`"1"`, `"2"`, `"A4"`, `"B1"`, `"SH"`, `"EP"`) verbatim into `design.json`. Never invent or assume pin numbers.

---

### RULE 4 — `design.json` Specification & Schematic Compilation

1. Build `design.json` inside `<PROJECT_DIR>/kaibridge_dump/design.json`.
2. **Canonical Schema Rules:**
   - **Net Names:** Name every junction explicitly (`VBUS`, `+3V3`, `GND`, `PWM_OUT`, `RESET`). Never use auto-generated names like `Net-(D1_Pad1)`.
   - **Net Structure:** Each net in `nets` contains a `connections` array: `"<NET_NAME>": { "connections": ["U1.1", "C1.1"] }`.
   - **Power Flags & Switched Rail Ingest Rule (Zero [pin_not_driven] Guarantee):**
     - KiCad ERC requires every power net feeding active IC `power_in` pins to have a driving source (`power_out` pin or `PWR_FLAG`).
     - **External Power Ingest Nets (Unregulated Inputs):** Any power rail entering the board from an external source (e.g. USB `VBUS`, DC barrel jack `VIN` / `DC_IN`, battery terminal `VBAT`, industrial `+12V` / `+24V`) and circuit reference ground (`GND`) must be declared in `"power_flags": ["<INPUT_RAIL>", "GND"]`.
     - **Passive-Interrupted Power Rails:** Any power rail downstream of purely passive inline elements (e.g. Schottky protection diodes, PTC fuses, toggle/push switches, LC filter inductors, current-sense shunts) that feeds an active IC's `power_in` pin lacks an active driver. You **MUST** declare all such interrupted rails in `"power_flags"` (e.g. `["DC_IN", "VBUS_SW", "VIN_PROT", "VBAT_FUSED", "GND"]`). Failure to do so triggers `[pin_not_driven]` ERC errors.
     - **Active Regulator Outputs (Do NOT flag):** Regulators (LDOs, buck/boost converters, charge pumps) have output pins internally typed as `power_out`. Never assign `power_flags` to active regulator output nets (e.g. `+3V3`, `+5V`, `VOUT`), as doing so creates a `[pin_to_pin]` driver collision error.
   - **Unconnected Pins:** Unconnected `power_in` or bidirectional pins must be wired or declared in `no_connect`: `["U1.5", "J1.A6", "J1.A7"]`.
   - **Stacked Pins Warning (`stacked_pins_fix.md`):** If a symbol has multiple stacked identical pins sharing the exact same coordinate (e.g. multiple GND pins on MCU or USB-C), **only list the single visible pin** in `design.json`. KiCad internally connects the stacked pins; listing all of them creates an illegible label ladder in the schematic.
   - **Netclasses Configuration (`trackwidth_clearence_viasize.md`):** Declare `netclasses` at the root of `design.json` tailored to the specific board's current and signal requirements:
     ```json
     "netclasses": {
       "Default": { "track_width": 0.25, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3 },
       "Power": {
         "track_width": 0.6,
         "clearance": 0.25,
         "via_diameter": 0.8,
         "via_drill": 0.4,
         "nets": ["<POWER_RAILS_AND_HIGH_CURRENT_NETS>"]
       }
     }
     ```
     *Note:* The `"nets"` array in `"Power"` should enumerate the power rails and ground returns for this specific design (e.g. `["+12V", "MOTOR_PWR", "GND"]`, `["VBAT", "VDD", "GND"]`, or `["VBUS", "VBUS_SW", "+3V3", "GND"]`). Additional custom netclasses (e.g. `High_Current`, `RF_50R`, `Analog_Sensitive`) can be declared similarly. The compiler and router automatically synthesize `netclass_patterns` to `.kicad_pro`, ensuring Freerouting and `ExportSpecctraDSN` route power nets at their wide width and signals at standard width.
3. Compile schematic with `kaibridge_build_schematic` (with `run_erc_check=True`). Ensure **0 errors** before proceeding.

---

### RULE 5 — Schematic Visual Verification (Vector Render Gate)

After `kaibridge_build_schematic` passes with 0 ERC errors, call `kaibridge_render_schematic_preview` to generate vector renders of the compiled schematic:

1. **Export:** Call `kaibridge_render_schematic_preview` with `format: "svg"` and `exclude_drawing_sheet: true`.
2. **Output:** Clean vector SVG files are saved into `<PROJECT_DIR>/kaibridge_dump/schematic_svg/`.
3. **AI Visual Review:** Verify:
   - All symbols are cleanly placed without wire overlaps.
   - Net labels, hierarchical labels, and power flags connect to their target pins.
   - No dangling stubs or floating unconnected pins exist.
4. **HITL Deliverable:** Present the schematic preview path to the user before moving to PCB synchronization.

---

### RULE 6 — Headless Schematic-to-PCB Synchronization (F8 Net Binding)

* **Headless Execution (Automated):** Call `kaibridge_sync_to_pcb` to instantiate footprints in `.kicad_pcb` and bind nets/ratsnest directly.
* **Manual / GUI Execution:** If KiCad GUI is open, user presses **F8** (Update PCB from Schematic) -> **Ctrl+S**.

---

### RULE 7 — Component Placement, Geometry Gate & Spatial Critique

1. **The Precedence Ladder (`pcb_placement_rules.md` §0.3):**
   When placing components or resolving layout conflicts, follow this strict hierarchy:
   - `Tier 0`: **Human Directives** (Explicit user requests, layout constraints, symmetry preferences)
   - `Tier 1`: **Safety & High-Voltage Isolation**
   - `Tier 2`: **Mechanical Datums** (Connectors on outer edges facing outward, mounting holes)
   - `Tier 3`: **Electrical Proximity** (Decoupling caps < 2mm from IC power pins, crystal adjacent to OSC pins, feedback resistors < 5mm from FB pin)
   - `Tier 4`: **Thermal Survival** (Linear regulator heatsink tab facing board edge, distributed hot components)
   - `Tier 5`: **EMC Margin** (Switching nodes isolated from sensitive analog/clocks)
   - `Tier 6`: **Manufacturability / DFM**
   - `Tier 7`: **Aesthetics & Visual Symmetry**

2. **Multimodal Closed-Loop Visual Placement & Rotational Intent:**
   - Call `kaibridge_render_pcb_preview` to export `<project>_board.svg` and `<project>_top.png` for multimodal AI critique.
   - **UNIVERSAL ROTATIONAL DOCTRINE (DO NOT JUST TRANSLATE X/Y!):**
     Component placement is fundamentally rotational. Moving $(X, Y)$ without setting proper angular orientations produces tangled ratsnests, reverse connectors, and thermal traps:
     - **Perimeter Connectors & Headers (All Types: USB, Barrel Jacks, Terminal Blocks, Pin Headers):**
       Connector openings, plug insertion corridors, or wire terminals MUST face outward toward the nearest board edge:
       - Placed near Left edge: `"rot": 180` (receptacle opens Left)
       - Placed near Bottom edge: `"rot": 270` (receptacle opens Down)
       - Placed near Right edge: `"rot": 0` (receptacle opens Right)
       - Placed near Top edge: `"rot": 90` (receptacle opens Up)
     - **Thermal Dissipation Devices (LDOs, Buck Converters, Power MOSFETs, Motor Drivers):**
       The primary heatsink tab or exposed thermal slug (e.g. SOT-223, DPAK, TO-220, SOIC-EP) MUST face outward toward the board edge or broad copper ground pour areas. Never orient high-heat tabs inward toward sensitive MCUs, analog sensors, or crystals.
     - **Core ICs & Processing Units (MCUs, SOCs, Op-Amps, Driver ICs):**
       Rotate the IC ($0^\circ, 90^\circ, 180^\circ, 270^\circ$) so that its primary peripheral pin groups face their functional companion blocks (e.g. power pins towards power stage, high-speed buses toward headers/sensors), minimizing trace crossings and ratsnest tangle.
     - **Decoupling Capacitors & Filtering Passives (0805 / 0603):**
       Rotate 90° or 0° to orient GND and power pads directly inline with their companion IC supply pins. This creates direct, straight-line routing channels and reduces via counts to near zero.
     - **RF Antennas & Transceivers:**
       Antenna radiating elements, trace antennas, or chip antennas must face outward toward an outer edge, with recommended manufacturer keep-out clearance free of copper and traces.

3. **Execute Placement via `kaibridge_apply_ops_layout` (`ops.json`):**
   - 16 built-in layout ops: `footprint.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.unlock`, `footprint.set_field`, `track.add`, `track.set_width`, `via.add`, `item.delete`, `net.delete_routing`, `zone.refill`, `zone.delete`, `board.set_size`, `board.fit_outline`, `board.prep_for_route`.
   - **Op Schema Reference:** Refer to `ops_template.json` for full examples.
   - **Sample `ops.json` Template with Explicit Rotations:**
     ```json
     [
       {"op": "board.set_size", "width": 50.0, "height": 40.0, "origin_x": 0.0, "origin_y": 0.0},
       {"op": "footprint.place", "ref": "J1", "x": 5.0, "y": 20.0, "rot": 180, "locked": true},
       {"op": "footprint.place", "ref": "U1", "x": 25.0, "y": 20.0, "rot": 0},
       {"op": "footprint.place", "ref": "C1", "x": 20.0, "y": 16.0, "rot": 90},
       {"op": "footprint.rotate", "ref": "R1", "rot": 90, "relative": false}
     ]
     ```
   - All $(X, Y)$ coordinates are automatically quantized to a clean **0.5mm grid** by the Geometry Gate.
   - Preserves existing rotation if `"rot"` is omitted during fine coordinate nudging (`footprint.move`).
   - **Safe Simulation Mode (`"dry_run": true`):** Pass `"dry_run": true` to `kaibridge_apply_ops_layout` to simulate placement, rotation, and geometry collision checks in memory with a 100% zero-disk-write guarantee before committing.

4. **Visual & Structural Critique:**
   - Call `kaibridge_render_pcb_preview` to export `<project>_board.svg` and inspect `board_analysis`.
   - Audit placement against the 80-rule floorplanning doctrine in [`references/pcb_placement_rules.md`](references/pcb_placement_rules.md) (Decoupling Proximity `< 2.5mm`, Clock/RF Loops `< 5mm`, Thermal Dissipation Tabs facing outward, Symmetry & Axis Alignment).
   - Formulate corrective `ops.json` layout operations with explicit rotations and coordinates before re-rendering.

---

### RULE 8 — Spatial Symmetry, Alignment & Silkscreen Hygiene

1. **Universal 4-Zone Hardware Floorplan:**
   Arrange components in clean, functional clusters aligned to a 0.5mm / 1.0mm grid following natural signal and power flow:
   - **Zone 1: Power Ingest & Conditioning:** Input connectors, reverse-polarity protection diodes, fuses, input filter capacitors, and voltage regulators positioned along the outer edge.
   - **Zone 2: Core Processing / Main Active Stage:** Central IC (MCU, FPGA, DSP, main analog stage, or motor driver) centrally placed with clean perimeter routing channels.
   - **Zone 3: High-Frequency & Precision Ancillary Circuits:** Bypass capacitors, crystal oscillators, feedback dividers, and filtering inductors placed tightly adjacent ($< 2.5\text{mm}$) to their respective IC pins.
   - **Zone 4: User Interfaces, Output Drivers & External Ports:** Status LEDs, push buttons, switches, output headers, and terminal blocks placed along accessible board perimeters.
2. **Silkscreen Hygiene & Zero Overlap Rule:**
   - Reference designators (`R1`, `C1`, `U1`, `SW1`, `D1`) must be visible, sized $1.0\text{mm} \times 1.0\text{mm}$ (thickness $0.15\text{mm}$), and positioned cleanly outside component courtyards.
   - **Hide bulky value text** from the silkscreen layer (`F.SilkS`) to prevent text overlapping with tracks, pads, or neighboring components.
3. **Trace Routing Elegance & Minimal Via Rule:**
   - Prefer clean 45-degree trace angles and parallel bus routing over erratic zig-zags.
   - Align component pin orientations to face their net companions directly, minimizing layer changes and reducing via counts to 0–2 for simple boards.

---

### RULE 9 — Headless Routing & Freerouting Engine

1. **Prepare:** Run `kaibridge_unroute_pcb` or `{"op": "board.prep_for_route"}` to purge orphaned tracks. Ensure `Edge.Cuts` boundary is closed.
2. **0.15mm JLCPCB Copper Edge Clearance Standard:**
   - KiCad 10's internal default copper edge clearance is `0.50mm`, which causes false DRC errors on USB-C, micro-USB, and edge-mounted connectors whose pads or mounting tabs sit `0.20–0.30mm` from the board edge.
   - Kaibridge automatically writes JLCPCB production rules into `.kicad_pro` (`min_copper_edge_clearance: 0.15mm`, `min_clearance: 0.15mm`, `min_track_width: 0.15mm`). Never permit `.kicad_pro` to omit these design settings.
3. **Route:** Call `kaibridge_route_pcb`:
   - **Pre-flight Specctra DSN Audit (`audit_dsn`):** Exports Specctra DSN and audits rules in < 2ms before launching Java. Catches zero/negative track widths, negative clearances, and missing nets to prevent Freerouting from hanging or silently routing 0 tracks.
   - **Freerouting 2.4.1 Decoupled Universal Pipeline:** Runs Java Freerouting 2.4.1 headlessly without AWT/Swing dependencies.
   - **Automatic Copper-to-Edge Keepout (`--router.copperToEdgeClearanceUm=150`):** Enforces JLCPCB 150µm board outline keepout, solving KiCad DSN board outline omission (#558).
   - **Strict Geometric DRC (`--router.strictDrc=true`):** Prevents micro-clearance approximations during maze expansion.
   - **Deterministic Optimization Passes (`max_passes` / `-mp`):** Optionally caps auto-routing passes to guarantee bounded execution time.
   - Imports SES file with clean copper tracks into `.kicad_pcb`.
   - **Mandatory Post-SES Zone Refill:** Automatically executes `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` and `board.BuildConnectivity()` to recalculate copper clearances around newly placed tracks and vias, preventing copper zone track shorts.
4. **Re-routing / Rip-up:** Use `kaibridge_unroute_pcb` to strip tracks (entire board, per net, or per layer) when iterating.

---

### RULE 10 — Ground Copper Pour & Plane Management

1. Call `kaibridge_add_ground_plane` to add and fill a GND copper zone across `B.Cu` and/or `F.Cu` with 0.3mm clearance.
2. **Exact Board Outline Boundary:** The engine automatically sets `zone.SetOutline(poly)` from the closed `Edge.Cuts` polygon (`board.GetBoardPolygonOutlines(poly, True)`), ensuring 0 outline overflow beyond the board perimeter and eliminating negative space overflow errors.
3. **Solid Thermal Reliefs (`ZONE_CONNECTION_FULL`):** Ground copper planes use solid pad connections (`zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)`) with `0.2mm` minimum thickness to eliminate starved thermal relief spoke errors (`[starved_thermal]`) on dense SMT footprints.
4. The engine automatically replaces duplicate zones on the same layer to prevent `zones_intersect` DRC errors.
5. To remove/clear ground zones, use `kaibridge_unroute_pcb(remove_zones=True)` or `{"op": "zone.delete"}`.

---

### RULE 11 — DRC Audit & JLCPCB Production Export

1. **DRC Check:** Call `kaibridge_run_drc` (or `kicad-cli pcb drc`). Must achieve **0 clearance violations** and **0 unrouted nets**.
2. **JLCPCB Export:** Call `kaibridge_export_production`:
   - Generates `Gerber_*.zip`, Drill files, `BOM_*.csv`, and `CPL_*.csv` inside `<PROJECT_DIR>/jlcpcb_production/`.
   - **Auto-Healing BOM:** If any standard passive part omitted an explicit `LCSC` field, the exporter automatically resolves the JLCPCB Basic Part number from the local database.

---

### RULE 12 — Universal Error Recovery & Failure Matrix

1. **Mandatory Matrix Consultation (`failure_recovery_matrix.md`):**
   - Whenever an ERC violation, DRC error, Freerouting issue, Python SWIG memory exception, or file lock occurs, the agent **MUST** immediately read and consult [`references/failure_recovery_matrix.md`](references/failure_recovery_matrix.md).
   - Follow the exact deterministic remedy prescribed in the matrix. Never invent ad-hoc, unverified workarounds.
2. **Two-Strike Algorithmic Dead-End Policy:**
   - If the exact same error persists across **two consecutive automated attempts** after applying the prescribed fix, **HALT** execution immediately.
   - Report the failing command, exact error output, and current board state to the user and request human feedback. Never loop blindly.

---

### RULE 13 — Cognitive Engineering Reasoning & User Intent Primacy

1. **Multimodal Engineering Sense:**
   - The AI Agent must actively use its vision capabilities and domain knowledge to inspect generated schematics and PCB layout previews.
   - If a layout looks scattered, cramped, or unaligned, the agent must proactively propose or execute clean geometric alignments.
2. **User Directives Are Supreme (Tier 0):**
   - If the user provides specific guidelines, reference pictures, symmetry rules (e.g. *"Place resistor left, sensor center, resistor right"*), connector orientations, or form-factor constraints, the agent **MUST** prioritize the user's instructions over all generic heuristics.
   - Never overwrite or discard user-specified component coordinates without explicit confirmation.

---

### RULE 14 — Live KiCad SWIG API Oracle & Memory Safety Protocol

**STRICT MANDATE:** Zero-hallucination policy for KiCad `pcbnew` Python scripting. Never write a single line of `pcbnew` code based on memory or assumptions.

1. **Multi-Mode Oracle Resolution (`kaibridge_api_oracle`):**
   - **Method Signature Query:** `kaibridge_api_oracle(query="<method_name>", class_name="<CLASS>")` (e.g. `query="ExportSpecctraDSN"`, `query="Delete", class_name="BOARD"`).
   - **Class Inspection Query:** `kaibridge_api_oracle(query="<CLASS>")` (e.g. `query="ZONE_FILLER"` or `query="BOARD"`) returns constructor signatures, docstrings, and complete lists of public methods.
   - **Constants & Enums Query:** `kaibridge_api_oracle(query="<CONSTANT>")` (e.g. `query="ZONE_CONNECTION_FULL"`, `query="Edge_Cuts"`, `query="F_Cu"`) returns exact assignment and type.
   - **Production Rules Query:** `kaibridge_api_oracle(query="drc_rules")`, `query="swig_memory"`, `query="zone_filling"`, or `query="power_flags"` returns grounded JLCPCB specifications and code patterns.

2. **SWIG Memory Safety & Pointer Lifecycle Doctrine:**
   - **Garbage Collection:** Always run `gc.collect()` before and after calling `pcbnew.LoadBoard()` to clean up dead SWIG wrappers.
   - **Explicit Pointer Teardown:** Always call `del board` at the conclusion of board operations. Never retain a module-level `board` reference across multiple tool calls.
   - **Subprocess Isolation:** When executing outside KiCad's bundled Python 3.11 environment (e.g. system Python 3.14), backend tools automatically execute board mutations in an isolated subprocess using `load_kicad_python()` to guarantee 100% OS-level memory reclamation.
3. **Execute Verbatim:** Use only Oracle-confirmed method signatures. Never guess method names or parameter orders.

---

### RULE 15 — Board State Introspection, Geometry Gate & Snapshot/Diff Protocol

1. **Introspection:** Call `kaibridge_inspect_board(mode="summary")` for high-level board statistics or `mode="full"` for complete coordinate trees.
2. **Geometry Gate Audit:** Call `kaibridge_audit_placement` to verify:
   - `overlaps == 0` (no courtyard collisions)
   - `outside_boundary == 0` (all components inside `Edge.Cuts`)
   - `route_ready == True`
3. **Snapshot Diffing:**
   - Before major layout changes or routing, call `kaibridge_snapshot_board(tag="pre_action")`.
   - After execution, call `kaibridge_diff_board(tag_a="pre_action")` to inspect exact structural changes (tracks added, components moved, nets routed).
   - If routing fails or layout regresses, call `kaibridge_restore_snapshot(tag="pre_action")` to instantly roll back safely.
