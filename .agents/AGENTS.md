# Hardware Synthesis Directive (Kaibridge 3.0 Executive Router)

For any hardware design, schematic, placement, routing, or KiCad task in this workspace, you MUST strictly adhere to this fail-closed synthesis protocol:

---

## ⚡ Ground-Truth Pipeline (11 Steps & 4 Mandatory Human Gates)

```
[Prompt] ➔ Step 0: Bootstrap ➔ Step 1: Wishlist ➔ Step 2: Source ➔ Step 3: Pin Extraction
   │
   ▼
🛑 HUMAN GATE 1: Architecture & Sourcing Blueprint Sign-off (Step 4)
   │ (Pause for explicit user confirmation before writing design.json)
   ▼
Step 5: Write design.json ➔ Step 6: Compile Schematic & ERC (json2sch.py --erc --svg --netlist)
   │
   ▼
🛑 HUMAN GATE 2: Schematic, Netlist & ERC Review (Post Step 6)
   │ (Present SVG preview, XML netlist, BOM CSV, 0 ERC errors; pause for approval)
   ▼
Step 7: Sync PCB (kicad_pcb_sync.py) ➔ Step 8: Placement & 9-Angle 3D Snapshot (pcb_snapshot.py --inspect --3d)
   │
   ▼
🛑 HUMAN GATE 3: 3D Mechanical Freeze & Routing Speed Selection (Step 9A)
   │ (Present dual_view.png & 3d_views; ask connector orientation, RF keepout, routing mode)
   ▼
Step 9B: ISRRO-X Optimizer ➔ Step 10: Headless Route (kicad_route.py) & Ground Plane
   │
   ▼
🛑 HUMAN GATE 4: Pre-Production & Manufacturing Sign-off (Step 11)
   │ (Present 0-error DRC, copper render, gerbers.zip, BOM/CPL CSVs before ordering)
   ▼
[Factory Release to JLCPCB]
```

---

## 🛠️ Inlined CLI Command Cheat-Sheet (Never Guess or Hallucinate)

| Step | Unified CLI (`kaibridge <cmd>`) | Python Script Wrapper | Purpose |
|---|---|---|---|
| **Step 0** | `kaibridge init "projects/<NAME>"` | `python kicad_lib_init.py "projects/<NAME>"` | Creates `.kicad_pro`, `.kicad_pcb`, `.kicad_sch`, sym/fp lib tables |
| **Step 1** | `kaibridge check <C_ID> [C_ID ...]` | `python -m kaibridge.sourcing.check_cli <C_ID>` | Query live JLCPCB stock, Basic/Extended SMT fee, & datasheets |
| **Step 2** | `kaibridge fetch <C_ID> [C_ID ...]` | `python -m kaibridge.sourcing.jlc_api <C_ID>` | Ingest modern KiCad 10 CAD via JLC2KiCadLib (auto-fallback) |
| **Step 2B**| `kaibridge 3d "projects/<NAME>"` | `python kicad_3d.py "projects/<NAME>"` | Download 3D STEP/WRL models with rate pacing |
| **Step 3** | `kaibridge pins "projects/<NAME>" <PART> --save-json` | `python kicad_pins.py "projects/<NAME>" <PART>` | Extract real hardware pins, numbers & types |
| **Step 6** | `kaibridge build "projects/<NAME>" --erc --svg` | `python json2sch.py "projects/<NAME>" --erc --svg` | Compile schematic, netclasses, netlist XML, BOM & vector SVG |
| **Step 7** | `kaibridge sync "projects/<NAME>"` | `python kicad_pcb_sync.py "projects/<NAME>"` | Reconcile netlist directly into PCB layout |
| **Step 8** | `kaibridge layout "projects/<NAME>"` | `python kicad_layout.py "projects/<NAME>"` | Execute algorithmic / `ops.json` placement |
| **Step 8F** | `kaibridge snapshot "projects/<NAME>" --inspect --3d` | `python pcb_snapshot.py "projects/<NAME>" --inspect --3d` | Render HUD component map, dual-view, and 9-angle 3D views |
| **Step 9B** | `kaibridge opt "projects/<NAME>" --commit` | `python kicad_swap_optimizer.py "projects/<NAME>" --commit` | Physics-preserving ISRRO-X pin escape & ratsnest crossing optimizer |
| **Step 9D** | `kaibridge oracle <topic_or_class>` | `python kicad_oracle.py <topic_or_class>` | Live host KiCad C++ SWIG reflection probe (<4ms) |
| **Step 9E** | `kaibridge inspect "projects/<NAME>" --audit` | `python kicad_inspect.py "projects/<NAME>" --audit` | Fail-closed Gatekeeper Route-Readiness Proof |
| **Step 10** | `kaibridge route "projects/<NAME>"` | `python kicad_route.py "projects/<NAME>"` | Headless Freerouting 2.4.1, B.Cu ground pour & DRC |
| **Step 10E** | `kaibridge diff-pair "projects/<NAME>" --audit` | `python kicad_diff_pair.py "projects/<NAME>" --audit` | 3D physical differential pair skew and length matching audit |
| **Step 11** | `kaibridge export "projects/<NAME>"` | `python export_jlcpcb.py "projects/<NAME>"` | Export factory Gerbers, drill files, DFM-ROT CPL, and BOM CSV |

---

## 🔒 Hard Architectural Invariants

1. **Strict Autonomous Sequence (Steps 0–3):**
   - **DO NOT** trigger generic IDE planning mode or pause for permission before Step 0.
   - Steps 0, 1, 2, and 3 MUST execute autonomously in sequence upon receiving the user's prompt.
   - The ONLY implementation plan permitted is the **Step 4 Evidence-Backed Design Blueprint**, presented at **Human Gate 1**.

2. **Strict Multi-Sheet Preservation (Zero Gate Gaming):**
   - **NEVER** collapse a multi-sheet hierarchical design into a single sheet or artificially inflate paper size to bypass ERC warnings or errors.
   - If ERC reports violations, inspect netlist or pin healing — **NEVER** delete `"sheets"` from `design.json`.

3. **Standard CLI & Console First:**
   - Always use the dedicated `kaibridge-*` console entry points or Python CLI wrappers listed in the table above (both are 100% interchangeable in `v2.6.0`).
   - **DO NOT** write or execute ad-hoc scratch Python scripts for placement, routing, or schematic creation.

4. **Component Sourcing:**
   - Active ICs, sensors, and connectors MUST be fetched via `kaibridge fetch <ID>` (`JLC2KiCadLib` with fail-closed `easyeda2kicad` fallback) directly to `libs/kaibridge`.
   - Passives MUST follow [`references/jlcpcb_basic_parts.md`](../references/jlcpcb_basic_parts.md).

5. **Schema Template:**
   - [`design_template.json`](../design_template.json) is the sole canonical reference for `design.json`.

6. **Procedural Depth:**
   - For deep edge-case handling, track width clearance formulas, and Appendix A operations catalog, inspect specific sections of [`../SKILL.md`](../SKILL.md) on demand.
