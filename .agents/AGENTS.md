# abIDE Specific Agent Rules

The following rules MUST be followed by all agents working on this project. These were discovered through painful trial and error:

### 1. STRICT ADHERENCE TO SKILL.md
Never reinvent KiCad operations. Always read the root `SKILL.md` before doing any PCB manipulations. Do NOT write custom Python scripts (like `autoplace.py` or `headless_place.py`) to manipulate KiCad directly. Use the REST API bridge (`kicad_agent_bridge.py`) with `ops.json` following the **Semantic Placement Protocol** exactly as documented in `SKILL.md`.

### 2. SwigPyObject Corruption Error
If you ever encounter the error:
`RuntimeError: BOARD proxy is corrupt (SwigPyObject). Close and reopen the abIDE window.`
Or `AttributeError: 'SwigPyObject' object has no attribute...`
**DO NOT** repeatedly try to run the bridge. This means the KiCad internal Python state is permanently corrupted (usually from Reverting to Saved or a bad script crash). The ONLY fix is to forcefully restart the ENTIRE KiCad application (not just the plugin window). Use `taskkill /IM kicad.exe /F` and politely ask the user to reopen KiCad and the abIDE plugin.

### 3. Edge.Cuts / Board Outline Failures
When running the `board.fit_outline` operation via `ops.json`, if it fails with:
`OpError: Edge.Cuts written but KiCad still will not close it. Usual cause: a stray Edge.Cuts graphic inside a footprint.`
This means a component (often a USB-C connector like HRO_TYPE-C-31) has internal Edge.Cuts lines, which confuses KiCad's outline detector.
**Fix:** Stop trying to automate the outline. Do NOT delete existing outlines without redrawing them. Politely ask the human user to manually draw the `Edge.Cuts` rectangle in KiCad and save, then proceed with the rest of the automated pipeline (like Freerouting).

### 4. NO FILES IN PLUGIN DIRECTORY (STRICT)
Under NO circumstances should you create, generate, or save ANY files (like custom python scripts, temporary files, `ops.json`, or text files) inside the main plugin folder (`abIDE-main` or any of its subdirectories). All project-related files (like `ops.json` or `design.json`) MUST be created inside the user's specific `<PROJECT_DIR>` (e.g., the `hotdog` folder). Polluting the plugin's source code tree is strictly forbidden.
