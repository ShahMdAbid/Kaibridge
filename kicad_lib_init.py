#!/usr/bin/env python3
"""
kicad_lib_init.py -- add project-scoped library plumbing to an existing KiCad project.

    python kicad_lib_init.py "F:/kicadtest1" -n abide

Creates / upserts:
    <PROJECT_DIR>/sym-lib-table
    <PROJECT_DIR>/fp-lib-table
    <PROJECT_DIR>/libs/<NAME>.kicad_sym
    <PROJECT_DIR>/libs/<NAME>.pretty/
    <PROJECT_DIR>/libs/<NAME>.3dshapes/

Format versions are copied from your own installed KiCad -- never hardcoded.
Existing files are never overwritten; an edited table is backed up to .bak first.
"""

import argparse
import re
import sys
from pathlib import Path

from kicad_pins import find, load_paths, parse

# table file name -> (root tag, uri template)
TABLES = {
    "sym-lib-table": ("sym_lib_table", "libs/{name}.kicad_sym"),
    "fp-lib-table": ("fp_lib_table", "libs/{name}.pretty"),
}

def format_version(path: Path):
    """Read the (version N) token from any KiCad s-expression file."""
    match = re.search(
        r"\(\s*version\s+([0-9]+)\s*\)",
        path.read_text(encoding="utf-8", errors="replace")[:4000],
    )
    if not match:
        raise ValueError(f"no (version N) token in {path}")
    return match.group(1)

def detect_versions(cfg):
    """(lib-table version, .kicad_sym version) taken from this machine's KiCad."""
    table_src = cfg["kicad_config_dir"] / "sym-lib-table"
    if not table_src.is_file():
        raise ValueError(f"no sym-lib-table in {cfg['kicad_config_dir']} -- wrong kicad_config_dir?")
    stock = sorted(cfg["kicad_symbol_dir"].glob("*.kicad_sym"))
    if not stock:
        raise ValueError(f"no .kicad_sym files in {cfg['kicad_symbol_dir']}")
    return format_version(table_src), format_version(stock[0])

def lib_entry(name, uri_tpl):
    return (
        f'  (lib (name "{name}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{uri_tpl.format(name=name)}")(options "")(descr ""))\n'
    )

def listed_names(text, file_name):
    """Library names already present in a lib table (parsed, not string-matched)."""
    try:
        root = parse(text)
    except ValueError as e:
        raise ValueError(f"{file_name} is not a valid KiCad library table ({e})")
    names = []
    for lib in find(root, "lib"):
        names += [node[1] for node in find(lib, "name") if len(node) > 1]
    return names

def upsert_table(file: Path, tag, version, name, uri_tpl):
    if not file.exists():
        file.write_text(
            f"({tag}\n  (version {version})\n{lib_entry(name, uri_tpl)})\n", encoding="utf-8"
        )
        return f"created {file.name}"

    text = file.read_text(encoding="utf-8")
    if name in listed_names(text, file.name):
        return f"{file.name}: '{name}' already listed, skipped"

    cut = text.rstrip().rfind(")")
    if cut == -1:
        raise ValueError(f"{file.name} has no closing parenthesis")

    file.with_name(file.name + ".bak").write_text(text, encoding="utf-8")
    file.write_text(text[:cut] + lib_entry(name, uri_tpl) + text[cut:], encoding="utf-8")
    return f"{file.name}: added '{name}' (backup: {file.name}.bak)"

def main():
    ap = argparse.ArgumentParser(description="Set up project libraries for a KiCad project.")
    ap.add_argument("project_dir", help="existing KiCad project folder")
    ap.add_argument("-n", "--name", default="abide", help="project library name")
    a = ap.parse_args()

    name = a.name.strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("library name must be a plain name with no path separators")

    project = Path(a.project_dir).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project directory does not exist: {project}")
    if not any(project.glob("*.kicad_pro")):
        raise ValueError(
            f"no .kicad_pro file in {project}\n"
            "Create the project in KiCad first -- ${KIPRJMOD} only works for a real project."
        )

    table_version, symbol_version = detect_versions(load_paths("kicad_config_dir", "kicad_symbol_dir"))
    print(f"  ..  versions from your KiCad: table={table_version} sym={symbol_version}")

    libs = project / "libs"
    for folder in (libs, libs / f"{name}.pretty", libs / f"{name}.3dshapes"):
        folder.mkdir(parents=True, exist_ok=True)
        print(f"  ok  {folder}")

    symbol_file = libs / f"{name}.kicad_sym"
    if symbol_file.exists():
        print(f"  --  {symbol_file.name} already exists, left untouched")
    else:
        symbol_file.write_text(
            f'(kicad_symbol_lib (version {symbol_version}) (generator "kicad_lib_init"))\n',
            encoding="utf-8",
        )
        print(f"  ok  {symbol_file}")

    for file_name, (tag, uri_tpl) in TABLES.items():
        print("  ok  " + upsert_table(project / file_name, tag, table_version, name, uri_tpl))

    print(f"\nDone: {project}")
    print("If KiCad is open, reopen the project so the new library tables load.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as e:
        sys.exit(f"Error: {type(e).__name__}: {e}")
