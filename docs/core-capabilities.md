# Kaibridge 3.0 — Core Capabilities & Architecture

Kaibridge is an end-to-end, headless hardware synthesis engine that translates high-level electronic circuit requirements into fully verified, factory-ready Printed Circuit Board (PCB) manufacturing files without requiring manual CAD GUI interactions.

Designed for electrical engineers, firmware developers, and autonomous AI agents, Kaibridge eliminates the trial-and-error cycle of traditional PCB design. It couples KiCad 10 with Freerouting 2.4.1, proprietary geometric solvers, on-demand component intelligence, and fail-closed verification gates.

---

## 1. What Kaibridge Does: From Idea to Fabricated Board

In traditional electronics design, an engineer must manually search component catalogs, draw schematics, manually wire hundreds of pins, run Electrical Rules Checks (ERC), export netlists, open a PCB editor, manually arrange components, run autorouters or hand-route traces, fix clearance errors, pour ground zones, and generate fabrication packages. This process takes days to weeks.

Kaibridge executes this entire workflow programmatically:

```
[ Natural Language / System Prompt ]
                 │
                 ▼
     1. Ground-Truth Sourcing (On-Demand LCSC / Native IPC Passives)
                 │
                 ▼
     2. Evidence Extraction (Real Pin Numbers, Types, Footprints)
                 │
                 ▼
     3. Schematic Synthesis (KiCad 10 S-Expression Compiler + ERC)
                 │
                 ▼
     4. PCB Netlist Synchronization (Headless F8 Binding)
                 │
                 ▼
     5. Staged Physical Placement (Free-Space Mapping + Push & Shove)
                 │
                 ▼
     6. Multi-Perspective 3D Visual Audit (9 Orthogonal & Isometric Views)
                 │
                 ▼
     7. Gatekeeper Route-Readiness Proof (Fail-Closed Geometry Gate)
                 │
                 ▼
     8. Autonomous Maze Routing & Ground Pouring (Freerouting + KiCad DRC)
                 │
                 ▼
     9. Factory Production Export (JLCPCB Gerbers, Drill, BOM, CPL)
```

Every stage is governed by **Fail-Closed Invariant Gates**: if an electrical collision, courtyard overlap, or design rule violation occurs, the engine halts immediately with actionable diagnostics rather than producing unbuildable hardware.

---

## 2. The 11-Stage Synthesis Pipeline

Kaibridge divides hardware synthesis into 11 distinct, verifiable steps.

### Step 0: Project Bootstrap & Plumbing
- **Tool:** `python kicad_lib_init.py "projects/<NAME>" -n kaibridge`
- **What it does:** Programmatically creates the complete KiCad 10 project structure (`.kicad_pro`, empty `.kicad_pcb`, `kaibridge_dump/`), configures project-scoped symbol and footprint library tables (`sym-lib-table`, `fp-lib-table`), configures JLCPCB design rules, and initializes the hardware synthesis audit log (`warning.md`). Supports both 2-layer and 4-layer stackups (JLCPCB JLC04161H).

### Step 1: Requirements & Sourcing Wishlist
- **What it does:** Parses functional specifications (voltage rails, communication buses like I²C/SPI/UART/USB, sensor requirements, connectors) into a candidate bill of materials. Cross-references adversarial checklists (`references/art_gate_protocol.md`, `references/adversarial_dfm_checklist.md`) to stress-test inrush current, thermal dissipation, and reverse-polarity protection upfront.

### Step 2: Ground-Truth Component Sourcing
- **Tools:** `easyeda2kicad`, `kicad_3d.py`, `references/jlcpcb_basic_parts.md`
- **Active ICs & Connectors:** Fetches exact manufacturer symbols, footprints, and 3D models (`.step`, `.wrl`) directly from LCSC/EasyEDA into `libs/kaibridge`.
- **Standard Passives:** Maps resistors, capacitors, and generic diodes to native KiCad `Device:*` symbols and standard IPC-7351 SMD/THT footprints. Attaches verified zero-fee JLCPCB Basic Part C-IDs from `references/jlcpcb_basic_parts.md` to eliminate manual sourcing surcharges.

### Step 3: Ground-Truth Pin & Footprint Extraction
- **Tool:** `python kicad_pins.py`
- **What it does:** Inspects downloaded `.kicad_sym` files to extract the exact physical pin numbers, pin names, electrical types (`power_in`, `power_out`, `bidirectional`, `passive`), and default footprint names. The system never guesses pinouts or footprint assignments from training data; all subsequent circuit connections use verified ground truth.

### Step 4: Architectural Implementation Plan
- **What it does:** Synthesizes an evidence-backed circuit architecture including complete BOM, pin-to-pin net connections, decoupling capacitor topology, power flag declarations, netclass assignments (track widths and clearances), and mechanical board dimensions.

### Step 5: Declarative Circuit Specification (`design.json`)
- **Template:** [`design_template.json`](../design_template.json) (Schema 3)
- **What it does:** Encodes the circuit into a canonical JSON file defining `meta`, `board`, `netclasses`, `groups`, `parts`, `nets`, and `power_flags`. Standardizes net names, links schematic components to physical footprints, and structures multi-sheet schematic groupings.

### Step 6: Headless Schematic Compilation & ERC Gate ⟨Checkpoint 1⟩
- **Tool:** `python json2sch.py "projects/<NAME>" --erc --svg`
- **What it does:** Compiles `design.json` directly into a KiCad 10 S-expression schematic (`.kicad_sch`). Automatically resolves power flag requirements, configures netclasses in `.kicad_pro`, auto-heals symbol pin types to prevent false warnings, executes `kicad-cli sch erc --severity-all`, and renders a vector SVG preview.
- **Gate:** Hard gate requires **0 Errors** to proceed.

### Step 7: PCB Netlist Synchronization ⟨Ground Truth Establishment⟩
- **Tool:** `python kicad_pcb_sync.py "projects/<NAME>"`
- **What it does:** Executes a headless equivalent of KiCad's GUI "F8" (Update PCB from Schematic). Programmatically binds schematic netlists, footprints, and component values into `.kicad_pcb`, generating full ratsnest airwires. Reconciles compiler metadata (`kaibridge_build.json`) including synthetic bypass capacitors and physical pad numbers.

### Step 8: Staged Component Placement & Push-and-Shove Engine
- **Tool:** `python kicad_layout.py "projects/<NAME>" <OPS_PATH> --shove`
- **What it does:** Employs a disciplined multi-phase layout protocol mirroring experienced PCB layout engineers:
  1. *Staging Lot Isolation:* Keeps unplaced footprints outside the board boundary until explicitly positioned.
  2. *Perimeter Bedrock:* Places edge connectors with outward-facing mating clearance and locks them as immovable anchors.
  3. *Free-Space Mapping:* Analyzes spatial density (`kicad_inspect.py --free-space`) and places core ICs into the largest available pockets.
  4. *Passive Proximity Clustering:* Positions decoupling capacitors and pull-up/down resistors adjacent to target IC pins.
  5. *Push-and-Shove Relaxation:* Detects courtyard overlaps and elastically displaces unlocked components into free space along minimal penetration vectors.
  6. *Silkscreen Sanitization:* Automatically hides overlapping reference designators and values to eliminate `[silk_over_copper]` DRC warnings (`--sanitize-silk`).
- **Gate:** Requires `Courtyard Collisions: 0` verified via `--dry-run`.

### Step 9: Gatekeeper Audit & 9-Angle 3D Visual Suite ⟨Checkpoint 2⟩
- **Tools:** `kicad_inspect.py`, `pcb_snapshot.py --3d`, `placement_audit()`
- **What it does:**
  - Audits board geometry with `kaibridge.pcb.gatekeeper.placement_audit`: verifies closed board outlines, zero overlaps, zero footprints outside the board edge, and valid netclass track widths (`route_ready: True`).
  - Exports a complete 9-angle 3D rendering suite (Top orthogonal, 4x 45° corner isometrics, 4x 30° edge elevations) with unclipped camera boundaries for visual and AI multimodal sign-off.

### Step 10: Autonomous Maze Routing & DRC Gate ⟨Checkpoint 3⟩
- **Tool:** `python kicad_route.py "projects/<NAME>" --pour-gnd --drc`
- **What it does:**
  - Exports Specctra DSN netlists with differential netclass track widths and 150µm edge clearance keepouts.
  - Launches Freerouting 2.4.1 daemon with adaptive routing strategies (Fanout-first single-layer routing vs Dual-layer maze routing).
  - Imports routed SES tracks into `.kicad_pcb` and automatically prunes micro-stubs (<0.08mm).
  - Pours solid continuous copper ground planes (`B.Cu` / `F.Cu`) with automatic island removal (`ISLAND_REMOVAL_MODE_ALWAYS`).
  - Executes `kicad-cli pcb drc --severity-all --refill-zones`.
- **Gate:** Requires **0 Clearance Violations** and **0 Unconnected Items**.

### Step 11: Production Export for JLCPCB
- **Tool:** `python export_jlcpcb.py "projects/<NAME>"`
- **What it does:** Generates a 100% factory-ready production package in `production_output/`:
  - Gerber RS-274X zip with Excellon drill files.
  - JLCPCB-formatted BOM CSV with pre-populated LCSC Part Numbers.
  - JLCPCB-formatted CPL (Pick-and-Place) CSV with **DFM-ROT** auto-rotation compensation to harmonize KiCad IPC-7351 vs JLCPCB EIA-481 tape feeder orientations.

---

## 3. Core Architectural Pillars

### A. Ground-Truth Component Intelligence
- **On-Demand LCSC Extraction:** Active parts are fetched dynamically via `easyeda2kicad`, capturing official manufacturer pad numbering, courtyard geometries, and 3D models.
- **Zero-Fee Basic Part Sourcing:** Directly maps passives to native IPC-7351 footprints with pre-verified zero-fee JLCPCB Basic Part C-IDs (`references/jlcpcb_basic_parts.md`), eliminating 467 MB local SQLite database bloat and extended component fees.
- **Mechanical Pad Auto-Sanitization:** Footprints with mechanical alignment holes (e.g. TCRT5000 optical sensors) where pad size matches drill hole size (`size == drill`) are automatically converted from `thru_hole` with copper to unplated `np_thru_hole` (`*.Mask` layer), eliminating zero-annular-ring DRC errors.

### B. Headless Schematic & ERC Engine
- **Direct S-Expression Generation:** Synthesizes `.kicad_sch` files natively without launching the KiCad GUI.
- **Pin Healing & Type Resolution:** Automatically detects EasyEDA `unspecified` pin types and maps them to electrically valid types (`power_in`, `passive`, `bidirectional`), logging every change to `kaibridge_dump/warning.md`.
- **Power Flag Collision Prevention:** Distinguishes external power inputs (`VBUS`, `VIN`, `GND`) from active linear regulator outputs (`+3V3`), injecting `PWR_FLAG` symbols only where required to avoid `[pin_to_pin]` driver collisions.

### C. Physics-Based Staged Placement Engine
- **17 Discrete Layout Primitives:** The layout engine operates via structured operations in `ops.json`: `footprint.place`, `array.place`, `footprint.move`, `footprint.rotate`, `footprint.lock`, `footprint.unlock`, `footprint.set_field`, `item.delete`, `board.set_size`, `board.fit_outline`, `board.prep_for_route`, `track.add`, `track.set_width`, `via.add`, `zone.delete`, `zone.refill`, and `net.delete_routing`.
- **Courtyard Centroid Offsets:** Evaluates overlaps using true polygonal bounding-box centroids (`cx, cy`) rather than raw footprint origins, ensuring accurate clearance calculations for asymmetric connectors.
- **Elastic Push-and-Shove:** Calculates penetration depth vectors between colliding bounding boxes and cascades non-colliding displacement pulses across neighboring passives while respecting locked bedrock components.
- **Transactional Disk Safety:** Operations are simulated in-memory first; changes are committed to `.kicad_pcb` only if all batch operations succeed (`len(errors) == 0`).

### D. Mathematical Planar Optimizer (`kicad_planar_optimizer.py`)
- **Simulated Annealing on Live PCB State:** Uses Kruskal's Minimum Spanning Tree (MST) and 2D line segment intersection counting to minimize airwire crossings.
- **Live Board Seeding:** Seeds directly from live `.kicad_pcb` footprint positions, preserving locked edge connectors and prior push-and-shove displacements.

### E. 9-Angle 3D Computer Vision Suite
- **Unclipped Frustum Projections:** Renders high-resolution PNGs across 9 predefined perspective angles:
  - Orthogonal: `top` (0°)
  - Isometric (45°): `corner_front_left`, `corner_front_right`, `corner_back_left`, `corner_back_right`
  - Elevation (30°): `side_front`, `side_back`, `side_left`, `side_right`
- **Stale Evidence Elimination:** Prior image artifacts are unlinked before rendering, and process exit codes and non-zero byte sizes are verified to guarantee fresh visual feedback.

### F. Headless Autorouting Daemon & Continuous Ground Pour
- **Freerouting 2.4.1 REST Daemon:** Eliminates repeated JVM initialization overhead by running Freerouting as a persistent local background service.
- **Adaptive Routing Strategy:**
  - *Strategy 1 (Dog-Bone Fanout):* For simple boards (<24 IC pins, $\le$ 20 nets), pre-places GND vias and routes all signals on `F.Cu` with zero signal vias.
  - *Strategy 2 (Dual-Layer Maze):* Automatically falls back to dual-layer routing (`F.Cu` + `B.Cu`) with jumper vias for dense layouts.
- **Solid Ground Planes:** Automatically creates boundary-clipped ground copper zones on `B.Cu` with `ZONE_CONNECTION_FULL`, automated thermal relief, and dead copper island pruning.

### G. Live SWIG C++ Reflection Oracle (`kicad_oracle.py`)
- Introspects KiCad's internal C++ SWIG wrapper (`pcbnew.py`) in <4ms.
- Extracts live class inheritance trees, method signatures, and constants (`ZONE_CONNECTION_FULL`, `ISLAND_REMOVAL_MODE_ALWAYS`), preventing API hallucinations.

---

## 4. Canonical CLI Tool Suite

Kaibridge provides dedicated standalone command-line entry points covering the entire design lifecycle:

| Tool | Primary Command | Purpose | Input | Output |
|---|---|---|---|---|
| **`kicad_lib_init.py`** | `python kicad_lib_init.py <PROJECT>` | Initializes project tables, directories & rules | Project path | `.kicad_pro`, empty `.kicad_pcb`, `sym-lib-table`, `fp-lib-table` |
| **`easyeda2kicad`** | `easyeda2kicad --lcsc_id <ID> ...` | Fetches active IC symbols, footprints & 3D models | LCSC Part ID | `.kicad_sym`, `.kicad_mod`, `.step`/`.wrl` |
| **`kicad_pins.py`** | `python kicad_pins.py <SYM_FILE> -s <SYM>` | Queries ground-truth pin names, numbers & types | Symbol file | JSON pin mapping and pad count |
| **`json2sch.py`** | `python json2sch.py <PROJECT> --erc --svg` | Compiles schematic, validates ERC & renders SVG | `design.json` | `.kicad_sch`, `.svg`, `erc_report.json` |
| **`kicad_pcb_sync.py`** | `python kicad_pcb_sync.py <PROJECT>` | Headless F8 netlist & footprint synchronization | `.kicad_sch` | Synchronized `.kicad_pcb` with ratsnest |
| **`kicad_inspect.py`** | `python kicad_inspect.py <PROJECT> --free-space` | Extracts board state, density & free pockets | `.kicad_pcb` | Geometric state summary, free-space catalog |
| **`kicad_layout.py`** | `python kicad_layout.py <PROJECT> <OPS> --shove` | Executes staged placement, shove & silk sanitization | `ops.json` | Positioned `.kicad_pcb`, collision status |
| **`pcb_snapshot.py`** | `python pcb_snapshot.py <PROJECT> --3d` | Renders 2D vector SVG and 9-angle 3D suite | `.kicad_pcb` | `3d_views/*.png`, `board.svg` |
| **`kicad_route.py`** | `python kicad_route.py <PROJECT> --pour-gnd --drc` | Autoroutes tracks, pours GND plane & runs DRC | `.kicad_pcb` | Fully routed board, `drc_report.json` |
| **`export_jlcpcb.py`** | `python export_jlcpcb.py <PROJECT>` | Exports factory-ready fabrication bundle | Routed board | Gerbers ZIP, BOM CSV, CPL CSV |

---

## 5. Comparison: Manual PCB Design vs. Kaibridge 3.0

| Feature | Traditional Manual Design | Kaibridge 3.0 Autonomous Synthesis |
|---|---|---|
| **Component Sourcing** | Manual datasheet reading, custom symbol drawing, footprint drafting (hours) | Instant LCSC extraction via `easyeda2kicad` + verified Basic Passives (<10 seconds) |
| **Pin Verification** | Manual cross-checking against PDF pin tables (prone to human error) | Ground-truth pin extraction directly from `.kicad_sym` (<1 second) |
| **Schematic Drafting** | Manual clicking, dragging symbols, drawing wires in GUI (hours) | Headless compilation from `design.json` with auto-power flags (<3 seconds) |
| **ERC Verification** | Manual clicking in GUI, fixing confusing net collisions | Automated `kicad-cli sch erc` with pin type auto-healing (<5 seconds) |
| **PCB Netlist Sync** | Manual "Update PCB from Schematic" modal dialog in GUI | Headless programmatic F8 synchronization with build metadata (<2 seconds) |
| **Component Placement** | Manual drag-and-drop, estimating clearances and airwire density (hours) | 2D free-space pocket mapping + elastic push-and-shove physics (<5 seconds) |
| **Visual Audit** | Manually rotating 3D viewer in GUI | Automated 9-angle unclipped 3D orthogonal & isometric suite (<10 seconds) |
| **Routing & Ground Pour** | Manual interactive trace routing or slow GUI autorouting plugins (hours) | Headless Freerouting 2.4.1 daemon + automatic continuous ground pour (<30 seconds) |
| **DRC Verification** | Manual GUI dialog, hunting for clearance markers | Automated fail-closed `kicad-cli pcb drc` with structured JSON reports (<5 seconds) |
| **Production Export** | Manual Gerber plot dialogs, manual BOM editing, manual CPL export | One-command generation of Gerbers ZIP, BOM CSV, and DFM-ROT compensated CPL CSV (<5 seconds) |
| **Total Turnaround** | **2 to 10 hours** or more | **< 10 minutes** |

