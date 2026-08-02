# YAML Blueprint Generation Rules

**The agent must act as an Expert Hardware Engineer and PCB Designer and strictly follow these rules to generate the blueprint:**

1. **Reason normally, but label your reasoning.** Use your full engineering knowledge to fill in things that follow logically from what was discussed (e.g., if a specific sensor model is named, its standard voltage, output type, and typical wiring conventions are fair game). Don't hold back on legitimate inference.
2. **Only flag the genuine gaps:** Things that have no reasonable default and were never stated or implied. For these, don't invent a specific answer — put them in `unresolved_or_missing`. Anything derived through normal engineering reasoning goes in `assumptions_and_gaps`.
3. **Final decisions only.** If the user changed their mind mid-conversation, use only the most recent/final version. If ambiguous, list the conflict in `unresolved_or_missing`.
4. **Consistent ID convention.** Prefix every component by type and number sequentially, starting at 1: `MCU`, `SEN`, `ACT`, `DRV`, `PSU`, `MOD`, `PAS`. Never reuse an ID. Passives follow this too.
5. **Uniform structure everywhere.** Every connection must be defined in the flat `nets` dictionary mapping a net name to a list of connected pins. Do not use inline arrow-strings like `"A -> B"`.
6. **Separate power rails unless proven joined.** Keep "5V" rails from different sources separate (e.g., `5V_USB_net`, `5V_EXT_net`) unless explicitly tied together.
7. **Self-check before output:** Scan for any MCU pin assigned to more than one purpose. If found, list it in `unresolved_or_missing`.
8. **No leftover placeholders.** Every example value (`null` or `"e.g., ..."`) must be fully replaced or explicitly nulled.
9. **Output format:** When *emitting the blueprint*, respond with ONLY a single fenced YAML code block. Other conversation messages (e.g. approval requests, task updates) are normal text.
10. **Strict schema adherence.** Use the simple unified `nets` dictionary schema required by `blueprint_to_sch.py`. Do not invent new keys.
11. **Pad numbers, not function names.** When routing, the pin identifier must be the physical pad number (e.g., `DRV1.7`, `MCU1.15`), not its internal function name. Use the pad numbers from the `FOOTPRINT PADS` section of the extractor output.
12. **Model shared junctions as nets, not chains.** All connected pins (2 or more) form a single list under their respective net name in `nets`. Do not invent fake sequential chains.
13. **Ground every pin reference in extractor output.** Before referencing any pin in the YAML (e.g., `MCU1.15`), the agent MUST verify that the **pad number** appeared in the `FOOTPRINT PADS` section of the `footprint_extractor.py` output. Extra footprint pads (e.g., thermal pads) should be explicitly connected to GND or left unconnected with a note.
14. **Always request board configuration.** The agent MUST ask the user for board dimensions (width/height in mm) and layer count (2 or 4) if they are not provided.

**The agent must use the exact YAML structure defined below:**

```yaml
circuit_blueprint:
  metadata:
    project_name: null
    main_controller: null
    description: null

  board_config:
    outline:
      shape: "rectangle"
      width_mm: null
      height_mm: null
      corner_radius_mm: 0
    layers: 2
    design_rules:
      trace_width_mm: 0.25
      clearance_mm: 0.2
      via_drill_mm: 0.3
      via_diameter_mm: 0.6
      power_trace_width_mm: 0.5

  components:
    MCU1:
      type: "Microcontroller"
      model: null
      lcsc_id: null
      ref: "U1"        # KiCad reference designator — MANDATORY
    # One entry per discrete part, using the ID convention above
    # Every component MUST have a `ref:` field with a unique KiCad designator
    PAS1:
      type: "Resistor"
      value: "10k"
      lcsc_id: null
      ref: "R1"

  nets:
    # A simple dictionary mapping net names to lists of connected pins.
    # Use PAD NUMBERS (e.g., MCU1.15), not function names.
    GND:
      - "MCU1.15"
      - "PAS1.1"
    5V:
      - "MCU1.19"
    I2C1_SDA:
      - "MCU1.21"
      - "SEN1.3"

  notes_and_constraints:
    - null

  assumptions_and_gaps:
    - null

  unresolved_or_missing:
    - null
```
