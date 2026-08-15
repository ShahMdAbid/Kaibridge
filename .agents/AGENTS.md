# abIDE Specific Agent Rules

The following rules MUST be followed by all agents working on this project. These were discovered through painful trial and error:

### 1. STRICT ADHERENCE TO SKILL.md
Never reinvent KiCad operations. Always read the root `SKILL.md` before doing any PCB manipulations. Do NOT write custom Python scripts (like `autoplace.py` or `headless_place.py`) to manipulate KiCad directly. Use the REST API bridge (`kicad_agent_bridge.py`) with `ops.json` following the **Semantic Placement Protocol** exactly as documented in `SKILL.md`.

### 2. SwigPyObject Corruption Error & Unsaved Work
If you ever encounter the error:
`RuntimeError: BOARD proxy is corrupt (SwigPyObject). Close and reopen the abIDE window.`
Or `AttributeError: 'SwigPyObject' object has no attribute...`
**DO NOT** repeatedly try to run the bridge. This means the KiCad internal Python state is corrupted. 
**CRITICAL:** Do NOT immediately use `taskkill`, as this will destroy the user's unsaved work! First, politely inform the user that a memory corruption occurred and ask them to manually save their work (`Ctrl+S`), close KiCad, and reopen it. Only use `taskkill /IM kicad.exe /F` if the user explicitly confirms that KiCad is completely frozen and they cannot close it manually.

### 3. Edge.Cuts & Board Outline: Automated by Default (with Corrupted Footprint Fallback)
- **Standard Automated Path:** Always automate the board outline using `board.set_size` or `board.fit_outline` in `ops.json`. The engine automatically draws 4 clean `Edge.Cuts` segments and verifies closure with `GetBoardPolygonOutlines()`.
- **Corrupted Footprint Fallback:** In rare cases, if a 3rd-party footprint (e.g., some imported USB-C sockets) contains an illegal graphic line on the `Edge.Cuts` layer inside the footprint itself, KiCad will fail polygon closure with:
  `OpError: Edge.Cuts written but KiCad still will not close it. Usual cause: a stray Edge.Cuts graphic inside a footprint.`
  **Action:** If this specific error occurs, do not loop. Explain to the user that a footprint has an internal `Edge.Cuts` line, draw the outline manually in KiCad PCB Editor once, save, and proceed with the rest of the automated pipeline.

### 4. NO FILES IN PLUGIN DIRECTORY (STRICT)
Under NO circumstances should you create, generate, or save ANY files (like custom python scripts, temporary files, `ops.json`, or text files) inside the main plugin folder (`abIDE-main` or any of its subdirectories). All project-related files (like `ops.json` or `design.json`) MUST be created inside the user's specific `<PROJECT_DIR>` (e.g., the `hotdog` folder). Polluting the plugin's source code tree is strictly forbidden.

### 5. Ground Pouring & Crash-Proof Zone Handling (MANUAL)
- **NEVER** invoke `pcbnew.ZONE_FILLER` in Python scripts or plugins. In KiCad 10, executing zone fills from Python threads triggers C++ OpenMP / thread-lock access violation crashes (`kimathLogOverflow` or GUI freeze).
- **Ground Pouring is a Manual Task:** Do not use `zone.add` via JSON. Instruct the user to manually draw the GND copper zones (F.Cu and B.Cu) in the KiCad GUI using the 'Add a filled zone' tool and press **`B`** to fill them.
- **File Lock Contention:** **NEVER** write or overwrite `.kicad_pcb` from standalone background scripts while KiCad PCB Editor GUI has the project open (with the sole exception of `freerouting_runner.py`, which requires strict Save/Revert coordination). Always perform standard board operations via `kicad_agent_bridge.py` with `ops.json` on the live in-memory board.

### 6. Zero-Byte File Auto-Recovery Trigger
If `.kicad_pcb` ever becomes 0 bytes due to a crashed process or save interruption, **DO NOT START FROM SCRATCH**. Immediately restore the latest valid board file from `<PROJECT_DIR>/pcb_brain/backups/` using `Copy-Item`.
**Trigger:** Before running ANY heavy operation via `--json-ops` or `--state summary`, always verify the file size of `<PROJECT_DIR>\<project_stem>.kicad_pcb` using `Get-Item`. If the size is 0 bytes, halt and recover immediately.

