---
name: Autonomous KiCad PCB Generation
description: End-to-end workflow protocol for generating KiCad projects using local libraries and YAML blueprints.
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
1. Create or update an artifact named `task.md` using the `write_to_file` tool.
2. List out the steps clearly (e.g. Generate Blueprint, Query Oracle, Write Code).
3. Update the checklist (`[ ]` to `[x]`) as you progress through the workflow. Do NOT proceed to the next step until the current one is validated.

---

## 📝 RULE 3: GENERATE BLUEPRINT (YAML)
Before importing parts or writing any KiCad layout code, the agent **MUST** generate a structured YAML `circuit_blueprint`. This YAML file acts as the single source of truth for the BOM (Bill of Materials) and Netlist.

**To generate this blueprint correctly, the agent MUST read and strictly follow the 12 expert engineering rules and the exact YAML structure defined in `references/yaml_generation_rules.md`.**

---

## 📥 RULE 4: LCSC COMPONENT IMPORT PROTOCOL
Extract the required LCSC IDs from the YAML Blueprint and import the physical assets directly into the project directory using `run_command`.

**Command Structure:**
```bash
mkdir -Force "<PROJECT_DIR>/libs/easyeda2kicad"
easyeda2kicad --lcsc_id <LCSC_ID_1> <LCSC_ID_2> --full --output "<PROJECT_DIR>/libs/easyeda2kicad"
```
*Note: You must manually create the `libs/easyeda2kicad` directory using `mkdir` before running `easyeda2kicad`, otherwise it will fail with a folder not found error.*

---

## 🔍 RULE 5: COMPONENT DISCOVERY (ANTI-HALLUCINATION)
After a successful import, the agent must **never guess** the generated KiCad footprint names. To map the YAML components to physical KiCad footprints, execute the following Python snippet:

```python
import os
import glob

pretty_dir = r"C:\Path\To\NewProject\libs\easyeda2kicad\easyeda2kicad.pretty"
footprints = [os.path.splitext(os.path.basename(f))[0] 
              for f in glob.glob(os.path.join(pretty_dir, "*.kicad_mod"))]

for fp in footprints:
    print(f"Discovered Footprint: {fp}")
```
*Use the exact strings printed by this script for all subsequent placement instructions.*

---

## 🧠 RULE 6: AUTONOMOUS ORACLE QUERY
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
'@ | python <PATH_TO_YOUR_PLUGIN>\oracle.py --batch
```

**Step 3: Parse and Apply Strict Signatures**
The agent must read the standard output returned by `oracle.py`. 
- The Oracle automatically handles single and multiple inheritance (e.g., checking `EDA_ITEM` or `EDA_TEXT` base classes), so the output you receive is the absolute source of truth.
- **SWIG Memory Safety Rule:** Always prefer high-level Python wrappers (like `Add()`) over raw C++ methods (`AddNative()`) when inserting objects into the board to prevent segfaults.
- If a method is missing or unclear in the Oracle's output, the agent must refine its query and run `oracle.py` again. It must **never** proceed with unverified methods.

---

## ⚙️ RULE 7: PCB SCRIPT EXECUTION 
Using the YAML Blueprint (Rule 3), Discovered Footprints (Rule 5), and Verified API methods (Rule 6), the agent generates the final Python script.

To execute the script safely in KiCad's live memory (and to understand Watchdog limits), the agent **MUST** read `references/bridge_api_manual.md`.

**Correct Method (PowerShell Heredoc):**
```powershell
@'
import pcbnew
board = pcbnew.GetBoard()

# ... place footprints, route tracks, generate planes, rebuild connectivity ...

board.Save()
print("Executed directly in KiCad memory!")
'@ | python kicad_agent_bridge.py --stdin
```

---

## 🔄 RULE 8: ITERATIVE DEVELOPMENT & STATE FETCHING
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
'@ | python kicad_agent_bridge.py --stdin
```
*(Note: If you need to filter the output, you can pipe the output through `jq` or Python to extract only what you need).*

Read the JSON output to understand the board's current state, and ONLY THEN proceed to generate the next layout script following Rule 7.

