"""KiCad Symbol Pin Extraction & Footprint Verification Engine (kaibridge.sourcing.pins).
Reads pins out of .kicad_sym files, verifies their physical footprints in .kicad_mod,
and outputs structured JSON pin lists for synthesis.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from ..core.sexpr import head, find, parse
from ..core.paths import load_paths


def collect_pins(node: list, out: Dict[str, Dict[str, Any]]):
    """Pins sit in the symbol or in its child unit symbols. Dedupe by pin number."""
    for child in node:
        if head(child, "pin"):
            etype = child[1] if len(child) > 1 and isinstance(child[1], str) else "?"
            name = next((p[1] for p in find(child, "name") if len(p) > 1), "~")
            number = next((p[1] for p in find(child, "number") if len(p) > 1), "?")
            out.setdefault(number, {"number": number, "name": name, "type": etype})
        elif head(child, "symbol"):
            collect_pins(child, out)


def read_library(path: Path) -> Dict[str, Any]:
    root = parse(path.read_text(encoding="utf-8", errors="replace"))
    if not head(root, "kicad_symbol_lib"):
        raise ValueError(f"{path.name} is not a kicad_symbol_lib file")

    library: Dict[str, Any] = {}
    for symbol in find(root, "symbol"):
        if len(symbol) < 2 or not isinstance(symbol[1], str):
            continue
        props = {p[1]: p[2] for p in find(symbol, "property") if len(p) > 2}
        pins: Dict[str, Any] = {}
        collect_pins(symbol, pins)
        library[symbol[1]] = {
            "name": symbol[1],
            "extends": next((e[1] for e in find(symbol, "extends") if len(e) > 1), None),
            "footprint": props.get("Footprint", ""),
            "datasheet": props.get("Datasheet", ""),
            "pins": list(pins.values()),
        }

    for entry in library.values():
        parent, seen = entry["extends"], set()
        while parent and not entry["pins"] and parent in library and parent not in seen:
            seen.add(parent)
            entry["pins"] = library[parent]["pins"]
            entry["footprint"] = entry["footprint"] or library[parent]["footprint"]
            parent = library[parent]["extends"]

    return library


def sort_pins(pins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(pins, key=lambda p: (len(p["number"]), p["number"]))


def count_pads(path: Path) -> Set[str]:
    """Distinct pad numbers in a .kicad_mod, ignoring unnumbered mechanical pads."""
    root = parse(path.read_text(encoding="utf-8", errors="replace"))
    if not head(root, "footprint") and not head(root, "module"):
        raise ValueError(f"{path.name} is not a footprint file")

    numbers: Set[str] = set()

    def walk(node):
        for child in node:
            if head(child, "pad"):
                if len(child) > 1 and isinstance(child[1], str) and child[1].strip():
                    numbers.add(child[1])
            elif isinstance(child, list):
                walk(child)

    walk(root)
    return numbers


def find_pretty(symbol_file: Path, fp_library: str, cfg: Dict[str, Any]) -> Optional[Path]:
    """Project library sits next to the .kicad_sym; anything else is a stock library."""
    local = symbol_file.with_suffix(".pretty")
    if fp_library == symbol_file.stem and local.is_dir():
        return local
    root = cfg.get("kicad_footprint_dir")
    if root and (root / f"{fp_library}.pretty").is_dir():
        return root / f"{fp_library}.pretty"
    return None


def verify(library: Dict[str, Any], symbol_file: Path, cfg: Dict[str, Any]) -> int:
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
            print(f"FAIL  {label}: footprint library '{fp_library}' not reachable -- NOT VERIFIED")
            failures += 1
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Extract and verify KiCad symbol pins.")
    ap.add_argument("symbol_file", nargs="?", help="path to a .kicad_sym file or project dir")
    ap.add_argument("--native", help="stock library name, e.g. Device (path from kicad_paths.json)")
    ap.add_argument("-s", "--symbol", help="only this symbol (exact name)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--verify", action="store_true", help="footprint + pad-count gate")
    a = ap.parse_args(argv)

    if bool(a.symbol_file) == bool(a.native):
        print("Error: pass either a .kicad_sym path or --native <Library>, not both", file=sys.stderr)
        return 1

    if a.native:
        cfg = load_paths("kicad_symbol_dir")
        path = cfg["kicad_symbol_dir"] / f"{a.native}.kicad_sym"
        if not path.is_file():
            print(f"Error: stock library not found: {path}", file=sys.stderr)
            return 1
    else:
        cfg = load_paths("kicad_footprint_dir") if a.verify else {}
        path = Path(a.symbol_file).expanduser().resolve()
        if path.is_dir():
            # Check for libs/kaibridge.kicad_sym or any .kicad_sym in project
            cand = path / "libs" / "kaibridge.kicad_sym"
            if not cand.exists():
                syms = list(path.glob("**/*.kicad_sym"))
                if syms:
                    cand = syms[0]
            path = cand
        if not path.is_file():
            print(f"Error: symbol file not found: {path}", file=sys.stderr)
            return 1

    try:
        library = read_library(path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not library:
        print(f"Error: {path.name} contains no symbols", file=sys.stderr)
        return 1

    if a.symbol:
        target = a.symbol
        if target not in library:
            # Fuzzy / normalized lookup (handles dot vs underscore differences from JLC2KiCadLib)
            norm_target = target.replace(".", "_").lower()
            matched = [k for k in library if k.replace(".", "_").lower() == norm_target]
            if not matched:
                matched = [k for k in library if norm_target in k.replace(".", "_").lower()]
            if matched:
                target = matched[0]
            else:
                available = ", ".join(list(library.keys())[:5])
                print(f"Error: symbol '{a.symbol}' not in {path.name} ({len(library)} present: {available})", file=sys.stderr)
                return 1
        library = {target: library[target]}

    if a.verify:
        return 1 if verify(library, path, cfg) else 0

    if a.json:
        print(json.dumps(list(library.values()), indent=2, ensure_ascii=False))
        return 0

    for entry in library.values():
        print(f"\nComponent: {entry['name']}   ({len(entry['pins'])} pins)")
        if entry["footprint"]:
            print(f"  footprint: {entry['footprint']}")
        for pin in sort_pins(entry["pins"]):
            print(f"  - Pin {pin['number']:>3} : {pin['name']} ({pin['type']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
