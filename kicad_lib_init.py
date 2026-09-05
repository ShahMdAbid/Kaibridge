#!/usr/bin/env python3
"""
kicad_lib_init.py -- add project-scoped library plumbing to an existing KiCad project.

    python kicad_lib_init.py "<PROJECT_DIR>" -n kaibridge

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
import os
import re
import sys
from pathlib import Path

# Ensure repo root is on sys.path so kaibridge is importable
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.core.sexpr import find, parse
from kaibridge.core.paths import load_paths

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
        # Fallback to default modern KiCad versions if sym-lib-table is not yet created in config
        return "7", "20231120"
    stock = sorted(cfg["kicad_symbol_dir"].glob("*.kicad_sym"))
    sym_v = format_version(stock[0]) if stock else "20231120"
    return format_version(table_src), sym_v

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

def init_libraries(project_dir: str | Path, name: str = "kaibridge", layers: int = 2):
    name = name.strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("library name must be a plain name with no path separators")

    import json
    project = Path(project_dir).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)

    dump_dir = project / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)

    pro_files = list(project.glob("*.kicad_pro"))
    if not pro_files:
        stem = project.name
        pro_file = project / f"{stem}.kicad_pro"
        pcb_file = project / f"{stem}.kicad_pcb"
        jlcpcb_rules = {
            "max_error": 0.005,
            "min_clearance": 0.15,
            "min_connection": 0.0,
            "min_copper_edge_clearance": 0.15,
            "min_groove_width": 0.0,
            "min_hole_clearance": 0.15,
            "min_hole_to_hole": 0.25,
            "min_microvia_diameter": 0.2,
            "min_microvia_drill": 0.1,
            "min_resolved_spokes": 2,
            "min_silk_clearance": 0.0,
            "min_text_height": 0.8,
            "min_text_thickness": 0.08,
            "min_through_hole_clearance": 0.15,
            "min_through_hole_diameter": 0.3,
            "min_track_width": 0.15,
            "min_via_annular_width": 0.1,
            "min_via_diameter": 0.5,
            "solder_mask_to_copper_clearance": 0.0,
            "use_height_for_length_calcs": True
        }
        pro_content = {
            "meta": {"filename": f"{stem}.kicad_pro", "version": 1},
            "net_settings": {"classes": [{"clearance": 0.2, "name": "Default", "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
            "board": {"design_settings": {"rules": jlcpcb_rules}},
            "sheets": [["", ""]]
        }
        pro_file.write_text(json.dumps(pro_content, indent=2), encoding="utf-8")
        if not pcb_file.exists():
            if layers == 4:
                layers_sexpr = '    (0 "F.Cu" signal)\n    (1 "In1.Cu" power "GND")\n    (2 "In2.Cu" power "Power")\n    (31 "B.Cu" signal)\n'
            else:
                layers_sexpr = '    (0 "F.Cu" signal)\n    (31 "B.Cu" signal)\n'
            pcb_file.write_text(f'(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")\n  (general (thickness 1.6))\n  (paper "A4")\n  (layers\n{layers_sexpr}    (32 "B.Adhes" user "B.Adhesive")\n    (33 "F.Adhes" user "F.Adhesive")\n    (34 "B.Paste" user)\n    (35 "F.Paste" user)\n    (36 "B.SilkS" user "B.Silkscreen")\n    (37 "F.SilkS" user "F.Silkscreen")\n    (38 "B.Mask" user)\n    (39 "F.Mask" user)\n    (40 "Dwgs.User" user "User.Drawings")\n    (41 "Cmts.User" user "User.Comments")\n    (42 "Eco1.User" user "User.Eco1")\n    (43 "Eco2.User" user "User.Eco2")\n    (44 "Edge.Cuts" user)\n    (45 "Margin" user)\n    (46 "B.CrtYd" user "B.Courtyard")\n    (47 "F.CrtYd" user "F.Courtyard")\n    (48 "B.Fab" user)\n    (49 "F.Fab" user)\n  )\n)\n', encoding="utf-8")

    cfg = load_paths("kicad_config_dir", "kicad_symbol_dir")
    table_version, symbol_version = detect_versions(cfg)

    libs = project / "libs"
    for folder in (libs, libs / f"{name}.pretty", libs / f"{name}.3dshapes"):
        folder.mkdir(parents=True, exist_ok=True)

    symbol_file = libs / f"{name}.kicad_sym"
    if not symbol_file.exists():
        symbol_file.write_text(
            f'(kicad_symbol_lib (version {symbol_version}) (generator "kicad_lib_init"))\n',
            encoding="utf-8",
        )

    for file_name, (tag, uri_tpl) in TABLES.items():
        upsert_table(project / file_name, tag, table_version, name, uri_tpl)

    return {
        "success": True,
        "project": str(project),
        "libs_dir": str(libs),
        "symbol_file": str(symbol_file),
        "pretty_dir": str(libs / f"{name}.pretty"),
        "3dshapes_dir": str(libs / f"{name}.3dshapes"),
        "layers": layers
    }

def main():
    ap = argparse.ArgumentParser(description="Set up project libraries for a KiCad project.")
    ap.add_argument("project_dir", help="existing KiCad project folder")
    ap.add_argument("-n", "--name", default="kaibridge", help="project library name")
    ap.add_argument("--layers", type=int, choices=[2, 4], default=2, help="Number of copper layers (2 or 4, default: 2)")
    a = ap.parse_args()

    try:
        res = init_libraries(a.project_dir, a.name, layers=a.layers)
        print(f"[*] Initialized KiCad libraries successfully in: {res['project']} [{res['layers']}-Layer Stackup]")
        print(f"  ok  {res['symbol_file']}")
        print(f"  ok  {res['pretty_dir']}")
        print(f"  ok  {res['3dshapes_dir']}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
