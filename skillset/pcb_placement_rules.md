# 📐 Comprehensive PCB Placement Rules & Hardware Architecture Guide

This guide establishes the deterministic engineering rules that AI agents and human designers must follow when translating a schematic into a clean, manufacturable, and electrically sound PCB layout using **abIDE**.

---

## 🧭 1. General Spatial & Placement Strategy

When placing components from `ai_context_summary.json`:
1. **Determine Workspace Center & Board Envelope:**
   - Identify the target board dimensions (e.g., $60\text{mm} \times 40\text{mm}$).
   - Set the origin/center at the middle of the available coordinate space (e.g., $X=150, Y=100$).
2. **Flow Direction (Left-to-Right or Top-to-Bottom):**
   - **Input Section:** Left or Top edge.
   - **Processing / Regulation Section:** Center zone.
   - **Output / Actuation / Display Section:** Right or Bottom edge.

---

## 🔌 2. Component Class Rules

### A. Connectors & External Interfaces (`J`, `USB`, `CONN`, `TERMINAL`)
* **Placement Rule:** MUST be placed along the outer board boundaries.
* **Orientation:**
  * **DC Barrel Jack (`J6`):** Place on the left edge with opening facing outward (`rotation: 180`).
  * **USB Connectors (Type-C, Micro-B):** Outer perimeter, port mouth pointing outward (`rotation: 180` for left edge, `0` for right edge).
  * **Pin Headers / Terminal Blocks (`Conn_01x03`, Screw Terminals):** Top or bottom edge with pins easily accessible for wire insertion (`rotation: 90` or `270`).
* **Courtyard Clearance:** Keep at least $1.5\text{mm}$ to $2.0\text{mm}$ clearance around mounting holes or enclosure walls.

### B. Thermal & Power Components (`U`, `LM7805`, `LM317`, `TO-220`, `Diodes`)
* **Placement Rule:** Place power ICs and linear regulators along board edges for optimal heat dissipation and potential heatsink mounting.
* **Orientation:**
  * **TO-220 Package (e.g. `U2`, `LM7805`):** The metal heatsink tab MUST face outward toward the board edge (`rotation: 270` when placed on the top perimeter). Never point the heatsink tab inward toward sensitive passives!
  * **Power Diodes (`1N4007`, Schottky):** Keep inline between connector positive rail and regulator input pin.
* **Clearance:** Maintain $\ge 2.0\text{mm}$ clearance around TO-220 heatsink zones.

### C. Decoupling & Filter Capacitors (`C`, `0.1uF`, `10uF`, `100uF`)
* **Placement Rule:** Decoupling capacitors MUST be physically adjacent to the IC pins they protect.
* **Proximity Hierarchy:**
  1. **High-Frequency Ceramic Bypass ($0.1\mu\text{F}$ / $100\text{nF}$):** Place within $1.0\text{mm} - 2.5\text{mm}$ of the IC's $V_{IN}$ or $V_{CC}$ / $GND$ pin pair.
  2. **Bulk Electrolytic / Tantalum ($10\mu\text{F} - 470\mu\text{F}$):** Place immediately following the rectifier or regulator output stage.
* **Orientation:** Orient so the positive pad faces the incoming power rail and negative pad faces common GND.

### D. Resistors & Feedback Networks (`R`, `Dividers`, `Pull-ups`)
* **Placement Rule:** Feedback/voltage divider resistors (e.g., $R_1, R_3$ on adjustable regulators like LM317) must be placed directly next to the feedback/adjust pin to minimize parasitic trace capacitance and noise pickup.
* **LED Current Limiting Resistors:** Place inline between the IC/rail and the LED.

### E. User Interface Components (`SW`, `LED`, `POT`)
* **Placement Rule:** Must be located in accessible zones unobstructed by tall components (like electrolytic capacitors or TO-220 heatsinks).
* **Power Indicator LEDs:** Place near the output terminals or board corner where clearly visible.
* **Switches:** Place along the edge or front panel area.

---

## ⚡ 3. Netclasses & Track Widths

Always enforce netclass widths in `json2sch.py --apply-netclasses`:
* **`GND` (Ground Plane / Return):** $1.0\text{mm}$ width (or covered by Copper Pour zone).
* **`PWR` (Power Rails - +12V, +5V, +3V3, VBUS):** $0.8\text{mm} - 1.2\text{mm}$ width (depending on current).
* **`SIG` (Standard Signals / Feedback / Data):** $0.25\text{mm} - 0.30\text{mm}$ width.

---

## 🛡️ 4. The Zero-Overlap Protocol (abIDE Built-in Solver)

1. The AI calculates nominal coordinates with $1.0\text{mm} - 2.0\text{mm}$ inter-component spacing based on physical bounding boxes (`courtyard_mm.w`, `courtyard_mm.h`).
2. The AI writes `ops.json` using `"op": "footprint.place", "anchor": "centre"`.
3. The bridge executes `apply_ops` with `--commit`.
4. The built-in **Geometry Gate** automatically detects micro-collisions and performs physics relaxation (`geometry.separate()`) across up to 80 passes to snap components into 100% legal, zero-overlap positions.
5. The AI verifies with `pcb_snapshot.py` to confirm optimal aesthetic balance.
