# Kaibridge 3.0 CLI Command & Tool Reference

This document provides the complete technical reference for the standalone CLI tools and Python engine in Kaibridge 3.0.

---

## 1. Canonical CLI Tool Suite

Kaibridge operates headlessly through dedicated command-line utilities covering every stage of hardware synthesis:

### Step 0: Project Bootstrap
```powershell
python kicad_lib_init.py "projects/<NAME>" -n kaibridge [--layers 2|4]
```
- Creates `<NAME>.kicad_pro`, `<NAME>.kicad_pcb`, and `kaibridge_dump/`.
- Configures local project symbol and footprint library tables (`sym-lib-table`, `fp-lib-table`).
- Configures JLCPCB design rules and initializes `warning.md`.

### Step 2: Component Sourcing
```powershell
# Active ICs, sensors, and connectors (Symbol + Footprint)
easyeda2kicad --lcsc_id <LCSC_ID> --symbol --footprint --output "projects/<NAME>/libs/kaibridge" --overwrite --project-relative

# Background 3D Model Fetch (STEP + WRL)
python kicad_3d.py "projects/<NAME>" <LCSC_ID>... --bg --interval 5
```
- Fetches verified manufacturer symbols and footprints directly to `libs/kaibridge`.
- Downloads 3D mechanical models in a non-blocking queue.

### Step 3: Ground-Truth Pin & Footprint Extraction
```powershell
# For downloaded symbols in project library:
python kicad_pins.py "projects/<NAME>\libs\kaibridge.kicad_sym" -s <SYMBOL_NAME> --json

# For stock KiCad native library symbols:
python kicad_pins.py --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json
```
- Extracts physical pin numbers, pin names, electrical types, and default footprints.
- Prevents hallucinated or guessed pin connections.

### Step 6: Schematic Compilation & Electrical Rules Check (ERC)
```powershell
# Pre-flight dry-run check (zero writes)
python json2sch.py "projects/<NAME>" --dry-run

# Compile schematic, configure netclasses, run ERC, and export SVG preview
python json2sch.py "projects/<NAME>" --erc --svg [--heal-pins]
```
- Compiles `design.json` into KiCad 10 S-expression schematics (`.kicad_sch`).
- Configures netclasses and track width rules in `.kicad_pro`.
- Runs `kicad-cli sch erc --severity-all` to enforce 0 electrical errors.
- Exports a vector SVG schematic preview to `kaibridge_dump/`.

### Step 7: Headless Netlist Synchronization (F8)
```powershell
python kicad_pcb_sync.py "projects/<NAME>"
```
- Synchronizes footprints, component values, and net ratsnest into `.kicad_pcb`.
- Reconciles compiler metadata (`kaibridge_build.json`) including synthetic bypass capacitors.

### Step 8: Staged Component Placement & Push-and-Shove
```powershell
# Apply layout operations with elastic push-and-shove relaxation
python kicad_layout.py "projects/<NAME>" "projects/<NAME>/kaibridge_dump/ops.json" --shove

# Clean up silkscreen text overlapping copper pads
python kicad_layout.py "projects/<NAME>" --sanitize-silk

# Verify zero collisions in-memory (zero disk writes)
python kicad_layout.py "projects/<NAME>" --dry-run
```
- Executes discrete placement operations with 0.5mm grid snapping.
- Resolves courtyard overlaps elastically without moving locked perimeter connectors.

### Step 9: Inspection & 3D Visual Suite
```powershell
# Summary table of placed components
python kicad_inspect.py "projects/<NAME>" --summary

# 2D Spatial Occupancy & Available Free Rectangular Pockets
python kicad_inspect.py "projects/<NAME>" --free-space

# Comprehensive 9-Angle 3D Vision Suite (Top + 4 Corners + 4 Side Edges)
python pcb_snapshot.py "projects/<NAME>" --3d

# Full export (2D vector SVG + complete 9-angle 3D suite)
python pcb_snapshot.py "projects/<NAME>" --all
```
- Analyzes board density and identifies open rectangular corridors.
- Renders high-resolution 2D SVGs and 9 unclipped 3D perspective views.

### Step 10: Headless Autorouting & DRC
```powershell
# 2-layer board routing with continuous ground plane and DRC check
python kicad_route.py "projects/<NAME>" --pour-gnd --drc

# 4-layer board routing
python kicad_route.py "projects/<NAME>" --layers 4 --pour-gnd --drc

# Strip all routed traces and zones (if re-placement is needed)
python kicad_route.py "projects/<NAME>" --unroute
```
- Integrates Freerouting 2.4.1 background daemon with adaptive routing strategies.
- Prunes dangling micro-stubs (<0.08mm).
- Floods solid continuous ground copper planes (`B.Cu` / inner planes) with island removal.
- Runs `kicad-cli pcb drc --severity-all` to confirm 0 clearance errors and 0 unconnected airwires.

### Step 11: Production Export for JLCPCB
```powershell
python export_jlcpcb.py "projects/<NAME>"
```
- Generates complete RS-274X Gerber zip and Excellon drill archives.
- Produces JLCPCB-formatted BOM CSV with 100% verified LCSC Part Numbers.
- Generates CPL pick-and-place CSV with DFM-ROT auto-rotation compensation.

---

## 2. Python Engine API (`kaibridge`)

All capabilities can be called directly within Python:

```python
from kaibridge.schematic.compiler import compile_schematic
from kaibridge.pcb.sync import sync_schematic_to_pcb
from kaibridge.pcb.layout import apply_ops
from kaibridge.pcb.gatekeeper import placement_audit
from kaibridge.pcb.router import route_board
from kaibridge.pcb.export import export_production_files

# 1. Compile schematic
sch_res = compile_schematic(project_dir="projects/demo", apply_netclasses=True, run_erc=True)

# 2. Sync to PCB (headless F8)
sync_res = sync_schematic_to_pcb(project_dir="projects/demo")

# 3. Apply layout with in-memory dry-run verification
layout_res = apply_ops(project_dir="projects/demo", ops_data=ops_list, dry_run=False, shove=True)

# 4. Gatekeeper verification
audit_res = placement_audit(project_dir="projects/demo")
assert audit_res["route_ready"]

# 5. Route board with Freerouting & pour ground
route_res = route_board(project_dir="projects/demo", pour_gnd=True, run_drc=True)

# 6. Export manufacturing bundle
export_res = export_production_files(project_dir="projects/demo")
```
