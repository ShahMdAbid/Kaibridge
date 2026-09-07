# Handling Stacked Symbol Pins & Multi-Pad Connections in Kaibridge `design.json`

When defining nets in `design.json`, understand the critical distinction between **schematic visual pins** and **physical PCB footprint pads**.

---

## 1. The Issue: Schematic Stacking vs. Physical Footprints

Certain components have multiple physical pins for power, ground, or shielding:
- **USB-C Receptacles:** Mirrored ground contacts (`A1`, `B12`, `A12`, `B1`), VBUS contacts (`A4`, `B9`, `A9`, `B12`), and shield/chassis pads (`SH`, `SH1`, `SH2`).
- **Microcontrollers:** Multiple `GND` or `VDD` pins across package corners.
- **Transistors / Regulators:** Heatsink tabs sharing pad numbers or electrical nets.

### Schematic Level:
In some symbol libraries, redundant ground/power pins are drawn directly on top of each other at identical X/Y coordinates. Declaring multiple overlapping pins at the exact same schematic coordinate can produce stacked visual labels.

### PCB Layout Level:
On the physical PCB, **every single copper pad must have its net assigned**. If a secondary ground pad (such as `B12` on a USB-C connector) is omitted from net connections and not aliased, it will remain floating in the PCB, creating unrouted airwires and failing DRC.

---

## 2. The Solution & Best Practices

1. **Explicit Pad Connections:**
   In `design.json`, ensure all physical terminals requiring copper connection are declared in `"connections"`. For USB-C connectors with distinct pads (`A1`, `B12`, `A12`, `B1`), declare the pads or use composite aliases:
   ```json
   "GND": {
     "connections": ["J1.A1", "J1.B12", "J1.A12", "J1.B1", "U1.1", "C1.2"]
   }
   ```

2. **Composite Alias Support in `sync.py`:**
   Kaibridge's PCB synchronizer (`kaibridge/pcb/sync.py`) automatically matches exact pad numbers as well as composite aliases (e.g. declaring `"J1.A1/B12"` will automatically bind both physical pad `A1` and physical pad `B12` on the footprint).

3. **Shield & No-Connect Pins:**
   Unused or chassis shield pads (e.g. `J1.SH`, `J1.SH1-SH4`) must be explicitly declared in `"no_connect"` if left unconnected to prevent dangling pad warnings:
   ```json
   "no_connect": ["J1.SH"]
   ```

4. **Verify via DRC:**
   After syncing the PCB and routing, always run `kicad_route.py --drc` or `python kicad_drc.py`. Any missed physical pads will be caught immediately as `unconnected_items`.
