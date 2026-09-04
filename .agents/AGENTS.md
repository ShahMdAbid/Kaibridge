# Kaibridge Autonomous Agent Rules & Execution Protocol

The following core rules MUST be followed by all AI agents operating within this repository:

---

### 0. Hardware Design & Execution Protocol
When starting any new PCB project or responding to a design request, follow this sequential execution pipeline. Do not write scratch scripts, run exploratory probes, or guess pinouts.

```
+--------------------------------------------------------------------------------------------------------------------------------+
|  HARDWARE DESIGN & MANUFACTURING PIPELINE                                                                                      |
|                                                                                                                                |
|  [Step 1] Bootstrap                   python kicad_lib_init.py "projects/<NAME>" -n kaibridge                                  |
|  [Step 2] Sourcing (Local DB / CLI)   PartsDatabase().lookup_by_lcsc / easyeda2kicad --lcsc_id <ID> --symbol --footprint       |
|  [Step 3] Pin Verification            python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" -s <SYM> --json          |
|  [Step 4] Circuit Spec (design.json)  Write <PROJECT_DIR>/kaibridge_dump/design.json (LCSC IDs & power_flags)                  |
|  [Step 5] Compile & Automated ERC     python json2sch.py "projects/<NAME>" --apply-netclasses --erc                            |
|  [Step 6] Headless PCB Sync (F8)      python kicad_pcb_sync.py "projects/<NAME>"                                               |
|  [Step 7] Layout Placement            python kicad_layout.py "projects/<NAME>" [ops.json] [--dry-run]                          |
|  [Step 8] Route, Ground Pour & DRC    python kicad_route.py "projects/<NAME>" --pour-gnd --drc                                 |
|  [Step 9] JLCPCB Production Export    python export_jlcpcb.py "projects/<NAME>"                                                |
+--------------------------------------------------------------------------------------------------------------------------------+
```

#### Step 1: 1-Line Instant Project Bootstrap (< 0.2s)
Run the root bootstrapper tool directly from the Kaibridge repository root:
```powershell
python kicad_lib_init.py "projects/<Project_Name>" -n kaibridge
```
**What this automatically creates in one shot:**
- `projects/<Project_Name>/` project root directory
- `projects/<Project_Name>/kaibridge_dump/` intermediate scratch directory
- `projects/<Project_Name>/<Project_Name>.kicad_pro` (native KiCad 10 project file with default netclasses & JLCPCB DRC rules)
- `projects/<Project_Name>/<Project_Name>.kicad_pcb` (native KiCad 10 empty PCB header: version 20260206, generator_version "10.0", standard layer stack)
- `projects/<Project_Name>/sym-lib-table` (version 7, mapping library nickname `kaibridge` to `${KIPRJMOD}/libs/kaibridge.kicad_sym`)
- `projects/<Project_Name>/fp-lib-table` (version 7, mapping library nickname `kaibridge` to `${KIPRJMOD}/libs/kaibridge.pretty`)
- `projects/<Project_Name>/libs/kaibridge.kicad_sym` (empty KiCad 10 symbol library header)
- `projects/<Project_Name>/libs/kaibridge.pretty/` (footprint directory)
- `projects/<Project_Name>/libs/kaibridge.3dshapes/` (3D model directory)

#### Step 2: Component Sourcing (Local SQLite DB + Active IC CLI)
**A. Generic Passives & Connectors:**
- Query local parts cache & SQLite database (< 1ms):
  ```powershell
  python -c "from kaibridge.sourcing.parts_db import lookup_by_lcsc; print(lookup_by_lcsc('C17513'))"
  ```
- Or consult `references/jlcpcb_basic_parts.md` for pre-verified 0-fee Basic Parts.
- ALWAYS use native KiCad symbols (`Device:R`, `Device:C`, `Device:LED`, `Device:D`, `Connector_Generic:Conn_01x<N>`) and official IPC-7351 footprints (`Resistor_SMD:R_0805_2012Metric`, etc.).

**B. Active ICs & Modules (LCSC Downloads via `easyeda2kicad`):**
```powershell
Push-Location "projects/<Project_Name>"
easyeda2kicad --lcsc_id <LCSC_ID> --symbol --footprint --output "$PWD/libs/kaibridge" --overwrite --project-relative
Pop-Location
```

#### Step 3: Zero-Hallucinated Pin & Footprint Extraction (< 0.1s)
**NEVER guess pin numbers, pin names, or footprint strings from memory!**
Extract them directly from the symbol file:
```powershell
# For downloaded active ICs in project library:
python kicad_pins.py "projects/<Project_Name>\libs\kaibridge.kicad_sym" -s <SYMBOL_NAME> --json

# For stock KiCad symbols (e.g. Logic, Regulators, Connectors):
python kicad_pins.py --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json
```
- **Footprint Rule:** Copy the `"footprint"` field from the JSON output verbatim into `design.json` (e.g. `"kaibridge:ESOP-8_..."`).
- **Pins Rule:** Pin connections (`"<REF>.<PIN_NUMBER>"`, e.g. `"U1.1"`, `"U1.8"`) must match the JSON output exactly.

#### Step 4: Upfront BOM Sourcing & `design.json` Synthesis
Write the complete schematic specification to `projects/<Project_Name>/kaibridge_dump/design.json`:
- Supports both `"parts": { ... }` dict and `"components": [ ... ]` list format.
- Attach the LCSC C-Part ID upfront inside `"fields": {"LCSC": "Cxxxx", "JLCPCB_Class": "Basic Part"}` on EVERY part.
- Put external unregulated inputs (`VBUS`, `VIN`, `VBAT`, `GND`) in `"power_flags": ["VBUS", "GND"]`.
- Do NOT put active regulator outputs (`+3V3`, `+5V`) in `power_flags` (regulators already output power).
- Define netclasses with widths/clearances in `"netclasses"`.

#### Step 5: Dry-Run Preflight & Automated Schematic Compilation + ERC
```powershell
# 1. Preflight dry-run check:
python json2sch.py "projects/<Project_Name>" --dry-run

# 2. Compile schematic, write netclasses into .kicad_pro, and run KiCad ERC:
python json2sch.py "projects/<Project_Name>" --apply-netclasses --erc
```
**Gate Requirement:** Total ERC Errors must be 0 (`Status: PASSED (0 Errors)`).

#### Step 6: Export Vector Schematic Preview (Checkpoint 1)
```powershell
# Export vector SVG preview dynamically via kicad_paths.json or load_cli():
python -c "from kaibridge.pcb import render_schematic_preview; render_schematic_preview('projects/<Project_Name>')"
# Or compile with --svg flag: python json2sch.py "projects/<Project_Name>" --apply-netclasses --erc --svg
```
Presents clean SVG preview path in `kaibridge_dump/` to user as Checkpoint 1.

#### Step 7: Headless PCB Synchronization (Programmatic F8)
```powershell
python kicad_pcb_sync.py "projects/<Project_Name>"
```
Automatically instantiates footprints, sets references/values, and attaches net ratsnest to `.kicad_pcb`.

#### Step 8: Declarative Component Placement & Layout (Checkpoint 2)
```powershell
# 1. In-memory dry-run collision check:
python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json" --dry-run

# 2. Commit placement to .kicad_pcb:
python kicad_layout.py "projects/<Project_Name>" "projects/<Project_Name>/kaibridge_dump/ops.json"

# 3. Export vector placement snapshot for visual critique:
python pcb_snapshot.py "projects/<Project_Name>"
```

#### Step 9: Headless Routing, Solid Ground Pour & Automated DRC (Checkpoint 3)
```powershell
python kicad_route.py "projects/<Project_Name>" --pour-gnd --drc
```
Runs DSN track width audit, executes Freerouting 2.4.1 headlessly, imports SES, pours solid GND copper plane on `B.Cu` (0.3mm clearance), and validates 0 clearance violations via KiCad DRC.

#### Step 10: 100% Populated JLCPCB Production & BOM Export
```powershell
python export_jlcpcb.py "projects/<Project_Name>"
```
Generates 100% factory-ready JLCPCB files in `production_output/`:
- `<Project_Name>_bom_jlcpcb.csv`: Groups identical parts with columns `Comment,Designator,Footprint,LCSC Part #` completely populated with zero missing IDs.
- `<Project_Name>_cpl_jlcpcb.csv`: Centroid SMT placement table (`Designator,Val,Package,Mid X,Mid Y,Rotation,Layer`).
- `<Project_Name>_gerbers.zip`: Gerber & Excellon drill files ready for fabrication.

---

###1.  AUTONOMOUS AGENT FAST-PATH RULES (ZERO EXPLORATORY PROBES)
- **Do NOT read internal backend code upfront:** `SKILL.md` is the complete, canonical specification. Agents MUST NOT spend time reading or analyzing backend implementation files (`server.py`, `layout.py`, `sync.py`, `oracle.py`, etc.) during startup.
- **Do NOT run exploratory environment probes:** KiCad 10, `kicad-cli`, Python `pcbnew`, Java (Freerouting), and local databases are pre-configured. Do NOT run exploratory `Get-ChildItem`, dummy version checks, or test scripts before delivering the plan.
- **Immediate Planning on Turn 1:** On receiving a new PCB design prompt, immediately extract requirements (classifying each as STATED / INFERRED / UNKNOWN with impact rating) and write an `implementation_plan.md` artifact following the **Mandatory 4-Part Structure**:
  1. **Section 1: Baseline Architecture (Initial Draft):** The naive, unverified baseline from user requirements.
  2. **Section 2: ART-Gate Adversarial Loop & Corrections:** Iteration 1 attack findings (Layer 0, 1, 2) + **The Delta Table (Baseline vs. Hardened by ART-Gate)** mapping every finding to its component addition (with LCSC ID) and Why-Should-This-Exist rationale + Iteration 2 second-order convergence check.
  3. **Section 3: Final Hardened Implementation Specification:** Block diagram, target BOM with LCSC IDs & IPC footprints, **Zero-Hallucinated Pins Protocol** (active IC/module pinouts queried from `.kicad_sym` via `kicad_pins.py`), and floorplan zoning/creepage rules.
  4. **Section 4: Sequential Execution Roadmap:** Checkpoints 1 (Schematic SVG), 2 (Placement SVG), and 3 (DRC clean).
  Persist the full machine audit to `kaibridge_dump/art_gate_audit.md` and request user approval without delay.
- **CLI Tools Primacy:** Always use the 8 root CLI tools (`kicad_lib_init.py`, `kicad_pins.py`, `json2sch.py`, `kicad_pcb_sync.py`, `kicad_layout.py`, `pcb_snapshot.py`, `kicad_route.py`, `export_jlcpcb.py`). Never write custom python scratch scripts in `brain/.../scratch/`.

---

###2.  Clean Workspace & Intermediate Hygiene (`kaibridge_dump/`)
- Under NO circumstances should you pollute the KiCad project root folder or plugin directory with scratch files.
- Store all intermediate compiler specifications (`design.json`, `ops.json`, `erc_report.json`, `drc_report.json`, `board.dsn`, `board.ses`, schematic SVGs, board state dumps) inside `<PROJECT_DIR>/kaibridge_dump/`.
- The Kaibridge compiler and tooling natively resolve `<PROJECT_DIR>/kaibridge_dump/design.json`.

---

###3.  Sourcing, Native IPC Footprints & Upfront LCSC BOM Binding (Zero ERC Guarantee)
- **Generic Passives (Resistors, Capacitors, Inductors, LEDs, Diodes, Headers):**
  - **Symbols:** ALWAYS use native KiCad symbols (`Device:R`, `Device:C`, `Device:LED`, `Device:D`, `Device:L`, `Connector_Generic:*`). NEVER use raw EasyEDA passive symbols (which declare pins as `"Input"` and trigger `[pin_not_driven]` ERC errors).
  - **Footprints:** ALWAYS use native KiCad official IPC-7351 footprints (`Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`, `LED_SMD:LED_0805_2012Metric`, `Diode_SMD:D_SOD-123`, `Connector_PinHeader_2.54mm:PinHeader_1x*`). **NEVER download passive footprints from EasyEDA!** KiCad IPC footprints guarantee zero silkscreen overlaps, correct courtyards, and 100% JLCPCB SMT compatibility.
  - ** UPFRONT LCSC ID BINDING (MANDATORY BEFORE SCHEMATIC COMPILATION):**
    You MUST attach the JLCPCB LCSC C-Part ID directly during `design.json` synthesis inside `fields: {"LCSC": "Cxxxx", "JLCPCB_Class": "Basic Part"}` for EVERY component. Do NOT wait until BOM export! Sourcing the LCSC ID upfront ensures it travels automatically into the schematic, netlist, PCB footprint fields, and exports a 100% populated JLCPCB BOM CSV without missing part numbers.
  - **Instant Offline Resolution & Reference Catalog:**
    - Use `kaibridge_lookup_lcsc_part` (<1ms) to query parts dynamically from local SQLite DB.
    -  **Verified Basic Parts Catalog:** Refer to `references/jlcpcb_basic_parts.md` for the complete catalog of verified JLCPCB Basic Parts (resistors, capacitors, LEDs, diodes, transistors, LDOs) with exact LCSC IDs and KiCad IPC footprint mappings.
- **Active ICs (Regulators, MCUs, Sensors, Specialized Drivers):**
  - Download via CLI (`easyeda2kicad --lcsc_id <ID> --full --output "$PWD/libs/kaibridge" --overwrite --project-relative`) or MCP (`kaibridge_fetch_lcsc_component`).
  - **Zero-Hallucinated Pins & Footprint Copy Verbatim:** Run `python kicad_pins.py "<PROJECT_DIR>\libs\kaibridge.kicad_sym" -s <SYM> --json` (or `python kicad_pins.py --native <LIB> -s <SYM> --json`). Copy the `"footprint"` string verbatim into `design.json`. Pin references `"<REF>.<PIN_NUMBER>"` MUST come strictly from the JSON output.
- **Schematic Compilation & Automated ERC Gate:**
  - Dry run preflight: `python json2sch.py "<PROJECT_DIR>" --dry-run`
  - Automated compilation & ERC: `python json2sch.py "<PROJECT_DIR>" --apply-netclasses --erc` (or `kaibridge_build_schematic`).
  - Strict zero ERC error policy: **Total Errors MUST be 0** before proceeding to PCB synchronization.

---

###4.  Geometry Gate, In-Memory Simulation & Placement Protocol
- Execute component placement using `kaibridge_apply_ops_layout` with `ops.json`.
- The Geometry Gate automatically quantizes all placement coordinates to a clean **0.5mm grid** and prevents courtyard collisions.
- Use `"dry_run": true` to simulate placement moves and verify courtyard collisions in memory with a zero-disk-write guarantee before committing.
- Maintain logical functional flow: Power Ingest & Bypass Caps -> Core IC -> Analog/Timing Networks -> User Controls & Status LEDs.
- **Critical Component Locking (`LCK-01`):** Crystal oscillators, RF matching circuits, sensitive analog front-ends, and perimeter connectors MUST be locked via `{"op": "footprint.lock", "ref": "<REF>"}` or `"locked": true` in `ops.json` after placement to prevent displacement during relaxation or auto-routing.
- Silkscreen reference designators must be clean ($1.0\text{mm} \times 1.0\text{mm}$, thickness $0.15\text{mm}$) and positioned outside courtyards; hide bulky value text from silkscreen to avoid text overlaps.

---

###5.  Headless Ground Pouring & Zone Management
- Use `kaibridge_add_ground_plane` to add and fill `GND` copper pour zones across `B.Cu` and/or `F.Cu` with 0.3mm clearance and solid thermal pad connections (`ZONE_CONNECTION_FULL`).
- The engine automatically clips zones to exact `Edge.Cuts` boundaries, preventing isolated copper errors.

---

###6.  Headless Routing & Freerouting 2.4.1 (Java 25 LTS)
- Pre-flight DSN audit: `route_board` automatically validates track widths, clearances, and netclasses in < 2ms before starting Java.
- Execute headless routing via `kaibridge_route_pcb` (Freerouting 2.4.1).
- Automatic 150µm board edge keepout via `--router.copperToEdgeClearanceUm=150` prevents tracks from hugging `Edge.Cuts`.
- Run `kaibridge_run_drc` and ensure **0 Clearance Violations** and **0 Unconnected Items** before generating manufacturing files.
- Export 100% factory-ready JLCPCB bundles via `kaibridge_export_production` (`Gerber_*.zip`, Drill, `BOM_*.csv`, `CPL_*.csv`).

---

###7.  Human-in-the-Loop (HITL) & User Intent Primacy (Tier 0)
- Always create an `implementation_plan.md` artifact using the **Mandatory 4-Part Structure**:
  1. **Baseline Architecture:** The unverified starting point based directly on user prompt.
  2. **ART-Gate Adversarial Loop:** Iteration 1 attack findings, **The Delta Table (Baseline vs. Hardened by ART-Gate)** mapping every added part (with LCSC ID) to its Why-Should-This-Exist rationale, and Iteration 2 second-order convergence checks.
  3. **Final Hardened Specification:** Complete block diagram, BOM, **Zero-Hallucinated Pins Protocol** (active IC pins are queried from `.kicad_sym` after fetching, never guessed), and physical creepage/zoning rules.
  4. **Sequential Execution Roadmap:** Clear checkpoints (Checkpoints 1, 2, 3) with SVG visual reviews.
- The full audit trail lives in `kaibridge_dump/art_gate_audit.md`.
- Once approved, execute sequentially through Checkpoints 1, 2, and 3 without restarting or re-inspecting working files.

---

###8.  Python Runtime & Zero-Raw-Script Protocol (`pcbnew` Execution Policy)
- **Zero Raw Scripts for Board Mutations:** Never write manual Python scratch scripts to mutate `.kicad_pcb` directly. Always use Kaibridge's 22 dedicated MCP operations (`kaibridge_apply_ops_layout` with `{"op": "item.delete", "ref": "..."}`, `{"op": "footprint.place", ...}`, etc.).
- **Bundled KiCad Python Requirement:** KiCad's C++ SWIG wrapper (`pcbnew`) exists inside KiCad's bundled Python environment (resolved dynamically via `kaibridge.core.paths.load_kicad_python()`). Standard system Python (e.g. Python 3.14) lacks `pcbnew` and will immediately crash with `ModuleNotFoundError: No module named 'pcbnew'`. If any standalone inspection script is ever strictly necessary, it MUST be executed via KiCad's bundled Python executable resolved by `load_kicad_python()`.

