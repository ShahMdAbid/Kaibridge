---
name: KiCad abIDE Plugin Usage
description: Guidelines and instructions for using the abIDE plugin for KiCad 10.
---

### Agent Protocol: Autonomous KiCad Flow (v2.1)

STRICT instructions. Zero hallucination. If a rule and your instinct disagree, the rule wins.

### 🧭 RULE 0 — Session contract (do this before anything else)

1. Ask the user for exactly two paths and echo them back for confirmation:
    - `<PROJECT_DIR>` — the folder containing the `.kicad_pro`
    - `<PLUGIN_DIR>` — the folder containing `json2sch.py`
2. **Never search the filesystem for either.** If a path is wrong, ask again — do not probe.
3. `<LIB_NAME>` is `abide` everywhere. `kicad_lib_init.py -n abide` and `easyeda2kicad --output "$PWD/libs/abide"` must use the same name or the library tables will not resolve.
4. Confirm `kicad_paths.json` exists next to `json2sch.py` and is filled in. If a script errors about it, paste the error to the user verbatim — the error already contains the instructions. Do not write path-finding code.

### 🛑 RULE 1 — Environment & initialization

1. Never guess paths. Configuration lives in `kicad_paths.json` only.
2. Never create `.kicad_pro`. If `<PROJECT_DIR>` has none, **stop** and ask the user to create the project in the KiCad UI.
3. One `.kicad_pro` per folder. The project **stem** — not the folder name — is the identity used everywhere downstream.
4. Initialize libraries:

```powershell
python "<PLUGIN_DIR>\kicad_lib_init.py" "<PROJECT_DIR>" -n abide
```

### 📥 RULE 2 — Component acquisition

Split the BOM into **LCSC** (download) and **Native** (`Device:R`, `Device:C`, … — do nothing).

Preflight once: `easyeda2kicad --version`. If missing, ask the user to `pip install easyeda2kicad` and stop.

One component per command. CWD **must** be `<PROJECT_DIR>` or `--project-relative` fails with *"is not in the subpath of"*:

```powershell
Push-Location "<PROJECT_DIR>"
easyeda2kicad --lcsc_id <LCSC_ID> --full --output "$PWD/libs/abide" --overwrite --project-relative
Pop-Location
```

- `handshake operation timed out` / `Failed to fetch data` = network, not a bad ID. Retry that one ID at most twice, then report it and continue with the rest. **Never substitute a different component.**

### 🔎 RULE 3 — Pin verification (MANDATORY GATE)

```powershell
python "<PLUGIN_DIR>\kicad_pins.py" "<PROJECT_DIR>\libs\abide.kicad_sym" --verify
```

Exit code 1 = broken part. `FAIL` and `SKIP` are both blocking — a library you cannot reach is a library `Update PCB from Schematic` will silently skip.

Then extract exact data for each symbol you will use:

```powershell
python "<PLUGIN_DIR>\kicad_pins.py" "<PROJECT_DIR>\libs\abide.kicad_sym" -s <SYMBOL_NAME> --json
python "<PLUGIN_DIR>\kicad_pins.py" --native <LIBRARY_NAME> -s <SYMBOL_NAME> --json
```

<aside>
📌
The JSON contains a `footprint` field. **Copy it verbatim** into `design.json`. Do not reconstruct it from the package name — `easyeda2kicad` names footprints after the LCSC package and the string will not match anything you invent.
</aside>

### 📐 RULE 4 — `design.json`

Required top-level keys. Omitting any of these is a validation failure:

| Key | Required | Note |
| --- | --- | --- |
| `schema` | yes | must be exactly `2` |
| `parts` | yes | `lib_id`, `value`, `footprint` per ref |
| `nets` | yes | ≥2 pins each |
| `netclasses` | if any net sets `class` | a net referencing an undefined class fails |
| `groups` | optional | ungrouped parts land in `Unsorted` |
| `power_flags` | recommended | auto-adds `#FLGn` PWR_FLAG parts for ERC |
| `no_connect` | optional | `"U2.38"` or `"J1.SHIELD"` |
| `checks` | yes | set `"require_footprints": true` |

Rules:

1. Pin references are `"<REF>.<PIN_NUMBER>"` and come **only** from `kicad_pins.py --json`. Never guess a pin number.
2. Name every junction (`LED_A`, `EN`, `IO0`). Never `Net-(D1_Pad1)` — the compiler rejects it.
3. Power nets (`GND`, `+3V3`, `+5V`, `VIN`) get `"style": "global"`. Signals omit `style`.
4. Every unconnected `power_in` pin is a hard error. Wire it or list it in `no_connect`.

Save to `<PROJECT_DIR>\design.json`. Schema reference: `design_template.json`.

**The first command after writing `design.json` is always the dry run.** Writing the schematic before exit code 0 is forbidden:

```powershell
python "<PLUGIN_DIR>\json2sch.py" "<PROJECT_DIR>" "<PROJECT_DIR>\design.json" --dry-run
```

*(পিন রেফারেন্স অবশ্যই `kicad_pins.py --json`-এর নম্বর/নাম থেকে আসবে; `design.json` লেখার পর প্রথম কমান্ড সর্বদা `--dry-run`, exit code 0 না হলে schematic লেখা নিষিদ্ধ।)*

Then, with **KiCad closed** (it will overwrite both files on exit otherwise):

```powershell
python "<PLUGIN_DIR>\json2sch.py" "<PROJECT_DIR>" "<PROJECT_DIR>\design.json" --apply-netclasses
```

Generated files target KiCad 7 and newer.

### 🔧 RULE 5 — Schematic → PCB

1. 🧍 **HUMAN**: open the project in KiCad. Tools → Annotate (keep existing) → ERC.
2. 🧍 **HUMAN**: PCB Editor → **F8** (Update PCB from Schematic) → **Ctrl+S**.
    - There is **no** headless or scripted equivalent of F8. Do not attempt one. Stop and wait.
3. 🧍 **HUMAN**: Tools → External Plugins → **abIDE** (starts the bridge socket).
4. Baseline snapshot: `python "<PLUGIN_DIR>\Autoplacer\pcb_snapshot.py" "<PROJECT_DIR>"`
5. Untangle: `python "<PLUGIN_DIR>\Autoplacer\macro_placer.py" "<PROJECT_DIR>"`
6. Snapshot again to see the result of step 5.

### 🧠 RULE 6 — Placement (state-driven, not guessed)

Do **not** infer coordinates from the SVG. Pull the real numbers:

```powershell
python "<PLUGIN_DIR>\Autoplacer\kicad_agent_bridge.py" --state summary
```

This writes `<PROJECT_DIR>\pcb_brain\ai_context_summary.json` and prints its path — exact positions, rotations, bounding boxes, courtyards, pad coordinates, nets and the op schema. Read that file. Use `_board.svg` only as a visual sanity check.

Then:

1. **Function** — connectors and USB at the board edge; decoupling caps hard against their IC power pin.
2. **Connectivity** — trace `nets` in `design.json`; cross-check pad coordinates from the state file.
3. **Optimize** — rotate to 0/90/180/270 so connecting pads face each other.
4. **Emit ops** to `<PROJECT_DIR>\ops.json`:

```json
[
  {"op": "board.set_size", "width": 100, "height": 50},
  {"op": "footprint.move", "ref": "U1", "x": 55.0, "y": 25.0, "rotation": 0},
  {"op": "footprint.move", "ref": "C1", "x": 58.5, "y": 22.0, "rotation": 270}
]
```

1. **Apply**: `python "<PLUGIN_DIR>\Autoplacer\kicad_agent_bridge.py" --json-ops "<PROJECT_DIR>\ops.json" --timeout 180`
    - Exit code 0 = applied. Non-zero = **nothing to interpret, read the printed dry-run failures**.
    - `board.set_size` **deletes all existing Edge.Cuts**. Confirm with the user before the first one.
2. **Verify**: rerun `--state summary` (numbers) and `pcb_snapshot.py` (picture).

### 🔮 RULE 7 — Custom `pcbnew` scripting

1. Never guess an API method.
2. Cheap existence check first — grep `Autoplacer/all_functionName.md` for the class and method.
3. Exact signature second, from the **running** KiCad:

```powershell
python "<PLUGIN_DIR>\Autoplacer\kicad_agent_bridge.py" --oracle "BOARD GetTracks"
```

(`oracle.py` standalone works only where `pcbnew` is importable; the bridge always works.)

1. If the Oracle says NOT FOUND, it prints `did you mean:` candidates. Pick one of those. **Do not invent a third spelling.**
2. Use only methods the Oracle confirmed. Run via `kicad_agent_bridge.py <script.py>`.
3. The watchdog cannot interrupt a long C/SWIG call. Pass `--timeout` generously for zone fills and imports rather than writing your own retry loop.

### 🔄 RULE 8 — Autoroute + DRC loop

1. Set the outline: `board.set_size` op.
2. Place everything inside it (RULE 6).
3. Route:

```powershell
python "<PLUGIN_DIR>\Autoplacer\freerouting_runner.py" "<PROJECT_DIR>"
```

(`freerouting.jar` is expected in `<PLUGIN_DIR>\Autoplacer\`; override with `--jar`.)

1. DRC: `{"op": "board.drc_check"}`. Read the printed `DRC exit=N`. `0` = clean.
2. If not clean:
    - `{"op": "net.delete_routing"}` with **no** `net` key wipes all routing. With a `net` key it wipes one.
    - Read the violations, move the offending footprints apart, go to 3.
3. **Exit conditions — obey all three:**
    - `DRC exit=0`, **or**
    - three full loops with no improvement in violation count, **or**
    - the tangle score stops decreasing.
    
    On 2 or 3: stop and report to the user. Do not loop a fourth time.

### 🚨 RULE 9 — Error recovery (non-negotiable)

1. **Never run the same failing command more than twice.**
2. If the same error text appears twice, stop. Report the exact command, the exact error, and your best hypothesis. Ask the user.
3. `--- KICAD NOT CONNECTED ---` has exactly one cause: abIDE is not open. Ask the user to open it and retry **once**. Never search the filesystem, never look for the `.port` file, never restart anything.
4. Never "fix" an error by widening scope — no substitute components, no invented pin numbers, no guessed footprints, no synthesized paths.
5. A non-zero exit code from any script means **nothing downstream may run**.
6. After any aborted `apply_ops`, treat the board as undefined: rerun `--state summary` before deciding anything. Backups are in `<PROJECT_DIR>\pcb_brain\backups\`.

### 🧍 Human checkpoints — no automation exists for these

| # | Action | Why it cannot be scripted |
| --- | --- | --- |
| 1 | Create the `.kicad_pro` | `${KIPRJMOD}` needs a real project |
| 2 | Reopen the project after `json2sch` writes | KiCad caches the schematic in memory |
| 3 | **F8** — Update PCB from Schematic | No CLI and no Python API exposes it |
| 4 | **Ctrl+S** after F8 | `pcb_snapshot` and `kicad-cli` read from disk |
| 5 | Open **abIDE** | The bridge socket only exists while the window is open |
| 6 | Close KiCad before `--apply-netclasses` | KiCad rewrites `.kicad_pro` on exit |
