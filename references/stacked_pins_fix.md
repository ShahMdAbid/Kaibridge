#Handling Stacked Symbol Pins in Kaibridge 2.0 `design.json`

When defining nets in `design.json`, **do not list multiple pins for a component if those pins are physically stacked (share identical coordinates) in the KiCad symbol.**

---

##The Issue

Certain official KiCad symbols (such as microcontrollers or USB connectors) have multiple identical power or ground pins:
- Example: `GND` on pins 3, 5, 21 for ATmega328P-PU
- Example: `GND` on A1, A12, B1, B12 for USB-C Type-C connectors
- Example: Shield/shell pins on mechanical connectors

In many symbol libraries, these redundant power/ground pins are drawn directly on top of each other at identical X/Y coordinates to save visual space.

If you list all stacked pins in a net array inside `design.json`:
```json
"GND": [
  "U1.3",
  "U1.5",
  "U1.21"
]
```
The schematic compiler (`json2sch.py` or `kaibridge_build_schematic`) attaches a net label to each declared pin coordinate. When pins share the exact same location, labels overlap on top of each other, cluttering the schematic visual and triggering potential label collision warnings.

---

##The Solution

**Specify only the single visible primary pin** in `design.json`:

```json
"GND": [
  "U1.3",
  "C1.2",
  "J1.1"
]
```

###Why This Works:
1. **Schematic Cleanliness:** KiCad renders one clean, readable net label at pin 3 without overlapping text.
2. **Internal Net Connection:** KiCad's symbol definition automatically associates the stacked pins internally. When `kicad_pcb_sync.py` (or `kaibridge_sync_to_pcb`) generates `.kicad_pcb`, all physical footprint pads (e.g. pads 3, 5, and 21) are correctly connected to `GND`.
3. **Zero ERC Violations:** Headless ERC verifies that the power net is driven and continuous without duplicate pin errors.
