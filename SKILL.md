---
name: KiCad Kaibridge 2.0 Hardware Automation Engine & MCP Protocol
description: Procedural handbook and technical reference for Kaibridge 2.0 — headless KiCad 10 hardware synthesis, dual-modality execution (Root CLI & 25 MCP tools), upfront LCSC sourcing, zero-hallucinated pin extraction, declarative layout, closed-loop visual critique, Freerouting 2.4.1, and 100% JLCPCB production export.
---

# Kaibridge 2.0 Procedural Execution & Technical Reference

This handbook contains the exact procedural steps, schemas, CLI commands, visual critique rubrics, and technical parameters required to execute hardware synthesis in Kaibridge 2.0.

---

## 1. Execution Architecture, Session Contract & Tool Mappings

Kaibridge provides two coordinated execution interfaces: the **9 Canonical Root CLI Tools** (for terminal/subagent execution via `run_command`) and the **25 MCP Tools** (23 canonical + 2 aliases, for direct tool calling when registered in the environment).

### A. Session Contract & Project Resolution
1. **Directory Handling:** Default project path is `projects/<Project_Name>`. If user provides an explicit path, use it directly.
2. **Library Nickname:** `<LIB_NAME>` is strictly `kaibridge` everywhere (`kicad_lib_init.py -n kaibridge`, `easyeda2kicad --output "$PWD/libs/kaibridge"`).
3. **Clean Workspace Rule (`kaibridge_dump/`):** Store all intermediate compiler files (`design.json`, `ops.json`, `erc_report.json`, `drc_report.json`, `board.dsn`, `board.ses`, schematic SVGs, board snapshots) strictly inside `<PROJECT_DIR>/kaibridge_dump/`.
4. **Manual KiCad GUI Resumption:** If the user opens KiCad GUI for manual inspection or edits, they must save (`Ctrl+S`) and close the GUI before running headless commands to prevent OS file locks.

### B. Dual-Modality Mapping Table

| Execution Phase | Root CLI Tool (Mode A) | MCP Tool Equivalent (Mode B) | Typical Runtime |
|---|---|---|---|
| **1. Project Bootstrap** | `python kicad_lib_init.py "projects/<NAME>" -n kaibridge` | `kaibridge_init_project(project_dir, project_name)` | < 0.5s |
| **2A. Active IC Fetch (Priority 1)** | `easyeda2kicad --lcsc_id <ID> --symbol --footprint --output "$PWD/libs/kaibridge" --overwrite --project-relative` | `kaibridge_fetch_lcsc_component(project_dir, lcsc_id)` | 2–5s |
| **2B. Passive Sourcing (Native)** | Map C-Part ID from `references/jlcpcb_basic_parts.md` to native `Device:*` + IPC-7351 footprint | Bound upfront in `design.json` | < 0.1s |
| **2C. Offline Query (Optional)** | `python -c "from kaibridge.sourcing import lookup_by_lcsc; print(lookup_by_lcsc('<ID>'))"` | `kaibridge_lookup_lcsc_part(query, lcsc_id, ...)` | < 1ms |
| **3. Pin Extraction (Active)**| `python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" -s <SYM> --json` | `kaibridge_query_symbol_pins(project_dir, lib_id)` | < 0.1s |
| **3. Pin Extraction (Stock)** | `python kicad_pins.py --native <LIBRARY_NAME> -s <SYM> --json` | `kaibridge_query_symbol_pins(project_dir, lib_id)` | < 0.1s |
| **3. Pad Verification** | `python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" --verify` | Handled internally by `fetch_lcsc_component` | < 0.2s |
| **4. Preflight Dry-Run** | `python json2sch.py "projects/<NAME>" --dry-run` | Internal compiler validation | < 0.3s |
| **5. Compile & ERC** | `python json2sch.py "projects/<NAME>" --apply-netclasses --erc` | `kaibridge_build_schematic(project_dir, apply_netclasses=True, run_erc_check=True)` | ~ 1.5s |
| **5. Schematic Preview** | `python -c "from kaibridge.pcb import render_schematic_preview; render_schematic_preview('projects/<NAME>')"` | `kaibridge_render_schematic_preview(project_dir, format='svg')` | ~ 1.0s |
| **6. Headless PCB Sync** | `python kicad_pcb_sync.py "projects/<NAME>"` | `kaibridge_sync_to_pcb(project_dir)` | < 0.5s |
| **7A. Planar Optimization (Primary)** | `python kicad_planar_optimizer.py "projects/<NAME>"` | `kaibridge_optimize_planar_layout(project_dir, steps=6000, temp=70.0)` | ~ 1.5s |
| **7B. Placement Ops & Commit** | `python kicad_layout.py "projects/<NAME>" "kaibridge_dump/ops.json"` | `kaibridge_apply_ops_layout(project_dir, ops)` | < 0.3s |
| **7B. Visual Audit Snapshot** | `python pcb_snapshot.py "projects/<NAME>"` | `kaibridge_render_pcb_preview(project_dir)` | ~ 1.0s |
| **8. 3-Tier Route & DRC Gate** | `python kicad_route.py "projects/<NAME>" --pour-gnd --drc` | `kaibridge_route_pcb` + `kaibridge_add_ground_plane` + `kaibridge_run_drc` | ~ 5.0s |
| **9. JLCPCB Export** | `python export_jlcpcb.py "projects/<NAME>"` | `kaibridge_export_production(project_dir)` | ~ 2.0s |

---

## 2. Component Sourcing Hierarchy & Zero-Hallucinated Pin Protocol

### Step 1: The Two-Tier BOM Sourcing Doctrine
Split the Bill of Materials strictly by component class:

1. **Active Components, ICs, Modules & Complex Connectors (Priority 1 — On-Demand Download):**
   - **Rule:** ALL active ICs (MCUs, transceivers, op-amps, linear regulators, buck/boost converters, sensors, gate drivers) and complex connectors (USB-C receptacles like `TYPE-C-31-M-12`, barrel jacks, HDMI) MUST be fetched directly on-demand via `easyeda2kicad`.
   - **Command:**
     ```powershell
     Push-Location "projects/<Project_Name>"
     easyeda2kicad --lcsc_id <LCSC_ID> --symbol --footprint --output "$PWD/libs/kaibridge" --overwrite --project-relative
     Pop-Location
     ```
   - **Why:** Fetches exact manufacturer symbol, pad geometries, courtyard boundaries, and 3D step model into `libs/kaibridge`. Downloaded symbols are automatically pin-healed to standard KiCad electrical types.

2. **Small Discrete Passives & Pin Headers (Priority 2 — Native KiCad + Upfront LCSC Binding):**
   - **Rule:** NEVER download small passives from EasyEDA (their symbols trigger `[pin_not_driven]` ERC errors and their footprints lack standardized courtyards). Generic resistors, capacitors, inductors, discrete diodes, LEDs, and standard 2.54mm pin headers MUST use native KiCad symbols and standardized KiCad IPC-7351 SMD footprints.
   - **Symbols:** `Device:R`, `Device:C`, `Device:C_Polarized`, `Device:LED`, `Device:D`, `Device:D_Schottky`, `Device:L`, `Connector_Generic:Conn_01x<N>`.
   - **Footprints:** `Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`, `LED_SMD:LED_0805_2012Metric`, `Diode_SMD:D_SOD-123`, `Connector_PinHeader_2.54mm:PinHeader_1x*`.
   - **LCSC Binding:** Obtain the verified Basic Part C-ID directly from [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) and attach it to the part's `"fields"` block:
     `{"LCSC": "C17513", "JLCPCB_Class": "Basic Part"}`.

3. **Offline SQLite Catalog (`easyeda-std.elib`) (Optional Secondary Search Only):**
   - Purely an optional local search index for parametric lookup if the 142MB database is downloaded.
   - **Zero-Block Mandate:** The AI agent must NEVER assume or block on `easyeda-std.elib` being present. It does NOT supply symbols or footprints. If absent, simply proceed directly with Priority 1 (`easyeda2kicad`) and Priority 2 (native passives).


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

**Mode A JSON Output (`kicad_pins.py --json`):**
Returns a list of symbol dictionaries:
```json
[
  {
    "name": "AMS1117-3.3",
    "extends": null,
    "footprint": "kaibridge:SOT-223-3_TabPin2",
    "datasheet": "",
    "pins": [
      {"number": "1", "name": "ADJ/GND", "type": "power_in"},
      {"number": "2", "name": "VOUT", "type": "power_out"},
      {"number": "3", "name": "VIN", "type": "power_in"}
    ]
  }
]
```

**Mode B JSON Output (`kaibridge_query_symbol_pins`):**
Returns a dictionary with pins keyed by pin number:
```json
{
  "success": true,
  "lib_id": "kaibridge:AMS1117-3.3",
  "symbol_name": "AMS1117-3.3",
  "default_footprint": "kaibridge:SOT-223-3_TabPin2",
  "pin_count": 3,
  "pins": {
    "1": {"name": "ADJ/GND", "type": "power_in", "pos": [0.0, 0.0], "rot": 0},
    "2": {"name": "VOUT", "type": "power_out", "pos": [0.0, 0.0], "rot": 0},
    "3": {"name": "VIN", "type": "power_in", "pos": [0.0, 0.0], "rot": 0}
  }
}
```

**Extraction Binding Rules:**
- **Footprint:** Copy the footprint value verbatim (`"footprint"` in Mode A, `"default_footprint"` in Mode B) into `design.json` (e.g. `"kaibridge:SOT-223-3_TabPin2"`).
- **Pins:** Reference pins strictly by `"<REF>.<PIN_NUMBER>"` matching the extracted pin numbers (e.g. `"U1.1"`, `"U1.2"`, `"U1.3"`).

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

### B. Power Flag Rules & Netclass Architecture
- **Unregulated Inputs:** External inputs (`VBUS`, `VIN`, `VBAT`, `GND`) MUST be declared in `"power_flags"`.
- **Passive-Interrupted Rails:** Rails downstream of protection diodes, fuses, or switches feeding IC supply pins MUST be declared in `"power_flags"` (e.g. `["VIN_FUSED", "VBUS_SW"]`).
- **Active Regulators:** Active outputs (`+3V3`, `+5V`) internally have `power_out` driver pins. NEVER declare active regulator output nets in `"power_flags"` (causes `[pin_to_pin]` driver collision).
- **Stacked Pins & USB-C Receptacles:** If multiple symbol pins share identical physical coordinates or if a connector has mirrored/stacked copper pads (e.g. USB-C `TYPE-C-31-M-12` pads `A1/B12`, `A4/B9`, `A9/B4`, `A12/B1`), declare ONLY the primary visible pins (`A1`, `A4`, `A9`, `A12`) in `design.json`. Declare connector shield pins (`SH`) in `no_connect` unless tied to a dedicated chassis net.
- **Fine-Pitch IC Netclass Necking:** For components with pin pitch $\le 0.5\text{mm}$ (e.g. LQFP-48, QFN, BGA with $0.20\text{mm}$ pad-to-pad clearance), `Power` netclass track width MUST NOT exceed $0.25\text{mm}$ and clearance MUST NOT exceed $0.20\text{mm}$. Setting wider tracks ($0.5\text{mm}$–$0.6\text{mm}$) causes entry clearance collisions on supply pins (VDD/VSS), trapping Freerouting in infinite rip-up deadlocks. Consult [`references/trackwidth_clearence_viasize.md`](references/trackwidth_clearence_viasize.md).

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
5. **Silkscreen Hygiene & CPL Independence:**
   - Standard boards: Reference designators (`R1`, `C1`, `U1`) should be visible, sized $1.0\text{mm} \times 1.0\text{mm}$ (thickness $0.15\text{mm}$), positioned outside courtyards.
   - Hide bulky value text from `F.SilkS` to avoid text overlapping pads, tracks, or neighboring components.
   - *High-Density & Clean Aesthetics Protocol:* On high-density boards (e.g. 48-pin MCUs, compact layouts) or upon user request, silkscreen reference designators and values can be hidden (`fp.Reference().SetVisible(False)`, `fp.Value().SetVisible(False)`). JLCPCB automated SMT pick-and-place assembly relies 100% on the Centroid CPL file (`.cpl_jlcpcb.csv`) and BOM, NOT silkscreen text. Machine vision locates component centroids using board fiducials and pad geometries; silkscreen text visibility does not affect manufacturing yield.
   - *Native CLI Sanitation:* Run `python kicad_layout.py "projects/<NAME>" --sanitize-silk` to automatically hide bulky values and auto-hide references colliding with copper pads, or `--hide-silk` for complete clean aesthetic.

### Step 5: Primary Engine: In-Memory Planar Optimization
Immediately after footprint instantiation and netlist sync, run the mathematical planar optimizer:
```powershell
# Mode A: CLI
python kicad_planar_optimizer.py "projects/<Project_Name>"

# Mode B: MCP
kaibridge_optimize_planar_layout(project_dir="projects/<Project_Name>", steps=6000, temp=70.0)
```
- **Simulates 20,000 states in < 2 seconds** using simulated annealing with Kruskal's Minimum Spanning Tree (MST) per net.
- **Reduces cross-net ratsnest intersections by >85%**, drastically opening planar routing corridors on `F.Cu`.
- **Enforces physical pad-to-pad keepouts and decoupling proximity**, writing the globally optimal coordinates to `kaibridge_dump/ops.json` and committing to the board.
- **Dynamic Decoupling & Proximity Pairing:** Automatically identifies 2-pin bypass capacitors between power and GND, dynamically pairing them with their companion IC (distance constraint scaled by package: $\le 7.0\text{mm}$ for LQFP-48, $\le 5.0\text{mm}$ for SOIC, $\le 4.0\text{mm}$ for SOT). Binds crystal resonators ($\le 5.0\text{mm}$) to MCU OSC pins and crystal load capacitors ($\le 3.5\text{mm}$) to the crystal.
- **Agent Grouping Doctrine (`design.json`):** When authoring `design.json`, group parts into functional `"groups"` (e.g. `"mcu_core"`, `"can_bus"`, `"ldo_reg"`, `"clock_reset"`) or declare `"group": "<group_id>"` on each component. This ensures 100% deterministic pairing between decoupling capacitors and their target ICs when multiple ICs share a single power rail (`+3V3`/`VCC`).

---

## 5. Multimodal Visual Critique & Refinement Protocol (Secondary Audit Gate)

Before proceeding from placement (Checkpoint 2) to routing, the AI Agent renders the vector layout snapshot (`pcb_snapshot.py`) and executes the **Vision Gate**:

### A. Primary Engine vs. Secondary Audit Hierarchy
- **`kicad_planar_optimizer.py` is the Primary Global Layout Engine (Macro):** Computational heavy-lifting is executed purely via geometry math (reducing wirelength and topological crossings).
- **Visual Critique is the Secondary Quality Assurance Gate (Micro / Sanity Check):** Acts strictly as the inspector. The Vision Model inspects the rendered snapshot to audit physical, mechanical, and human ergonomics that pure cost functions cannot see (e.g. connector plug clearance, silkscreen text overlapping pads, heatsink tab direction).
- **Zero Redundant Iterations:** Because the Planar Optimizer solves global placement mathematically, in >90% of designs the Visual QA Gate passes immediately on the first evaluation without blind LLM layout shuffling.

### B. 5-Point Visual QA Evaluation Checklist:
1. **Routing Corridors (`DFM-03`):** Are there open, unblocked channels ($\ge 2.5\text{mm}$) between ICs and connectors for bus routing?
2. **Decoupling Proximity (`DEC-02`):** Are ceramic bypass capacitors ($0.1\mu\text{F}$) within $1.0–2.5\text{mm}$ of their companion IC supply pins with pads inline?
3. **Oscillator / Crystal Loop (`OSC-01`):** Is the crystal adjacent to OSC pins ($\le 5\text{mm}$) with compact, symmetrical load capacitors?
4. **Thermal & Mechanical Spacing (`THM-02`):** Are power FETs/regulators spaced $\ge 3\text{mm}$ from heat-sensitive ICs, with tabs facing outward?
5. **Connector Ergonomics (`CON-01`, `CON-02`):** Are headers and USB/power ports flush along board edges, facing outward, with $\ge 3\text{mm}$ plug clearance?

### C. Structured Visual Critique Table Format:
If any ergonomic or mechanical issues are detected during visual audit, output findings in this structured schema before generating ops:

| Ref | Current Observation | Violated Rule ID | Severity | Corrective Action | Target Coordinate / Rotation |
|---|---|---|---|---|---|
| `C1` | Placed 5.2mm away from MCU VDD pin 18 | `DEC-02` | High | Nudge closer to pin 18 | `x: 132.5, y: 84.0, rot: 90` |
| `Y1` | Long loop trace between crystal & pins | `OSC-01` | Medium | Move directly above pins 7-8 | `x: 125.0, y: 78.0, rot: 0` |
| `J1` | Receptacle facing inward toward MCU | `CON-02` | High | Rotate 180 deg to face left edge | `rot: 180` |
| `R1, R2`| Staggered irregularly | `SYM-01` | Low | Align Y axis to 92.0mm | `x: 118.0, y: 92.0, rot: 0` |

### D. Critique-to-Ops Translation Loop:
Convert corrective actions directly into an adjustment `ops.json`:
```json
[
  {"op": "footprint.place", "ref": "C1", "x": 132.5, "y": 84.0, "rot": 90},
  {"op": "footprint.place", "ref": "Y1", "x": 125.0, "y": 78.0, "rot": 0},
  {"op": "footprint.place", "ref": "J1", "x": 5.0, "y": 25.0, "rot": 180, "locked": true}
]
```
Execute via `python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json"` and re-render with `pcb_snapshot.py` until all visual criteria pass. Present the verified snapshot as Checkpoint 2.

---

## 6. Headless Routing, Dual-Strategy Engine & Production Export

### Step 1: Routing Strategy Selection & Headless Routing
Execute headless autorouting deterministically with zero configuration:
```powershell
python kicad_route.py "projects/<Project_Name>" --pour-gnd --drc
```

1. **Automatic Strategy Selection (`--strategy auto`):**
   - **Strategy 1 (Dog-Bone Fanout First):** Selected automatically for discrete/simple boards (all ICs $<24$ pins, nets $\le 20$). Pre-places $0.6\text{mm}$ structural vias ($0.3\text{mm}$ drill) outside SMD GND pads with $0.25\text{mm}$ `F.Cu` escape necks, strips GND from DSN, and routes signals purely on `F.Cu` with **zero signal vias**.
   - **Strategy 2 (Dual-Layer Routing):** Selected automatically for dense MCUs ($\ge 24$ pins or nets $>20$). Routes signals across `F.Cu` and `B.Cu` using short jumper vias ($0.6\text{mm}$ pad / $0.3\text{mm}$ drill), followed by a solid continuous GND copper plane on `B.Cu` ($0.3\text{mm}$ clearance, `ZONE_CONNECTION_FULL`, $\ge 0.2\text{mm}$ thickness) swallowing all GND vias and pins.
   - **Zero-Failure Auto-Fallback:** If Strategy 1 produces unrouted airwires or times out, the router automatically unlinks `<stem>.rules`, cleans tracks, and recovers via Strategy 2 with 5 optimization passes (`max_passes=5`), guaranteeing zero unrouted airwires without human intervention.

2. **CRITICAL: Specctra DSN Cleanliness & Stale Rules Elimination:**
   - **Zone & Track Purge:** Prior to exporting DSN, all existing copper tracks, vias, AND copper zones MUST be purged from the board (`board.prep_for_route`). If previous zones persist on `B.Cu`, KiCad exports `(plane GND (polygon B.Cu ...))` which locks `B.Cu` against signal routing in Freerouting, triggering infinite rip-up loops.
   - **Stale Rules Deletion:** When switching strategies or rerunning, `<stem>.rules` containing `(vias off)` is unconditionally unlinked.
   - **Deterministic Fast Optimizer (`-mp 1` & `-Xmx1024m`):** Freerouting is capped at 1 optimization pass (or 5 on fallback) and 1024MB heap, guaranteeing fast convergence (< 20s) while eliminating JVM runaway native memory allocations.
   - **Island Removal:** Copper ground zones enforce `ISLAND_REMOVAL_MODE_ALWAYS` to eliminate floating copper antennas.
   - **4-Layer Profile & Dedicated Planes:** Initialized via `kicad_lib_init.py --layers 4` for standard JLCPCB JLC04161H stackup (`F.Cu` signal, `In1.Cu` GND, `In2.Cu` Power, `B.Cu` GND). Routed via `kicad_route.py --layers 4 --pour-gnd`, which automatically detects primary power rails (`+3V3`, `3V3`, `+5V`, `5V`, `VCC`, `VDD`, `VBUS`, `VIN`, `VBAT`) and pours solid continuous copper planes on `In1.Cu` (GND), `In2.Cu` (Power), and `B.Cu` (GND) with automatic island removal (`ISLAND_REMOVAL_MODE_ALWAYS`).

3. **Via Density & DFM Standard (Engineering Truth):**
   - For a 2-layer board with a 32–48 pin MCU and 20–35 passives/ICs, having **15–30 total vias** (10–12 GND return vias from decoupling capacitors directly to the B.Cu plane + 10–18 short signal jumper vias) is standard industrial best practice.
   - A short via transition (inductance $\approx 1.2\text{nH}$) is far superior to a $30\text{mm}$ serpentine trace detour around the MCU edge (which adds $>30\text{nH}$ parasitic inductance and acts as a loop antenna).
   - Fabricators (e.g. JLCPCB standard pool) charge identically for 1 via vs 100 vias ($2 for 5 boards). Zero cost penalty applies.

4. **Mandatory Post-SES Zone Refill:** Merges routed tracks, rebuilds connectivity, and refills copper zones around newly routed traces to eliminate zone shorts.
5. **KiCad DRC Gate & Warning Transparency:**
   - Runs `kicad-cli pcb drc` with `--severity-all` and `--refill-zones`.
   - **Zero Tolerances:** Must report **0 clearance errors** and **0 unconnected items**.
   - **Warning Visibility:** All warnings (e.g. `[silk_over_copper]`, `[hole_clearance]`, `[track_dangling]`) are surfaced with full type, pad, and coordinate context.
   - **Micro-Track Auto-Pruning:** Dangling micro-stubs ($< 0.08\text{mm}$) left by Freerouting overshoot are automatically cleaned upon SES import, preventing spurious `[track_dangling]` warnings.
   - Status explicitly distinguishes `PASSED CLEAN (0 Errors, 0 Warnings)` from `PASSED WITH WARNINGS (0 Errors, X Warnings)`.

Present DRC pass confirmation as Checkpoint 3.

### Step 3: 100% Populated JLCPCB Production Export
```powershell
python export_jlcpcb.py "projects/<Project_Name>"
```

**Generates factory-ready files in `<PROJECT_DIR>/production_output/`:**
- `<Project_Name>_bom_jlcpcb.csv`: Groups identical parts with columns `Comment,Designator,Footprint,LCSC Part #` (100% populated with auto-healing).
- `<Project_Name>_cpl_jlcpcb.csv`: Centroid SMT placement table (`Designator,Val,Package,Mid X,Mid Y,Rotation,Layer`) formatted as clean numeric floats with **automated SMT rotation angle compensation (`DFM-ROT`)**. Corrects the $180^\circ$ discrepancy between KiCad IPC-7351 and JLCPCB EIA-481 tape feeders for `Diode_SMD`, `LED_SMD`, `SOT-23`, `SOT-223`, and polarized capacitors, while keeping EasyEDA `kaibridge:*` parts at $0^\circ$. Supports custom overrides via `"rotation_offset": <deg>` in `design.json`.
- `<Project_Name>_gerbers.zip`: Complete fabrication and Excellon drill archive ready for JLCPCB upload (automatically includes all 4 copper layers `F_Cu.gtl`, `GND.g1`, `Power.g2`, `B_Cu.gbl` on 4-layer boards).

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
| [`references/command_help.md`](references/command_help.md) | Detailed parameter lookup | Parameter documentation for all 25 MCP tools and 9 Root CLI tools. |
| [`references/architectural_landscape_and_contributions.md`](references/architectural_landscape_and_contributions.md) | Architecture review | Headless compiler paradigm vs interactive co-pilot analysis and technical innovations. |
