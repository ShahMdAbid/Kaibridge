# User Guide

This guide demonstrates a simple end-to-end conversation between a **Human Engineer** and the **AI Agent** using Kaibridge.

---

### Step 1: Initial Prompt & Implementation Plan

**👤 User:** 
> "Design an ATmega328P breakout board with a 16MHz crystal, a reset button, and an LED on Pin 13.
> The project directory is `C:\KiCad_Projects\ATmega_Breakout`."

**🤖 AI Agent:**
> *[Agent enters planning mode and creates `implementation_plan.md`]*
> "I have drafted an implementation plan for the circuit architecture. Please review it and let me know if I should proceed."

**👤 User:** 
> "Approved. Go ahead."

**🤖 AI Agent:**
> "Understood. I will now generate the schematic.
> 
> *[Agent automatically runs `easyeda2kicad` to fetch LCSC footprints, writes `design.json`, and runs `json2sch.py --erc`]*
> 
> **Checkpoint 1 (Schematic to PCB Handoff):**
> I have successfully generated the native KiCad schematic with 0 ERC errors. Please follow these steps in KiCad:
> 1. Open the project in KiCad.
> 2. Open the Schematic Editor → **Tools → Annotate** → Run ERC to verify.
> 3. Open the PCB Editor and press **F8** (Update PCB from Schematic).
> 4. Press **Ctrl+S** to save the board.
> 5. Click **Tools → External Plugins → Kaibridge** to start the local bridge.
> 
> Let me know when the bridge is running!"

---

### Step 2: Placement Planning & Alignment

**👤 User:** 
> "Done! The bridge is running."

**🤖 AI Agent:**
> *[Agent connects to the bridge via `--state summary` and analyzes the board]*
> 
> "Great, I've connected to the board. Before I physically place the components, here is my **Placement Implementation Plan**:
> - **MCU (U1):** Placed in the dead center of the board.
> - **Crystal (Y1) & Load Caps:** Placed immediately adjacent to XTAL1/XTAL2 pins for minimal loop area.
> - **Decoupling Caps:** Placed < 2mm from the VCC/GND pins.
> - **LED & Button:** Placed on the bottom edge for easy access.
> 
> **Checkpoint 2 (Alignment Gate):** 
> Does this layout strategy work for you, or do you have any specific constraints (e.g. board size, connector orientation)?"

---

### Step 3: Physical Placement & Visual Critique

**👤 User:** 
> "That sounds good, but make sure the board is exactly 50x50mm, and put the Reset button on the top right corner instead."

**🤖 AI Agent:**
> "Noted. I will set the board outline to 50x50mm and prioritize the Reset button on the top right.
> 
> *[Agent generates `ops.json` for placement. It commits via `kicad_agent_bridge.py` and exports a live `.svg` snapshot for its own multimodal visual evaluation]*
> 
> "I have placed the components and evaluated the visual layout. The decoupling capacitors are optimally close to the MCU, and the Reset button is exactly on the top right. No courtyard overlaps were detected by the Geometry Gate.
> 
> **Checkpoint 3 (Placement Approval):**
> The physical layout is complete and verified. Are you ready for me to proceed with automated routing?"

---

### Step 4: Routing & File-Lock Coordination

**👤 User:** 
> "Looks perfect! Go ahead and route it."

**🤖 AI Agent:**
> "Excellent. I will now prepare the board for routing.
> 
> *[Agent executes `board.prep_for_route` to purge stray tracks]*
> 
> **Checkpoint 4 (Freerouting Auto-Router):**
> I am ready to start the headless auto-router. Because the router directly edits the file on disk:
> 1. Please press **Ctrl+S** in the PCB Editor to save your board right now.
> 2. **Do not click or edit anything** while I route.
> 
> May I start the router?"

**👤 User:** 
> "Saved. You can start."

**🤖 AI Agent:**
> *[Agent executes `freerouting_runner.py`]*
> 
> "Routing is complete! 
> The new tracks should now be visible in your PCB editor."

---

### Step 5: Final Validation & DRC

**👤 User:** 
> "The tracks look great."

**🤖 AI Agent:**
> *[Agent runs `board.drc_check` via the bridge]*
> 
> "I have run the final Design Rules Check (DRC).
> **Result:** 0 Clearance Violations, 0 Unrouted Nets.
> 
> The board is mathematically and electrically verified! 
> *(Note: If you wish to add a Ground Copper Pour, please do so manually in KiCad as a final optional step, and re-run DRC).*
> 
> Would you like me to export the JLCPCB manufacturing files (Gerbers, BOM, Pick & Place)?"
