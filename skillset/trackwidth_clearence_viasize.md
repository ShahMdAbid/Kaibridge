# Setting Track Width, Clearance, and Via Sizes in abIDE

The `abIDE` plugin relies on KiCad's **Netclasses** feature to automatically enforce track widths, clearances, and via sizes. You can declare these design specifications directly in your `design.json` file, and `abIDE` will inject them into your KiCad project.

## 1. Defining Netclasses in `design.json`

At the root level of your `design.json` file, create a `"netclasses"` object. Inside it, define your specific classes (e.g., `Default`, `Power`, `Signal`). 

You can specify the following parameters (in millimeters):
- `clearance`: The minimum distance between this net and other copper items.
- `track_width`: The thickness of the traces.
- `via_diameter`: The total diameter of the via pad.
- `via_drill`: The size of the drilled hole in the via.

Next, assign these classes to specific nets within the `"nets"` object using the `"class"` attribute.

### Example Configuration:
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
      "track_width": 0.8,
      "via_diameter": 1.0,
      "via_drill": 0.6
    }
  },
  
  "nets": {
    "+5V": {
      "class": "Power"
    },
    "GND": {
      "class": "Power"
    },
    "OUT1": {
      "class": "Default"
    }
  },
  
  "parts": { ... },
  "groups": [ ... ]
}
```

## 2. Applying Netclasses to the KiCad Project

To inject these specifications into your project, you must use the `--apply-netclasses` flag when running the schematic generator script (`json2sch.py`).

**Command:**
```powershell
python "json2sch.py" "<PROJECT_DIR>" "<PROJECT_DIR>\design.json" --apply-netclasses
```

### ⚠️ CRITICAL WARNING: Close KiCad Before Running!
The `--apply-netclasses` flag writes these rules directly into the `.kicad_pro` (KiCad Project) file on disk. 
**You MUST completely close KiCad before running this command.** If KiCad is open, it holds the project file in memory and will overwrite your injected rules when you exit or save.

## 3. Downstream Effects
Once successfully applied:
1. When you open KiCad and press **F8** (Update PCB from Schematic), KiCad will automatically associate `+5V` and `GND` with the 0.8mm track width rules, and `OUT1` with the 0.25mm rule.
2. When you run **FreeRouting** headless, the autorouter natively reads these netclass constraints from the exported `.dsn` file and draws traces matching your exact size specifications.

Valid netclass keys: `clearance`, `track_width`, `via_diameter`, `via_drill`, `uvia_diameter`, `uvia_drill`, `diff_pair_width`, `diff_pair_gap`, `wire_width`, `bus_width`, `line_style`, `schematic_color`, `pcb_color`, `priority`, `description`. Anything else is ignored with a warning by `--apply-netclasses`.
