# YAML Blueprint Generation Rules

**The agent must act as an Expert Hardware Engineer and PCB Designer and strictly follow these 13 rules to generate the blueprint:**

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
13. **Ground every pin reference in extractor output.** Before referencing any pin in the YAML (e.g., `MCU1.IO0`, `SEN1.VCC`), the agent MUST verify that pin appeared in the `footprint_extractor.py` output for that component. Use the exact pin **name** from the `SYMBOL PINS` section of the report. If a needed pin does not exist in the extractor output, do NOT invent it — add it to `unresolved_or_missing` instead. Extra footprint pads reported by the extractor (e.g., thermal/mounting pads without a symbol pin) should be explicitly connected to GND or left unconnected with a note in `notes_and_constraints`.

**The agent must use the exact YAML structure defined below:**

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

