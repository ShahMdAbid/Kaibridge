---
name: Kaibridge 3.0 — Evidence-First Hardware Synthesis Engine
description: Procedural handbook for Kaibridge 3.0 — headless KiCad 10 hardware synthesis with evidence-first ground-truth planning, contract-first placement, pre-flight proofs, characterized circuit motifs, Freerouting 2.4.1, and 100% JLCPCB production export.
---

# Kaibridge 3.0 — Evidence-First Hardware Synthesis

> **Pipeline:** Bootstrap → Idea → Source → Extract → Plan → design.json → Compile → Sync → Place → Inspect → Route → Export

---

## Step 0: Bootstrap Project

**What:** Creates the KiCad 10 project directory with `.kicad_pro`, empty `.kicad_pcb`, `.kicad_sch`, library tables (`fp-lib-table`, `sym-lib-table`), and `kaibridge_dump/` folder immediately upon receiving the user's prompt.

**CLI:**
```powershell
# 2-layer board (default):
python kicad_lib_init.py "projects/<NAME>" -n kaibridge

# 4-layer board (JLCPCB JLC04161H stackup):
python kicad_lib_init.py "projects/<NAME>" -n kaibridge --layers 4
```

**Session Contract:**
- **Library Nickname:** Always `kaibridge` everywhere.
- **Clean Workspace:** All intermediate files go strictly inside `<PROJECT_DIR>/kaibridge_dump/`.
- **GUI Lock Rule:** If user opens KiCad GUI, they must save (`Ctrl+S`) and close before running headless commands.

**→ Next:** Step 1 (Idea & Requirement Capture)

---

## Step 1: Idea & Requirement Capture

**What:** Capture the user's raw design intent and identify candidate ICs/connectors to source.

> **Crucial Rule:** Step 1 is strictly an **intent capture & sourcing target wishlist**, NOT the final circuit plan. The agent must NEVER output a finalized BOM, netlist, or passive connection scheme here — because symbols and footprints have not been downloaded or inspected yet. The final, verified circuit specification is produced in **Step 4** using real extracted evidence.

**Process:**
1. Parse the user's prompt for: functional goals, target IC(s), voltage rails, interfaces (UART, SPI, I²C, USB), connector types, and mechanical constraints (board size, mounting holes).
2. Identify candidate active ICs / connectors and map them to target LCSC IDs (ask user if ambiguous).
3. Consult [`references/art_gate_protocol.md`](references/art_gate_protocol.md) (adversarial cognitive checklist to stress-test inrush, brownouts, and polarity during planning — executed as mental review, not an external CLI script).
4. Consult [`references/adversarial_dfm_checklist.md`](references/adversarial_dfm_checklist.md) for high-level domain constraints (`PWR`, `IND`, `MCU`, `MECH`).

**Step 1 Working Notes (Preliminary Targets Only):**
- Target functional requirements & interfaces
- Sourcing wishlist: Candidate active ICs & connectors with candidate LCSC IDs (for Step 2 download)
- Target power rails (e.g. 5V in → 3.3V target rail)
- Mechanical & layer constraints (e.g. 50x40mm, 2-layer)

*(Note: Detailed pin connections, passive BOM, decoupling counts, and power flags are strictly postponed to Step 4 after ground-truth extraction).*

**→ Next:** Step 2 (Source Components)

---

## Step 2: Source Components

Two strict categories — do not deviate:

### 2A. Active ICs & Connectors (Download on-demand)

For all MCUs, regulators, transceivers, op-amps, sensors, and USB/power connectors. Fetches exact manufacturer symbols, pin definitions, and footprints.

```powershell
# 1. Essential (Immediate, < 2s): Fetch Symbol & Footprint directly to project library:
easyeda2kicad --lcsc_id <LCSC_ID> --symbol --footprint --output "projects/<NAME>/libs/kaibridge" --overwrite --project-relative

# 2. Background 3D Fetch (Non-blocking, 5s pacing): Downloads in background while you proceed
python kicad_3d.py "projects/<NAME>" <LCSC_ID_1> <LCSC_ID_2> ... --bg --interval 5
```

- Symbol saved to `<PROJECT_DIR>/libs/kaibridge.kicad_sym`
- Footprint saved to `<PROJECT_DIR>/libs/kaibridge.pretty/`
- 3D Models (`.step`/`.wrl`) saved to `<PROJECT_DIR>/libs/kaibridge.3dshapes/` (downloaded in background with 5s spacing; missing 3D models never block synthesis)

**Critical Rules:**
- Must pass exact LCSC ID (e.g. `C6186`), never component names (`AMS1117`).
- Core fetch uses `--symbol --footprint` only. Never use `--full` or `--3d` in the main fetch.
- **NEVER download passives from EasyEDA** (their symbols trigger `[pin_not_driven]` ERC errors and footprints lack standardized courtyards).

**Batch Download:** When multiple active ICs are needed, download them in sequence:
```powershell
easyeda2kicad --lcsc_id C6186 --symbol --footprint --output "projects/<NAME>/libs/kaibridge" --overwrite --project-relative
easyeda2kicad --lcsc_id C99652 --symbol --footprint --output "projects/<NAME>/libs/kaibridge" --overwrite --project-relative
easyeda2kicad --lcsc_id C84681 --symbol --footprint --output "projects/<NAME>/libs/kaibridge" --overwrite --project-relative

# Then fire-and-forget 3D in background:
python kicad_3d.py "projects/<NAME>" C6186 C99652 C84681 --bg --interval 5
```

### 2B. Standard Passives (Native KiCad + JLCPCB ID Binding)

NEVER download passives from EasyEDA.

1. Use native KiCad symbols (`Device:R`, `Device:C`, `Device:C_Polarized`, `Device:LED`, `Device:D`, `Device:D_Schottky`, `Device:L`, `Connector_Generic:Conn_01x<N>`).
2. Use standard IPC-7351 footprints (`Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`, `LED_SMD:LED_0805_2012Metric`, `Diode_SMD:D_SOD-123`, `Connector_PinHeader_2.54mm:PinHeader_1x*`).
3. Copy the verified zero-fee Basic Part C-ID directly from [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) and attach in `design.json`:
```json
"fields": { "LCSC": "C17513", "JLCPCB_Class": "Basic Part" }
```

**→ Next:** Step 3 (Extract Pins)

---

## Step 3: Extract Pins & Footprints

**What:** Query exact pin numbers, pin names, electrical types, and footprint identifiers from downloaded symbols. NEVER guess from training weights.

**CLI:**
```powershell
# For downloaded active ICs in project library:
python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" -s <SYMBOL_NAME> --json

# For stock KiCad native library symbols:
python kicad_pins.py --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json

# Verify pad counts match symbol pin counts:
python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" --verify
```

**What to Expect (JSON Output):**
```json
[{
  "name": "AMS1117-3.3",
  "footprint": "kaibridge:SOT-223-3_TabPin2",
  "pins": [
    {"number": "1", "name": "ADJ/GND", "type": "power_in"},
    {"number": "2", "name": "VOUT", "type": "power_out"},
    {"number": "3", "name": "VIN", "type": "power_in"}
  ]
}]
```

 The extracted pin data, footprint names, and pad counts are the **ground-truth evidence** that the Implementation Plan is built upon. Without this data, the agent would be guessing pin connections from training weights — which is the #1 cause of ERC failures and incorrect netlists.

**→ Next:** Step 4 (Implementation Plan)

---

## Step 4: Implementation Plan 

**What:** Using the real extracted pin data from Step 3 and the passive catalog from [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md), author a rigorous implementation plan for the complete circuit before writing `design.json`.

This is the architectural decision gate. The AI agent now has:
- Real pin names, numbers, and electrical types (from Step 3)
- Real footprint identifiers (from Step 3)
- Real JLCPCB Basic Part IDs (from Step 2B reference)
- The user's design intent (from Step 1)

With all evidence in hand, the agent builds a verified plan — not a hallucinated one.

**What the Implementation Plan Must Contain:**

1. **Bill of Materials (Evidence-Backed):**
   - Every active IC with its LCSC ID, extracted footprint name, and pin count
   - Every passive with its value, native KiCad symbol, IPC footprint, and JLCPCB Basic Part C-ID
   - Every connector with type and pin count

2. **Net Connectivity Map:**
   - For each net: which pin of which component connects where
   - All pin references use the **exact extracted pin numbers** (e.g. `U1.3` for VIN, not guessed)
   - Power topology: input → protection → regulation → distribution
   - Signal routing: data bus connections, pull-ups, decoupling

3. **Power Flag Analysis:**
   - Which nets need `power_flags` declaration (external inputs, post-diode rails)
   - Which nets must NOT have power flags (active regulator outputs)

4. **Netclass Strategy:**
   - Default vs Power netclass track widths and clearances
   - Fine-pitch IC considerations (pin pitch ≤ 0.5mm → max 0.25mm power tracks)
   - Reference: [`references/trackwidth_clearence_viasize.md`](references/trackwidth_clearence_viasize.md)

5. **Stacked Pin Handling (if applicable):**
   - USB-C mirrored pads: only primary pins declared
   - Multi-GND IC pins: documented and handled per [`references/stacked_pins_fix.md`](references/stacked_pins_fix.md)

6. **Board Strategy:**
   - 2-layer vs 4-layer decision
   - Estimated board size
   - Connector placement strategy (which edges)

**Output (The Real, Evidence-Backed Design Blueprint):**
A comprehensive, verified circuit plan presented to the user (or secondary reviewer) containing the 6 sections above with 100% verified pin numbers, footprints, and JLCPCB Basic C-IDs. This plan is solid enough that any agent or engineer can verify it directly.

**→ Next:** Step 5 (Write design.json)

---

## Step 5: Write Circuit Specification (`design.json`)

**What:** Translate the Step 4 Implementation Plan into `<PROJECT_DIR>/kaibridge_dump/design.json` using [`design_template.json`](design_template.json) as the canonical template.

### Critical Rules for `design.json`:
1. **Canonical Schema:** Follow [`design_template.json`](design_template.json) (`schema: 3`, `meta`, `board`, `netclasses`, `parts`, `nets`).
2. **Power Flags (ERC Prevention):**
   - External inputs (`VBUS`, `VIN`, `GND`) → Declare in `"power_flags"`.
   - Post-protection rails (`VIN_FUSED`) → Declare in `"power_flags"`.
   - Active regulator outputs (`+3V3`, `+5V`) → **DO NOT** declare in `"power_flags"` (regulator pin is already `power_out`; adding flag causes `[pin_to_pin]` ERC collision).
3. **Pin & Footprint Fidelity:**
   - Pins in `"connections"` MUST use pin numbers (e.g. `"U1.3"`, `"R1.1"`), never pin names.
   - Footprints must match exact strings extracted in Step 3 (e.g. `"kaibridge:SOT-223-3_TabPin2"`).
4. **Fine-Pitch ICs (≤ 0.5mm pitch):** Max power track width 0.25mm, clearance 0.20mm to prevent routing deadlocks ([reference](references/trackwidth_clearence_viasize.md)).
5. **Multi-Pad Contacts (USB-C / Power):** Ensure all physical pads needing copper connection are declared in `"connections"` (exact or composite aliases like `A1/B12`); shield pins (`SH`) in `"no_connect"` ([reference](references/stacked_pins_fix.md)).
6. **Hierarchical Sheets & Groups:** For complex boards (> 25 parts), use `"sheets"` and `"group"` tags as demonstrated in `design_template.json`.

**→ Next:** Step 6 (Compile Schematic)

---

## Step 6: Compile Schematic & ERC Gate ⟨Checkpoint 1⟩

**What:** Compile `design.json` into `.kicad_sch`, write netclasses into `.kicad_pro`, run KiCad ERC.

**CLI (Mode A):**
```powershell
# Preflight dry-run (zero writes):
python json2sch.py "projects/<NAME>" --dry-run

# Compile + netclasses + ERC:
python json2sch.py "projects/<NAME>" --apply-netclasses --erc
```

**MCP (Mode B):**
```
kaibridge_build_schematic(project_dir="projects/<NAME>", apply_netclasses=true, run_erc_check=true)
```

**What to Expect:**
- `.kicad_sch` generated with all symbols, wires, power flags, and net labels
- `.kicad_pro` updated with netclass track/clearance/via rules
- ERC runs via `kicad-cli sch erc` with `--severity-all`
- EasyEDA symbols auto-healed (`--heal-pins`) to fix `unspecified` pin types

**Gate:** `Status: PASSED (0 Errors)`. If errors exist, fix `design.json` and recompile.

**Checkpoint 1 Action:** Export SVG preview and present to user:
```powershell
# CLI:
python pcb_snapshot.py "projects/<NAME>" --schematic
# MCP:
kaibridge_render_schematic_preview(project_dir="projects/<NAME>")
```
SVG saved to `<PROJECT>/kaibridge_dump/<NAME>_schematic.svg`.

**→ Next:** Step 7 (Sync PCB)

---

## Step 7: Sync PCB Netlist

**What:** Headless "F8" — binds footprints, values, and net ratsnest from schematic into `.kicad_pcb`.

**CLI (Mode A):**
```powershell
python kicad_pcb_sync.py "projects/<NAME>"
```

**MCP (Mode B):**
```
kaibridge_sync_to_pcb(project_dir="projects/<NAME>")
```

**What to Expect:**
- All footprints instantiated at default positions in `.kicad_pcb`
- Net ratsnest (airwires) visible between connected pads
- Console: `[OK] PCB synced — <N> footprints, <M> nets`

**→ Next:** Step 8 (Place Components)

---

## Step 8: Place Components

**What:** Position all footprints on the PCB using `ops.json` and/or the planar optimizer.

> **Recommended Default Pipeline:**
> 1. **Initial Anchor Placement:** Write edge connectors and key ICs in `<PROJECT>/kaibridge_dump/ops.json` (or use `kaibridge_autoplace_pcb`).
> 2. **Apply Placement:** `python kicad_layout.py "projects/<NAME>"`
> 3. **Planar Optimization (Minimize Ratsnest & Auto-Bind Decoupling):** `python kicad_planar_optimizer.py "projects/<NAME>"`
> 4. **Silkscreen Sanitation:** `python kicad_layout.py "projects/<NAME>" --sanitize-silk`

### 8A. Write Placement Operations (`ops.json`)

**What:** Author placement operations in `<PROJECT_DIR>/kaibridge_dump/ops.json` using [`ops_template.json`](ops_template.json) as the canonical template and [**Appendix A**](#appendix-a-opsjson-operation-catalog) for the 17-operation catalog.

**Critical Rules for `ops.json`:**
1. **Canonical Schema:** Follow [`ops_template.json`](ops_template.json) (supports either direct array `[{"op": ...}]` or structured `{"board": {...}, "ops": [...]}`).
2. **0.5mm Grid:** Round all placement coordinates to 0.5mm multiples.
3. **Courtyard Spacing:** Maintain ≥ 0.5mm clearance between adjacent courtyards.
4. **Perimeter Connectors:** Mating faces flush with board edge and facing outward (left edge: `180°`, bottom: `270°`, right: `0°`, top: `90°`). Lock edge connectors (`"locked": true`).
5. **Decoupling & Thermal:** Place decoupling MLCCs within 2.5mm of IC power pins. Linear regulator heatsink tabs face outward toward ground pour/board edge.

For the full 80-rule placement doctrine and conflict precedence ladder, see [`references/pcb_placement_rules.md`](references/pcb_placement_rules.md).

### 8B. Apply Layout

**CLI (Mode A):**
```powershell
# Dry-run validation (zero bytes written, reports courtyard collisions):
python kicad_layout.py "projects/<NAME>" "projects/<NAME>/kaibridge_dump/ops.json" --dry-run

# Commit to .kicad_pcb:
python kicad_layout.py "projects/<NAME>" "projects/<NAME>/kaibridge_dump/ops.json"

# Placement courtyard audit:
python kicad_layout.py "projects/<NAME>" --audit
```

**MCP (Mode B):**
```
kaibridge_apply_ops_layout(project_dir="projects/<NAME>", ops_file="kaibridge_dump/ops.json", dry_run=false)
```

### 8C. Planar Optimizer (Mathematical Auto-Placement)

After initial placement, run the simulated annealing optimizer to minimize ratsnest crossings:

**CLI (Mode A):**
```powershell
python kicad_planar_optimizer.py "projects/<NAME>"
```

**MCP (Mode B):**
```
kaibridge_optimize_planar_layout(project_dir="projects/<NAME>", steps=6000, temp=70.0)
```

**What to Expect:**
- Reduces ratsnest crossings by >85% in < 2 seconds
- Auto-pairs decoupling caps with companion ICs (≤ 7mm LQFP, ≤ 5mm SOIC, ≤ 4mm SOT)
- Auto-binds crystals ≤ 5mm to MCU OSC pins

### 8D. Geometric Autoplacer (Alternative to Manual ops.json)

**MCP (Mode B) only:**
```
kaibridge_autoplace_pcb(project_dir="projects/<NAME>", board_width_mm=50.0, board_height_mm=40.0, pitch_mm=8.0)
```

### 8E. Physics Relax (Resolve Courtyard Overlaps)

**MCP (Mode B) only:**
```
kaibridge_auto_relax_layout(project_dir="projects/<NAME>", passes=300, clearance=0.5)
```

### 8F. Silkscreen Sanitation

**CLI (Mode A):**
```powershell
# Auto-hide bulky values and overlapping references:
python kicad_layout.py "projects/<NAME>" --sanitize-silk

# Hide all silkscreen (high-density / clean aesthetic):
python kicad_layout.py "projects/<NAME>" --hide-silk
```

**→ Next:** Step 9 (Inspect & Audit)

---

## Step 9: Inspect & Audit Board ⟨Checkpoint 2⟩

**What:** Verify component positions, clearances, and connector orientations before routing.

### 9A. Live Board State Inspector

**CLI (Mode A):**
```powershell
# Summary table (Ref, Pos, Rot, Layer, Locked):
python kicad_inspect.py "projects/<NAME>" --summary

# Full JSON with pad coordinates, courtyards, nets:
python kicad_inspect.py "projects/<NAME>" --full --json
```

**MCP (Mode B):**
```
kaibridge_get_board_state(project_dir="projects/<NAME>", mode="summary")
kaibridge_get_board_state(project_dir="projects/<NAME>", mode="full")
```

### 9B. Live SWIG API Oracle

**CLI (Mode A):**
```powershell
python kicad_oracle.py "drc_rules"
python kicad_oracle.py "GetFootprints" -c BOARD --json
python kicad_oracle.py "swig_memory"
```

**MCP (Mode B):**
```
kaibridge_api_oracle(query="drc_rules")
kaibridge_api_oracle(query="GetFootprints", class_name="BOARD")
```

**Available Oracle Topics:** `drc_rules`, `jlcpcb_rules`, `swig_memory`, `freerouting_limits`, `stackup_4layer`, `track_clearance`.

### 9C. Visual Snapshot

**CLI (Mode A):**
```powershell
python pcb_snapshot.py "projects/<NAME>"
```

**MCP (Mode B):**
```
kaibridge_render_pcb_preview(project_dir="projects/<NAME>")
```

### 9D. Checkpoint 2 Audit Checklist

1. **Connectors:** Mating faces flush against board edge, facing outward?
2. **Heatsink tabs:** Facing outward toward ground pour, not toward MCU?
3. **Silkscreen:** References outside courtyards, no pad overlaps?
4. **Mounting holes:** Clear of courtyards by ≥ 1.5mm?

If adjustments needed → write surgical `ops.json` → dry-run → commit → re-inspect.

### 9E. Snapshot & Rollback (Optional)

```
kaibridge_snapshot_board(project_dir="projects/<NAME>", tag="pre_route")
kaibridge_diff_board(project_dir="projects/<NAME>", tag_a="pre_route")
kaibridge_restore_snapshot(project_dir="projects/<NAME>", tag="pre_route")
```

**→ Next:** Step 10 (Route & DRC)

---

## Step 10: Route & DRC Gate ⟨Checkpoint 3⟩

**What:** Autoroute all traces, pour GND plane, run DRC to verify zero violations.

### 10A. Headless Autorouting

**CLI (Mode A):**
```powershell
# Full pipeline: route + GND plane + DRC:
python kicad_route.py "projects/<NAME>" --pour-gnd --drc

# 4-layer boards:
python kicad_route.py "projects/<NAME>" --layers 4 --pour-gnd --drc
```

**MCP (Mode B):**
```
kaibridge_route_pcb(project_dir="projects/<NAME>", strategy="auto", max_passes=1)
kaibridge_add_ground_plane(project_dir="projects/<NAME>")
kaibridge_run_drc(project_dir="projects/<NAME>")
```

**What to Expect:**
- Router auto-selects strategy:
  - **Strategy 1 (Dog-Bone):** Simple boards (ICs < 24 pins, nets ≤ 20). Routes on F.Cu only with pre-placed GND vias. Zero signal vias.
  - **Strategy 2 (Dual-Layer):** Dense MCUs (≥ 24 pins or nets > 20). Routes F.Cu + B.Cu with jumper vias. GND copper plane on B.Cu.
- **Auto-Fallback:** If Strategy 1 fails, automatically retries with Strategy 2 (5 passes)
- Freerouting capped at 1 optimization pass, 1024MB heap, < 20s convergence
- Dangling micro-stubs (< 0.08mm) auto-pruned on SES import
- Copper zones: `ISLAND_REMOVAL_MODE_ALWAYS` eliminates floating islands

### 10B. What the Router Does Internally

1. Purges all existing tracks, vias, and copper zones (`board.prep_for_route`)
2. Deletes stale `<stem>.rules` files
3. Exports Specctra DSN
4. Launches Freerouting 2.4.1 daemon with `-mp 1 -Xmx1024m`
5. Imports SES result, prunes micro-stubs
6. Pours solid continuous GND plane (B.Cu) with `ZONE_CONNECTION_FULL`
7. Runs `kicad-cli pcb drc --severity-all --refill-zones`

### 10C. 4-Layer Auto-Plane Pouring

On `--layers 4`, the router auto-detects power rails (`+3V3`, `+5V`, `VCC`, `VDD`, `VBUS`, `VIN`, `VBAT`) and pours:
- `In1.Cu` → GND plane
- `In2.Cu` → Power plane (auto-detected rails)
- `B.Cu` → GND plane

### 10D. DRC Gate

**Gate:** Must report **0 clearance errors** and **0 unconnected items**.
- **Fail-Closed Execution:** Stale DRC reports are purged before running. If `kicad-cli` fails or report output is missing/unparseable, the gate halts immediately with `report_valid: false` rather than claiming a false pass.

DRC output distinguishes:
- `PASSED CLEAN (0 Errors, 0 Warnings)`
- `PASSED WITH WARNINGS (0 Errors, X Warnings)` — warnings like `[silk_over_copper]` are surfaced with full context

### 10E. Unroute (If Needed)

```powershell
# CLI:
python kicad_route.py "projects/<NAME>" --unroute
# MCP:
kaibridge_unroute_pcb(project_dir="projects/<NAME>")
```

Present DRC pass confirmation as Checkpoint 3.

**→ Next:** Step 11 (Export)

---

## Step 11: Export for JLCPCB Production

**What:** Generate 100% factory-ready Gerbers, BOM, and CPL files.

**CLI (Mode A):**
```powershell
python export_jlcpcb.py "projects/<NAME>"
```

**MCP (Mode B):**
```
kaibridge_export_production(project_dir="projects/<NAME>")
```

**What to Expect (in `<PROJECT>/production_output/`):**

| File | Contents |
|---|---|
| `<NAME>_gerbers.zip` | Complete Gerber + Excellon drill archive. 4-layer includes `F_Cu.gtl`, `GND.g1`, `Power.g2`, `B_Cu.gbl` |
| `<NAME>_bom_jlcpcb.csv` | BOM: `Comment, Designator, Footprint, LCSC Part #` — 100% populated with LCSC C-IDs |
| `<NAME>_cpl_jlcpcb.csv` | CPL centroid: `Designator, Val, Package, Mid X, Mid Y, Rotation, Layer` — numeric floats with **DFM-ROT** auto-correction |

**DFM-ROT Rotation Compensation:** Auto-corrects the 180° discrepancy between KiCad IPC-7351 and JLCPCB EIA-481 tape feeders for `Diode_SMD`, `LED_SMD`, `SOT-23`, `SOT-223`, and polarized capacitors. EasyEDA `kaibridge:*` parts kept at 0°. Custom overrides via `"rotation_offset": <deg>` in `design.json`.

**→ Done.** Upload `production_output/` to JLCPCB. See [`references/jlcpcb_production.md`](references/jlcpcb_production.md) for ordering walkthrough.

---
---

## Appendix A: `ops.json` Operation Catalog (17 Operations)

All operations are validated against physical board constraints. Invalid `ref` or `op` returns `{"success": false, "errors": [...]}`.

### Board Dimensions

| Operation | Description | Example |
|---|---|---|
| `board.set_size` | Create/update rectangular `Edge.Cuts` outline | `{"op": "board.set_size", "width": 55.0, "height": 40.0, "origin_x": 100.0, "origin_y": 100.0}` |
| `board.fit_outline` | Auto-fit outline to footprint bounding box + margin | `{"op": "board.fit_outline", "margin": 5.0}` |

### Component Placement

| Operation | Description | Key Parameters |
|---|---|---|
| `footprint.place` | Place at explicit coordinates | `ref`, `x`, `y`, `rot` (0/90/180/270), `layer` (F.Cu/B.Cu), `locked` (bool) |
| `footprint.move` | Reposition without changing rotation | `ref`, `x`, `y` |
| `footprint.rotate` | Change rotation (absolute or relative) | `ref`, `rot`, `relative` (bool) |
| `array.place` | Linear array with uniform pitch | `refs` (list), `start_x`, `start_y`, `pitch_x`, `pitch_y`, `rot` |

### Locking & Fields

| Operation | Description | Example |
|---|---|---|
| `footprint.lock` | Lock position (immune to auto-relax/routing) | `{"op": "footprint.lock", "ref": "Y1"}` |
| `footprint.unlock` | Unlock previously locked component | `{"op": "footprint.unlock", "ref": "C1"}` |
| `footprint.set_field` | Set/update footprint field | `{"op": "footprint.set_field", "ref": "U1", "field": "LCSC", "value": "C6186"}` |

### Deletion

| Operation | Description | Example |
|---|---|---|
| `item.delete` | Delete footprint/drawing (uses `b.Delete()` for SWIG safety) | `{"op": "item.delete", "ref": "TP1"}` |

### Manual Copper

| Operation | Description | Key Parameters |
|---|---|---|
| `track.add` | Draw manual trace segment | `start_x/y`, `end_x/y`, `width`, `layer`, `net` |
| `track.set_width` | Modify existing track width by net | `net`, `width` |
| `via.add` | Place through-hole via | `x`, `y`, `size`, `drill`, `net` |

### Zones & Cleanup

| Operation | Description | Example |
|---|---|---|
| `zone.delete` | Remove copper zones by layer/net | `{"op": "zone.delete", "layer": "B.Cu", "net": "GND"}` |
| `zone.refill` | Global zone recalculation | `{"op": "zone.refill"}` |
| `net.delete_routing` | Strip all tracks/vias for a net | `{"op": "net.delete_routing", "net": "GND"}` |
| `board.prep_for_route` | Purge tracks, check edge cuts, reset zones | `{"op": "board.prep_for_route"}` |

### File Format

`ops.json` accepts either:
- **Array:** `[{"op": ...}, {"op": ...}]`
- **Structured:** `{"board": {"clear_edge_cuts": false, "clear_tracks": false, "unroute_all": false}, "ops": [...]}`

---

## Appendix B: SWIG Memory Safety

KiCad's Python bindings wrap native C++ pointers. Following these invariants prevents memory leaks and fatal `SwigPyObject` corruption:

1. **Deletion Rule:** Always use `b.Delete(item)` when removing drawings, tracks, vias, or zones. Never use `b.Remove(item)` — it transfers pointer ownership to Python GC, corrupting SWIG's RTTI table.
2. **Explicit Deallocation:** After headless operations, `del board; gc.collect()`.

---

## Appendix C: Reference Documents

| Document | When to Consult |
|---|---|
| [`references/art_gate_protocol.md`](references/art_gate_protocol.md) | Turn-1 planning & adversarial verification |
| [`references/adversarial_dfm_checklist.md`](references/adversarial_dfm_checklist.md) | DFM audit during planning |
| [`references/jlcpcb_basic_parts.md`](references/jlcpcb_basic_parts.md) | Passive component LCSC IDs |
| [`references/pcb_placement_rules.md`](references/pcb_placement_rules.md) | 80-rule placement doctrine & precedence ladder |
| [`references/trackwidth_clearence_viasize.md`](references/trackwidth_clearence_viasize.md) | Netclass track/clearance/via sizing |
| [`references/stacked_pins_fix.md`](references/stacked_pins_fix.md) | USB-C / multi-GND stacked pin handling |
| [`references/failure_recovery_matrix.md`](references/failure_recovery_matrix.md) | Error symptom → root cause → recovery |
| [`references/jlcpcb_production.md`](references/jlcpcb_production.md) | JLCPCB ordering walkthrough |
| [`references/command_help.md`](references/command_help.md) | Detailed parameter docs for all tools |
| [`references/architectural_landscape_and_contributions.md`](references/architectural_landscape_and_contributions.md) | Architecture review & contributions |
