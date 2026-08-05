#!/usr/bin/env python3
"""
kicad_pins.py -- read pins out of .kicad_sym files and verify their footprints.
Also holds the shared kicad_paths.json reader used by kicad_lib_init.py.

    python kicad_pins.py "F:/kicadtest1/libs/abide.kicad_sym"
    python kicad_pins.py "F:/kicadtest1/libs/abide.kicad_sym" -s AMS1117-3.3 --json
    python kicad_pins.py --native Device -s R --json
    python kicad_pins.py "F:/kicadtest1/libs/abide.kicad_sym" --verify

--verify exits 1 if any symbol fails the footprint / pad-count gate.
"""

import argparse
import json
import sys
from pathlib import Path

CONFIG = Path(__file__).with_name("kicad_paths.json")

class Quoted(str):
    """A string atom that was quoted in the source and must stay quoted on output."""

    __slots__ = ()

_NEEDS_QUOTE = set(' \t\r\n()"')

def atom(value):
    text = str(value)
    if isinstance(value, Quoted) or text == "" or any(c in _NEEDS_QUOTE for c in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text

def dumps(node):
    """Serialize a parsed tree back into KiCad s-expression text."""
    if isinstance(node, list):
        return "(" + " ".join(dumps(child) for child in node) + ")"
    return atom(node)

HOWTO = f"""
Fix {CONFIG.name} (same folder as this script). It must contain:

{{
  "kicad_config_dir":    "<folder holding your global sym-lib-table>",
  "kicad_symbol_dir":    "<KiCad stock symbols folder>",
  "kicad_footprint_dir": "<KiCad stock footprints folder>"
}}

Where to find them (copy the values, do not type them):
  symbol / footprint dir : KiCad -> Preferences -> Configure Paths...
                           (rows ending in _SYMBOL_DIR and _FOOTPRINT_DIR)
  config dir             : PCB editor -> Tools -> Scripting Console, then run
                           import pcbnew; print(pcbnew.SETTINGS_MANAGER.GetUserSettingsPath())

Use forward slashes.
"""

def load_paths(*required):
    """Read kicad_paths.json and return {key: Path} for the non-empty entries."""
    if not CONFIG.exists():
        raise ValueError(f"{CONFIG} not found.{HOWTO}")
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{CONFIG.name} is not valid JSON ({e}).{HOWTO}")

    cfg = {}
    for key, value in raw.items():
        if not str(value).strip():
            continue
        path = Path(value).expanduser()
        if not path.is_dir():
            raise ValueError(f"{CONFIG.name}: '{key}' is not an existing folder -> {path}{HOWTO}")
        cfg[key] = path

    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(f"{CONFIG.name}: fill in {', '.join(missing)}.{HOWTO}")
    return cfg

# ---------------- tiny s-expression reader ----------------

def tokens(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            i, buf = i + 1, []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            i += 1
            yield Quoted("".join(buf))
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield text[i:j]
            i = j

def parse(text):
    """Return the first top-level list. Raises ValueError on malformed input."""
    stack = []
    for token in tokens(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                raise ValueError("unexpected closing parenthesis")
            done = stack.pop()
            if not stack:
                return done
            stack[-1].append(done)
        else:
            if not stack:
                raise ValueError("atom outside any list")
            stack[-1].append(token)
    raise ValueError("unbalanced parentheses")

def head(node, tag):
    return isinstance(node, list) and node and node[0] == tag

def find(node, tag):
    return [child for child in node if head(child, tag)]

# ---------------- symbols ----------------

def collect_pins(node, out):
    """Pins sit in the symbol or in its child unit symbols. Dedupe by pin number."""
    for child in node:
        if head(child, "pin"):
            etype = child[1] if len(child) > 1 and isinstance(child[1], str) else "?"
            name = next((p[1] for p in find(child, "name") if len(p) > 1), "~")
            number = next((p[1] for p in find(child, "number") if len(p) > 1), "?")
            out.setdefault(number, {"number": number, "name": name, "type": etype})
        elif head(child, "symbol"):
            collect_pins(child, out)

def read_library(path: Path):
    root = parse(path.read_text(encoding="utf-8", errors="replace"))
    if not head(root, "kicad_symbol_lib"):
        raise ValueError(f"{path.name} is not a kicad_symbol_lib file")

    library = {}
    for symbol in find(root, "symbol"):
        if len(symbol) < 2 or not isinstance(symbol[1], str):
            continue
        props = {p[1]: p[2] for p in find(symbol, "property") if len(p) > 2}
        pins = {}
        collect_pins(symbol, pins)
        library[symbol[1]] = {
            "name": symbol[1],
            "extends": next((e[1] for e in find(symbol, "extends") if len(e) > 1), None),
            "footprint": props.get("Footprint", ""),
            "datasheet": props.get("Datasheet", ""),
            "pins": list(pins.values()),
        }

    # derived symbols inherit pins / footprint from their parent
    for entry in library.values():
        parent, seen = entry["extends"], set()
        while parent and not entry["pins"] and parent in library and parent not in seen:
            seen.add(parent)
            entry["pins"] = library[parent]["pins"]
            entry["footprint"] = entry["footprint"] or library[parent]["footprint"]
            parent = library[parent]["extends"]

    return library

def sort_pins(pins):
    return sorted(pins, key=lambda p: (len(p["number"]), p["number"]))

# ---------------- footprint verification ----------------

def count_pads(path: Path):
    """Distinct pad numbers in a .kicad_mod, ignoring unnumbered mechanical pads."""
    root = parse(path.read_text(encoding="utf-8", errors="replace"))
    if not head(root, "footprint") and not head(root, "module"):
        raise ValueError(f"{path.name} is not a footprint file")

    numbers = set()

    def walk(node):
        for child in node:
            if head(child, "pad"):
                if len(child) > 1 and isinstance(child[1], str) and child[1].strip():
                    numbers.add(child[1])
            elif isinstance(child, list):
                walk(child)

    walk(root)
    return numbers

def find_pretty(symbol_file: Path, fp_library, cfg):
    """Project library sits next to the .kicad_sym; anything else is a stock library."""
    local = symbol_file.with_suffix(".pretty")
    if fp_library == symbol_file.stem and local.is_dir():
        return local
    root = cfg.get("kicad_footprint_dir")
    if root and (root / f"{fp_library}.pretty").is_dir():
        return root / f"{fp_library}.pretty"
    return None

def verify(library, symbol_file: Path, cfg):
    failures = 0
    for entry in library.values():
        pins = len(entry["pins"])
        label = f"{entry['name']} ({pins} pins)"

        if pins == 0:
            print(f"FAIL  {label}: no pins found (unresolved 'extends'?)")
            failures += 1
            continue
        if ":" not in entry["footprint"]:
            print(f"FAIL  {label}: no usable Footprint property")
            failures += 1
            continue

        fp_library, fp_name = entry["footprint"].split(":", 1)
        pretty = find_pretty(symbol_file, fp_library, cfg)
        if pretty is None:
            print(f"SKIP  {label}: footprint library '{fp_library}' not reachable -- NOT VERIFIED")
            continue

        mod = pretty / f"{fp_name}.kicad_mod"
        if not mod.exists():
            print(f"FAIL  {label}: footprint file missing -> {mod}")
            failures += 1
            continue

        pads = count_pads(mod)
        if len(pads) != pins:
            print(f"FAIL  {label}: {len(pads)} pads in {mod.name} != {pins} pins")
            failures += 1
        else:
            print(f"OK    {label}: {fp_name} ({len(pads)} pads)")

    print(f"\n{len(library)} symbol(s) checked, {failures} failure(s).")
    return failures

# ---------------- cli ----------------

def main():
    ap = argparse.ArgumentParser(description="Extract and verify KiCad symbol pins.")
    ap.add_argument("symbol_file", nargs="?", help="path to a .kicad_sym file")
    ap.add_argument("--native", help="stock library name, e.g. Device (path from kicad_paths.json)")
    ap.add_argument("-s", "--symbol", help="only this symbol (exact name)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--verify", action="store_true", help="footprint + pad-count gate")
    a = ap.parse_args()

    if bool(a.symbol_file) == bool(a.native):
        raise ValueError("pass either a .kicad_sym path or --native <Library>, not both")

    if a.native:
        cfg = load_paths("kicad_symbol_dir")
        path = cfg["kicad_symbol_dir"] / f"{a.native}.kicad_sym"
        if not path.is_file():
            raise ValueError(f"stock library not found: {path}")
    else:
        cfg = load_paths() if a.verify else {}
        path = Path(a.symbol_file).expanduser()
        if not path.is_file():
            raise ValueError(f"file not found: {path}")

    library = read_library(path)
    if not library:
        raise ValueError(f"{path.name} contains no symbols")
    if a.symbol:
        if a.symbol not in library:
            raise KeyError(f"symbol '{a.symbol}' not in {path.name} ({len(library)} present)")
        library = {a.symbol: library[a.symbol]}

    if a.verify:
        sys.exit(1 if verify(library, path, cfg) else 0)

    if a.json:
        print(json.dumps(list(library.values()), indent=2, ensure_ascii=False))
        return

    for entry in library.values():
        print(f"\nComponent: {entry['name']}   ({len(entry['pins'])} pins)")
        if entry["footprint"]:
            print(f"  footprint: {entry['footprint']}")
        for pin in sort_pins(entry["pins"]):
            print(f"  - Pin {pin['number']:>3} : {pin['name']} ({pin['type']})")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as e:
        sys.exit(f"Error: {type(e).__name__}: {e}")
