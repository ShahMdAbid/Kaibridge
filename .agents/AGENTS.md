# Hardware Synthesis Directive

For any hardware design, schematic, placement, routing, or KiCad task in this workspace:

1. **Strict Sequence Invariance (No Early Generic Planning):**
   - **DO NOT** trigger generic IDE planning mode or pause for permission before Step 0.
   - Step 0 (Bootstrap), Step 1 (Wishlist), Step 2 (Download), and Step 3 (Pin Extraction) MUST execute immediately in sequence upon receiving the user's prompt.
   - The ONLY implementation plan permitted is the **Step 4 Evidence-Backed Design Blueprint**, which can ONLY be written AFTER Step 3 pin and footprint extraction is complete.

2. **Strict Multi-Sheet Preservation (Zero Gate Gaming):**
   - **NEVER** collapse a multi-sheet hierarchical design into a single sheet or artificially inflate paper size to bypass ERC warnings or errors.
   - If ERC reports violations, inspect the netlist, pin healing, or toolchain — **NEVER** delete `"sheets"` from `design.json`.

3. **Strict Single Source of Truth:**
   - You MUST read and strictly follow [`SKILL.md`](../SKILL.md) from Step 0 to Step 11.
   - Never skip steps, never invent alternative workflows, and never guess pinouts or footprints.

4. **99% CLI First:**
   - Always use the dedicated CLI tools documented in [`SKILL.md`](../SKILL.md) (`kicad_lib_init.py`, `easyeda2kicad`, `kicad_pins.py`, `json2sch.py`, `kicad_pcb_sync.py`, `kicad_layout.py`, `pcb_snapshot.py`, `kicad_route.py`, `export_jlcpcb.py`).
   - Do NOT write or execute ad-hoc scratch Python scripts.

5. **Component Sourcing:**
   - Active ICs, sensors, and connectors MUST be fetched via `easyeda2kicad --lcsc_id <ID>` directly to `libs/kaibridge`. Never search local KiCad stock libraries for active parts.
   - Passives MUST follow `SKILL.md` Step 2B.

6. **Schema Template:**
   - [`design_template.json`](../design_template.json) is the sole canonical reference for `design.json`. Never reverse-engineer old project dump folders.
