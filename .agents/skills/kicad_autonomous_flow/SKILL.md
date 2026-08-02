---
name: Autonomous KiCad PCB Generation
description: End-to-end workflow protocol for generating KiCad projects using local libraries and YAML blueprints.
---

## 🌐 RULE 0: ENVIRONMENT RESOLUTION (§4.2)
Before ANY other step, the agent MUST resolve and record these values:

1. **`PLUGIN_DIR`** — The directory containing `kicad_agent_bridge.py`. This is the directory where abIDE is installed (typically inside KiCad's scripting/plugins folder). Ask the user if unknown.
2. **`PROJECT_DIR`** — The KiCad project directory, provided by the user in Rule 1.

The agent MUST echo both paths back to the user in one message and wait for confirmation before proceeding.

---

## ⚠️ FAILURE PROTOCOL (§4.2)
If any command returns a non-zero exit code, an `EXECUTION ERROR`, or `KICAD NOT CONNECTED`:
1. Do **not** retry the same command more than once.
2. Do **not** improvise an alternative API call.
3. Report the exact stdout/stderr to the user and stop.
4. Never proceed to the next Rule with a failed prerequisite.

---

## 🏗️ RULE 1: PROJECT INITIALIZATION PROTOCOL
The agent does **not** create the KiCad project. The USER manually creates and opens a native project in KiCad to ensure perfect file formatting, and provides the project path to the agent.

When the agent receives the `<PROJECT_DIR>` from the user, it must immediately execute the following steps to bind local libraries to the project:

1. **Generate Local Footprint Table (`<PROJECT_DIR>/fp-lib-table`)**:
   Write the following exact content to define a project-relative (`${KIPRJMOD}`) footprint library:
   ```lisp
   (fp_lib_table
     (lib (name "easyeda2kicad") (type "KiCad") (uri "${KIPRJMOD}/libs/easyeda2kicad/easyeda2kicad.pretty") (options "") (descr "Local LCSC Footprints"))
   )
   ```

2. **Generate Local Symbol Table (`<PROJECT_DIR>/sym-lib-table`)**:
   Write the following exact content to define a project-relative symbol library:
   ```lisp
   (sym_lib_table
     (lib (name "easyeda2kicad") (type "KiCad") (uri "${KIPRJMOD}/libs/easyeda2kicad/easyeda2kicad.kicad_sym") (options "") (descr "Local LCSC Symbols"))
   )
   ```

---

## 📋 RULE 2: DETERMINISTIC TASK CHECKLIST (MANDATORY)
To prevent skipping steps, the agent **MUST** create a checklist before proceeding with execution. 
1. Create or update a task checklist artifact (e.g. `task.md`).
2. List out the steps clearly (e.g. Identify Components, Download, Extract Pins, Generate Blueprint, Query Oracle, Write Code).
3. Update the checklist (`[ ]` to `[x]`) as you progress through the workflow. Do NOT proceed to the next step until the current one is validated.

---

## 🔎 RULE 3: COMPONENT IDENTIFICATION & INTAKE (§4.2)
Before downloading anything, the agent must collect **all** required information in a **single message**. Do not scatter these questions across multiple rounds.

**Ask the user for ALL of the following at once:**
1. **Board dimensions:** width × height in mm
2. **Layer count:** 2 or 4
3. **For each component:** A description AND its LCSC part number (e.g., `C2913202`)

**If the user did NOT provide an LCSC ID**, the agent must **ask the user** for the specific LCSC part number rather than guessing. The agent should suggest what to search for on [JLCPCB Parts](https://jlcpcb.com/parts) to help the user find the right part.

**The agent must NEVER proceed to Rule 4 without a confirmed LCSC ID for every component.**

---

## 📥 RULE 4: LCSC COMPONENT IMPORT + VALIDATION
Using the confirmed LCSC IDs from Rule 3, download the physical assets (footprints + symbols) directly into the project directory.

**Step 1 — Download:**
```powershell
mkdir -Force "<PROJECT_DIR>/libs/easyeda2kicad"
easyeda2kicad --lcsc_id <LCSC_ID_1> <LCSC_ID_2> --full --output "<PROJECT_DIR>/libs/easyeda2kicad"
```
*Note: You must manually create the `libs/easyeda2kicad` directory using `mkdir` before running `easyeda2kicad`, otherwise it will fail with a folder not found error.*

**Step 2 — Validate the download:**
After the command completes, the agent **MUST verify** that every requested LCSC ID produced output files:
1. Check that a `.kicad_mod` file exists in `<PROJECT_DIR>/libs/easyeda2kicad/easyeda2kicad.pretty/` for each component.
2. Check that the `.kicad_sym` file at `<PROJECT_DIR>/libs/easyeda2kicad/easyeda2kicad.kicad_sym` exists and is non-empty.

**If any component is missing**, the agent must stop and report the failure to the user (e.g., wrong LCSC ID, discontinued part, network error). Do NOT proceed with missing components.

---

## 📌 RULE 5: FULL PIN EXTRACTION (ANTI-HALLUCINATION)
After a validated download, the agent must run `footprint_extractor.py` to discover the **exact** pin names, pad numbers, and electrical types for every downloaded component. The agent must **never guess or assume** pin configurations.

**Command:**
```powershell
python <PLUGIN_DIR>\footprint_extractor.py "<PROJECT_DIR>\libs\easyeda2kicad"
```

**What the extractor reports for each component:**
- **Symbol Pins:** The logical pin names (e.g., `GND`, `3V3`, `IO0`) and their electrical types (e.g., `power_in`, `bidirectional`). These are the names the agent will use in the YAML blueprint.
- **Footprint Pads:** The physical pad numbers and mount types (e.g., `Pad 1 (smd, rect)`).
- **Pin-to-Pad Cross-Reference:** Which logical pin maps to which physical pad.
- **Extra Pads:** Pads that have no symbol pin (e.g., thermal/mounting pads). These must still be connected to the correct net (usually GND) in the YAML.

**The agent MUST read and internalize this output before proceeding to YAML generation.** Any pin name not listed in this output **does not exist** and must not be used.

---

## 📝 RULE 6: GENERATE BLUEPRINT (YAML)
Now that the agent has hard data from Rule 5 (exact pin names and counts), it generates the structured YAML `circuit_blueprint`. This YAML file acts as the single source of truth for the BOM (Bill of Materials) and Netlist.

**To generate this blueprint correctly, the agent MUST read and strictly follow the 14 expert engineering rules and the exact YAML structure defined in `references/yaml_generation_rules.md`.**

**Critical constraints:**
- Every pin referenced in the YAML **must** come from the extractor output (Rule 5). If a needed pin does not appear in the extractor report, the agent must flag it in `unresolved_or_missing` rather than inventing a pin name.
- Every component **must** include a `ref:` field containing its KiCad reference designator (e.g., `U1`, `C1`, `J1`). This ref is what `autoplacer_engine.py` uses to look up components on the board.

**Write the blueprint to:** `<PROJECT_DIR>/circuit_blueprint.yaml`

---

## 👁️ RULE 7: REAL-SHAPE BLUEPRINT VISUALIZATION & USER APPROVAL
After generating the YAML blueprint (Rule 6), the agent **MUST** visualize it using the real schematic symbol geometry from `.kicad_sym` files.

**Step 1 — Generate the visual:**
```powershell
python <PLUGIN_DIR>\yaml_visualizer.py "<PROJECT_DIR>\circuit_blueprint.yaml"
```
This reads `<PROJECT_DIR>/libs/easyeda2kicad/easyeda2kicad.kicad_sym` automatically and produces `<PROJECT_DIR>/blueprint_view.html`.

**Step 2 — Present to the user:**
Tell the user to open `blueprint_view.html` in their browser by explicitly providing a clickable file link in the chat (e.g. `[blueprint_view.html](file:///<PROJECT_DIR>/blueprint_view.html)`). The diagram shows real schematic symbol shapes with labeled pins and color-coded wires:
- 🟠 Orange = Power, 🔵 Blue = Digital, 🟣 Purple = Analog
- 🟢 Green = Bus, 🔵 Teal = PWM, 🟠 Deep Orange = Net
- Pan with mouse drag, Zoom with scroll wheel.

**Step 3 — Wait for approval:**
The agent **MUST NOT** proceed to Rule 8 (Oracle Query) until the user explicitly approves the blueprint.
- **CRITICAL GATE:** Check the `RESULT: {"unresolved": N, "refs": [...]}` line printed by the visualizer. If `unresolved > 0` (or if the visualizer crashes without printing the line), the agent **MUST NOT** present the file to the user for approval. It must attempt to fix the YAML blueprint and re-run the visualizer **ONCE**. 
- If the warning persists after 1 retry, stop and report the exact missing `refs` list verbatim in the chat to the user so they can diagnose the hallucinated pads.
- If the user requests manual changes, regenerate the YAML (Rule 6) and re-run the visualizer.

---

## 🧠 RULE 8: AUTONOMOUS ORACLE QUERY
Before generating the final PCB layout Python script, the agent **MUST NOT guess or hallucinate** any KiCad 10 API method names or signatures. KiCad 10's Python API (SWIG bindings) differs significantly from KiCad 5/6/7. Your internal training data is likely outdated. The agent must autonomously query the KiCad API Oracle (`oracle.py`).

**Step 1: Analyze and Map Needed APIs**
The agent must act as a PCB Layout Automation Architect. It must analyze the YAML Blueprint and determine exactly which KiCad API actions are needed:
- **Footprints:** How to load them? How to set position/rotation?
- **Tracks/Vias:** How to create them, set start/end points, and set width?
- **Zones:** How to define boundaries and fill them?

**Step 2: Consult API Map & Query Oracle**
1. **Search the Index First:** Never guess method names! First, use `grep_search` or `view_file` on `API_method_names.md` or `all_functionName.md` located in the plugin folder. These markdown files act as a token-efficient map/index for the AI to find possible classes and methods.
2. **Query the Oracle:** Once you find a candidate method in the `.md` index, verify it by using the `run_command` tool to pipe the class/method names directly into `oracle.py` using a PowerShell Here-String. **Always use `--batch` mode via standard input** to look up multiple methods at once. This confirms the exact live signature from KiCad 10 and saves tokens.

```powershell
@'
PCB_TRACK SetStart
PCB_TRACK SetEnd
BOARD Add
FOOTPRINT SetPosition
ZONE_FILLER Fill
GLOBAL ToMM
'@ | python <PLUGIN_DIR>\oracle.py --batch
```

**Step 3: Parse and Apply Strict Signatures**
The agent must read the standard output returned by `oracle.py`. 
- The Oracle automatically handles single and multiple inheritance (e.g., checking `EDA_ITEM` or `EDA_TEXT` base classes), so the output you receive is the absolute source of truth.
- **SWIG Memory Safety Rule:** Always prefer high-level Python wrappers (like `Add()`) over raw C++ methods (`AddNative()`) when inserting objects into the board to prevent segfaults.
- If a method is missing or unclear in the Oracle's output, the agent must refine its query and run `oracle.py` again. It must **never** proceed with unverified methods.

---

## ⚙️ RULE 9A: SKELETON GENERATION
Using the YAML Blueprint (Rule 6), Discovered Pins/Footprints (Rule 5), and Verified API methods (Rule 8), the agent generates the initial Python script to load components and define nets.

The agent MUST:
1. **Draw the board outline** on the Edge.Cuts layer using dimensions from `board_config` in the YAML.
2. **Set the copper layer count** from `board_config.layers`.
3. **Load all footprints** from the local library.
4. **Apply reference designators** via `fp.SetReference("U1")` using the `ref:` field from the YAML. This is **mandatory** — the autoplacer uses KiCad refs (`U1`, `C1`, `J1`), not semantic IDs (`MCU1`).
5. **Set rough initial positions** on a grid. (Note: Do not use legacy unit conversions like `Millimeter2iu`. Always use `pcbnew.FromMM()`).
6. **Create all nets** from the YAML (`NETINFO_ITEM`) and assign pads to their respective nets.
7. DO NOT route traces yet.

**YAML to KiCad Net Mapping Logic:**
The agent must extract nets from the YAML blueprint using the following logic to create `NETINFO_ITEM`s and assign pads:

| YAML Section | How to generate the net |
|---|---|
| `power_distribution.<net_name>` | Net `<net_name>` → members: `[source] + [connections]` |
| `signal_routing.digital_signals[i]` | Net `digital_sig_<i>` → members: `[source, destination]` |
| `signal_routing.analog_signals[i]` | Net `analog_sig_<i>` → members: `[source, destination]` |
| `signal_routing.pwm_signals[i]` | Net `pwm_sig_<i>` → members: `[source, destination]` |
| `signal_nets[i]` | Net `<net_name>` → members: `[members]` |
| `communication_buses.<bus_type>[i].<line>`| Net `<bus_type><id>_<line>` → members: `[source] + [destinations]` |

To execute the script safely in KiCad's live memory (and to understand Watchdog limits), the agent **MUST** read `references/bridge_api_manual.md`.

**Correct Method (PowerShell Heredoc):**
```powershell
@'
import pcbnew
board = pcbnew.GetBoard()

# ... draw board outline, load footprints, SetReference for each,
#     create NETINFO_ITEMs, assign pads to nets ...

board.BuildConnectivity()
pcbnew.Refresh()
pcbnew.SaveBoard(board.GetFileName(), board)
print("Skeleton generated directly in KiCad memory! Ratsnest is now visible.")
'@ | python <PLUGIN_DIR>\kicad_agent_bridge.py --stdin --timeout 60
```

The agent MUST wait for the user to confirm the ratsnest looks correct in KiCad before proceeding.

---

## ✅ RULE 9A.5: NETLIST VERIFICATION (§1.4)
After Rule 9A completes, the agent MUST verify the skeleton by fetching the board state and checking:
1. Every net defined in the YAML exists on the board (`board.GetNetsByName()`).
2. Every pad assignment is correct (expected pad count per net).
3. All reference designators match the YAML `ref:` fields.

If any mismatch is found, report it to the user and halt. Do NOT proceed to 9B with a broken skeleton.

---

## ⚙️ RULE 9B: AUTO-PLACEMENT
Once the skeleton is approved, the agent:
1. Reads `references/design_rules.md` to understand placement best practices.
2. Generates `<PROJECT_DIR>/placement_constraints.yaml` using the schema from `references/autoplacement_template.yaml`. The YAML uses **KiCad reference designators** (`U1`, `C1`, `J1`), NOT semantic IDs.
3. Runs the autoplacer engine via the bridge with an explicit YAML path and extended timeout:

```powershell
@'
import importlib
import autoplacer_engine
importlib.reload(autoplacer_engine)
result = autoplacer_engine.run_physics_placer(yaml_path=r"<PROJECT_DIR>\placement_constraints.yaml")
import pcbnew
pcbnew.GetBoard().BuildConnectivity()
pcbnew.Refresh()
pcbnew.GetBoard().Save()
print("Auto-placement complete.")
'@ | python <PLUGIN_DIR>\kicad_agent_bridge.py --stdin --timeout 120
```

The agent MUST wait for the user to review the placement in KiCad. The user may manually adjust placement or ask the agent to rerun the placer.
- **CRITICAL GATE:** The `run_physics_placer()` script returns a JSON dict via standard output containing keys like `overlaps` and `outside_bounds`. If `overlaps > 0` or `outside_bounds > 0`, the agent **MUST NOT** present the placement for approval. It must attempt to fix `placement_constraints.yaml` and re-run the placer **ONCE**. If it fails again, stop and report the metrics to the user.

---

## ⚙️ RULE 9C: ROUTING (Future)
Once placement is locked, the agent generates the final routing script to draw traces, vias, and zones. (This phase will be defined later).

---

## 🔄 RULE 10: ITERATIVE DEVELOPMENT & STATE FETCHING
Complex PCBs cannot always be routed in a single shot. If the user requests modifications to an existing board or asks for step-by-step routing, you MUST fetch the current state of the board before generating new layout code.

**How to fetch state:**
Because execution is strictly stateless, you must run the pre-built `currentboardfetcher.py` script via `kicad_agent_bridge.py` to extract the full JSON state of the board.

**Command to run (Token-Efficient Summary):**
```powershell
@'
import currentboardfetcher as fetcher
import json
# Fetch the 'summary' mode to avoid blowing out token limits (hides track geometries)
ctx = fetcher.ai_context(mode="summary")
print(json.dumps(ctx, indent=2, default=fetcher.safe_json_default))
'@ | python <PLUGIN_DIR>\kicad_agent_bridge.py --stdin
```
*(Note: If you need to filter the output, you can pipe the output through `jq` or Python to extract only what you need).*

Read the JSON output to understand the board's current state, and ONLY THEN proceed to generate the next layout script following Rule 9.
