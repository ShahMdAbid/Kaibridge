# Known Problems to be Solved

## 1. Schematic Component Spillage (`json2sch.py`)
**Description:** 
When generating a schematic from `design.json`, `json2sch.py` currently places components sequentially in a vertical list. If there are many components, the list becomes very long and spills outside the schematic page boundary.
**Impact:** ZERO electrical impact. The page boundary is purely cosmetic. But it looks untidy.
**Proposed Solution:** Implement a wrapping algorithm in `json2sch.py` to arrange components in columns.

## 2. KiCad Live API SWIG Object Corruption / Type Casting Issue (`kicad_agent_bridge.py`)
**Description:** 
`pcbnew.GetBoard()` frequently returns a raw C++ pointer (named `SwigPyObject`) instead of a properly wrapped `BOARD` Python object if the live PCB Editor state is disturbed (e.g., user deletes tracks manually, opens a dialog, or after an SES import). 
Because of this **Type Casting failure**, the object "forgets" all of its own methods. This causes the API to throw errors like `AttributeError: 'SwigPyObject' object has no attribute 'GetFootprints'` (or `GetTracks`, `GetNetInfo`, etc.), even though these methods definitely exist in KiCad 10!
**Impact:** 
The `kicad_agent_bridge.py` crashes entirely, rendering the AI agent completely blind and unable to modify the live board.
**Proposed Solution:** 
Update `currentboardfetcher.py` to handle this Type Casting issue by forcing it with `pcbnew.Cast_to_BOARD()`, or completely shift to using "Offline Mode" by default via `pcbnew.LoadBoard(filename)` to read/write the disk file directly, which is 100% stable.

## 3. FreeRouting Crashing on Unclean/Out-of-bound Tracks
**Description:** 
If old tracks exist in memory that violate board boundaries or are badly placed, FreeRouting's `ShapeSearchTree` throws a `NullPointerException` (java) and the autorouting fails.
**Impact:** 
The auto-router generates a partial or broken SES file and stops.
**Proposed Solution:** 
Ensure a flawless track-wiping script runs *before* exporting the `.dsn` to FreeRouting.

## 4. KiCad CLI `pcb import specctra-ses` Deprecation
**Description:** 
In KiCad v10, the CLI command `kicad-cli pcb import specctra-ses` fails because the subcommand is removed/changed. 
**Impact:** 
Headless `freerouting_runner.py` fails to save the SES file back to the board automatically via CLI.
**Proposed Solution:** 
Use the Python API `pcbnew.ImportSpecctraSES(board, ses_path)` via an offline script, then `SaveBoard()`, completely bypassing the CLI.

## 5. Autorouting "Spaghetti" (No Power Planes)
**Description:** 
Without power planes, FreeRouting draws extremely messy tracks for `+5V` and `GND`, jumping all over the board and sometimes causing clearance violations (shorts).
**Impact:** 
Terrible PCB routing quality.
**Proposed Solution:** 
The AI must programmatically add Copper Zones (`pcbnew.ZONE`) for GND and +5V *before* launching FreeRouting.
