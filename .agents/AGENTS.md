#Kaibridge 2.0 Autonomous Agent Rules & Fast-Path Protocol

The following core rules MUST be followed by all AI agents operating within this repository:

---

###0.  FAST BOOTSTRAP & ZERO EXPLORATORY PROBES (CRITICAL)
- **Active Engine:** The canonical engine is **Kaibridge 2.0**.
- **Do NOT read internal backend code upfront:** `SKILL.md` is the complete, canonical specification. Agents MUST NOT spend time reading or analyzing backend implementation files (`server.py`, `layout.py`, `sync.py`, `oracle.py`, etc.) during startup.
- **Do NOT run exploratory environment probes:** KiCad 10, `kicad-cli`, Python `pcbnew`, Java (Freerouting), and local databases are pre-configured. Do NOT run exploratory `Get-ChildItem`, dummy version checks, or test scripts before delivering the plan.
- **Immediate Planning on Turn 1:** On receiving a new PCB design prompt, immediately synthesize the component list, netlist, and floorplan, write `implementation_plan.md` on the very first turn, and request user approval without delay.

---

###1.  STRICT ADHERENCE TO SKILL.md & 22-TOOL MCP MAP
Use the 22 dedicated Kaibridge 2.0 MCP tools (or their exact Python APIs in `kaibridge`) for all hardware synthesis steps. Follow the master rules in `SKILL.md`.

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
  - Download symbol and footprint via `kaibridge_fetch_lcsc_component`.
  - Query pin names using `kaibridge_query_symbol_pins` to ensure 100% pin matching.

---

###4.  Geometry Gate, In-Memory Simulation & Placement Protocol
- Execute component placement using `kaibridge_apply_ops_layout` with `ops.json`.
- The Geometry Gate automatically quantizes all placement coordinates to a clean **0.5mm grid** and prevents courtyard collisions.
- Use `"dry_run": true` to simulate placement moves and verify courtyard collisions in memory with a zero-disk-write guarantee before committing.
- Maintain logical functional flow: Power Ingest & Bypass Caps -> Core IC -> Analog/Timing Networks -> User Controls & Status LEDs.
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
- Always create an `implementation_plan.md` artifact and obtain user approval before modifying files on a new design task.
- Once approved, execute sequentially through Checkpoints 1, 2, 3, and 4 without restarting or re-inspecting working files.
