# abIDE Command Line Interface (CLI) Guide

This project includes several important scripts that can be run from the command line (CLI) with various flags (options). The entire system can be divided into 4 main categories: Root Scripts, PCB Orchestrator, Live PCB Bridge (HTTP REST Bridge), and Supporting Scripts. The purpose and usage of each are detailed below:

---

## 1. Root Scripts

### `json2sch.py` (JSON to Schematic Generator)
This script reads your `design.json` file and generates KiCad schematic (`.kicad_sch`) files. It supports multi-sheet hierarchies and creates an `abide_build.json` sidecar file for `macro_placer.py`.

**Usage:**
```bash
python json2sch.py <project_dir> [design.json] [options]
```

**Flags (Options):**
- `-h, --help` : Show the help menu.
- `-o, --out PATH` : Root schematic path (default: `<project>.kicad_sch`).
- `--dry-run` : Only compile, validate, and report; do not save any files. **Always run `--dry-run` first.**
- `--apply-netclasses` : Using this saves the track width, clearance, and other rules defined in your JSON file directly into the KiCad `.kicad_pro` file. *(KiCad MUST be completely closed when running this!)*
- `--no-backup` : Do not create timestamped `.bak` copies.
- `--kicad-version N` : Format stamp; `20250114` = KiCad 9 (default), `20231120` = KiCad 8.

### `kicad_lib_init.py` (Project Library Initializer)
This script sets up the necessary `sym-lib-table` and `fp-lib-table` in your project directory so that KiCad can correctly identify the libraries.

**Usage:**
```bash
python kicad_lib_init.py <project_dir> -n abide
```

### `kicad_pins.py` (Pin Extractor & Verifier)
This script extracts pin data from `.kicad_sym` files and helps verify footprints.

**Usage:**
```bash
python kicad_pins.py <symbol_file> [options]
```
**Flags:**
- `--verify` : Verifies if the footprint and pad-counts are correct.
- `--json` : Prints the data in JSON format.
- `-s, --symbol SYMBOL` : View data for a specific symbol only.

---

## 2. PCB Orchestrator

### `abide_pcb.py` (Automated Pipeline)
This is the most powerful command in the new architecture. It automates the entire Place → Route → Check loop.

**Usage:**
```bash
python abide_pcb.py <project_dir> --step {place,route,check,auto} [--commit]
```

**Options:**
- `--step auto` : Automates placement, routing (using `freerouting_runner.py`), and DRC checks in one go (default budget: 4 iterations).
- `--commit` : Applies and saves the changes (otherwise it just runs a dry-run).

---

## 3. Live PCB Bridge (The HTTP REST Bridge)

### `Autoplacer/kicad_agent_bridge.py` 
This is our live KiCad API Bridge. **It is now a complete HTTP REST API Server**, not a socket architecture! This bridge is used to run code in KiCad 10's live memory (where your PCB Editor is open), read the board state, and send JSON commands.

**Usage:**
```bash
python Autoplacer/kicad_agent_bridge.py [script_path] [options]
```

**Flags (Options):**
- `-h, --help` : Show the help menu.
- `--state {summary,full}` : **(Most frequently used)** Prints the entire list of components currently on the KiCad PCB, their positions, and nets in JSON format. (`--state summary` is typically used).
- `--json-ops JSON_OPS` : **(Most frequently used)** Applies placement rules or other operations (e.g., `footprint.place`, `board.fit_outline`) from an `ops.json` file directly to the live PCB.
- `--commit` : When used with `--json-ops`, applies the changes to the live board; otherwise, it acts as a dry-run.
- `--oracle ORACLE` : Checks for the existence of a method inside the live KiCad API. For example, `--oracle "BOARD GetTracks"` will tell you if the `GetTracks` method exists inside the `BOARD` class.
- `--stdin` : Type live Python code in the terminal and send it to KiCad.
- `--code CODE` : Run inline code. Example: `--code "import pcbnew; print(pcbnew.GetBoard())"`
- `--timeout TIMEOUT` : Sets the maximum wait time for the script (default: 30.0s).
- `--keep-state` : Keeps the script's variables saved in memory (like a REPL).
- `--reset-state` : Completely cleans the live memory.

---

## 4. Supporting Scripts

### `Autoplacer/macro_placer.py` (Component Untangler)
After pressing F8, all components from the schematic are tangled at the (0,0) position. This script reads `design.json`, untangles them, and organizes the components into separate groups.

**Usage:**
```bash
python Autoplacer/macro_placer.py <project_dir>
```

### `Autoplacer/freerouting_runner.py` (Headless Auto-Router)
This script exports the DSN file from KiCad, routes the entire board in the background using FreeRouting (Java), and imports the SES file back into KiCad.

**Usage:**
```bash
python Autoplacer/freerouting_runner.py <project_dir>
```
**Flag:** `--jar JAR` (if the `freerouting.jar` file is located in a different directory).

### `Autoplacer/pcb_snapshot.py` (Visual SVG Snapshot)
This takes the project directory as input, forces live KiCad to save the PCB to disk, and then generates a vector image (SVG picture) of the PCB using `kicad-cli`. This allows AI or humans to visually review the aesthetics of the placement.

**Usage:**
```bash
python Autoplacer/pcb_snapshot.py <project_dir>
```

---
*(Note: There is a highly critical engine file named `currentboardfetcher.py` that serves as the backend for `--state` and `--json-ops`. However, it does not need to be called directly from the terminal; it is automatically invoked by the bridge file.)*
