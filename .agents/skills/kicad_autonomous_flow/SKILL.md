---
name: Autonomous KiCad PCB Generation (End-to-End)
description: End-to-end workflow protocol for generating KiCad projects using local libraries and YAML blueprints.
---

# AI Protocol: Autonomous KiCad PCB Generation (End-to-End)

**TARGET AUDIENCE:** AI Agents operating in the KiCad 10 environment (e.g., Antigravity).  
**OBJECTIVE:** 100% autonomous, zero-hallucination PCB generation using project-specific libraries, strict YAML blueprints, and runtime API verification.

---

## 🚫 RULE 1: STRICTLY NO GLOBAL LIBRARIES
Agents must **never** configure global footprint or symbol libraries in the user's `AppData` directory. All LCSC components must be downloaded directly into the current active KiCad project folder. This prevents naming collisions and cross-project hallucination.

---

## 🏗️ RULE 2: PROJECT INITIALIZATION PROTOCOL
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

## 📝 RULE 3: GENERATE BLUEPRINT (YAML)
Before importing parts or writing any KiCad layout code, the agent **MUST** generate a structured YAML `circuit_blueprint`. This YAML file acts as the single source of truth for the BOM (Bill of Materials) and Netlist.

**The agent must act as an Expert Hardware Engineer and PCB Designer and strictly follow these rules to generate the blueprint:**

1. **Reason normally, but label your reasoning.** Use your full engineering knowledge to fill in things that follow logically from what was discussed (e.g., if a specific sensor model is named, its standard voltage, output type, and typical wiring conventions are fair game). Don't hold back on legitimate inference.
2. **Only flag the genuine gaps:** Things that have no reasonable default and were never stated or implied (e.g., which analog pin a sensor is wired to, a custom-chosen wire color). For these, don't invent a specific answer — put them in `unresolved_or_missing`. Anything derived through normal engineering reasoning goes in `assumptions_and_gaps`.
3. **Final decisions only.** If the user changed their mind mid-conversation, use only the most recent/final version. If ambiguous, list the conflict in `unresolved_or_missing`.
4. **Consistent ID convention.** Prefix every component by type and number sequentially, starting at 1: `MCU`, `SEN`, `ACT`, `DRV`, `PSU`, `MOD`, `PAS`. Never reuse an ID. Passives follow this too — they are components with real pins, so wire them into signal_routing/power_distribution the same as any other part (e.g., `MCU1.D2 -> PAS1.1`, `PAS1.2 -> SEN1.IN`).
5. **Uniform structure everywhere.** Every connection must use structured key-value pairs — no inline arrow-strings like `"A -> B"` anywhere in the file. For point-to-point signals use `source`/`destination`. For bus lines, use `source`/`destinations` (plural, a list).
6. **Separate power rails unless proven joined.** Keep "5V" rails from different sources separate (e.g., `5V_USB_net`, `5V_EXT_net`) unless explicitly tied together.
7. **Self-check before output:** Scan for any MCU pin assigned to more than one purpose. If found, list it in `unresolved_or_missing`.
8. **No leftover placeholders.** Every example value (`null` or `"e.g., ..."`) must be fully replaced or explicitly nulled.
9. **Output format:** Respond with ONLY a single fenced YAML code block.
10. **Strict schema adherence.** Do not change the data type of any section. If it shows a list, output a list. If it shows a dictionary, output a dictionary. Do not invent new keys. Reference pins directly inside `source`/`destination`/`members` fields.
11. **Pin numbers, not function names.** When routing, the pin identifier must be the physical pin number/label (e.g., `DRV1.7`, `MCU1.D2`), not its internal function name. Put functions in the `purpose` field instead.
12. **Model shared junctions as nets, not chains.** If 3+ pins are tied together at one electrical junction, do NOT invent a fake sequential chain. List it under `signal_nets` as a single named node with all its members.

**The agent must use this exact YAML structure:**

```yaml
circuit_blueprint:
  metadata:
    project_name: null
    main_controller: null
    description: null

  components:
    MCU1: { type: "Microcontroller", model: null, lcsc_id: null }
    # One entry per discrete part, using the ID convention above

  passive_components:
    # Standalone resistors/capacitors/diodes NOT already inside a module.
    # This is a LIST (note the leading "-"). Each entry is a real component
    # with its own ID — wire its pins into signal_routing / power_distribution
    # / signal_nets like any other part (e.g., "PAS1.1" -> "DRV1.7").
    - id: "PAS1"
      type: "Resistor"
      value: null
      purpose: null
      lcsc_id: null

  power_distribution:
    # Keep rails from different physical sources separate (see Rule 6)
    GND_net:
      source: "MCU1.GND"
      connections: []
    5V_net:
      source: "MCU1.5V"
      connections: []

  signal_routing:
    # Use ONLY for genuine 2-pin, point-to-point connections.
    # If 3+ pins are tied together at one junction, do NOT chain them here —
    # use signal_nets below instead.
    analog_signals:
      - source: null
        destination: null
        purpose: null
    digital_signals:
      - source: null
        destination: null
        purpose: null
    pwm_signals:
      - source: null
        destination: null
        purpose: null

  signal_nets:
    # For any junction where 3+ pins are simply tied together (not a real
    # series path) — e.g., an RC timing node shared by two resistors and an
    # IC pin. Modeled the same way power_distribution handles GND/5V.
    - net_name: null
      members: []
      purpose: null

  communication_buses:
    # Bus lines can have MULTIPLE devices sharing the same SDA/SCL.
    # Always use "destinations" as a list.
    I2C:
      - bus_id: "I2C1"
        SDA: { source: "MCU1.A4", destinations: [] }
        SCL: { source: "MCU1.A5", destinations: [] }
    SPI: []
    UART: []

  notes_and_constraints:
    - null

  assumptions_and_gaps:
    # Anything you inferred rather than something explicitly stated (Rule 2)
    - null

  unresolved_or_missing:
    # Anything you couldn't determine, or genuine conflicts (Rules 1, 3, 7)
    - null
```

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
Before generating the final PCB layout Python script, the agent **MUST NOT guess or hallucinate** any KiCad 10 API method names or signatures. The agent must autonomously query the KiCad API Oracle (`oracle.py`).

**Step 1: Analyze and Map Needed APIs**
The agent must act as a PCB Layout Automation Architect. It must analyze the YAML Blueprint and determine exactly which KiCad API actions are needed:
- **Footprints:** How to load them? How to set position/rotation?
- **Tracks/Vias:** How to create them, set start/end points, and set width?
- **Zones:** How to define boundaries and fill them?

**Step 2: Consult API Map & Query Oracle**
1. First, consult `API_method_names.md` (or search the workspace) to verify the method names exist in KiCad 10.
2. Then, use the `run_command` tool to pipe the verified class/method names directly into `oracle.py` using a PowerShell Here-String:

```powershell
@'
PCB_TRACK SetStart
PCB_TRACK SetEnd
BOARD Add
FOOTPRINT SetPosition
ZONE_FILLER Fill
'@ | python <PATH_TO_YOUR_PLUGIN>\oracle.py --batch
```

**Step 3: Parse and Apply Strict Signatures**
The agent must read the standard output returned by `oracle.py`. 
- The output contains the absolute source of truth for KiCad 10 C++ method signatures and docstrings.
- **SWIG Memory Safety Rule:** Always prefer high-level Python wrappers (like `Add()`) over raw C++ methods (`AddNative()`) when inserting objects into the board to prevent segfaults.
- If a method is missing or unclear in the Oracle's output, the agent must refine its query and run `oracle.py` again. It must **never** proceed with unverified methods.

---

## ⚙️ RULE 7: PCB SCRIPT EXECUTION
Using the YAML Blueprint (Rule 3), Discovered Footprints (Rule 5), and Verified API methods (Rule 6), the agent generates the final Python script.
- Execute this script via the abIDE socket bridge (`kicad_agent_bridge.py`).
- The script should place footprints, route tracks, generate planes, rebuild connectivity, and call `board.Save()`.
