#Setting Track Width, Clearance, and Via Sizes in Kaibridge 2.0

Kaibridge 2.0 leverages KiCad's **Netclasses** feature to automatically enforce trace widths, clearances, and via sizes. You declare these specifications declaratively in `design.json`, and the Kaibridge engine automatically injects them into your KiCad project (`.kicad_pro`) and enforces them through routing.

---

##1. Defining Netclasses in `design.json`

At the root level of your `design.json`, define the `"netclasses"` dictionary. Inside it, declare custom classes (e.g., `Default`, `Power`, `HighSpeed`):

```json
{
  "netclasses": {
    "Default": {
      "clearance": 0.2,
      "track_width": 0.25,
      "via_diameter": 0.8,
      "via_drill": 0.4
    },
    "Power": {
      "clearance": 0.3,
      "track_width": 0.6,
      "via_diameter": 1.0,
      "via_drill": 0.5
    }
  },
  
  "nets": {
    "+5V": {
      "class": "Power"
    },
    "GND": {
      "class": "Power"
    },
    "SIG_OUT": {
      "class": "Default"
    }
  }
}
```

###Supported Netclass Properties (all dimensions in mm):
- `clearance`: Minimum electrical clearance between this net and other copper elements (default `0.2`).
- `track_width`: Trace thickness for routing (e.g. `0.25` for signals, `0.5`–`0.8` for power).
- `via_diameter`: Total outer diameter of via annular ring (e.g. `0.8`).
- `via_drill`: Drill diameter for via hole (e.g. `0.4`).
- `diff_pair_width`, `diff_pair_gap`: Differential pair routing rules.

---

##2. Automated Pipeline Injection

In Kaibridge 2.0, you do **not** need to run manual CLI commands or remember flags:

1. **Automatic Project Sync:**  
   When compiling `design.json` via `json2sch.py --apply-netclasses` (or `kaibridge_build_schematic`), the compiler automatically updates the KiCad project file (`.kicad_pro`) with your `netclasses` and `netclass_patterns`.
2. **Headless PCB Sync:**  
   `python kicad_pcb_sync.py` (or `kaibridge_sync_to_pcb`) syncs the schematic netlist into `.kicad_pcb` without opening the KiCad GUI, binding all netclass assignments directly to the copper ratsnest.
3. **Pre-Flight DSN Audit:**  
   When running `python kicad_route.py` (or `kaibridge_route_pcb`), the engine executes a pre-flight audit on the exported Specctra `.dsn` in < 2ms, verifying that all power and signal nets have valid track widths > 0 and correct clearances before handing off to Freerouting 2.4.1.
4. **Freerouting 2.4.1 Compliance:**  
   Freerouting strictly honors the netclass rules from the DSN file, routing power nets with thick traces (`0.6mm`+) and signals with clean nominal traces (`0.25mm`).
