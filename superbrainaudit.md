# abIDE — Principal Engineer Audit

Read the whole monodoc.[[1]](https://app.notion.com/p/3af29eba8c4480599107ddffeb1ab11a?pvs=21) Verdict up front: **the architecture is ~70% sound and the ideas (Oracle, YAML-first, physics placer, stateless bridge) are genuinely good — but there are at least six defects that make the documented happy path impossible to complete, and the single biggest one is that `oracle.py` cannot run at all as shipped.**

Severity key: 🔴 fatal (blocks the flow) · 🟠 critical (silent wrong behavior) · 🟡 quality.

---

## 1. Flow & Architectural Integrity

### 1.1 The naming universe splits in two and never reconnects 🔴

This is the deepest structural flaw in the system.

- `yaml_generation_rules.md` Rule 4 mandates semantic IDs: `MCU1`, `SEN1`, `PAS1`, `DRV1`.
- `design_rules.md` (consumed at Rule 9B) keys **every single rule** off KiCad reference designators: `U1`, `C1`, `J1`, `H1`, `Y1`, `R3`. See Rules 1, 2, 5, 6, 9, 12.
- `autoplacer_engine.py` builds `ref_to_fp = {fp.GetReference(): fp}` — i.e. it looks up `U1`, not `MCU1`.
- Nothing in `SKILL.md` Rule 9A ever tells the agent to call `fp.SetReference(...)`, and nothing defines a `MCU1 → U1` mapping table.

**Consequence:** every anchor, zone preference and tight group the agent writes will hit the `[Anchor] WARNING: ref '...' not found on board` branch, and the placer will silently run fully unconstrained. The physics engine will *appear* to work and produce garbage.

**Fix:** add a mandatory `ref_designator:` field to each component in `circuit_blueprint.yaml` (`MCU1: { ..., ref: "U1" }`), require Rule 9A to call `SetReference` from it, and make the constraints YAML use `ref` exclusively. Or drop semantic IDs and use KiCad refs everywhere — simpler, and I'd recommend it.

### 1.2 The constraints YAML has no defined home 🔴

`SKILL.md` Rule 9B calls `autoplacer_engine.run_physics_placer()` with **no argument**. The engine then defaults to:

```python
yaml_path = os.path.join(os.path.dirname(__file__), "placement_constraints.yaml")
```

That is the **plugin directory**, not `<PROJECT_DIR>`. Meanwhile the template file is named `autoplacement_template.yaml` and no rule anywhere says "write your generated constraints to `<PROJECT_DIR>/placement_constraints.yaml`". Result: `[Constraints] No YAML found... Running unconstrained.` — printed as an info message, not an error, so the agent will report success.

Also violates your own Global Library Protection principle (project-local everything).

### 1.3 The op-schema in `currentboardfetcher.py` is orphaned 🟠

You built a genuinely excellent validated mutation layer — `OPS`, `apply_ops()` with validate-all → backup → execute → diff-verify, `_resolve_net` refusing invented net names, `intent.json`. This is the correct way to let an LLM touch a board.

`SKILL.md` never mentions it. Rules 9A/9B instruct the agent to write **raw `pcbnew` code** instead — the exact hallucination-prone path `apply_ops` exists to eliminate. You have a safety harness and the docs route around it.

**Fix:** make Rule 9A emit a JSON op list applied via `apply_ops(ops, dry_run=False, save=True)`. Restrict raw `pcbnew` to escape-hatch cases.

### 1.4 There is no verification stage — the loop never closes 🔴

- `run_drc()` is hard-disabled (`return None`).
- Rule 9A ends with "wait for the user to confirm the ratsnest looks correct" — the only check is a human eyeballing the canvas.
- Nothing re-reads state after 9A to confirm every YAML net actually exists on the board with the right pad count.
- Rule 9C (routing) is `(Future)`. The flow dead-ends after placement.

An autonomous agent with no machine-readable success criterion will confidently declare victory on a broken board. Minimum viable fix: after 9A, run a `verify_netlist.py` that diffs YAML nets against `board.GetNetsByName()` and pad assignments, and fail loudly.

### 1.5 Contradictory file-writing policy 🟡

- `AGENTS.md`: "**Zero Temporary Files Policy** — DO NOT use `write_to_file`."
- `SKILL.md` Rule 2: "Create or update an artifact named `task.md` using the `write_to_file` tool."
- `currentboardfetcher.ai_context()` writes `ai_context_summary.json`, `state_*.json`, `intent.json`, and `.kicad_pcb` backups to disk on every call.

The intent (don't write scratch `.py` files for the bridge) is right; the wording is absolute and an LLM will either refuse to write `task.md` or ignore the policy wholesale. Rewrite as: "No scratch `.py` files — pipe code via stdin. Persistent project artifacts (`task.md`, YAMLs, snapshots) are expected."

### 1.6 What is actually solid ✅

- Stateless-by-default execution namespace with opt-in `--keep-state` is the right call, and the reasoning comment in `script_runner.py` is excellent.
- OS-assigned port + discovery file + zombie-port detection is a smart, dependency-free IPC design.
- The Oracle *concept* (verify SWIG signatures instead of trusting training data) is the highest-leverage idea in the repo.
- `snapshot` / `diff_states` / `_fingerprint` is a professional-grade change-tracking layer.

---

## 2. Fatal & Critical Bugs

### 2.1 `oracle.py` reads a file that does not exist 🔴

```python
file_path = os.path.join(os.path.dirname(__file__), "all_functionNameWithDetailedUsecase.py")
if not os.path.exists(file_path):
    print(f"Error: Could not find {file_path}"); sys.exit(1)
```

Your own directory listing annotates that file: *"actually pcbnew from kicad source code not present here"*. So the documented Rule 8 command — `... | python oracle.py --batch` — **exits 1 every time**. Rule 8 is mandatory and cannot be satisfied.

Ironically, the *working* implementation is `ScriptRunnerFrame._execute_oracle`, which resolves the live `pcbnew.py` from `pcbnew.__file__` and greps that. Two oracles, two sources of truth, and `SKILL.md` documents the broken one.

**Fix:** make `oracle.py` locate `pcbnew.py` the same way (import pcbnew, strip `.pyc`), or route Rule 8 through `kicad_agent_bridge.py --oracle`. Delete the other path.

### 2.2 Locked anchors can never reach their zone 🔴

In `run_physics_placer`:

- STEP 2 applies `SetLocked(True)` for any anchor with `locked: true`, and only sets a position if `position_mm` exists.
- STEP 3 puts all locked footprints into `anchors_fp` and excludes them from `movable`.
- STEP 7 block C (zone attraction) iterates `for fp1 in movable`.

So `J2` in `autoplacement_template.yaml` — `zone: EDGE_LEFT`, `locked: true`, **no `position_mm`** — is locked in place wherever `easyeda2kicad`/9A happened to drop it, forever. `zone` on a locked anchor is a **no-op**. The template ships this exact pattern as an example, so every agent will reproduce it.

**Fix:** in STEP 2, if `locked` and no `position_mm`, snap the footprint to `zone_center(zone, bounds)` before locking.

### 2.3 Locking is a permanent, accumulating side effect 🟠

`fp.SetLocked(True)` is never reversed. Plus the fallback branch:

```python
fallback = conns[0] if conns else max(movable, key=get_bounding_radius)
fallback.SetLocked(True)
```

Re-run the placer three times with a tweaked YAML and you have progressively more frozen footprints, including one the user never asked to lock. Track engine-applied locks separately and release them at the start of each run.

### 2.4 Non-decaying forces = the simulation never converges 🟠

Three of the five force terms are **constant magnitude, independent of distance**:

```python
# C. Zone attraction
fm = K_SPRING * priority * 0.5          # constant
# D. Tight group
fm = K_SPRING * 3.0 * (1.0 + overshoot) # ≥ 3.0 even at distance 0
# E. Relative constraint
fm = K_SPRING * 2.0                     # constant
```

Each is then applied as a unit vector `fm * (dx/dist)`. A constant attractive force toward a target has **no equilibrium** — the component accelerates in, overshoots, gets yanked back, and orbits. With `velocities[u] = (v + f) * 0.8`, steady-state velocity is `4 × f`, so a tight-group member sits at ~12 mm/iteration of raw velocity, clamped only by `temp` and `MAX_DISP`. It will jitter at the clamp forever.

Also: `early_stop_mm: 0.05` is compared against **post-clamp** movement, so any component pinned at `MAX_DISP` prevents early stop entirely — you always burn all 200 iterations.

**Fix:** make all three Hookean (`fm = k * (dist - target)`), so force → 0 at the target. Add a mass/`dt` term or switch to a proper Verlet step.

### 2.5 Repulsion ignores component size 🟠

```python
fm = K_REPULSION / (dist_sq + EPSILON)
```

`radii` is computed (`get_bounding_radius`) and used for spring rest-length and overlap *metrics*, but **never in the repulsion term**. A 0402 and a 40-pin connector repel identically. There is no hard overlap constraint anywhere, so `final_overlaps` will routinely be non-zero — and the code prints it as a metric rather than treating it as failure.

Additionally `get_bounding_radius` uses the bbox **diagonal ÷ 2**, i.e. a circumscribed circle. A 40 mm header becomes a 20 mm-radius disc. Packing density will be terrible for anything non-square.

### 2.6 The watchdog + O(N²) physics = guaranteed timeout on real boards 🔴

`ScriptRunnerFrame._execute` installs `sys.settrace(trace_calls)`, whose returned local tracer fires on **every line event**. That is a 10–100× interpreter slowdown. Under that penalty, `run_physics_placer` does:

- `adj_list` construction: O(N²) pad-set intersections
- `calculate_overlapping_pairs`: O(N²), called twice
- main loop: `iterations × |movable| × N` repulsion pairs → 200 × N²

At N = 60 that's ~720k inner iterations of pure Python under `settrace`, on **KiCad's main GUI thread**. It will blow the 15 s watchdog long before finishing, and KiCad's UI is frozen the whole time. Same problem for `get_full_board_state` on any non-trivial board (it walks every pad, every graphic, every zone outline point).

**Fixes, in order of value:**

1. Don't use `settrace` as the watchdog. It's the wrong tool — it also **cannot interrupt a long C++ SWIG call**, which is the actual freeze risk. Use a `wx.Timer`-based cooperative check, or move heavy compute off the GUI thread and only touch `pcbnew` for the final write-back.
2. Spatial hashing / grid bucketing for repulsion, plus a cutoff radius (currently every component repels every other at infinite range).
3. Barnes–Hut or simple cell lists for `calculate_overlapping_pairs`.
4. Vectorize with numpy if available.

### 2.7 TCP bridge: phantom execution race 🔴

In `_handle_agent_connection`:

```python
wx.CallAfter(run_on_main)
finished = done.wait(timeout=timeout + 5)
if not finished:
    self._send_json(conn, {"status": "error", ...})
    return
```

If the main thread is busy (modal dialog, long DRC, another script), `run_on_main` has **not yet started**. You reply "timeout" and close the socket — but the callable is still queued and **will execute later**, mutating the board with nobody listening. The agent, seeing a timeout, will very plausibly retry → the same script runs **twice**. For `track.add`/`via.add` that means duplicate geometry; for `net.delete_routing` it's merely wasteful; for footprint loading it's duplicated components.

**Fix:** guard with a cancellation flag checked at the top of `run_on_main`, and refuse new requests while one is in flight (`503 busy`) instead of queueing.

### 2.8 The bridge is unauthenticated arbitrary code execution 🔴

Anything on the machine that can open a TCP socket to `127.0.0.1:<port>` — and the port is sitting in a world-readable file at a fixed path — gets **arbitrary Python execution inside KiCad**, with full filesystem access via `os`. The zombie-port check only fires *after* your code has already been transmitted to the unknown listener.

**Fix:** write `<port>:<random_256bit_token>` into the port file, require the token in the JSON payload, reject mismatches, and `chmod 600` the file on POSIX.

### 2.9 `footprint_extractor.py` almost never finds the footprint 🟠

The cross-reference — the core anti-hallucination deliverable of Rule 5 — is gated on:

```python
if sym_name in footprints:
```

where `sym_name` comes from `(symbol "...")` (easyeda2kicad names it after the LCSC ID or part name) and `footprints` keys come from `.kicad_mod` **filenames** (named after the *package*, e.g. `ESP32-WROOM-32-N4_2P54`). These almost never match. In practice the report prints "No matching footprint found" and skips both the pad list and the PIN-TO-PAD CROSS-REFERENCE.

Note that `yaml_visualizer.parse_kicad_sym` **already solves this correctly** by reading the `LCSC Part` property into `lcsc_map`. `footprint_extractor.py` should do the same, plus read the symbol's `Footprint` property (`easyeda2kicad:<name>`) to link symbol → `.kicad_mod` deterministically.

Also: the report never prints the LCSC ID, so the agent cannot map `lcsc_id` in its YAML back to a symbol.

### 2.10 Pin names are not unique — the whole addressing scheme is unsound 🔴

`yaml_visualizer.parse_kicad_sym` stores pins in a dict keyed by **name**:

```python
pins[pin_name] = {...}
```

An ESP32 has multiple pins named `GND`. Four of them collapse to one. Worse, this is systemic, not local:

- `yaml_generation_rules.md` **Rule 11**: "Pin numbers, not function names… the pin identifier must be the physical pin number/label (e.g. `DRV1.7`, `MCU1.D2`)."
- `yaml_generation_rules.md` **Rule 13**: "Use the exact pin **name** from the `SYMBOL PINS` section."

These two rules **directly contradict each other**, and an LLM will oscillate between them within a single file. Meanwhile Rule 9A's mapping table has to resolve `MCU1.GND` to a specific pad — impossible when four pads share the name.

**Fix:** standardize on `<ID>.<pad_number>` everywhere (unambiguous, matches `FindPadByNumber`), and have the extractor emit `pin_number` as the canonical key with `name` as a comment/`purpose`. Rewrite Rule 13 to say "verify the *number* exists in the extractor output."

### 2.11 Template fields the engine silently ignores 🟠

`autoplacement_template.yaml` and `design_rules.md` promise features `PlacementConstraints` never parses:

| Field | Where promised | Engine reality |
| --- | --- | --- |
| `meta.board_bounds_mm` | template header | never read; bounds come only from Edge.Cuts |
| `tight_groups[].keep_clear_radius_mm` | template (`mcu_crystal`) | never read |
| `tight_groups[].members[].rotation_deg` | template | never applied |
| `keep_clear_zones[].center_mm/radius_mm` | template | only `owner_ref`+`margin_mm` used |
| `min_clearance_mm` | `design_rules.md` Rule 11 | not in schema, not parsed |
| `rotation_hint` | `design_rules.md` Rule 4 | schema uses `rotation_deg` |

Every one of these produces a silent no-op. The agent will emit them (the template tells it to), see no error, and assume the constraint applied.

### 2.12 Assorted correctness bugs 🟡

- **`autoplacer_engine.py`, summary block:** `print(f"Iterations run : {iteration+1} ...")` — `iteration` is undefined if `physics_params.iterations` is `0`, or if the loop body never executes. `NameError` after the board has already been mutated.
- **`autoplacer_engine.py`, STEP 8:** positions are written back, `pcbnew.Refresh()` is called, but **`board.BuildConnectivity()` is not** — ratsnest lines stay stale relative to the new positions.
- **`autoplacer_engine.py`, module scope:** `import yaml` at top level. PyYAML is **not guaranteed** in KiCad's bundled Python across platforms/installers. If absent, `import autoplacer_engine` raises and Rule 9B dies with an opaque traceback. Wrap it: `try: import yaml except ImportError: yaml = None` and degrade gracefully.
- **`autoplacer_engine.py`, STEP 4:** `FANOUT_THRESHOLD = max(20, int(len(footprints)*0.20))`. On a 15-component board GND has ~18 pads → below 20 → GND is *not* filtered → every component springs toward every other and the layout collapses into a blob. Lower the floor to ~6, or filter by net **name** heuristics (`GND`, `VCC`, `3V3`, `5V`) in addition to fanout.
- **`autoplacer_engine.py`:** `is_mounting_hole()` is defined and never called. Rule 9 of `design_rules.md` depends on mounting holes being handled; the only path is via explicit YAML anchors.
- **`currentboardfetcher.py`, `_extract_zone`:** calls `z.GetDoNotAllowCopperPour()`. Your own `API_method_names.md` `[ZONE METHODS]` list shows KiCad 10 has `GetDoNotAllowZoneFills` — no `CopperPour`. Wrapped in `_try`, so the **entire** `keepout` dict silently becomes `None`. Classic case of `_try` hiding a real bug.
- **`currentboardfetcher.py`, `apply_ops`:** `idx = build_index(board)` inside the per-op loop → O(N) index rebuild per op → O(N·M). With 200 track ops on a 100-footprint board under `settrace`, guaranteed watchdog kill mid-mutation.
- **`sexp_utils.py`, `_find_matching_close`:** the string-escape check `text[i-1] != '\\'` mishandles `"...\\\\"` (escaped backslash immediately before the closing quote) — parser desyncs. Rare with easyeda2kicad output, but it's a silent corruption path.
- **`sexp_utils.py`, `_extract_blocks`:** `re.compile(r'\(' + keyword + r'[\s"]')` matches occurrences **inside string literals** too (e.g. a description property containing `(pad "`). Should skip matches while inside a quoted region.
- **`footprint_extractor.py`, `extract_pads`:** pad-type alternation is `(smd|thru_hole|np_thru_hole|connect)`. Any other type is dropped silently rather than reported as unknown.
- **`yaml_visualizer.py`, `generate_svg`:** verify the SVG header survived the paste — the monodoc shows `xmlns="<http://www.w3.org/2000/svg>"` with stray angle brackets. If that's in the real source, every generated HTML is malformed. (Likely a Notion autolink artifact, but check.)
- **`yaml_visualizer.py`, component label:** drawn at local `x=0`, but the group transform is offset by `-min_x*SCALE`, so the label lands at the symbol *origin*, not its visual center — labels will drift off-center for asymmetric symbols.
- **`script_runner.py`, `_execute`:** `pcbnew.UpdateUserInterface(); pcbnew.Refresh()` are inside the `try`, so on a **partial failure** (half the footprints placed, then an exception) the canvas is never refreshed and the user sees a stale, misleading board. Move to `finally`.
- **`script_runner.py`, `_execute`:** the "fresh" namespace is `globals().copy()` of `script_runner` — it contains `wx`, `pcbnew`, `os`, `sys`, `json`, `traceback`. Agent code that forgets `import pcbnew` works by accident here and then fails elsewhere. Use a genuinely minimal dict.
- **`script_runner.py`, `stop_agent_server`:** unconditionally deletes `PORT_FILE`. Open two abIDE windows, close either one, and the survivor becomes undiscoverable. Only delete if the file's port matches yours.
- **`script_runner.py`, `log_debug`:** unsynchronized appends from the server thread and main thread — interleaved/torn lines.
- **Watchdog timeout inconsistency:** `bridge_api_manual.md` states a hard **15 s** limit; `_execute` defaults to 15 but the agent-path passes `req["timeout"]` which the CLI defaults to **30**. The doc and the code disagree about the contract the agent is being taught.
- **Undo stack:** direct SWIG mutation + `Refresh()` bypasses KiCad's commit framework entirely. **Ctrl+Z will not undo agent edits and may desync the editor.** This is not documented anywhere for users. The `.kicad_pcb` backup in `apply_ops` is your only safety net — and Rules 9A/9B don't use `apply_ops`.

---

## 3. Codebase Improvements & Best Practices

**Error handling**

- `_try()` is used far too liberally in `currentboardfetcher.py`. It converts real API mismatches (§2.12, `GetDoNotAllowCopperPour`) into `None` values that flow downstream as "this board has no keepouts." Split it: `_try_optional()` for genuinely version-variant APIs, and a strict path that records a structured warning into `state["errors"]` — which you already have and barely use.
- `PlacementConstraints.__init__` prints "Running unconstrained" and returns on a missing/invalid YAML. For an autonomous agent, that must be a **raised exception**. Add `strict=True`.
- Add a real schema validator for both YAMLs (`pydantic` or hand-rolled). Reject unknown keys loudly — that alone would have surfaced every issue in §2.11.

**Logging**

- Replace all `print()` in the engine with a `logging` logger writing to both the abIDE console and a rotating file. Agents parse stdout; give them a machine-readable tail (`RESULT: {json}`) alongside the human summary.
- Emit a structured result object from `run_physics_placer` (`{converged, iterations, ratsnest_before/after, overlaps_after, unresolved_refs: [...]}`) instead of only printing. `unresolved_refs` is the single most valuable field — it's how the agent learns §1.1 broke.

**Performance**

- Spatial grid for repulsion + overlap counting (§2.6).
- Precompute `radii`, courtyard polys once; don't call `GetBoundingBox()` in the loop.
- Cap `iterations` adaptively by component count so the watchdog is never the thing that stops you.
- `get_full_board_state`: add `include_pads=False` to `summary` mode. Pads dominate the payload and the agent rarely needs them post-9A.

**KiCad-specific pitfalls you're hitting**

1. **No `BuildConnectivity()` after moves** (§2.12) — ratsnest desync.
2. **No commit/undo integration** — document it loudly, and always snapshot a `.kicad_pcb` backup before any mutation, not just in `apply_ops`.
3. **Heavy compute on the GUI thread** (§2.6) — the root cause of the watchdog existing at all. Fix the cause, not the symptom.
4. **Module caching:** Rule 9B does `import autoplacer_engine` in a *stateless* namespace, but Python's `sys.modules` cache is process-global. Edit `autoplacer_engine.py` mid-session and the change **will not take effect**. Add `importlib.reload(autoplacer_engine)` to the Rule 9B snippet.
5. **SWIG lifetime:** you correctly prefer `Add()` over `AddNative()` — keep that rule prominent. Also warn against holding Python references to items after `board.Remove()`; `apply_ops` rebuilds the index, which happens to save you.
6. **`GetFPID().GetLibItemName().wx_str()`** returns a `UTF8`, not `str`. Works, but normalize with `str(...)` for safety across versions.

**Portability** 🟠

Every documented command is a **PowerShell here-string**. `mkdir -Force`, `@'...'@ |`. macOS and Linux agents cannot follow `SKILL.md` at all. Add a bash column to every command block, or ship a tiny cross-platform `abide` CLI wrapper and document only that.

---

## 4. AI Prompt & Skill Optimization

### 4.1 Blocking defects in `SKILL.md`

| # | Problem | Impact |
| --- | --- | --- |
| 1 | `<PATH_TO_YOUR_PLUGIN>` and `<PROJECT_DIR>` are used in 6 commands and **never defined or discovered** | Agent guesses paths → every command fails |
| 2 | Rule 6 says "the **13** expert engineering rules"; `yaml_generation_rules.md` has **14** | Agents will stop at 13 and skip Rule 14 (board dimensions) — which is a *blocking* question |
| 3 | Rule 8 mandates `oracle.py --batch`, which cannot run (§2.1) | Hard stop |
| 4 | Rule 9B never says where to write the constraints YAML (§1.2) | Silent no-op |
| 5 | Tool names are IDE-specific: `write_to_file`, `grep_search`, `view_file`, `run_command` | Agents without those exact tools stall |
| 6 | Rule 2 (`write_to_file task.md`) contradicts `AGENTS.md` Zero Temp Files | Agent freezes or ignores a policy |
| 7 | No reference-designator assignment step anywhere (§1.1) | 9B is fully decoupled from 9A |
| 8 | Blocking questions scattered: LCSC IDs (Rule 3), board dims + layers (yaml rule 14) | Multi-round ping-pong instead of one intake |
| 9 | No failure/rollback protocol for any rule | Agent improvises on error |
| 10 | Rule 9A says "draw board outline, set copper layers" only in a **code comment** | Not treated as a requirement; layer count from `board_config.layers` never applied |

### 4.2 Rule-level rewrites

**Add a new Rule 0 — Environment Resolution (before everything):**

> Resolve and record these three values before any other step. Do not proceed until all three are known:
> 

> - `PLUGIN_DIR` — the directory containing `kicad_agent_bridge.py`. Discover it by running `python -c "import pcbnew,os;print(os.path.join(os.path.dirname(pcbnew.__file__),'plugins'))"` or ask the user.
> 

> - `PROJECT_DIR` — provided by the user (Rule 1).
> 

> - `SHELL` — `powershell` or `bash`. Use the matching command syntax below.
> 

> Echo all three back to the user in one message and wait for confirmation.
> 

**Merge all blocking questions into a single Rule 3 — Intake.** One message, one form:

> Before any downloads, ask the user for **all** of the following in a single message:
> 

> 1. `PROJECT_DIR`
> 

> 2. Board width × height in mm
> 

> 3. Layer count (2 or 4)
> 

> 4. For every component: description **and** LCSC part number
> 

> Do not proceed until every field is answered. Never guess an LCSC ID.
> 

**Rewrite Rule 6 to make the two YAMLs and their paths explicit:**

> Write exactly two files:
> 

> - `<PROJECT_DIR>/circuit_blueprint.yaml` — schema in `references/yaml_generation_rules.md` (**14 rules**, all mandatory)
> 

> - `<PROJECT_DIR>/placement_constraints.yaml` — schema in `references/autoplacement_template.yaml`
> 

> 
> 

> Every component in `circuit_blueprint.yaml` **must** carry a `ref:` field holding its KiCad reference designator (`U1`, `C1`, `J1`, `Y1`, `H1`). `placement_constraints.yaml` uses **only** those `ref` values. Rule 9A must apply them via `SetReference()`.
> 

**Rewrite Rule 9B's command to pass the path and reload:**

```powershell
@'
import importlib, autoplacer_engine, pcbnew
importlib.reload(autoplacer_engine)
autoplacer_engine.run_physics_placer(yaml_path=r"<PROJECT_DIR>\placement_constraints.yaml")
pcbnew.GetBoard().BuildConnectivity(); pcbnew.Refresh(); pcbnew.GetBoard().Save()
'@ | python <PLUGIN_DIR>\kicad_agent_bridge.py --stdin --timeout 120
```

**Add a Rule 9A.5 — Netlist Verification** (closes §1.4): re-fetch state, assert every YAML net exists with the expected pad count, report any diff, halt on mismatch.

**Add a global Failure Protocol section:**

> If any command returns a non-zero result, an `EXECUTION ERROR`, or `KICAD NOT CONNECTED`:
> 

> 1. Do **not** retry the same command more than once.
> 

> 2. Do **not** improvise an alternative API call.
> 

> 3. Report the exact stdout to the user and stop.
> 

> 4. Never proceed to the next Rule with a failed prerequisite.
> 

### 4.3 `yaml_generation_rules.md`

- **Resolve the Rule 11 / Rule 13 contradiction** (§2.10). Pick pad numbers. Then Rule 13 becomes: "verify the pad number appears in the extractor's `FOOTPRINT PADS` section."
- Rule 1 vs Rule 2 (`assumptions_and_gaps` vs `unresolved_or_missing`) is a genuinely subtle distinction stated abstractly. Add two concrete worked examples — LLMs mirror examples far more reliably than definitions.
- The header says "13 rules"; there are 14. Fix, and number the list explicitly `Rule 1 … Rule 14`.
- Rule 9 ("respond with ONLY a single fenced YAML block") conflicts with Rule 2 of `SKILL.md` (maintain a `task.md` checklist) and with Rule 7's approval dialogue. Scope it: "when *emitting the blueprint*, output only the YAML block."

### 4.4 `design_rules.md`

Mostly good — clear zones, clear priority ordering, and the `ZONE_MAP` fractions in `autoplacer_engine.py` match the documented percentages. Three fixes:

- Rules 4 and 11 reference `rotation_hint` and `min_clearance_mm`, which don't exist in the schema (§2.11). Delete or implement.
- Rules 1 and 5 tell the agent to use `anchor` + `zone` — which is a **no-op for locked parts** (§2.2). Either fix the engine or change the doc to require `position_mm` on every locked anchor.
- Rule 2's heuristic ("caps sharing a VCC/VDD net with an IC are its decoupling caps") requires net data the agent has *only* from the YAML it is currently authoring. Restate it as: "derive decoupling groups from `power_distribution` in your own blueprint."

### 4.5 `bridge_api_manual.md`

- Fix the 15 s vs 30 s inconsistency (§2.12).
- The warning "Do not use `time.sleep()`" is right but incomplete — add: "and do not call `wx.MessageBox`, `ShowModal`, or any blocking dialog; it will deadlock the bridge."
- Add: "Long operations (auto-placement, full state fetch) must pass an explicit `--timeout`; the default will kill them."

---

## Priority Fix Order

1. `oracle.py` file path (§2.1) — nothing downstream works without it.
2. Reference-designator bridge between the two YAMLs (§1.1) — silently invalidates all of 9B.
3. Constraints-YAML path + `run_physics_placer(yaml_path=...)` (§1.2).
4. Bridge auth token (§2.8) and the phantom-execution race (§2.7).
5. Replace the `settrace` watchdog; move physics off the GUI thread (§2.6).
6. Pin-number vs pin-name contradiction (§2.10) and `footprint_extractor` symbol↔footprint matching (§2.9).
7. Hookean forces + size-aware repulsion (§2.4, §2.5).
8. `SKILL.md` Rule 0 + unified Intake + Failure Protocol (§4.2).

The bones are good. The failures are almost all **contract mismatches between documents and code**, not bad engineering — which is the best kind of problem to have, because a schema validator plus one honest end-to-end dry run on a 5-component board would surface roughly 80% of this list.