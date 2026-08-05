# abIDE — Architecture Review & Minimal Fix Plan

<aside>
🎯

Scope: no new features, no rewrites. Every change below is either a **delete**, a **few-line swap**, or a **line in [SKILL.md](http://SKILL.md)**. Total net code delta is roughly **−80 / +140 lines**, plus one 24k-line file removed. Ordered by "how likely is this to put the agent in an error loop".

</aside>

## 0. Verdict per file

| File | Verdict | Reason |
| --- | --- | --- |
| `json2sch.py` | 3 targeted fixes | Project identity bug silently breaks annotation |
| `kicad_pins.py` | +1 helper, 2-line gate fix | Becomes the single path resolver |
| `kicad_lib_init.py` | **leave as is** | Genuinely clean, version-derived, non-destructive |
| `Autoplacer/oracle.py` | Rewire source | Two conflicting sources of truth |
| `Autoplacer/script_runner.py` | 3-line watchdog fix | Watchdog is currently swallowable |
| `Autoplacer/kicad_agent_bridge.py` | +exit codes, +`--state` | Silent failure + no board-state access |
| `Autoplacer/currentboardfetcher.py` | 5 targeted fixes | Solid design, a few runtime traps |
| `Autoplacer/macro_placer.py` | −25 lines | Duplicates `--json-ops` |
| `Autoplacer/pcb_snapshot.py` | 2 fixes | Hardcoded path + stale snapshot |
| `Autoplacer/freerouting_runner.py` | 3 guards | Silent failure path |
| `all_functionNameWithDetailedUsecase.py` | **delete** | It is KiCad's own `pcbnew.py`; token bomb + stale |
| `SKILL.md` | rewrite | This is where 80% of the value is |

---

# 1. P0 — the things that actually cause loops

## 1.1 Project identity is taken from the folder name

`json2sch.py` writes symbol instances with `project.name` (the **folder**). KiCad resolves references against the `.kicad_pro` **stem**. When `F:/pcb/rev_a/` contains `sensor_node.kicad_pro`, every symbol comes back as `R?`, `C?` — annotation appears lost. The agent then re-annotates, re-runs, re-fails. This is the single most likely loop in the repo.

Same function also picks the schematic by folder-name match, falling back to *alphabetically first* `.kicad_sch` — on a multi-sheet project that overwrites a sub-sheet.

**Before**

```python
def detect_header(project: Path):
    files = sorted(project.glob("*.kicad_sch"))
    preferred = [f for f in files if f.stem == project.name] or files
    if not preferred:
        fail(f"no .kicad_sch in {project} -- create the project in KiCad first")
    path = preferred[0]
    ...

# in main():
root_sch, version, gen_version = detect_header(project)
...
embedded, symbols, ... = build(design, libs, version, project.name, root_uuid)
```

**After**

```python
def detect_project(project: Path):
    """Identity comes from the .kicad_pro. Never from the folder name."""
    pros = sorted(project.glob("*.kicad_pro"))
    if not pros:
        fail(f"no .kicad_pro in {project} -- create the project in KiCad first")
    if len(pros) > 1:
        fail(f"{len(pros)} .kicad_pro files in {project} -- one project per folder")
    stem = pros[0].stem
    root_sch = project / f"{stem}.kicad_sch"
    if not root_sch.is_file():
        fail(f"{root_sch.name} missing -- open the project in KiCad once so it writes the root sheet")
    text = root_sch.read_text(encoding="utf-8", errors="replace")[:4000]
    version = re.search(r"\(\s*version\s+([0-9]+)\s*\)", text)
    if not version:
        fail(f"cannot read the schematic format version from {root_sch.name}")
    gen = re.search(r'\(\s*generator_version\s+"([^"]+)"', text)
    return stem, pros[0], root_sch, int(version.group(1)), (gen.group(1) if gen else None)

# in main():
project_name, pro_file, root_sch, version, gen_version = detect_project(project)
...
embedded, symbols, ... = build(design, libs, version, project_name, root_uuid)
...
if a.apply_netclasses:
    print(apply_netclasses(pro_file, design))   # pass the resolved file, don't re-glob
```

`apply_netclasses` loses its own glob and takes `path: Path` directly.

## 1.2 The Oracle has two different sources of truth

`oracle.py` (CLI) parses the pasted `all_functionNameWithDetailedUsecase.py`. `script_runner._execute_oracle` (GUI/bridge) parses the **live** `pcbnew.__file__`. Two answers for the same question, and the pasted one goes stale the day KiCad updates. That is a hallucination generator, and it is the file eating your token budget.

**Before**

```python
file_path = os.path.join(os.path.dirname(__file__), "all_functionNameWithDetailedUsecase.py")
if not os.path.exists(file_path):
    print(f"Error: Could not find {file_path}")
    sys.exit(1)
```

**After**

```python
def find_pcbnew_source():
    """The live pcbnew.py is the only source of truth. Never a pasted copy."""
    try:
        import pcbnew                       # succeeds inside KiCad's python
        p = pcbnew.__file__
        if p.endswith((".pyc", ".pyo")):
            p = p[:-1]
        if os.path.isfile(p):
            return p
    except Exception:
        pass
    try:                                    # optional escape hatch, still not hardcoded
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kicad_pins import load_paths
        d = load_paths().get("kicad_python_dir")
        if d and (d / "pcbnew.py").is_file():
            return str(d / "pcbnew.py")
    except Exception:
        pass
    return None

# in __main__:
file_path = find_pcbnew_source()
if not file_path:
    sys.exit('Live pcbnew.py not reachable from this interpreter.\n'
             'Use the bridge instead (it runs inside KiCad, always resolves):\n'
             '  python "<PLUGIN_DIR>/Autoplacer/kicad_agent_bridge.py" --oracle "BOARD GetTracks"\n'
             'Or add "kicad_python_dir" to kicad_paths.json.')
```

**Plus: stop the guess-loop on a miss.** Right now `METHOD NOT FOUND` gives the agent nothing, so it guesses again. Twelve lines fix that:

```python
def suggest(file_content, method_name, limit=8):
    frag = method_name[:6].lower()
    if not frag:
        return ""
    names = sorted({m.group(1) for m in re.finditer(r"\n[ \t]*def (\w+)", file_content)
                    if frag in m.group(1).lower()})
    if names:
        return "\n  did you mean: " + ", ".join(names[:limit])
    return "\n  no similar name -- grep all_functionName.md for the real spelling"

# both NOT FOUND returns become:
return f"[{class_name}.{method_name}] -> METHOD NOT FOUND.{suggest(file_content, method_name)}\n"
```

## 1.3 The watchdog is swallowable — this is the real infinite loop

`currentboardfetcher._try()` wraps nearly every call in `except Exception`. The watchdog raises a plain `Exception`. So a timeout during `get_full_board_state` is **caught and discarded**, the watchdog fires again on the next call, gets discarded again, forever. KiCad's main thread never returns, the client times out, the agent retries, and you are stuck.

Second problem: `return trace_calls` from a `call` event turns on **line tracing for every frame** — that is the reason board extraction feels slow. Returning `None` keeps call-level tracing only.

**Before** (`script_runner._execute`)

```python
def trace_calls(frame, event, arg):
    instruction_count[0] += 1
    if instruction_count[0] > 1000:
        instruction_count[0] = 0
        if time.time() - start_time > timeout_seconds:
            raise Exception(f"Execution timed out ({timeout_seconds}s limit exceeded). ...")
    return trace_calls
...
except Exception:
    error_tb = traceback.format_exc()
```

**After**

```python
class AbideTimeout(BaseException):
    """BaseException on purpose: `except Exception` in user code must NOT swallow it."""

def trace_calls(frame, event, arg):
    instruction_count[0] += 1
    if instruction_count[0] >= 200:
        instruction_count[0] = 0
        if time.time() - start_time > timeout_seconds:
            raise AbideTimeout(
                f"Timed out after {timeout_seconds}s -- killed by the abIDE watchdog. "
                "The board may be partially modified; a backup is in pcb_brain/backups/.")
    return None      # <-- call-level tracing only. Do not trace every line.
...
except AbideTimeout as e:
    error_tb = f"AbideTimeout: {e}\n"
except BaseException:
    error_tb = traceback.format_exc()
```

<aside>
⚠️

`except BaseException` is deliberate — it also lets `SystemExit` from the `--json-ops` snippet mark the run as failed (see 1.4). The `finally` block already restores stdout/stderr/trace, so nothing leaks.

</aside>

Note the honest limit, and put it in [SKILL.md](http://SKILL.md): `sys.settrace` cannot interrupt a long **C/SWIG** call (zone fill, SES import). The socket timeout is the real backstop there.

## 1.4 The bridge always exits 0

`kicad_agent_bridge.py` prints `--- KICAD ERROR ---` and then returns normally. `$LASTEXITCODE` is 0. `macro_placer` checks `returncode == 0` and reports **SUCCESS on a failed placement**. The agent proceeds on a false premise — classic loop fuel.

**Before**

```python
status = resp.get("status", "unknown")
output = resp.get("output", "")
print(f"--- KICAD {status.upper()} ---")
print(output)
...
run_kicad_code(args.script_path, args.stdin, args.code, args.oracle,
               args.timeout, args.keep_state, args.reset_state)
```

**After**

```python
# every early return in run_kicad_code becomes `return False`; the happy path:
print(f"--- KICAD {status.upper()} ---")
print(output)
return status == "success"
...
ok = run_kicad_code(args.script_path, args.stdin, args.code, args.oracle,
                    args.timeout, args.keep_state, args.reset_state)
sys.exit(0 if ok else 1)
```

And close the chain inside the `--json-ops` snippet so a failed op reaches the shell:

```python
"if result.get('applied') and not result.get('failed'):\n"
"    print('\\nJSON Ops SUCCESS!')\n"
"else:\n"
"    print('\\nJSON Ops FAILED:', result.get('problems') or result.get('failed'))\n"
"    raise SystemExit(1)\n"
```

## 1.5 RULE 8 tells the agent to do something the code rejects

[SKILL.md](http://SKILL.md): *"Send a `net.delete_routing` JSON operation to delete all existing tracks."* The handler does `_need(op, "net")` and hard-fails. The agent has no way to wipe routing before a re-route, so it invents net lists and loops.

**Before**

```python
def _op_delete_net_tracks(board, idx, op, dry):
    _need(op, "net")
    _resolve_net(idx, op["net"])
    ...
    for t in list(board.GetTracks()):
        if _try(lambda: t.GetNetname()) != op["net"]:
            continue
    ...
    return "delete %d routed items on net '%s'" % (len(victims), op["net"])
```

**After**

```python
def _op_delete_net_tracks(board, idx, op, dry):
    net = op.get("net")                 # omit 'net' -> wipe ALL routing (re-route loop)
    if net:
        _resolve_net(idx, net)
    layers = op.get("layers")
    victims = []
    for t in list(board.GetTracks()):
        if net and _try(lambda: t.GetNetname()) != net:
            continue
        if layers and _try(lambda: t.GetLayerName()) not in layers:
            continue
        if t.IsLocked() and not op.get("force"):
            continue
        victims.append(t)
    if not dry:
        for t in victims:
            board.Remove(t)
    return "delete %d routed items on %s" % (
        len(victims), ("net '%s'" % net) if net else "ALL nets")
```

## 1.6 The biggest architectural gap: the agent is told to guess

RULE 6 hands the agent an SVG and says *"ratsnest lines are not visible, so trace connections mentally"*, then asks for exact millimetre coordinates. Meanwhile `currentboardfetcher.get_full_board_state()` already returns **every footprint position, rotation, bbox, courtyard and pad coordinate**, and `ai_context()` already bundles it with the op schema. It is written, tested, and completely unreachable from the CLI.

This is the fix with the highest payoff per line. Ten lines in the bridge:

```python
parser.add_argument("--state", choices=["summary", "full"],
                    help="Dump live board state (footprints, pads, nets, exact positions) to pcb_brain/")
...
if args.state:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    args.code = (
        "import sys, json, importlib\n"
        f"sys.path.insert(0, r'{script_dir}')\n"
        "import currentboardfetcher as cbf; importlib.reload(cbf)\n"
        f"b = cbf.ai_context(mode='{args.state}')\n"
        "print(json.dumps(b['state']['stats'], indent=1))\n"
    )
    args.timeout = max(args.timeout, 120.0)
```

`ai_context` already prints `[pcb_brain] ai_context(summary) -> <path> (NN KB)`, so the agent gets a **file path plus stats** instead of a megabyte on stdout. It reads the file only when it needs coordinates. Token-safe, zero new features.

## 1.7 F8 has no headless path — say so, loudly

There is no `kicad-cli` command and no `pcbnew` Python entry point for *Update PCB from Schematic*. An agent that does not know this will script, fail, script differently, fail, forever. Same for *open abIDE*. These must be declared as hard human checkpoints in [SKILL.md](http://SKILL.md) (section 4).

---

# 2. P1 — robustness, still minimal

## 2.1 The one hardcoded path in the repo

`pcb_snapshot.py` has `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe`, and `_op_board_drc` reconstructs it by string-splitting `kicad_symbol_dir` on `"share"`. Both go through one resolver.

`kicad_paths.json` gains two optional keys:

```json
{
  "kicad_config_dir":    "",
  "kicad_symbol_dir":    "",
  "kicad_footprint_dir": "",
  "kicad_cli":           "",
  "kicad_python_dir":    ""
}
```

`kicad_pins.py` — `load_paths` must stop treating every value as a directory, then gets a sibling for tools:

```python
_FILE_KEYS = {"kicad_cli"}

# inside load_paths():
for key, value in raw.items():
    if not str(value).strip() or key in _FILE_KEYS:
        continue
    ...

def load_cli(key="kicad_cli", exe="kicad-cli"):
    """Explicit entry in kicad_paths.json, else PATH. Never a guessed install dir."""
    raw = {}
    if CONFIG.exists():
        try:
            raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    value = str(raw.get(key, "")).strip()
    if value:
        p = Path(value).expanduser()
        if p.is_file():
            return str(p)
        raise ValueError(f"{CONFIG.name}: '{key}' is not an existing file -> {p}")
    found = shutil.which(exe)
    if found:
        return found
    raise ValueError(f"'{exe}' not on PATH. Put its full path in {CONFIG.name} under \"{key}\".")
```

(`import shutil` at the top of `kicad_pins.py`.)

**`_op_board_drc` before / after**

```python
# BEFORE - guesses the install root by splitting a symbol path on "share"
kicad_cli = "kicad-cli"
try:
    paths_json = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kicad_paths.json")
    if os.path.exists(paths_json):
        ... sym_dir.split("share")[0] ...
except Exception:
    pass
cmd = [kicad_cli, "pcb", "drc", "--all-track-errors", board_path]
res = subprocess.run(cmd, capture_output=True, text=True)
return f"CLI DRC Check Completed. Output:\n{out}"
```

```python
# AFTER
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kicad_pins import load_cli
try:
    kicad_cli = load_cli()
except Exception as e:
    return f"DRC skipped: {e}"
pcbnew.SaveBoard(board_path, board)
cmd = [kicad_cli, "pcb", "drc", "--all-track-errors", "--exit-code-violations", board_path]
res = subprocess.run(cmd, capture_output=True, text=True)
out = (res.stdout or res.stderr).strip()
return f"DRC exit={res.returncode} (0 = clean)\n{out}"
```

`--exit-code-violations` is the difference between the agent *reading* a number and the agent *interpreting prose*. Add `import sys` to `currentboardfetcher.py` (currently missing).

## 2.2 `apply_netclasses` backs up the file it already modified

**Before**

```python
data = json.loads(path.read_text(encoding="utf-8"))
settings = data.setdefault("net_settings", {})
settings["classes"] = [...]
settings["netclass_patterns"] = [...]
path.with_name(path.name + ".bak").write_text(json.dumps(data, indent=2), encoding="utf-8")
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

The `.bak` is byte-identical to the new file. There is no rollback.

**After**

```python
original = path.read_text(encoding="utf-8")
path.with_name(path.name + ".bak").write_text(original, encoding="utf-8")   # back up FIRST
data = json.loads(original)
settings = data.setdefault("net_settings", {})
settings["classes"] = [dict(name=name, **spec) for name, spec in design["netclasses"].items()]
settings["netclass_patterns"] = [{"netclass": net["class"], "pattern": name}
                                 for name, net in design["nets"].items()
                                 if net["class"] != "Default"]
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

## 2.3 `pcb_snapshot.py` can snapshot the wrong board, or a stale one

Two independent problems. It takes `glob("*.kicad_pcb")[0]`, and it exports **from disk** — after a manual F8 the live board is unsaved, so the agent gets an empty or outdated SVG and places parts against fiction.

**After**

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kicad_pins import load_cli

def resolve_board(project_dir):
    pros = sorted(glob.glob(os.path.join(project_dir, "*.kicad_pro")))
    if not pros:
        sys.exit(f"Error: no .kicad_pro in {project_dir}")
    stem = os.path.splitext(os.path.basename(pros[0]))[0]
    pcb = os.path.join(project_dir, stem + ".kicad_pcb")
    if not os.path.exists(pcb):
        sys.exit(f"Error: {stem}.kicad_pcb not found -- open the PCB editor once and save.")
    return pcb, stem

def save_live_board():
    """The SVG is exported from disk. Flush KiCad's in-memory board first."""
    bridge = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kicad_agent_bridge.py")
    code = ("import pcbnew\n"
            "b = pcbnew.GetBoard()\n"
            "pcbnew.SaveBoard(b.GetFileName(), b)\n"
            "print('saved', b.GetFileName())\n")
    r = subprocess.run([sys.executable, bridge, "--code", code, "--timeout", "60"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("WARN: could not save the live board through abIDE.\n"
              "      This SVG shows the LAST SAVED state.\n"
              "      Press Ctrl+S in the PCB editor (or open abIDE) and rerun.")

# in main():
pcb_file, base_name = resolve_board(project_dir)
save_live_board()
kicad_cli = load_cli()
```

Best-effort by design: if abIDE is closed you get a warning, not a crash.

## 2.4 Timeouts are set for the wrong workload

`apply_ops(verify=True)` runs `get_full_board_state` **twice** plus an O(n²) tangle score. On anything real that blows past 30 s, the watchdog kills it **mid-write**, and the board is left half-modified. Then the agent "fixes" a board that is in an undefined state.

| Call site | Before | After |
| --- | --- | --- |
| `macro_placer.send_to_kicad` | `--timeout 30` | `--timeout 180` |
| `freerouting_runner` DSN export | default 30 | `--timeout 120` |
| `freerouting_runner` SES import | default 30 | `--timeout 300` |
| `--json-ops` (any) | default 30 | pass `--timeout 180` from callers |
| `--state full` | default 30 | forced to ≥120 (see 1.6) |

No code restructuring — `run_kicad_code` already forwards `timeout` into the payload and the server already adds a 5 s grace, the client 10 s.

## 2.5 `macro_placer` reimplements `--json-ops` and lies about success

`send_to_kicad` base64-encodes ops into an inline snippet — an exact duplicate of what `kicad_agent_bridge.py --json-ops` already does, with a different timeout and a different `apply_ops` signature. That is the "pasted from different chats" desync you suspected. It also returns `returncode == 0`, which was always true.

**After** (drop `import base64`, ~25 lines gone)

```python
def send_to_kicad(ops, project_dir, timeout=180):
    """One path into KiCad: write ops.json, let the bridge apply it."""
    bridge = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kicad_agent_bridge.py")
    ops_path = os.path.join(project_dir, "ops_macro_placer.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump(ops, f, indent=2)
    print(f"\nWrote {ops_path}\nSending to KiCad via bridge...")
    r = subprocess.run([sys.executable, bridge, "--json-ops", ops_path,
                        "--timeout", str(timeout)], capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode == 0        # now meaningful, thanks to 1.4

# call site:
success = send_to_kicad(ops, project_dir)
```

Bonus: the agent can now inspect and hand-edit `ops_macro_placer.json` — same artefact format it uses in RULE 6.

## 2.6 `freerouting_runner` fails silently in three places

**Before**: `--jar freerouting.jar` is resolved against the **current working directory**; a missing/empty `.ses` still gets imported; a stale `.ses` from a previous run gets re-imported as if it were new.

**After**

```python
DEFAULT_JAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freerouting.jar")

def run_freerouting(project_dir, jar_path=None):
    jar_path = os.path.abspath(jar_path or DEFAULT_JAR)
    if not os.path.isfile(jar_path):
        sys.exit(f"freerouting.jar not found at {jar_path}\n"
                 f"Drop it in {os.path.dirname(DEFAULT_JAR)} or pass --jar <path>.")
    for stale in (dsn_path, ses_path):          # never re-import last run's result
        if os.path.exists(stale):
            os.remove(stale)
    ...
    # after java:
    if not os.path.exists(ses_path) or os.path.getsize(ses_path) < 100:
        sys.exit("FreeRouting produced no usable .ses -- nothing imported, board untouched.")
```

and both bridge calls get `"--timeout", "120"` / `"300"` plus a `returncode` check instead of substring-matching `"FAILED"` in stdout.

## 2.7 `board.set_size` passes dry-run then fails at runtime

The dry run only checks that `width`/`height` exist. The Edge.Cuts lookup — a manual scan over `pcbnew.PCB_LAYER_ID_COUNT` — happens only in the apply phase, **after earlier ops have already mutated the board**. A partial apply is the worst possible state to hand back to an agent.

**After**

```python
def _op_board_set_size(board, idx, op, dry):
    _need(op, "width", "height")
    edge_cuts = _resolve_layer(idx, "Edge.Cuts")     # validated during DRY RUN too
    w, h = op["width"], op["height"]
    ox, oy = op.get("origin_x", 0.0), op.get("origin_y", 0.0)
    if not dry:
        for drw in list(board.GetDrawings()):
            if drw.GetLayer() == edge_cuts:
                board.Remove(drw)
        pts = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
        for i in range(4):
            seg = pcbnew.PCB_SHAPE(board)
            seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
            seg.SetLayer(edge_cuts)
            seg.SetStart(mk_point(*pts[i]))
            seg.SetEnd(mk_point(*pts[(i + 1) % 4]))
            seg.SetWidth(from_mm(0.1))
            board.Add(seg)
    return f"set board outline {w}x{h} mm at ({ox},{oy}) [REPLACES existing Edge.Cuts]"
```

The `[REPLACES...]` in the dry-run text matters: the agent sees the destruction before approving it.

## 2.8 `--verify` can pass while verifying nothing

RULE 3 calls this a MANDATORY GATE, but `SKIP ... NOT VERIFIED` does not increment `failures`, and `load_paths()` is called with **no required keys** — so an unset `kicad_footprint_dir` turns the whole gate into a no-op that exits 0.

**Before**

```python
cfg = load_paths() if a.verify else {}
...
if pretty is None:
    print(f"SKIP  {label}: footprint library '{fp_library}' not reachable -- NOT VERIFIED")
    continue
```

**After**

```python
cfg = load_paths("kicad_footprint_dir") if a.verify else {}
...
if pretty is None:
    print(f"FAIL  {label}: footprint library '{fp_library}' not reachable "
          f"-- add it to fp-lib-table or fix kicad_footprint_dir")
    failures += 1
    continue
```

Two lines, and the gate becomes a gate.

## 2.9 Every schematic is A2

`SHEET_W` is a constant `380.0`, so `width = 380 + 50.8 = 430.8` always exceeds A3 (420) and always lands on A2 — even for a three-resistor design. Cosmetic, but it makes generated sheets look wrong and invites the agent to "fix" it.

**After** — `build()` already computes `box_right` per group; just remember the max:

```python
sheet_bottom = MARGIN
sheet_right = MARGIN                                     # NEW
for group in design["groups"]:
    ...
    sheet_right = max(sheet_right, box_right + GROUP_PAD)   # NEW, next to sheet_bottom update
...
width = sheet_right + MARGIN                             # was: SHEET_W + MARGIN
```

`SHEET_W` stays as the wrap threshold. One variable, three lines.

## 2.10 Tangle score runs even when the apply failed

It is O(pads²) per net and it runs unconditionally at the end of `apply_ops` — including after an abort, which is exactly when you least want a 20-second computation on a half-written board. It is also dominated by GND, where the number is meaningless.

**After**

```python
if verify and failed is None:
    result["tangle_score"] = _tangle_score(board)
    print(f"--- TANGLE SCORE: {result['tangle_score']} mm ---")
```

and inside the helper, one guard: `if len(pads) < 2 or len(pads) > 60: continue  # pours skew the metric and cost O(n^2)`.

## 2.11 Your machine paths are in the repo

`kicad_paths.json` currently ships `C:/Users/HP/AppData/Roaming/kicad/10.0`. Ship the template, ignore the real one — `load_paths` already prints a perfect setup message when the file is missing, so first run guides the user instead of silently using someone else's paths.

---

# 3. Files: delete / add / ignore

**Delete**

- `Autoplacer/all_functionNameWithDetailedUsecase.py` — it is KiCad's own `pcbnew.py`. It is 24k lines of tokens, it is GPL code vendored into your repo, and after 1.2 nothing reads it.
- `currentboardfetcher.run_drc()` — a dead stub that prints *"DRC explicitly disabled to prevent KiCad 10 crash"* while `board.drc_check` happily runs DRC. An agent reading both will not know which to believe.

**Keep**

- `Autoplacer/all_functionName.md` — this is genuinely useful: a cheap *"does `BOARD.GetTracks` exist at all"* index the agent can grep before spending a bridge round-trip. RULE 7 should point at it first.

**Add**

- `kicad_paths.example.json` with the five keys, all empty.

**`.gitignore`**

```
__pycache__/
*.pyc
*.pyo
*.pyd
*.log
*.jar
*.port
kicad_paths.json
Autoplacer/all_functionNameWithDetailedUsecase.py
pcb_brain/
ops*.json
board.dsn
board.ses
*_board.svg
*.bak
```

**Nits worth 10 seconds each**

- `currentboardfetcher.py`'s docstring says `pcb_brain.py`. Rename the docstring, not the file — error messages already say `[pcb_brain]`.
- `import time` in `currentboardfetcher.py` is unused.
- In `validate()`, `design["nc_resolved"] = nc` aliases the list that the unused-pin loop later appends to. It works, but add `# same list object -- later appends land here on purpose` so nobody "fixes" it.
- Generated schematics use the id-less `(property ...)` form: KiCad 7+ only. Worth one line in [SKILL.md](http://SKILL.md).

---

# 4. [SKILL.md](http://SKILL.md) — rewritten

This is where the leverage is. Changes: a new RULE 0 (session contract), a human-checkpoint table, a new RULE 9 (error recovery), the required-keys list for `design.json`, corrected RULE 5 numbering, and RULE 6 rebuilt around real board state instead of eyeballing an SVG. The broken code fence and the orphaned Bangla line in RULE 4 are folded into the flow.

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

---

# 5. Post-change verification

Run in order; each should be green before the next.

1. `python kicad_pins.py "<PROJECT_DIR>\libs\abide.kicad_sym" --verify` → exit 0, no `SKIP`.
2. `python json2sch.py "<PROJECT_DIR>" design.json --dry-run` → exit 0.
3. Write for real, open in KiCad → references show `R1`, not `R?`. **This is the 1.1 regression test.**
4. `kicad_agent_bridge.py --oracle "BOARD NoSuchMethod"` → prints `did you mean:` and exits non-zero.
5. `kicad_agent_bridge.py --code "raise RuntimeError('x')"` → `echo $LASTEXITCODE` is 1.
6. `kicad_agent_bridge.py --code "while True: pass" --timeout 5` → returns in ~5 s with `AbideTimeout`, KiCad still responsive.
7. `kicad_agent_bridge.py --state summary` → prints a path to `pcb_brain\ai_context_summary.json`.
8. `--json-ops` with a deliberately bad ref → exit code 1, nothing applied.
9. `pcb_snapshot.py` with abIDE closed → warns about last-saved state, still produces the SVG.

---

<aside>
🧊

**Left untouched on purpose.** `kicad_lib_init.py` (version detection from the user's own install, `.bak` before every edit, idempotent upserts — nothing to improve). The symbol geometry in `measure()`/`pin_geometry` (the away-vector and stub fan-out are correct; the 180° global-label justification is KiCad's own convention). The token auth + loopback-only bridge socket. The `_try()` degradation pattern in the extractor — with the `BaseException` watchdog it is now safe.

</aside>
