#!/usr/bin/env python3
"""
json2sch.py -- design.json -> KiCad hierarchical schematics.

  python json2sch.py <PROJECT_DIR> [design.json] [-o board.kicad_sch]
                     [--dry-run] [--apply-netclasses] [--no-backup]

Sub-sheets are written next to the root file as <sheet_id>.kicad_sch.
A sidecar <PROJECT_DIR>/abide_build.json records the resolved design for
Autoplacer/macro_placer.py.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from abide import __version__
from abide.klib import LibError, LibIndex
from abide.model import DesignError, load, sidecar
from abide.place import plan
from abide.render import VERSION, build, existing_uuid, uid, write
from abide.sexpr import SexprError

# KiCad's own keys. Anything else in a netclass is a typo, and a typo that
# silently does nothing is worse than an error.
NETCLASS_KEYS = {
    "clearance", "track_width", "via_diameter", "via_drill", "uvia_diameter",
    "uvia_drill", "diff_pair_width", "diff_pair_gap", "diff_pair_via_gap",
    "wire_width", "bus_width", "line_style", "schematic_color", "pcb_color",
    "priority", "description",
}
ALIASES = {"via_dia": "via_diameter", "via_size": "via_diameter",
           "trackwidth": "track_width", "width": "track_width"}

def fail(message):
    print(f"Error: {message}", file=sys.stderr)
    return 1

def detect_project(project_dir):
    """(name, .kicad_pro path, default root .kicad_sch path)."""
    folder = Path(project_dir)
    pros = sorted(folder.glob("*.kicad_pro"))
    if len(pros) > 1:
        names = ", ".join(p.name for p in pros)
        raise SystemExit(f"Error: {folder} holds more than one project: {names}")
    if pros:
        stem = pros[0].stem
        return stem, pros[0], folder / f"{stem}.kicad_sch"
    stem = folder.name
    return stem, folder / f"{stem}.kicad_pro", folder / f"{stem}.kicad_sch"

def apply_netclasses(pro_path, netclasses, backup=True):
    """Write netclasses into the .kicad_pro, loudly rejecting unknown keys."""
    notes = []
    if not netclasses:
        return notes
    if not pro_path.exists():
        return [f"netclasses skipped: {pro_path.name} does not exist yet"]
    try:
        data = json.loads(pro_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"netclasses skipped: {pro_path.name} is not valid JSON ({e})"]
    settings = data.get("net_settings") or {}
    existing = {}
    for item in settings.get("classes") or []:
        if isinstance(item, dict) and item.get("name"):
            existing[item["name"]] = item
    classes = []
    for name, spec in netclasses.items():
        entry = {"name": str(name)}
        for key, item in (spec or {}).items():
            key = str(key)
            if key in ALIASES:
                notes.append(f"netclass '{name}': '{key}' is not a KiCad key, "
                             f"wrote '{ALIASES[key]}' instead")
                key = ALIASES[key]
            if key not in NETCLASS_KEYS:
                notes.append(f"netclass '{name}': ignored unknown key '{key}'")
                continue
            entry[key] = item
        classes.append(entry)
    if not any(c["name"] == "Default" for c in classes):
        keep = existing.get("Default") or {"name": "Default"}
        classes.insert(0, keep)
        notes.append("kept the project's existing Default netclass")
    settings["classes"] = classes
    data["net_settings"] = settings
    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(pro_path, pro_path.with_name(f"{pro_path.name}.{stamp}.bak"))
    pro_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    notes.append(f"wrote {len(classes)} netclass(es) into {pro_path.name}")
    return notes

def report(design, files, results, orphans, notes):
    pad = max([len(s.id) for s in design.sheets] + [5])
    print(f"  {'sheet'.ljust(pad)}  parts  nets  paper")
    for sheet in design.sheets:
        parts = len(design.sheet_parts(sheet.id))
        nets = len([n for n in design.nets.values() if sheet.id in n.sheets])
        print(f"  {sheet.id.ljust(pad)}  {parts:>5}  {nets:>4}  {sheet.paper}")
    for name, status in results:
        print(f"  {status:<22} {name}")
    for name in orphans:
        print(f"  ORPHAN, delete by hand:  {name}")
    for note in notes:
        print(f"  note: {note}")

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Compile design.json into KiCad hierarchical schematics.")
    ap.add_argument("project_dir", help="folder that holds the .kicad_pro")
    ap.add_argument("design_json", nargs="?",
                    help="default: <project_dir>/design.json")
    ap.add_argument("-o", "--out",
                    help="root schematic path; sub-sheets go beside it")
    ap.add_argument("--dry-run", action="store_true",
                    help="compile and report, write nothing")
    ap.add_argument("--apply-netclasses", action="store_true",
                    help="also write netclasses into the .kicad_pro")
    ap.add_argument("--no-backup", action="store_true",
                    help="do not keep .bak copies of replaced files")
    ap.add_argument("--kicad-version", type=int, default=VERSION,
                    help=f"format stamp, default {VERSION} (KiCad 9)")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.is_dir():
        return fail(f"{project_dir} is not a folder")
    name, pro_path, default_sch = detect_project(project_dir)
    design_path = (Path(args.design_json).expanduser()
                   if args.design_json else project_dir / "design.json")
    out_path = Path(args.out).expanduser() if args.out else default_sch

    try:
        raw = json.loads(design_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fail(f"{design_path} not found")
    except json.JSONDecodeError as e:
        return fail(f"{design_path.name} is not valid JSON: {e}")

    try:
        lib = LibIndex(project_dir)
        design = load(raw, lib)
        layout = plan(design)
        files = build(design, layout, lib, name, out_path.stem,
                      version=args.kicad_version)
    except (DesignError, LibError, SexprError) as e:
        return fail(str(e))
    except ValueError as e:              # kicad_paths.json problems
        return fail(str(e))

    print(f"abIDE {__version__}  project '{name}'  {lib.summary()}")
    for warning in design.warnings:
        print(f"  warning: {warning}")

    old = existing_uuid(out_path) if out_path.exists() else ""
    if old and old != uid(design.design_id, "sheet", "root"):
        print("  ! the root sheet uuid changed, which means meta.design_id "
              "changed.")
        print("    KiCad will treat every footprint as new and your placement "
              "will be lost.")
        print("    Restore the previous design_id if this board is already "
              "laid out.")

    if args.dry_run:
        report(design, files, [(n, "would write") for n in sorted(files)], [], [])
        return 0

    results, orphans = write(files, out_path.parent, backup=not args.no_backup)
    notes = []
    build_path = project_dir / "abide_build.json"
    build_path.write_text(json.dumps(sidecar(design), indent=2), encoding="utf-8")
    notes.append(f"sidecar: {build_path.name}")
    if args.apply_netclasses:
        notes += apply_netclasses(pro_path, design.netclasses,
                                  backup=not args.no_backup)
    report(design, files, results, orphans, notes)
    print("  next: open the project in KiCad, then Tools -> Update PCB from "
          "Schematic (F8)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
