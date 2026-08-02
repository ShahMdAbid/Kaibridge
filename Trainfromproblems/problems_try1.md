# Problems & Errors Encountered - Try 1
# Date: 2026-08-02
# Goal: Make the abIDE workflow more robust and token efficient.

Below is a comprehensive list of all the friction points, API errors, and logical bugs encountered during the end-to-end execution of the KiCad autonomous flow. Fixing these in the plugin will significantly reduce token usage and prevent the agent from getting stuck in loop-and-fix cycles.

## 1. KiCad 10 Python API Changes (`Millimeter2iu`)
- **Error:** `AttributeError: module 'pcbnew' has no attribute 'Millimeter2iu'`
- **Context:** Occurred during Skeleton Generation. Older KiCad scripts use `Millimeter2iu`, but KiCad 10 requires `pcbnew.FromMM()`.
- **Recommendation:** Provide a utility wrapper in the plugin or explicitly state the KiCad 10 API conversions in `SKILL.md` (e.g., `FromMM`, `ToMM`) so the agent doesn't have to guess or query the oracle for basic conversions.

## 2. `BOARD.Save()` Signature Change
- **Error:** `TypeError: BOARD.Save() missing 1 required positional argument: 'filename'`
- **Context:** The skeleton script crashed when trying to save. 
- **Recommendation:** Explicitly document in `SKILL.md` that boards must be saved using `pcbnew.SaveBoard(board.GetFileName(), board)` instead of `board.Save()`.

## 3. Lack of Script Idempotency (Ghost/Duplicate Footprints)
- **Problem:** Because the skeleton script crashed halfway through, the next successful run added a *second* set of components to the live memory. This resulted in 38 footprints instead of 19 stacked at the origin.
- **Context:** This caused the autoplacer to calculate 120 overlaps and act erratically.
- **Recommendation:** The skeleton generation script template in `SKILL.md` should include a cleanup step at the top (e.g., clearing the board or deleting all footprints and tracks) before injecting the new layout, ensuring the script is fully idempotent.

## 4. Bridge Missing `sys.path` Injection
- **Error:** `ModuleNotFoundError: No module named 'currentboardfetcher'`
- **Context:** When running scripts via `kicad_agent_bridge.py --stdin`, the embedded Python doesn't inherently know where the plugin files are. The agent had to manually inject `sys.path.append(...)`.
- **Recommendation:** Modify `kicad_agent_bridge.py` so that it automatically appends the plugin's root directory to `sys.path` before executing any incoming stdin scripts.

## 5. Missing `PyYAML` Dependency in KiCad's Python
- **Error:** `autoplacer_engine.py` threw `Failed to load constraints: [Constraints] PyYAML not installed.`
- **Context:** KiCad's embedded Python environment does not ship with `PyYAML` by default.
- **Recommendation:** Either bundle a pure-python YAML parser with the plugin, or update `autoplacer_engine.py` to natively accept `.json` files (which I patched dynamically during this run using the built-in `json` module).

## 6. Bridge Server Hang / Timeout on Subprocess
- **Error:** `Server busy: another execution is in progress. Retry later.`
- **Context:** Attempting to run `pip install pyyaml` via the bridge took longer than the timeout, which left the RPC server deadlocked. The user had to manually restart the plugin.
- **Recommendation:** Implement a safe thread-cancellation or timeout-release mechanism in the RPC server inside `abIDE`, so that hanging scripts don't lock the UI permanently.

## 7. SWIG Pointer Corruption on `GetFootprints()`
- **Error:** `AttributeError: 'SwigPyObject' object has no attribute 'GetFootprints'`
- **Context:** After I successfully deleted the 19 duplicate footprints using `board.Remove()`, the next run of the autoplacer crashed at `list(board.GetFootprints())`. 
- **Recommendation:** Modifying the board (especially deleting items) can corrupt the SWIG wrapper or iterators in the same session. Scripts that modify the board heavily should force a refresh of the board pointer (e.g., `board = pcbnew.GetBoard()`) or avoid passing stale `board` objects to sub-functions.

## 8. Autoplacer Physics Results ("Garbage Layout")
- **Problem:** While the `J1` and `U1-U6` anchors placed correctly, the resistors grouped tightly but rotated wildly and collided with each other, resulting in a messy "garbage" look.
- **Context:** Spring-physics alone doesn't understand aesthetic grid alignment.
- **Recommendation:** Update `autoplacer_engine.py` to include a final "Snap-to-Grid and Align" pass for tight groups, or allow strict rotation inheritance (e.g., locking resistor rotations to match their anchor's rotation).

## 9. YAML Visualizer Coordinates (`blueprint_view.html`)
- **Problem:** Documented previously in `fix for 1.0.4.txt`. The visualizer coordinates and overlap logic make the generated HTML very messy for complex schematics.
- **Recommendation:** Implement a basic auto-routing or hierarchical force-directed graph in the HTML visualizer so components don't overlap.
