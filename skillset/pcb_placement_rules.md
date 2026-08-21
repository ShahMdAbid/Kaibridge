# 📐 Advanced PCB Placement & Hardware Architecture Rulebook

<aside>
🎯
**Doctrine, not suggestions.** This is the canonical, production-grade placement law for AI agents and human designers translating a schematic into a manufacturable, electrically robust PCB layout in **Kaibridge**. It is project-agnostic and vision-loop native: every rule states a *target*, a *tolerance*, and the *failure it prevents*, so it can be checked by geometry math, by a rendered snapshot, or by a human in one glance.
</aside>

**Version:** 2.0  
**Scope:** Every Kaibridge-driven board, any project.  
**Audience:** AI placement agents + human reviewers.  
**Rule of Engagement:** §0 governs how every conflict is resolved — read it before placing a single footprint.

---

## 🧠 0. Using This Rulebook

### 0.1 Normative Language
* **MUST / MUST NOT:** Hard constraint. A violation is a defect, not a trade-off. Block the commit.
* **SHOULD:** Strong default. Comply, or emit a written deviation.
* **MAY:** Discretionary optimization based on spatial constraints.

### 0.2 Rule IDs
Every rule carries a stable ID (e.g., `FP-04`, `PDN-07`, `DEC-02`). **AI Agents MUST cite these IDs** in their visual critique tables (Step 5 in `SKILL.md`) when suggesting corrective actions. 

### 0.3 The Precedence Ladder
When two rules collide, resolve strictly in this order. Higher tiers are never sacrificed for lower ones:
0. **Human Directives (Top Priority)** — Explicit user overrides, reference pictures, or layout requests (per `SKILL.md` Step 2).
1. **Safety & High-Voltage Isolation** — Keeping logically distinct or marked high-voltage zones physically separated.
2. **Mechanical Datums** — Immovable constraints: connectors on edges, mounting holes, board outline.
3. **Electrical Proximity** — Decoupling tightness, feedback node distance, clustering of associated components.
4. **Thermal Survival** — Heat spreading and separation of hot components.
5. **EMC Margin** — Keeping switching aggressors far from sensitive crystals or analog blocks.
6. **Manufacturability (DFM)** — Providing enough breathing room for the Geometry Gate to relax overlaps.
7. **Symmetry & aesthetics** — last, always. A beautiful layout that pushes a decoupling capacitor 6mm away is a **failed** layout.

### 0.4 Units & Coordinate Frame
* **Units:** Millimeters (`mm`).
* **Origin:** KiCad absolute coordinates (top-left is `0,0`, X increases right, Y increases down).
* **Rotation:** Counter-clockwise positive. Quantized to `0`, `90`, `180`, `270`.
* **Anchor:** Center (`"anchor": "centre"` in `ops.json`) by default.

---

## 🧭 1. General Board Topology & Floorplanning

### 1.1 Preflight & Net Classification (`IN`)
* `IN-01` **MUST** classify components by function before placement: 
  * High-current / Power $\rightarrow$ Cluster components tightly to allow the auto-router to draw short, wide copper fills.
  * Switching nodes (aggressors) $\rightarrow$ Group tightly and isolate from sensitive areas.
  * Feedback / Crystals (victims) $\rightarrow$ Place immediately adjacent to their target pins, positioned such that the main IC's physical body acts as a wall blocking direct line-of-sight to switching aggressors.

### 1.2 Signal Flow & Zoning (`FP`)
* `FP-01` **The Anchor-Flow Rule:** Identify the immovable mechanical datums (e.g., Power input connector, Output headers) and arrange the internal functional blocks in a direct spatial path between them (Power $\rightarrow$ Regulation $\rightarrow$ Processing $\rightarrow$ Output).
* `FP-02` **No Back-flow:** Place components such that the logical circuit flow progresses in one direction without doubling back.
* `FP-03` **The Core-and-Shell Heuristic:** Connectors and high-power switching form the outer shell (perimeter) for physical access and thermal dissipation. Sensitive intelligence (MCUs, ADCs) and their precise orbits form the protected inner core.
* `FP-04` **The Orbit Rule:** Group components by functional sub-circuit. Define a central focal point for each sub-circuit (e.g., the primary IC) and place related passives in a tight spatial orbit around it.

### 1.3 Mechanical Datums (`MECH`)
* `MECH-01` Place mounting holes at the corners, offset inward by at least their keepout radius (e.g., $X=5\text{mm}, Y=5\text{mm}$) so they do not fracture the board outline.
* `MECH-02` **Mounting Keep-Out Math:** The center coordinate of any component MUST be at least $2.5\text{mm} + (\text{ComponentDimension}/2)$ away from the center of a mounting hole to prevent the screw head from crushing it.
* `MECH-03` **Edge Clearance:** Because of center-anchors, a component's center coordinate MUST be at least $(Width/2) + 1.0\text{mm}$ away from any board outline to prevent physical edge collisions.

---

## 🔌 2. Component Class Rules

### A. Connectors & External Interfaces (`CON`)
* `CON-01` MUST be placed strictly along the outer perimeter.
* `CON-02` Mating face MUST face outward. Since `ops.json` uses center-anchors, calculate the geometric offset (e.g., $X = \text{BoardEdge} \pm (\text{Width} / 2)$) to ensure the connector sits flush *inside* the outline, rather than hanging halfway into thin air.
* `CON-03` **Cable Overmold Clearance:** Leave an unobstructed $\ge 3\text{mm}$ keep-out zone immediately behind and beside manually mated connectors to accommodate thick cable plugs and human fingers.

### B. Circuit Protection (`PRO`)
* `PRO-01` **Line-of-Sight Blocking:** To force the auto-router to hit protection devices (TVS/ESD) first, place them physically intersecting the direct straight-line path between the connector and the internal IC.
* `PRO-02` Distance between the connector and its protection device MUST be $\le 5\text{mm}$.

### C. Power Delivery & Thermals (`PDN` / `THM`)
* `PDN-01` Position high-current components near power inputs.
* `PDN-02` **The Hot Loop:** Keep SMPS commutating loops as tight as physically possible. The input capacitor MUST be placed immediately adjacent to the IC's VIN/GND pins (courtyards almost touching).
* `THM-01` Linear regulators (TO-220, DPAK) and MOSFETs MUST have adequate empty space reserved around them so the global ground pour can reach their thermal pads.
* `THM-02` **TO-220 Rule:** The metal heatsink tab MUST face outward toward the board edge. Never point tabs inward toward heat-sensitive components (electrolytic caps, oscillators).
* `THM-03` Distribute heat-generating components. Do not cluster power ICs tightly in one area; separate them to distribute the thermal load.

### D. Decoupling & High-Frequency Bypassing (`DEC`)
* `DEC-01` **The Golden Rule:** Decoupling capacitors MUST physically hug the IC pins they protect.
* `DEC-02` High-frequency ceramic bypass ($0.1\mu\text{F}$ / $100\text{nF}$) MUST be within **1.0mm - 2.5mm** of the VCC/GND pin pair.
* `DEC-03` **Line-of-Sight Blocking:** Place decoupling capacitors so they physically block the direct straight-line path from the power source to the IC pin, forcing the auto-router to naturally route through the capacitor pads.
* `DEC-04` Bulk storage (10-100$\mu\text{F}$ electrolytics) can be $\le 15\text{mm}$ from the rail entry.

### E. Oscillators & Clocks (`OSC`)
* `OSC-01` Place as close as physically possible to the MCU's XTAL/OSC pins (target $\le 5\text{mm}$).
* `OSC-02` Load capacitors sit *between* the crystal and the MCU. Load-cap positions MUST be symmetric.
* `OSC-03` Keep-out: Do not place fast digital ICs or high-current components near a crystal.

### F. Feedback & Precision Passives (`FBK` / `ANA`)
* `FBK-01` **Voltage Dividers:** For adjustable regulators, feedback resistors MUST be immediately adjacent ($\le 5\text{mm}$) to the `FB`/`ADJ` pin.
* `FBK-02` Current limiting / pull-ups: Place in-line with the signal path (e.g., right next to the LED).
* `ANA-01` Analog and Digital zones MUST be physically partitioned. Group them in entirely separate board areas to prevent the auto-router from mixing their traces.

---

## 📐 3. Symmetry & Multi-Channel Design (`SYM`)
* `SYM-01` **The Copy-Paste Rule:** Repeating identical circuits (e.g., multi-channel ADCs or stereo amplifiers) MUST reflect exact physical symmetry. Calculate standard offsets (e.g., $\Delta X = 10\text{mm}$) when generating their coordinates in `ops.json`.
* `SYM-02` Maintain orientation across replicated channels. Do not assign inverted rotations to a replicated channel unless explicitly required.
* `SYM-03` Align similar components on a common grid axis (e.g., all pull-up resistors in a neat row).
* `SYM-04` Standardize orientations to prevent assembly errors (e.g., all polarized diodes facing the same way).

---

## 🏭 4. DFM (Design for Manufacturing & Assembly) (`DFM`)
* `DFM-01` **Collision Awareness:** The Geometry Gate strictly rejects any overlapping placement. The AI MUST calculate nominal coordinates with enough breathing room to pass on the first attempt. Rely on the 0.5mm grid-snap to eliminate decimal noise — but the agent owns the spatial math.
* `DFM-02` Be mindful of Z-axis height. Do not hide low-profile SMD components underneath large overhanging components.
* `DFM-03` **Routing Corridors:** Leave unobstructed visible avenues ($\ge 2.5\text{mm}$) between dense components and headers to prevent auto-router chokepoints.

---

## 🤖 5. The Kaibridge Execution Protocol

When an AI agent executes placement:
1. The AI calculates nominal coordinates based on these rules, injecting exact symmetry (`SYM-01`) and semantic alignment.
2. The AI writes `ops.json` using `{"op": "footprint.place", "ref": "...", "x": ..., "y": ..., "rotation": ...}`.
3. **Grid-Snap:** The bridge automatically quantizes all `footprint.place` and `footprint.move` coordinates to a **0.5mm grid** before applying them. This eliminates micro-overlap decimal noise without moving components in unpredictable ways. Override per-op with `"grid": 0.25` (finer) or `"grid": 0` (disable).
4. The bridge executes `apply_ops` with `--commit`.
5. **The Geometry Gate:** The built-in solver strictly evaluates courtyard collisions and layout boundaries to enforce 100% legal, zero-overlap positions. Collisions result in immediate rejection, requiring an explicit, geometry-verified fix in the next `ops.json` generation.
6. **The Vision Gate:** The AI verifies the layout by analyzing the SVG generated by `pcb_snapshot.py`, citing rule IDs (e.g., `DEC-02`, `THM-02`) in its structured feedback table if corrections are needed.

---

## 📊 Appendix A — Numeric Constraint Target Reference

| Constraint | Target | Rule ID |
| --- | --- | --- |
| HF decap (100nF) to its power pin | 1.0–2.5 mm | `DEC-02` |
| Bulk cap to rail entry / regulator out | ≤ 15 mm | `DEC-04` |
| SMPS input cap to VIN/PGND | Courtyards touching | `PDN-02` |
| Feedback divider net length | ≤ 5 mm | `FBK-01` |
| Crystal to XTAL pins | ≤ 5 mm | `OSC-01` |
| TVS/ESD device to connector pin | ≤ 5 mm | `PRO-02` |
| Courtyard to courtyard (SMD) | Breathing room | `DFM-01` |
| Component body to outline | 1.0 mm | `MECH-03` |
| Mounting-hole keep-out radius | 2.5 mm | `MECH-02` |
| Hot part to electrolytic / crystal | ≥ 10 mm | `THM-02` |

---

## 👁️ Appendix B — Vision QA Rubric (The Snapshot Review)

Geometry math proves legality (`--commit` passes); **vision proves sanity**. AI Agents MUST review the rendered SVG snapshot against these checks in order:

1. **Silhouette:** Does the board read as clean functional blocks, or confetti? (`FP-04`)
2. **Perimeter:** Are connectors on the edge, mating faces outward, unobstructed? (`CON-01`)
3. **Decoupling Halo:** Does every IC have small capacitors visibly hugging it? (`DEC-01`)
4. **Power Island:** Are the regulator, input cap, inductor, and output cap a tight cluster? (`PDN-02`)
5. **Crystal Island:** Is the crystal a compact triangle beside the MCU? (`OSC-01`)
6. **Rows & Rhythm:** Do repeated channels form a visually perfect array? (`SYM-01`)
7. **Orientation:** Do polarized components agree? (`SYM-04`)
8. **Thermal Distance:** Is anything hot sitting against an electrolytic or crystal? (`THM-02`)
9. **Escape Corridors:** Are there visible pathways between dense ICs for the auto-router? (`DFM-03`)

*When a check fails, the agent MUST report the Rule ID in the critique table and generate adjustment operations.*

---

## ⛔ Appendix C — Anti-Pattern Catalogue

Failures to spot during Vision QA:

| Visual Signature | Real-world Consequence | Rule ID |
| --- | --- | --- |
| Capacitors scattered in a neat row far from IC | Rail collapse, EMI | `DEC-01` |
| Crystal on the far side of the MCU | Oscillator fails to start or drifts | `OSC-01` |
| Feedback resistors near the output connector | Loop instability, oscillation | `FBK-01` |
| TVS diodes placed 15mm inside the board | ESD damage on first handling | `PRO-01` |
| Perfectly symmetric grid of EVERYTHING | Long critical nets hidden behind "beauty" | `0.3` |
| Connector rotated inward or mid-board | Unbuildable enclosure, bent cables | `CON-02` |
| TO-220 tab facing an electrolytic capacitor | Cooked capacitor, shortened life | `THM-02` |
| Hot parts clustered in one corner | Local hotspot, thermal failure | `THM-03` |
