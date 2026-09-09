---
name: Kaibridge 3.0 — Evidence-First Hardware Synthesis Engine
description: Procedural handbook for Kaibridge 3.0 — headless KiCad 10 hardware synthesis with evidence-first ground-truth planning, contract-first placement, pre-flight proofs, characterized circuit motifs, Freerouting 2.4.1, and 100% JLCPCB production export.
---

# Kaibridge skill

> **Pipeline with 4 Mandatory Human Interception Gates:**
> - **Step 0–3:** Bootstrap → Idea → Source → Extract
> - 🛑 **Human Checkpoint 1:** Architecture & Sourcing Blueprint Sign-off (Step 4)
> - **Step 5–6:** Write `design.json` → Compile Schematic & ERC
> - 🛑 **Human Checkpoint 2:** Schematic, Netlist & ERC Review (Post Step 6)
> - **Step 7–8:** Sync PCB → Constructive Placement & 9-Angle 3D Snapshot (Step 8F)
> - 🛑 **Human Checkpoint 3:** 3D Mechanical Freeze, ISRRO-X Planning & Speed Selection (Step 9A)
> - **Step 9B–10:** ISRRO-X Physics Optimization → Headless Freerouting & Ground Pour
> - 🛑 **Human Checkpoint 4:** Pre-Production & Manufacturing Sign-off (Step 11)

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
- **Audit Log (`warning.md`):** Automatically initializes `<PROJECT_DIR>/kaibridge_dump/warning.md` to record all symbol modifications, pin healing actions, and electrical audit logs.
- **GUI Lock Rule:** If user opens KiCad GUI, they must save (`Ctrl+S`) and close before running headless commands.

**→ Next:** Step 1 (Idea & Requirement Capture)

---

## Step 1: Idea & Requirement Capture

**What:** Capture the user's raw design intent and identify candidate ICs/connectors to source.

> **Crucial Rule:** Step 1 is strictly an **intent capture & sourcing target wishlist**, NOT the final circuit plan. The agent must NEVER output a finalized BOM, netlist, or passive connection scheme here — because symbols and footprints have not been downloaded or inspected yet. The final, verified circuit specification is produced in **Step 4** using real extracted evidence.

**Process:**
1. Parse the user's prompt for: functional goals, target IC(s), voltage rails, interfaces (UART, SPI, I²C, USB), connector types, and mechanical constraints (board size, mounting holes).
2. Identify candidate active ICs / connectors and map them to target LCSC IDs (ask user if ambiguous).
3. Consult [`references/art_gate_protocol.md`](references/art_gate_protocol.md) (adversarial cognitive checklist to stress-test inrush, brownouts, and polarity during planning).
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

## Step 4: Implementation Plan ⟨Human Checkpoint 1: Architecture & Sourcing Blueprint⟩

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

5. **Multi-Pad Contacts (USB-C / Power):**
   - Ensure all physical pads needing copper are declared in `"connections"` (exact or composite aliases like `A1/B12`)
   - Unconnected chassis shield pins (`SH`) placed in `"no_connect"` per [`references/stacked_pins_fix.md`](references/stacked_pins_fix.md)

6. **Board Strategy:**
   - 2-layer vs 4-layer decision
   - Estimated board size
   - Connector placement strategy (which edges)

**Output (The Real, Evidence-Backed Design Blueprint):**
A comprehensive, verified circuit plan presented to the user (or secondary reviewer) containing the 6 sections above with 100% verified pin numbers, footprints, and JLCPCB Basic C-IDs. This plan is solid enough that any agent or engineer can verify it directly.

🛑 **MANDATORY HUMAN GATE 1 (Architecture & Sourcing Sign-off):**
Present the completed 6-section blueprint to the user. The agent MUST NOT write `design.json` or proceed to Step 5 until the user explicitly approves the BOM, active IC choices, and power architecture.

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

## Step 6: Compile Schematic & ERC Gate ⟨Human Checkpoint 2: Schematic, Netlist & ERC Sign-off⟩

**What:** Compile `design.json` into `.kicad_sch`, write netclasses into `.kicad_pro`, run KiCad ERC, and export vector SVG preview.

```powershell
# 1. Preflight dry-run check (zero writes):
python json2sch.py "projects/<NAME>" --dry-run

# 2. Compile schematic + netclasses + run KiCad ERC + export SVG preview + netlist & BOM:
python json2sch.py "projects/<NAME>" --erc --svg --netlist
```

**What to Expect:**
- `.kicad_sch` generated with all symbols, wires, power flags, and net labels
- `.kicad_pro` updated with netclass track/clearance/via rules
- ERC automatically runs via `kicad-cli sch erc` with `--severity-all` (100% warning and error visibility)
- Vector SVG preview saved to `<PROJECT>/kaibridge_dump/<NAME>_schematic.svg` (Checkpoint 2 Ready)
- Complete XML Netlist saved to `<PROJECT>/kaibridge_dump/netlist.xml`
- Bill of Materials (BOM) saved to `<PROJECT>/kaibridge_dump/bom.csv`
- Pure 1-line netlist connectivity (`NET <NAME> : <Ref.Pin> ...`) printed to console for instant cross-AI review (ChatGPT/Claude/DeepSeek)

### 6B. Standalone Netlist & BOM Export (kicad-cli)
If exporting or re-generating netlist / BOM independently without recompiling:
```powershell
# Export complete XML Netlist (Components + Pin Connectivity):
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" sch export netlist --format kicadxml -o "projects/<NAME>/kaibridge_dump/netlist.xml" "projects/<NAME>/<NAME>.kicad_sch"

# Export Bill of Materials (BOM CSV):
& "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" sch export bom -o "projects/<NAME>/kaibridge_dump/bom.csv" "projects/<NAME>/<NAME>.kicad_sch"
```

**Audit Transparency (`warning.md`):**
- EasyEDA active IC symbols frequently arrive with `unspecified` pin types. When `--heal-pins` resolves these into electrical types (`power_in`, `power_out`, `bidirectional`), every single modification (`Symbol`, `Pin`, `Name`, `unspecified` → `type`) is logged transparently to `<PROJECT>/kaibridge_dump/warning.md` for human review.

🛑 **MANDATORY HUMAN GATE 2 (Schematic & Netlist Sign-off):**
Present the generated vector SVG schematic preview, XML netlist, BOM CSV, and ERC report to the user.
**Human Verifies:**
1. ✅ ERC Report has 0 Errors (all warnings like `[pin_to_pin]` or `[power_flags]` fully explained).
2. ✅ Netlist connectivity matches intended schematic topology.
3. ✅ Part values and LCSC Basic Part C-IDs are confirmed.
The agent MUST pause for user confirmation before syncing components to the PCB.

**Gate:** `Status: PASSED (0 Errors)`. If errors exist, inspect `kaibridge_dump/erc_report.json` and `kaibridge_dump/warning.md`, fix `design.json`, and recompile.

**→ Next:** Step 7 (Sync PCB)

---

## Step 7: Sync PCB Netlist ⟨Establish Ground Truth⟩

**What:** Headless "F8" — binds footprints, values, and net ratsnest from schematic into `.kicad_pcb`. Reconciles compiled build metadata (`kaibridge_build.json`) including synthetic decoupling capacitors and resolved physical pin numbers.

### 7A. Pre-Sync Board Snapshot (If modifying an existing board)
```powershell
python -c "import json,sys; from kaibridge.pcb.snapshot import snapshot_board; r=snapshot_board(sys.argv[1],tag='pre_sync'); print(json.dumps(r,indent=2))" "projects/<NAME>"
```

### 7B. Execute Netlist Reconciliation
```powershell
python kicad_pcb_sync.py "projects/<NAME>"
```

**What to Expect:**
- All footprints instantiated at default positions in `.kicad_pcb` staging lot.
- Net ratsnest (airwires) visible between connected physical pads.
- Synthetic components (e.g. schematic decoupling capacitors) instantiated.
- Console: `[OK] PCB synced — <N> footprints, <M> nets`.

**→ Next:** Step 8 (Place Components)

---

## Step 8: Place Components ⟨Staged Ingestion Protocol⟩

**What:** Position all footprints on the PCB in disciplined stages — exactly how a human layout engineer thinks.

> **⚠ CRITICAL:** This step uses a **Staged Ingestion Protocol**. Do NOT dump all components at once. Ingest them in functional groups, verify zero collisions after each stage, and audit visually before proceeding to the next.

### 8A. Cognitive Overview

A human layout engineer follows this mental model:
1. **Staging Isolation:** After `kicad_pcb_sync.py` (Step 7), all footprints sit in a default staging lot (upper-left, typically $X \in [25..150], Y \in [25..130]$). **NEVER** draw the board outline on top of these. Place the board outline origin far away (e.g., $X \ge 180, Y \ge 180$) so unplaced parts remain safely in `STAGING` status and never contaminate the board.
2. **Bedrock Anchors First:** Physical edge connectors go in first, locked as immovable bedrock.
3. **Free Space → Silicon:** Query where empty space is, then drop core ICs into the largest pocket.
4. **Passives → Push-and-Shove:** Cluster passives near their parent ICs. The solver automatically resolves any collisions.
5. **Zero-Collision Gate → 3D Audit:** Hard gate: must reach `ZERO COLLISIONS` before routing.

---

### 8B. Phase 1 — Board Envelope & Perimeter Bedrock

#### Decision 1: Board Dimensions

If the user has already specified board dimensions in `design.json` or verbally, use those exactly. Otherwise, estimate from component count and total courtyard area.
Never silently override user-provided dimensions.

#### Decision 2: Board Outline Origin

Choose an origin that guarantees **zero overlap** with the KiCad staging lot. Safe default: `origin_x: 180.0, origin_y: 180.0`. The actual value does not matter as long as it is far from the staging grid.

#### Decision 3: Identify Edge Connectors

Scan the schematic BOM / footprint list from `kicad_inspect.py --summary`. Identify all connectors (USB, headers, jacks, barrel jacks, test points). These are your **perimeter anchors**.

#### Decision 4: Connector Placement & Orientation

Place each connector so its **mating face (mouth/opening) faces outward** past the board edge:

| Connector Position | Mouth Faces | Rotation Heuristic |
|---|---|---|
| Left edge | $-X$ (outward left) | Try `rot: 180` or `rot: 270`; verify with 3D |
| Right edge | $+X$ (outward right) | Try `rot: 0`; verify with 3D |
| Top edge | $-Y$ (outward up) | Try `rot: 90`; verify with 3D |
| Bottom edge | $+Y$ (outward down) | Try `rot: 270`; verify with 3D |

> **⚠ Rotation is footprint-dependent.** Different footprint libraries orient the body differently. The above are starting heuristics. You **MUST** render `pcb_snapshot.py --angle top` after placing each connector and visually confirm the mouth faces outward. If it faces inward, add/subtract 180°.

**Always set `"locked": true`** on perimeter connectors. Locked parts are immune to push-and-shove displacement.

#### Execute Phase 1

Write `<PROJECT>/kaibridge_dump/ops.json` with:
1. `board.set_size` (user-specified or estimated `width`, `height`, safe `origin_x/y`)
2. One `footprint.place` per edge connector (with `locked: true`)

```powershell
python kicad_layout.py "projects/<NAME>"
python pcb_snapshot.py "projects/<NAME>" --angle top
```
**Gate:** View `top.png`. Every connector mouth must face outward. If any is inverted → fix rotation in `ops.json` → re-apply → re-render until correct.

---

### 8C. Phase 2 — Free-Space Mapping & Core Silicon

#### Step 1: Query Available Free Pockets
```powershell
python kicad_inspect.py "projects/<NAME>" --free-space
```
This reports:
- **Board occupancy density** (% of courtyard area used)
- **Maximal Free Rectangular Pockets** sorted by area with `Fit Guide` labels
- **Component Geometry Catalog** showing each part's physical size, position, and `Status: ON BOARD` vs `STAGING`

#### Step 2: Decide Where to Place Core ICs

Using the free-pocket report, apply these placement principles:
- **Signal Flow Alignment:** Arrange core ICs to follow the schematic's signal/power flow linearly (e.g., Input Connector → Protection → Regulator → Output Connector). Avoid zigzag routing.
- **Heatsink Orientation:** For SOT-223/DPAK ICs with exposed thermal tabs, orient the tab toward the nearest board edge or a large copper pour area.
- **Largest Pocket First:** Place the physically largest IC (MCU, regulator) into the largest available pocket.

#### Step 3: Apply & Verify
Add `footprint.place` entries for core ICs to `ops.json` and apply:
```powershell
python kicad_layout.py "projects/<NAME>" --shove
python kicad_inspect.py "projects/<NAME>" --free-space
```
**Check:** Core ICs now show `Status: ON BOARD`. Free pockets have shrunk. No collisions.

---

### 8D. Phase 3 — Passives Ingestion & Push-and-Shove

#### Step 1: Cluster Passives by Functional Proximity

Follow these proximity rules when choosing coordinates:
- **Decoupling caps:** Within ≤ 2.5mm of the target IC's power pin (VIN side caps near VIN, VOUT side caps near VOUT).
- **Pull-up/pull-down resistors:** Adjacent to the connector or IC pin they serve.
- **LED + current-limiting resistor pairs:** Group together near the board perimeter or in an indicator cluster.
- **Crystal + load caps:** Within ≤ 5mm of MCU oscillator pins.

> **Tip:** You do not need perfect coordinates. Place passives in the approximate neighborhood of their parent IC. The push-and-shove solver will elastically resolve any overlaps.

#### Step 2: Apply with Push-and-Shove

Add all remaining `footprint.place` entries to `ops.json` and apply:
```powershell
python kicad_layout.py "projects/<NAME>" --shove
```

**How Push-and-Shove works:**
1. Detects courtyard overlaps between all on-board (non-staging) components.
2. Calculates minimum penetration vector for each collision pair.
3. Elastically displaces the unlocked component along the shortest escape axis.
4. If the displaced part hits another, the shove cascades (ripple effect).
5. Locked connectors are immovable bedrock — never displaced.
6. All final positions are clamped within board margins and snapped to the 0.5mm grid.

#### Step 3: Zero-Collision Gate (HARD REQUIREMENT)
```powershell
python kicad_layout.py "projects/<NAME>" --dry-run
```
**MUST produce:**
```
Courtyard Collisions: 0
Status: ZERO COLLISIONS (Geometry Gate Verified)
```
Also verify with:
```powershell
python kicad_inspect.py "projects/<NAME>" --free-space
```
**ALL components must show `Status: ON BOARD`** and **zero must remain in `STAGING`**.

> **If collisions remain:** Adjust coordinates in `ops.json`, re-apply with `--shove`, and re-check. Do NOT proceed to routing with non-zero collisions.

---

### 8E. Phase 4 — Silkscreen Sanitation

```powershell
python kicad_layout.py "projects/<NAME>" --sanitize-silk
```
Hides bulky value labels and auto-hides reference designators that overlap copper pads. Prevents `[silk_over_copper]` DRC warnings.

---

### 8F. Phase 5 — 9-Angle 3D Visual Audit

```powershell
python pcb_snapshot.py "projects/<NAME>" --3d
```
Renders 9 unclipped perspective views to `<PROJECT>/kaibridge_dump/3d_views/`:
- `top.png` — Top orthogonal
- `corner_front_left.png`, `corner_front_right.png`, `corner_back_left.png`, `corner_back_right.png` — 45° isometric corners
- `side_front.png`, `side_back.png`, `side_left.png`, `side_right.png` — 30° edge elevations

**Sign-off Checklist (must pass ALL before routing):**
1. ✅ Every connector mouth faces outward with unobstructed mating clearance
2. ✅ Decoupling caps sit directly adjacent to their parent IC power pins
3. ✅ No component overhangs or crosses the board edge cuts
4. ✅ Component density looks visually balanced — no obvious dead zones or cramped clusters

**→ Next:** Step 9 (Inspect & Audit)

---

## Step 9: 3D Mechanical Freeze & ISRRO-X Optimization ⟨Human Checkpoint 3⟩

**What:** Verify 3D mechanical constraints, freeze connectors and RF antennas, select routing performance mode, and execute physics-preserving ISRRO-X detailed placement.

### 9A. 3D Mechanical Freeze & Visual Audit (Human Interception Gate)

```powershell
python pcb_snapshot.py "projects/<NAME>" --3d
```
The agent generates 9-angle 3D views (`top.png`, isometric corners) into `<PROJECT>/kaibridge_dump/3d_views/` and **MUST present them to the user with the following 3 mandatory questions**:

1. **Connector Mouth Orientation:**
   - Are all perimeter connectors (USB-C, Pin Headers, Screw Terminals) facing strictly **OUTWARD** towards the board edge with unobstructed mating clearance?
   - *(If inverted, adjust rotation in `ops.json` by adding/subtracting 180°, re-apply with `python kicad_layout.py`, and re-render)*.
2. **RF Antenna & Thermal Clearance:**
   - Is the ESP32 / RF module antenna protruding or facing the board edge with clean ground keepout?
   - Are regulator/transistor heatsink tabs oriented away from sensitive silicon?
3. **Anchor Locking & Routing Speed Choice:**
   - Which critical components to freeze (`"locked": true`)? (Connectors, MCUs, Mounting holes).
   - What routing speed mode does the user prefer?
     - **Fast Mode (`max_passes=1`):** ~25-30 seconds (100% completion, ideal for rapid visual iteration).
     - **Deep Quality Mode (`max_passes=5`):** ~3-5 minutes (Aggressive rip-up & reroute for ~30-40% via minimization, ideal for factory release).

🛑 **MANDATORY HUMAN GATE 3:**
The agent MUST NOT invoke the router or commit ISRRO-X until the user confirms connector orientation, RF/antenna clearance, locked anchors, and preferred routing mode.

### 9B. ISRRO-X: Physics-Preserving Detailed Placement Optimization

Once mechanical anchors are locked, invoke the deterministic physics-preserving detailed placer:
```powershell
# Audit run (inspect before/after crossings, escape blockage, RUDY congestion):
python kicad_swap_optimizer.py "projects/<NAME>" --json

# Commit verified improvement with automatic backup and independent reload:
python kicad_swap_optimizer.py "projects/<NAME>" --commit
```

**What ISRRO-X guarantees:**
- Immovable locked anchors remain 100% untouched.
- Swaps only strictly geometry-isomorphic passives within safe semantic roles and same-anchor decoupling groups.
- Evaluates true lexicographic score: `Hard Legality > Physics/Anchors > Blocked Escapes > RUDY Congestion > Crossings > HPWL`.
- Eliminates pin escape blockages and ratsnest crossings before traces are drawn.
- Automatic rollback if post-commit verification degrades hard violations or anchor constraints.

### 9C. Live Board State & Free Space Inspector

```powershell
# Summary table (Ref, Pos, Size, Rot, Layer, Locked):
python kicad_inspect.py "projects/<NAME>" --summary

# 2D Spatial Occupancy & Available Free Rectangular Pockets:
python kicad_inspect.py "projects/<NAME>" --free-space

# Full JSON with pad coordinates, courtyards, nets:
python kicad_inspect.py "projects/<NAME>" --full --json
```

### 9D. Live SWIG API Oracle & Zero-Hallucination Autonomy Guard

**Why & How This Guarantees Robustness in Autonomous Workflows & Custom Instructions:**
KiCad 10's underlying C++ SWIG wrapper (`pcbnew`) changes breakingly between major versions (`wxPoint` -> `VECTOR2I`, `EDA_ANGLE`, `GetFootprints`). When users issue custom automation instructions or edge-case board modifications, AI models frequently hallucinate obsolete KiCad 5/6 API calls, causing fatal `AttributeError` crashes or C++ segfaults.

`kicad_oracle.py` eliminates this by providing an instant (<4ms) live reflection probe directly into the host machine's KiCad C++ installation:
1. **Zero-Hallucination Custom Execution:** When executing custom instructions or complex automation, querying `kicad_oracle.py <method>` guarantees exact signatures and copy-paste-ready tested Python idioms (`VECTOR2I`, `FromMM`, `EDA_ANGLE`), preventing trial-and-error debugging loops.
2. **Pre-Flight DFM & Stackup Enforcement:** Before modifying traces or layers, querying `drc_rules`, `stackup_4layer`, or `track_clearance` locks in ground-truth JLCPCB constraints directly.
3. **Memory Safety Shield:** Querying `swig_memory` enforces Appendix B invariants (`b.Delete()` and `del board; gc.collect()`), completely preventing fatal `0xC0000005` memory corruption.

```powershell
# List all 8 architectural and manufacturing rule topics:
python kicad_oracle.py --list

# Query specific production rules & code patterns:
python kicad_oracle.py "drc_rules"
python kicad_oracle.py "stackup_4layer"
python kicad_oracle.py "freerouting_limits"

# Live C++ class inspection with keyword filter:
python kicad_oracle.py "BOARD" --filter "track"
python kicad_oracle.py "PCB_VIA" --filter "layer"

# Exact method signature & tested Python code snippet:
python kicad_oracle.py "FindFootprintByReference" -c BOARD
```

**Available Oracle Topics (8 Total):** `drc_rules`, `jlcpcb_rules`, `swig_memory`, `zone_filling`, `power_flags`, `freerouting_limits`, `stackup_4layer`, `track_clearance`.

### 9E. Hard Gatekeeper Route-Readiness Proof
```powershell
python -c "import json,sys; from kaibridge.pcb.gatekeeper import placement_audit; r=placement_audit(sys.argv[1]); print(json.dumps(r,indent=2)); ok=(r.get('success') is True and r.get('route_ready') is True); sys.exit(0 if ok else 1)" "projects/<NAME>"
```

**Gatekeeper Invariants (Fail-Closed):**
- `outline_closed`: True
- `overlap_count`: 0
- `outside_outline_count`: 0
- `netclasses_without_track_width`: []
- `route_ready`: True (Components strictly contained within board bounds, zero collisions, all nets configured with track width).

> **Planar Optimizer Note:** `kicad_planar_optimizer.py` seeds strictly from the live `.kicad_pcb` state and respects locked components without wiping out Step 8 placements. On a properly placed board with zero collisions and verified cells, annealing is optional and should not be invoked blindly.

**→ Next:** Step 10 (Route & DRC)

---

## Step 10: Route & DRC Gate ⟨Checkpoint 3⟩

**What:** Autoroute all traces, pour GND plane, run DRC to verify zero violations.

### 10A. Headless Autorouting

```powershell
# Full pipeline: route + GND plane + DRC:
python kicad_route.py "projects/<NAME>" --pour-gnd --drc

# 4-layer boards:
python kicad_route.py "projects/<NAME>" --layers 4 --pour-gnd --drc
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
python kicad_route.py "projects/<NAME>" --unroute
```

Present DRC pass confirmation as Checkpoint 3.

**→ Next:** Step 11 (Export)

---

## Step 11: Export for JLCPCB Production ⟨Human Checkpoint 4: Pre-Production Sign-off⟩

**What:** Generate 100% factory-ready Gerbers, BOM, and CPL files.

```powershell
python export_jlcpcb.py "projects/<NAME>"
```

**What to Expect (in `<PROJECT>/production_output/`):**

| File | Contents |
|---|---|
| `<NAME>_gerbers.zip` | Complete Gerber + Excellon drill archive. 4-layer includes `F_Cu.gtl`, `GND.g1`, `Power.g2`, `B_Cu.gbl` |
| `<NAME>_bom_jlcpcb.csv` | BOM: `Comment, Designator, Footprint, LCSC Part #` — 100% populated with LCSC C-IDs |
| `<NAME>_cpl_jlcpcb.csv` | CPL centroid: `Designator, Val, Package, Mid X, Mid Y, Rotation, Layer` — numeric floats with **DFM-ROT** auto-correction |

**DFM-ROT Rotation Compensation:** Auto-corrects the 180° discrepancy between KiCad IPC-7351 and JLCPCB EIA-481 tape feeders for `Diode_SMD`, `LED_SMD`, `SOT-23`, `SOT-223`, and polarized capacitors. EasyEDA `kaibridge:*` parts kept at 0°. Custom overrides via `"rotation_offset": <deg>` in `design.json`.

🛑 **MANDATORY HUMAN GATE 4 (Manufacturing Sign-off):**
Present the manufacturing summary to the user:
1. ✅ KiCad DRC report confirms 0 errors and 0 unconnected items.
2. ✅ Completed copper trace render (`top.png`) and via count summary.
3. ✅ B.Cu Ground plane continuity confirmed (no floating copper islands).
4. ✅ Production bundle ready: `<NAME>_gerbers.zip`, `bom_jlcpcb.csv`, `cpl_jlcpcb.csv`.
Human engineer signs off before final zip upload to JLCPCB.

**→ Done.** Upload `production_output/` to JLCPCB. See [`references/jlcpcb_production.md`](references/jlcpcb_production.md) for ordering walkthrough.

---
---

## Appendix A: `ops.json` Operation Catalog (28 Operations)

All operations are validated against physical board constraints. Invalid `ref` or `op` returns `{"success": false, "errors": [...]}`.

### Board Dimensions & Mechanical Geometry

| Operation | Description | Example / Parameters |
|---|---|---|
| `board.set_size` | Create/update rectangular `Edge.Cuts` outline | `{"op": "board.set_size", "width": 55.0, "height": 40.0, "origin_x": 100.0, "origin_y": 100.0}` |
| `board.fit_outline` | Auto-fit outline to footprint bounding box + margin | `{"op": "board.fit_outline", "margin": 5.0}` |
| `board.fillet` | Smooth corner fillets/radii on `Edge.Cuts` | `{"op": "board.fillet", "radius": 2.5}` |
| `hole.add` | M2/M3 mounting holes (single or 4 corners) | `{"op": "hole.add", "corners": true, "margin": 3.5, "drill": 3.2}` |
| `slot.add` | High-voltage isolation slot or board cutout | `{"op": "slot.add", "x1": 30.0, "y1": 10.0, "x2": 30.0, "y2": 25.0, "width": 1.2}` |

### Component Placement & Smart Alignment

| Operation | Description | Key Parameters |
|---|---|---|
| `footprint.place` | Place at explicit coordinates | `ref`, `x`, `y`, `rot` (0/90/180/270), `layer` (F.Cu/B.Cu), `locked` (bool) |
| `footprint.move` | Reposition without changing rotation | `ref`, `x`, `y` |
| `footprint.rotate` | Change rotation (absolute or relative) | `ref`, `rot`, `relative` (bool) |
| `array.place` | Linear array with uniform pitch | `refs` (list), `start_x`, `start_y`, `pitch_x`, `pitch_y`, `rot` |
| `footprint.align` | Multi-footprint alignment & equal distribution | `refs` (list), `align` (top/bottom/left/right/center_x/center_y), `distribute` (pitch mm) |

### Silkscreen, Branding & Labels

| Operation | Description | Example / Parameters |
|---|---|---|
| `text.add` | Project branding, version, and custom text | `{"op": "text.add", "text": "OmniCore v1.0", "x": 15.0, "y": 8.0, "layer": "F.SilkS", "size": 1.2}` |
| `connector.pinout_labels` | Auto-extract net names & label connector pins | `{"op": "connector.pinout_labels", "ref": "J2", "offset": 1.5, "size": 0.8}` |
| `dimension.add` | Fabrication dimension markings on `Dwgs.User` | `{"op": "dimension.add", "layer": "Dwgs.User", "offset": 4.0}` |
| `silkscreen.sanitize` | Auto-hide bulky values or pad-colliding silk | `{"op": "silkscreen.sanitize", "mode": "sanitize"}` |

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

### Copper Traces, Vias & Shielding

| Operation | Description | Key Parameters |
|---|---|---|
| `track.add` | Draw manual trace segment | `start_x/y`, `end_x/y`, `width`, `layer`, `net` |
| `track.set_width` | Modify existing track width by net/netclass | `net`, `netclass`, `width` |
| `via.add` | Place single through-hole via | `x`, `y`, `size`, `drill`, `net` |
| `via.matrix` | Thermal via array under exposed IC pad | `net`, `center_x`/`center_y` (or `ref`), `rows`, `cols`, `pitch`, `drill`, `size` |
| `via.fence` | Perimeter ground shielding via fence | `net`, `pitch`, `offset` (from board edge), `drill`, `size` |

### Copper Pours, Keepouts & Cleanup

| Operation | Description | Example |
|---|---|---|
| `zone.add` | Add copper plane / ground pour (full-board or polygon) | `{"op": "zone.add", "net": "GND", "layer": "B.Cu", "full_board": true, "connection": "full"}` |
| `rule_area.add` | RF antenna keepout (no copper, tracks, or vias) | `{"op": "rule_area.add", "x": 5.0, "y": 5.0, "w": 18.0, "h": 10.0, "no_copper": true, "no_vias": true}` |
| `zone.delete` | Remove copper zones by layer/net | `{"op": "zone.delete", "layer": "B.Cu", "net": "GND"}` |
| `zone.refill` | Global zone recalculation via `ZONE_FILLER` | `{"op": "zone.refill"}` |
| `net.delete_routing` | Strip all tracks/vias for a net | `{"op": "net.delete_routing", "net": "GND"}` |
| `board.prep_for_route` | Purge orphaned tracks, check edge cuts, reset zones | `{"op": "board.prep_for_route"}` |

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
