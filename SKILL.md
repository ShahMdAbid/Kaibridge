---
name: KiCad Kaibridge 2.0 Hardware Automation Engine & MCP Protocol
description: Procedural handbook and technical reference for Kaibridge 2.0 — headless KiCad 10 hardware synthesis, dual-modality execution (Root CLI & 22 MCP tools), upfront LCSC sourcing, zero-hallucinated pin extraction, declarative layout, closed-loop visual critique, Freerouting 2.4.1, and 100% JLCPCB production export.
---

# Kaibridge 2.0 Procedural Execution & Technical Reference

This handbook contains the exact procedural steps, schemas, CLI commands, visual critique rubrics, and technical parameters required to execute hardware synthesis in Kaibridge 2.0.

---

## 1. Execution Architecture, Session Contract & Tool Mappings

Kaibridge provides two coordinated execution interfaces: the **8 Canonical Root CLI Tools** (for terminal/subagent execution via `run_command`) and the **22 MCP Tools** (for direct tool calling when registered in the environment).

### A. Session Contract & Project Resolution
1. **Directory Handling:** Default project path is `projects/<Project_Name>`. If user provides an explicit path, use it directly.
2. **Library Nickname:** `<LIB_NAME>` is strictly `kaibridge` everywhere (`kicad_lib_init.py -n kaibridge`, `easyeda2kicad --output "$PWD/libs/kaibridge"`).
3. **Clean Workspace Rule (`kaibridge_dump/`):** Store all intermediate compiler files (`design.json`, `ops.json`, `erc_report.json`, `drc_report.json`, `board.dsn`, `board.ses`, schematic SVGs, board snapshots) strictly inside `<PROJECT_DIR>/kaibridge_dump/`.
4. **Manual KiCad GUI Resumption:** If the user opens KiCad GUI for manual inspection or edits, they must save (`Ctrl+S`) and close the GUI before running headless commands to prevent OS file locks.

### B. Dual-Modality Mapping Table

| Execution Phase | Root CLI Tool (Mode A) | MCP Tool Equivalent (Mode B) | Typical Runtime |
|---|---|---|---|
| **1. Project Bootstrap** | `python kicad_lib_init.py "projects/<NAME>" -n kaibridge` | `kaibridge_init_project(project_dir, project_name)` | < 0.5s |
| **2. Parts Sourcing (DB)** | `python -c "from kaibridge.sourcing import lookup_by_lcsc; print(lookup_by_lcsc('<ID>'))"` | `kaibridge_lookup_lcsc_part(query, lcsc_id, ...)` | < 1ms |
| **2. Parts Fetch (LCSC)** | `easyeda2kicad --lcsc_id <ID> --symbol --footprint --output "$PWD/libs/kaibridge" --overwrite --project-relative` | `kaibridge_fetch_lcsc_component(project_dir, lcsc_id)` | 2–5s |
| **3. Pin Extraction (Active)**| `python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" -s <SYM> --json` | `kaibridge_query_symbol_pins(project_dir, lib_id)` | < 0.1s |
| **3. Pin Extraction (Stock)** | `python kicad_pins.py --native <LIBRARY_NAME> -s <SYM> --json` | `kaibridge_query_symbol_pins(project_dir, lib_id)` | < 0.1s |
| **3. Pad Verification** | `python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" --verify` | Handled internally by `fetch_lcsc_component` | < 0.2s |
| **4. Preflight Dry-Run** | `python json2sch.py "projects/<NAME>" --dry-run` | Internal compiler validation | < 0.3s |
| **5. Compile & ERC** | `python json2sch.py "projects/<NAME>" --apply-netclasses --erc` | `kaibridge_build_schematic(project_dir, apply_netclasses=True, run_erc_check=True)` | ~ 1.5s |
| **5. Schematic Preview** | `python -c "from kaibridge.pcb import render_schematic_preview; render_schematic_preview('projects/<NAME>')"` | `kaibridge_render_schematic_preview(project_dir, format='svg')` | ~ 1.0s |
| **6. Headless PCB Sync** | `python kicad_pcb_sync.py "projects/<NAME>"` | `kaibridge_sync_to_pcb(project_dir)` | < 0.5s |
| **7. Layout Simulation** | `python kicad_layout.py "projects/<NAME>" "kaibridge_dump/ops.json" --dry-run` | `kaibridge_apply_ops_layout(project_dir, ops, dry_run=True)` | < 0.1s |
| **7. Layout Placement** | `python kicad_layout.py "projects/<NAME>" "kaibridge_dump/ops.json"` | `kaibridge_apply_ops_layout(project_dir, ops, dry_run=False)` | < 0.3s |
| **7. Layout Relaxation** | Integrated in layout compiler | `kaibridge_auto_relax_layout(project_dir, locked_refs=...)` | < 0.5s |
| **7. Placement Snapshot** | `python pcb_snapshot.py "projects/<NAME>"` | `kaibridge_render_pcb_preview(project_dir)` | ~ 1.0s |
| **8. Headless Route & DRC** | `python kicad_route.py "projects/<NAME>" --pour-gnd --drc` | `kaibridge_route_pcb` + `kaibridge_add_ground_plane` + `kaibridge_run_drc` | ~ 5.0s |
| **9. JLCPCB Export** | `python export_jlcpcb.py "projects/<NAME>"` | `kaibridge_export_production(project_dir)` | ~ 2.0s |

---

## 2. Component Sourcing & Zero-Hallucinated Pin Protocol

### Step 1: Upfront BOM Sourcing
Split the Bill of Materials into two categories:

1. **Generic Passives & Standard Connectors (Native KiCad Symbols):**
   - **Symbols:** `Device:R`, `Device:C`, `Device:C_Polarized`, `Device:LED`, `Device:D`, `Device:D_Schottky`, `Device:L`, `Connector_Generic:Conn_01x<N>`.
   - **Footprints:** `Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`, `LED_SMD:LED_0805_2012Metric`, `Diode_SMD:D_SOD-123`, `Connector_PinHeader_2.54mm:PinHeader_1x*`.
   - **LCSC Binding:** Obtain the C-Part ID from [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) or query local database:
     ```powershell
     python -c "from kaibridge.sourcing.parts_db import lookup_by_lcsc; print(lookup_by_lcsc('C17513'))"
     ```
     Attach the ID to the part's `"fields"` block: `{"LCSC": "C17513", "JLCPCB_Class": "Basic Part"}`.

2. **Active ICs, Modules & Specialized Drivers (LCSC Downloads):**
   - Download the symbol, footprint, and 3D model into the project's library:
     ```powershell
     Push-Location "projects/<Project_Name>"
     easyeda2kicad --lcsc_id <LCSC_ID> --symbol --footprint --output "$PWD/libs/kaibridge" --overwrite --project-relative
     Pop-Location
     ```

### Step 2: Zero-Hallucinated Pin & Footprint Extraction
Never assume active IC pinouts or footprint names. Extract them directly from the symbol file:

```powershell
# For downloaded active ICs in project library:
python kicad_pins.py "projects/<Project_Name>\libs\kaibridge.kicad_sym" -s <SYMBOL_NAME> --json

# For stock KiCad native library symbols:
python kicad_pins.py --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json

# Verify pad counts match symbol pin counts:
python kicad_pins.py "projects/<Project_Name>\libs\kaibridge.kicad_sym" --verify
```

**JSON Output Example:**
```json
{
  "symbol": "AMS1117-3.3",
  "footprint": "kaibridge:SOT-223-3_TabPin2",
  "pins": [
    {"num": "1", "name": "ADJ/GND", "type": "power_in"},
    {"num": "2", "name": "VOUT", "type": "power_out"},
    {"num": "3", "name": "VIN", "type": "power_in"}
  ]
}
```

**Extraction Binding Rules:**
- **Footprint:** Copy the `"footprint"` value verbatim into `design.json` (e.g. `"kaibridge:SOT-223-3_TabPin2"`).
- **Pins:** Reference pins strictly by `"<REF>.<PIN_NUM>"` (e.g. `"U1.1"`, `"U1.2"`, `"U1.3"`).

---

## 3. Circuit Specification (`design.json`) Architecture

Write the complete schematic specification to `<PROJECT_DIR>/kaibridge_dump/design.json`.

### A. Minimal Valid Schema Example
```json
{
  "project_name": "PowerModule",
  "paper": "A4",
  "power_flags": ["VBUS", "GND"],
  "netclasses": {
    "Default": { "track_width": 0.25, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3 },
    "Power": {
      "track_width": 0.6,
      "clearance": 0.25,
      "via_diameter": 0.8,
      "via_drill": 0.4,
      "nets": ["VBUS", "+3V3", "GND"]
    }
  },
  "parts": {
    "J1": {
      "symbol": "Connector_Generic:Conn_01x02",
      "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
      "value": "VBUS_IN",
      "fields": { "LCSC": "C22452", "JLCPCB_Class": "Basic Part" }
    },
    "U1": {
      "symbol": "kaibridge:AMS1117-3.3",
      "footprint": "kaibridge:SOT-223-3_TabPin2",
      "value": "AMS1117-3.3",
      "fields": { "LCSC": "C6186", "JLCPCB_Class": "Basic Part" }
    },
    "C1": {
      "symbol": "Device:C",
      "footprint": "Capacitor_SMD:C_0805_2012Metric",
      "value": "10uF",
      "fields": { "LCSC": "C15850", "JLCPCB_Class": "Basic Part" }
    },
    "C2": {
      "symbol": "Device:C",
      "footprint": "Capacitor_SMD:C_0805_2012Metric",
      "value": "22uF",
      "fields": { "LCSC": "C45783", "JLCPCB_Class": "Basic Part" }
    }
  },
  "nets": {
    "VBUS": { "connections": ["J1.1", "U1.3", "C1.1"] },
    "GND": { "connections": ["J1.2", "U1.1", "C1.2", "C2.2"] },
    "+3V3": { "connections": ["U1.2", "C2.1"] }
  }
}
```

### B. Power Flag Rules & Collision Prevention
- **Unregulated Inputs:** External inputs (`VBUS`, `VIN`, `VBAT`, `GND`) MUST be declared in `"power_flags"`.
- **Passive-Interrupted Rails:** Rails downstream of protection diodes, fuses, or switches feeding IC supply pins MUST be declared in `"power_flags"` (e.g. `["VIN_FUSED", "VBUS_SW"]`).
- **Active Regulators:** Active outputs (`+3V3`, `+5V`) internally have `power_out` driver pins. NEVER declare active regulator output nets in `"power_flags"` (causes `[pin_to_pin]` driver collision).
- **Stacked Pins:** If a symbol contains duplicate stacked pins at identical coordinates (e.g. ATmega328P GND pins or USB-C shell pins), declare only the primary visible pin in `design.json` (see [`references/stacked_pins_fix.md`](references/stacked_pins_fix.md)).

### C. Multi-Sheet Hierarchical Schematics
For designs with > 25 components, group sub-circuits into hierarchical sheets:
```json
{
  "sheets": [
    { "id": "power", "title": "Power Regulation", "paper": "A4" },
    { "id": "mcu", "title": "Microcontroller & Crystals", "paper": "A4" },
    { "id": "io", "title": "Connectors & Status LEDs", "paper": "A4" }
  ]
}
```
Assign parts to sheets via `"sheet": "<sheet_id>"`. The compiler automatically creates hierarchical sheet boxes, pins, and labels.

### D. Automated Compilation & Checkpoint 1
```powershell
# 1. Preflight dry-run check:
python json2sch.py "projects/<Project_Name>" --dry-run

# 2. Compile schematic, write netclasses into .kicad_pro, and run KiCad ERC:
python json2sch.py "projects/<Project_Name>" --apply-netclasses --erc
```
**Gate Requirement:** Total ERC Errors must be 0 (`Status: PASSED (0 Errors)`).
Export vector SVG preview to `<PROJECT_DIR>/kaibridge_dump/schematic_svg/` and present as Checkpoint 1.

---

## 4. Declarative Component Layout, Physics & Rotational Doctrine

### Step 1: Headless PCB Synchronization (Programmatic F8)
```powershell
python kicad_pcb_sync.py "projects/<Project_Name>"
```
Binds footprints, values, and net ratsnest into `.kicad_pcb`.

### Step 2: The Conflict Precedence Ladder ([`references/pcb_placement_rules.md`](references/pcb_placement_rules.md) §0.3)
When resolving layout conflicts between competing design rules, apply this strict priority:
- `Tier 0`: **Human Directives** (Explicit user requests, layout constraints, symmetry preferences)
- `Tier 1`: **Safety & High-Voltage Isolation**
- `Tier 2`: **Mechanical Datums** (Perimeter connectors facing outward, mounting holes)
- `Tier 3`: **Electrical Proximity** (Decoupling caps < 2.5mm from IC power pins, crystal adjacent to OSC pins, feedback resistors < 5mm from FB pin)
- `Tier 4`: **Thermal Survival** (Linear regulator heatsink tabs facing board edge, distributed hot components)
- `Tier 5`: **EMC Margin** (Switching nodes isolated from sensitive analog/clocks)
- `Tier 6`: **Manufacturability / DFM**
- `Tier 7`: **Aesthetics & Visual Symmetry** (Last: never push decoupling capacitors away to make a pretty row)

### Step 3: Discrete Layout Operations (`ops.json`)
Construct `<PROJECT_DIR>/kaibridge_dump/ops.json` using the 17 built-in layout operations. Coordinates are automatically quantized to a **0.5mm grid**.

**Layout Operations Catalog:**
| Operation | Key Parameters | Description |
|---|---|---|
| `board.set_size` | `width`, `height`, `origin_x`, `origin_y` | Creates clean rectangular `Edge.Cuts` board boundary. |
| `board.fit_outline` | `margin` | Dynamically fits `Edge.Cuts` around placed footprints. |
| `footprint.place` | `ref`, `x`, `y`, `rot`, `locked` | Places footprint at $(X,Y)$ with specified rotation ($0^\circ, 90^\circ, 180^\circ, 270^\circ$). |
| `array.place` | `refs`, `start_x`, `start_y`, `pitch_x`, `pitch_y`, `rot` | Places a linear sequence of components with uniform spacing. |
| `footprint.move` | `ref`, `x`, `y` | Repositions footprint. |
| `footprint.rotate` | `ref`, `rot`, `relative` | Sets absolute or relative angular orientation. |
| `footprint.lock` | `ref` | Locks component to prevent displacement during routing or auto-relaxation. |
| `footprint.unlock` | `ref` | Unlocks component. |
| `footprint.set_field` | `ref`, `field`, `value` | Sets footprint field (e.g. `"LCSC"`, `"Value"`). |
| `item.delete` | `ref` or `uuid` | Removes footprint or item. |
| `track.add` | `start_x`, `start_y`, `end_x`, `end_y`, `width`, `layer`, `net` | Adds manual copper trace segment. |
| `track.set_width` | `width`, `net`, `netclass` | Resizes existing tracks. |
| `via.add` | `x`, `y`, `size`, `drill`, `net` | Adds copper through-hole via. |
| `zone.delete` | `layer`, `net` | Removes copper zone. |
| `zone.refill` | (None) | Recalculates all copper pour fills on board. |
| `net.delete_routing` | `net` | Purges tracks and vias associated with net. |
| `board.prep_for_route` | (None) | Purges orphaned tracks and validates `Edge.Cuts` closure. |

### Step 4: Universal Rotational Doctrine
Component placement requires intentional angular orientations:
1. **Perimeter Connectors & Headers:**
   Mating openings and wire corridors MUST face outward toward the nearest board edge:
   - Left edge: `"rot": 180`
   - Bottom edge: `"rot": 270`
   - Right edge: `"rot": 0`
   - Top edge: `"rot": 90`
2. **Thermal Dissipation Devices (LDOs, MOSFETs, Regulators):**
   Heatsink tabs (e.g. SOT-223 tab 2, DPAK) MUST face outward toward the board edge or ground pour areas. Never face tabs toward sensitive MCUs or crystals.
3. **Decoupling Capacitors (0805 / 0603):**
   Rotate ($0^\circ$ or $90^\circ$) to align GND and supply pads directly inline with companion IC pins (< 2.5mm distance).
4. **Critical Component Locking (`LCK-01`):**
   Immediately after placing crystals (`OSC-01`), RF elements, sensitive analog nodes, and perimeter connectors (`CON-01`), lock their positions:
   ```json
   { "op": "footprint.lock", "ref": "Y1" }
   ```
5. **Silkscreen Hygiene:**
   - Reference designators (`R1`, `C1`, `U1`) must be visible, sized $1.0\text{mm} \times 1.0\text{mm}$ (thickness $0.15\text{mm}$), and positioned outside courtyards.
   - Hide bulky value text from `F.SilkS` to avoid text overlapping pads, tracks, or neighboring components.

### Step 5: Execution & In-Memory Simulation
```powershell
# 1. In-memory dry-run collision simulation (zero disk write):
python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json" --dry-run

# 2. Commit placement to board file:
python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json"

# 3. Export vector snapshot for visual critique:
python pcb_snapshot.py "projects/<Project_Name>"
```

---

## 5. Multimodal Visual Critique & Refinement Protocol (The Vision Gate)

Before proceeding from placement (Checkpoint 2) to routing, the AI Agent MUST view the rendered vector layout snapshot (`<project>_board.svg` / `<project>_top.png`) and execute the **Vision Gate**:

### A. 5-Point Visual QA Evaluation Checklist:
1. **Routing Corridors (`DFM-03`):** Are there open, unblocked channels ($\ge 2.5\text{mm}$) between ICs and connectors for bus routing?
2. **Decoupling Proximity (`DEC-02`):** Are ceramic bypass capacitors ($0.1\mu\text{F}$) within $1.0–2.5\text{mm}$ of their companion IC supply pins with pads inline?
3. **Oscillator / Crystal Loop (`OSC-01`):** Is the crystal adjacent to OSC pins ($\le 5\text{mm}$) with compact, symmetrical load capacitors?
4. **Thermal & Mechanical Spacing (`THM-02`):** Are power FETs/regulators spaced $\ge 3\text{mm}$ from heat-sensitive ICs, with tabs facing outward?
5. **Connector Ergonomics (`CON-01`, `CON-02`):** Are headers and USB/power ports flush along board edges, facing outward, with $\ge 3\text{mm}$ plug clearance?

### B. Structured Visual Critique Table Format:
The agent MUST formulate its visual inspection findings in this structured schema before generating adjustment ops:

| Ref | Current Observation | Violated Rule ID | Severity | Corrective Action | Target Coordinate / Rotation |
|---|---|---|---|---|---|
| `C1` | Placed 5.2mm away from MCU VDD pin 18 | `DEC-02` | High | Nudge closer to pin 18 | `x: 132.5, y: 84.0, rot: 90` |
| `Y1` | Long loop trace between crystal & pins | `OSC-01` | Medium | Move directly above pins 7-8 | `x: 125.0, y: 78.0, rot: 0` |
| `J1` | Receptacle facing inward toward MCU | `CON-02` | High | Rotate 180 deg to face left edge | `rot: 180` |
| `R1, R2`| Staggered irregularly | `SYM-01` | Low | Align Y axis to 92.0mm | `x: 118.0, y: 92.0, rot: 0` |

### C. Critique-to-Ops Translation Loop:
Convert the corrective actions directly into an adjustment `ops.json`:
```json
[
  {"op": "footprint.place", "ref": "C1", "x": 132.5, "y": 84.0, "rot": 90},
  {"op": "footprint.place", "ref": "Y1", "x": 125.0, "y": 78.0, "rot": 0},
  {"op": "footprint.place", "ref": "J1", "x": 5.0, "y": 25.0, "rot": 180, "locked": true}
]
```
Execute via `python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json"` and re-render with `pcb_snapshot.py` until all visual criteria pass. Present the verified snapshot as Checkpoint 2.

---

## 6. Headless Routing, Ground Pour & Production Export

### Step 1: Headless Autorouting (Freerouting 2.4.1)
```powershell
python kicad_route.py "projects/<Project_Name>" --pour-gnd --drc
```

**Technical Pipeline Details:**
1. **0.15mm JLCPCB Copper Edge Clearance Rule:** KiCad 10 default is `0.50mm`, which causes false DRC errors on USB-C and edge connectors. Kaibridge automatically writes JLCPCB production rules (`min_copper_edge_clearance: 0.15mm`, `min_clearance: 0.15mm`, `min_track_width: 0.15mm`) into `.kicad_pro`.
2. **Specctra DSN Pre-Flight Audit:** Verifies track widths > 0, clearances, and netclasses in < 2ms before starting Java.
3. **Freerouting 2.4.1 Decoupled Execution:** Runs headless Java router with 150µm edge keepout (`--router.copperToEdgeClearanceUm=150`) and strict geometric DRC (`--router.strictDrc=true`).
4. **Mandatory Post-SES Zone Refill:** Merges routed tracks, rebuilds connectivity, and refills copper zones around newly routed traces to eliminate zone shorts.
5. **Solid Ground Pour:** Clips a solid GND copper plane across `B.Cu` (0.3mm clearance, `ZONE_CONNECTION_FULL`, minimum 0.2mm thickness) to prevent starved thermal relief errors.
6. **KiCad DRC Gate:** Runs `kicad-cli pcb drc` with `--refill-zones`. **Must report 0 clearance violations and 0 unconnected items.**

Present DRC pass confirmation as Checkpoint 3.

### Step 2: 100% Populated JLCPCB Production Export
```powershell
python export_jlcpcb.py "projects/<Project_Name>"
```

**Generates factory-ready files in `<PROJECT_DIR>/production_output/`:**
- `<Project_Name>_bom_jlcpcb.csv`: Groups identical parts with columns `Comment,Designator,Footprint,LCSC Part #` (100% populated with auto-healing).
- `<Project_Name>_cpl_jlcpcb.csv`: Centroid SMT placement table (`Designator,Val,Package,Mid X,Mid Y,Rotation,Layer`) formatted as clean numeric floats.
- `<Project_Name>_gerbers.zip`: Complete fabrication and Excellon drill archive ready for JLCPCB upload.

---

## 7. Board State Introspection, Snapshots & API Oracle (Mode B)

When running via MCP tools or diagnostic scripts:
1. **Introspection:** Call `kaibridge_inspect_board(project_dir, mode="summary"|"full")` or `kaibridge_audit_placement(project_dir)`.
2. **Snapshot Diff & Rollback Protocol:**
   - Pre-action checkpoint: `kaibridge_snapshot_board(project_dir, tag="pre_layout")`
   - Structural diffing: `kaibridge_diff_board(project_dir, tag_a="pre_layout")`
   - Deterministic rollback: `kaibridge_restore_snapshot(project_dir, tag="pre_layout")`
3. **SWIG Memory Safety & Subprocess Isolation:**
   Always run SWIG `pcbnew` via KiCad's bundled Python (`load_kicad_python()`), and perform explicit memory cleanup:
   ```python
   import gc, pcbnew
   gc.collect()
   board = pcbnew.LoadBoard("project.kicad_pcb")
   # ... operations ...
   del board
   gc.collect()
   ```
4. **Live SWIG Oracle:** Query host `pcbnew.py` methods/constants in < 4ms: `kaibridge_api_oracle(query="ExportSpecctraDSN", class_name="BOARD")`.

---

## 8. Deep Domain Knowledge Base Directory

Consult these canonical reference documents inside `references/` for specialized rules:

| Document | Trigger / When to Consult | Core Contents |
|---|---|---|
| [`references/art_gate_protocol.md`](references/art_gate_protocol.md) | Turn 1 requirement extraction & adversarial red-team verification | 3-layer attack (Requirements, DFM, Domain failure modes), Why-Should-This-Exist resolver, and convergence criteria. |
| [`references/adversarial_dfm_checklist.md`](references/adversarial_dfm_checklist.md) | Layer 1 DFM audit during planning | Tier A Hard Rules (`PWR`, `IND`, `MCU`, `MECH`, `DFM`), Tier B Heuristics (`DEC`, `LAY`, `SIG`, `THM`). |
| [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) | Component sourcing for passives, LEDs, diodes, and regulators | Verified 0-fee JLCPCB Basic Parts catalog with exact LCSC IDs and KiCad IPC footprint mappings. |
| [`references/pcb_placement_rules.md`](references/pcb_placement_rules.md) | Formulating `ops.json` coordinates and visual critique | 80-rule comprehensive floorplanning doctrine, precedence ladder (§0.3), Appendix A target constraints, and Appendix B vision QA rubric. |
| [`references/trackwidth_clearence_viasize.md`](references/trackwidth_clearence_viasize.md) | Declaring `"netclasses"` in `design.json` | Current-carrying trace width formulas, minimum clearances, and via hole/pad sizing rules. |
| [`references/stacked_pins_fix.md`](references/stacked_pins_fix.md) | Symbols with duplicate stacked pins (MCU GND, USB shell) | Protocol for specifying only primary visible pin to avoid netlabel overlap and ERC warnings. |
| [`references/failure_recovery_matrix.md`](references/failure_recovery_matrix.md) | Any ERC violation, DRC error, Freerouting fault, or SWIG crash | Deterministic symptom -> root cause -> exact recovery lookup table. |
| [`references/jlcpcb_production.md`](references/jlcpcb_production.md) | Final manufacturing handoff | JLCPCB file formats, layer naming, centroid coordinate calculation, and ordering walk-through. |
| [`references/command_help.md`](references/command_help.md) | Detailed parameter lookup | Parameter documentation for all 22 MCP tools and 8 Root CLI tools. |
| [`references/architectural_landscape_and_contributions.md`](references/architectural_landscape_and_contributions.md) | Architecture review | Headless compiler paradigm vs interactive co-pilot analysis and technical innovations. |
