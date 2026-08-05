---
name: Autonomous KiCad PCB Generation (v2)
description: Strict workflow protocol for the AI agent to acquire components, verify pins, and set up KiCad project plumbing.
---

# Agent Protocol: Autonomous KiCad Flow (v2)

This document contains STRICT instructions for the AI Agent. You must follow these steps precisely to ensure zero-hallucination and robust KiCad project generation using the `abideV2` toolset.

## 🛑 RULE 1: Environment & Initialization
1. **Never guess paths.** The environment configuration is stored in `kicad_paths.json`. This file must exist next to the v2 scripts. If it is missing or malformed, the scripts will raise an error detailing how the user should configure it. 
2. **Never create `.kicad_pro` files.** Ensure the `<PROJECT_DIR>` provided by the user contains a `.kicad_pro` file. If not, ask the user to manually create a new project via the KiCad UI.
3. **Initialize Libraries.** Run the library setup script to safely upsert `sym-lib-table` and `fp-lib-table`, and initialize the local library structure:
   ```powershell
   python "<PLUGIN_DIR>\kicad_lib_init.py" "<PROJECT_DIR>" -n abide
   ```
   *(This script automatically reads format versions from the user's KiCad installation using `kicad_paths.json`. Existing tables are backed up to `.bak` before modification.)*

## 📥 RULE 2: Component Acquisition
Categorize the user's requested components into **LCSC** (needs downloading) and **Native** (built-in KiCad).

**For LCSC parts (one component per command):**
The working directory MUST be <PROJECT_DIR>, otherwise --project-relative crashes
with "is not in the subpath of" because easyeda2kicad resolves the 3D path against CWD.

```powershell
Push-Location "<PROJECT_DIR>"

easyeda2kicad --lcsc_id <LCSC_ID> --full --output "$PWD/libs/abide" --overwrite --project-relative

Pop-Location
```

- On `handshake operation timed out` / `Failed to fetch data`: this is a network error,
  not a bad part id. Retry that single id up to 2 times, then report it to the user
  and continue with the remaining parts. Never substitute a different component.
- After every batch, run the verification gate before writing design.json:
  `python "<PLUGIN_DIR>\kicad_pins.py" "<PROJECT_DIR>\libs\abide.kicad_sym" --verify`

**For Native Parts:**
Do nothing to acquire them. Parts like `Device:R` or `Device:C_Small` are already resolved by KiCad's global library table.

## 🔎 RULE 3: Zero-Hallucination Pin Verification (MANDATORY GATE)
Before generating any schematic topology, you MUST extract exact pin data from the S-Expression files. Never guess pin names or numbers.

**1. Verification Gate (All Project Parts)**
Run the verify command to ensure footprints exist and physical pad counts match symbol pin counts for the project library:
```powershell
python "<PLUGIN_DIR>\kicad_pins.py" "<PROJECT_DIR>\libs\abide.kicad_sym" --verify
```
*If this command exits with code 1, a component is broken (e.g., missing footprint or pad count mismatch). You must fix it or inform the user.*

**2. Data Extraction**
Read the exact pin data (Name, Number, Electrical Type) in JSON format for the specific symbol you are about to use:

```powershell
# For LCSC / Project parts:
python "<PLUGIN_DIR>\kicad_pins.py" "<PROJECT_DIR>\libs\abide.kicad_sym" -s <SYMBOL_NAME> --json

# For Native KiCad parts:
python "<PLUGIN_DIR>\kicad_pins.py" --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json
```
*(Example native: `--native Device -s R`)*

## 📐 RULE 4: Circuit Topology Specification (`design.json`)
After verifying component footprints and extracting exact pin data via `kicad_pins.py --json`, the AI agent must construct the circuit topology in structured `design.json` format:

1. **`parts`**: Define each component reference (e.g., `U1`, `R1`, `C1`), its symbol, value, and footprint.
   - For LCSC parts, use `symbol: "abide:<SYMBOL_NAME>"` and `footprint: "abide:<FOOTPRINT_NAME>"`.
   - For Native parts, use standard library symbols e.g., `symbol: "Device:R"`, `footprint: "Resistor_SMD:R_0603_1608Metric"`.
2. **`nets`**: Define net names (e.g., `GND`, `VIN`, `+3V3`, `SIGNAL_NAME`) and map connected pins in the format `"<REF>.<PIN_NUMBER>"` (e.g., `"U1.1"`, `"C1.2"`).
   - **CRITICAL**: ONLY use exact pin numbers extracted via `kicad_pins.py`. Never guess or hallucinate pin numbers!
   - **MANDATORY**: Name every single junction/net properly (e.g. `LED_A`). Do NOT use KiCad auto-generated names like `Net-(D1_Pad1)`.
   - **STYLE**: For Power nets (`GND`, `+3V3`, `+5V`, `VIN`), set `"style": "global"`. For standard signals, omit or use `"style": "local"`.
3. **`no_connect`**: List any intentionally unconnected pins in `"<REF>.<PIN_NUMBER>"` format.
4. **`checks`**: Always set `"require_footprints": true` so missing footprint errors are caught during dry-run before writing the schematic file.

Save the generated design file to `<PROJECT_DIR>\design.json` (refer to `design_template.json` for schema).
- পিন রেফারেন্স অবশ্যই `kicad_pins.py --json`-এর নম্বর/নাম থেকে আসবে; `design.json` লেখার পর প্রথম কমান্ড সর্বদা `python json2sch.py <PROJECT_DIR> design.json --dry-run`, exit code 0 না হলে schematic লেখা নিষিদ্ধ।।

## 🔧 RULE 5: PCB Sync & Snapshot
After writing the `.kicad_sch` file, you must sync it to the PCB and take a snapshot for Visual AI placement:
1. Open KiCad PCB Editor and press `F8` (Update PCB from Schematic) to import components.
3. Open the KiCad Plugin (abIDE) to start the bridge socket server.
4. Run `python "<PLUGIN_DIR>\Autoplacer\macro_placer.py" "<PROJECT_DIR>"` to safely untangle the footprints and organize them into grouped blocks using `apply_ops`.
5. Run `python "<PLUGIN_DIR>\Autoplacer\pcb_snapshot.py" "<PROJECT_DIR>"` again to generate a clean `_board.svg` snapshot of the newly grouped board state.

## 🧠 RULE 6: Visual AI Placement
When acting as the **Visual AI Placer**, you will receive the `_board.svg` snapshot AND the `design.json` file. Your goal is to make human-like PCB placement decisions:
1. **Analyze Component Function:** Understand what the parts are (e.g. Connectors/USB should be at the board edge, Decoupling capacitors must be placed intimately close to the IC power pins).
2. **Analyze Connectivity:** Use the `nets` object in `design.json` to know exactly which pins connect to each other. (Note: Ratsnest lines are not visible in the SVG, so you must rely on the JSON netlist to trace connections mentally).
3. **Optimize Layout:** Look at the `_board.svg` to see the pad numbers and shapes. Rotate (0, 90, 180, 270) and move components so their connecting pads face each other, minimizing the distance traces will have to travel.
4. **Generate JSON Ops:** Create a JSON array of your planned moves.
   ```json
   [
     {"op": "footprint.move", "ref": "C1", "x": 55.0, "y": 50.0, "rotation": 270},
     {"op": "footprint.move", "ref": "U1", "x": 100.0, "y": 50.0, "rotation": 0}
   ]
   ```
5. **Apply:** Save the JSON to a file (e.g. `ops.json`) and apply it using:
   `python "<PLUGIN_DIR>\Autoplacer\kicad_agent_bridge.py" --json-ops ops.json`
6. **Verify:** You MUST run `pcb_snapshot.py` again after applying the moves to verify the layout!

## 🔮 RULE 7: Advanced KiCad Python Scripting (Zero Hallucination)
While simple placements use `ops.json`, you may need to write custom Python scripts (`pcbnew`) for advanced tasks (e.g. complex routing, custom shapes). KiCad's Python API changes frequently and LLMs often hallucinate methods. 
1. **Never guess API methods.**
2. **Use the Oracle:** Before writing any `pcbnew` code, you MUST query the Oracle to get the exact SWIG signature and docstring.
   ```powershell
   python "<PLUGIN_DIR>\Autoplacer\oracle.py" <ClassName> <MethodName>
   # Example: python oracle.py BOARD GetTracks
   ```
3. **Write the Script:** Only use the methods exactly as they are defined in the Oracle's output. Run the script using `kicad_agent_bridge.py --script_path <your_script.py>`.

## 🔄 RULE 8: Autonomous Auto-Routing & DRC Optimization Loop
Once components are grouped and ready for final placement, any AI agent must follow this autonomous closed-loop optimization to ensure a 100% routed, error-free PCB:

1. **Set Board Constraints:** First, define the PCB boundaries using the `"board.set_size"` operation in your JSON ops (e.g. `{"op": "board.set_size", "width": 100, "height": 50}`).
2. **Initial Placement:** Move components inside the board area using `"footprint.move"` operations.
3. **Run Autorouter:** Run the headless FreeRouting engine via the runner script:
   ```powershell
   python "<PLUGIN_DIR>\Autoplacer\freerouting_runner.py" "<PROJECT_DIR>" --jar "freerouting.jar"
   ```
   *(This will automatically export DSN, run the Java engine, and import the SES file).*
4. **DRC Check:** Trigger the DRC check via the bridge using the `"board.drc_check"` JSON operation.
5. **The Feedback Loop:** If the DRC Check returns errors (e.g. Clearance Violations):
   - **Wipe Routing:** Send a `"net.delete_routing"` JSON operation to delete all existing tracks.
   - **Analyze & Rearrange:** Read the DRC errors, identify the overlapping components, and use `"footprint.move"` to shift them apart.
   - **Loop:** Go back to Step 3 (Run Autorouter).
   - **Exit Condition:** Repeat this loop continuously until the DRC check returns exactly `0 errors` and the Tangle Score is optimized.

---
*(End of flow)*
