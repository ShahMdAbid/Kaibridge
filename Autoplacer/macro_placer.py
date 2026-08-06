#!/usr/bin/env python3
"""
macro_placer.py — Untangles PCB footprints into grouped clusters.

After pressing F8 in KiCad (Update PCB from Schematic), all footprints land
at (0, 0) in a messy pile. This script reads design.json, computes clean
grid positions for each group, and sends footprint.move ops to KiCad via the
bridge so the parts snap into organized clusters on your live board.

Usage:
    python macro_placer.py <PROJECT_DIR>              # plan + execute
    python macro_placer.py <PROJECT_DIR> --plan-only  # just show the plan

Requires:
    KiCad PCB Editor must be open with the abIDE plugin active (socket server).
"""

import os
import sys
import json
import subprocess
import base64

# ---------------------------------------------------------------------------
# 1. Load design.json
# ---------------------------------------------------------------------------

def load_design(project_dir):
    """Prefer the compiler's resolved sidecar; fall back to raw design.json."""
    sidecar = os.path.join(project_dir, "abide_build.json")
    path = sidecar if os.path.exists(sidecar) else os.path.join(project_dir, "design.json")
    if not os.path.exists(path):
        print(f"Error: neither abide_build.json nor design.json found in {project_dir}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        design = json.load(f)
    if "parts" not in design:
        print(f"Error: {os.path.basename(path)} has no 'parts' section.")
        sys.exit(1)
    if path == sidecar:
        print(f"  using abide_build.json ({len(design['parts'])} parts, "
              f"{len(design.get('groups', []))} groups)")
    return design


# ---------------------------------------------------------------------------
# 2. Build groups from design.json
# ---------------------------------------------------------------------------

def build_groups(design):
    """
    Return a list of {"id": str, "title": str, "refs": [str, ...]}
    from design.json's 'groups' array.  If 'groups' is missing, fall back
    to the 'group' field on individual parts.  If neither exists, put
    everything in one big group.
    """
    parts = design.get("parts", {})

    # --- Path A: explicit groups array ---
    if "groups" in design and design["groups"]:
        result = []
        for g in design["groups"]:
            refs = g.get("parts", [])
            result.append({
                "id":    g.get("id", "unknown"),
                "title": g.get("title", g.get("id", "Group")),
                "refs":  refs,
                "sheet": g.get("sheet", "root"),
            })

        # Catch any parts NOT listed in any group
        grouped = {ref for g in result for ref in g["refs"]}
        ungrouped = [ref for ref in parts if ref not in grouped]
        if ungrouped:
            result.append({
                "id":    "_ungrouped",
                "title": "Ungrouped",
                "refs":  ungrouped,
            })
        return result

    # --- Path B: per-part 'group' field ---
    group_map = {}  # group_id -> [ref, ...]
    no_group = []
    for ref, info in parts.items():
        gid = info.get("group")
        if gid:
            group_map.setdefault(gid, []).append(ref)
        else:
            no_group.append(ref)

    if group_map:
        result = [{"id": gid, "title": gid, "refs": refs}
                  for gid, refs in group_map.items()]
        if no_group:
            result.append({"id": "_ungrouped", "title": "Ungrouped",
                           "refs": no_group})
        return result

    # --- Path C: no grouping info at all ---
    return [{"id": "all", "title": "All Parts", "refs": list(parts.keys())}]


# ---------------------------------------------------------------------------
# 3. Compute grid positions
# ---------------------------------------------------------------------------

def compute_placement(groups, start_x=50.0, start_y=50.0,
                      part_gap=15.0, group_gap=35.0, sheet_gap=25.0):
    """
    Lay out groups left-to-right.  Within each group, arrange parts in a
    roughly-square grid.  Coordinates are in mm.  KiCad Y-axis points DOWN.
    Per-sheet banding: when the sheet changes, start a new band below.
    """
    ops = []
    cursor_x, band_y = start_x, start_y
    current_sheet = None

    for group in groups:
        refs = group["refs"]
        if not refs:
            continue

        sheet = group.get("sheet") or "root"
        if current_sheet is not None and sheet != current_sheet:
            band_y += 4 * part_gap + sheet_gap
            cursor_x = start_x
        current_sheet = sheet

        # Compute grid dimensions (aim for roughly square)
        cols = max(1, round(len(refs) ** 0.5))

        for i, ref in enumerate(refs):
            ops.append({
                "op":  "footprint.place",
                "anchor": "centre",
                "ref": ref,
                "x":   round(cursor_x + (i % cols) * part_gap, 2),
                "y":   round(band_y  + (i // cols) * part_gap, 2),
            })

        # Advance cursor past this group + gap
        cursor_x += cols * part_gap + group_gap

    return ops


# ---------------------------------------------------------------------------
# 4. Pretty-print the plan
# ---------------------------------------------------------------------------

def print_plan(groups, ops):
    """Print a human-readable placement plan."""
    print("=" * 60)
    print("  MACRO PLACER — Group Placement Plan")
    print("=" * 60)

    # Build a ref -> position lookup
    pos = {o["ref"]: (o["x"], o["y"]) for o in ops}

    for g in groups:
        print(f"\n  [{g['id']}] {g['title']}")
        print(f"  {'─' * 40}")
        for ref in g["refs"]:
            x, y = pos.get(ref, (0, 0))
            print(f"    {ref:>5s}  →  ({x:7.1f}, {y:7.1f}) mm")

    print()
    print(f"  Total: {len(ops)} footprints across {len(groups)} groups")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 5. Send to KiCad via bridge
# ---------------------------------------------------------------------------

def send_to_kicad(ops, project_dir):
    """Dry run first (RULE 6), then commit."""
    autoplacer_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path    = os.path.join(autoplacer_dir, "kicad_agent_bridge.py")

    ops_file = os.path.join(project_dir, "ops_macro_placer.json")
    with open(ops_file, "w", encoding="utf-8") as f:
        json.dump(ops, f, indent=2)
    print(f"\n  ops written to {ops_file}")

    for stage in ("dry run", "commit"):
        cmd = [sys.executable, bridge_path, "--json-ops", ops_file, "--timeout", "180"]
        if stage == "commit":
            cmd.append("--commit")
        print(f"\n--- {stage} ---")
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        if r.returncode != 0:
            print(f"\nStopped at the {stage}. The ops file is kept at {ops_file}")
            return False
    return True


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Macro Placer: untangle PCB footprints into grouped clusters")
    parser.add_argument("project_dir", help="Path to KiCad project directory")
    parser.add_argument("--plan-only", action="store_true",
                        help="Print the placement plan without sending to KiCad")
    parser.add_argument("--start-x", type=float, default=50.0,
                        help="X origin for first group (mm, default 50)")
    parser.add_argument("--start-y", type=float, default=50.0,
                        help="Y origin for first group (mm, default 50)")
    parser.add_argument("--part-gap", type=float, default=15.0,
                        help="Spacing between parts in a group (mm, default 15)")
    parser.add_argument("--group-gap", type=float, default=35.0,
                        help="Extra spacing between groups (mm, default 35)")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    if not os.path.isdir(project_dir):
        print(f"Error: Not a directory: {project_dir}")
        sys.exit(1)

    # 1. Load design
    design = load_design(project_dir)

    # 2. Build groups
    groups = build_groups(design)

    # 3. Compute positions
    ops = compute_placement(
        groups,
        start_x=args.start_x,
        start_y=args.start_y,
        part_gap=args.part_gap,
        group_gap=args.group_gap,
    )

    if not ops:
        print("No parts found to place.")
        sys.exit(0)

    # 4. Show the plan
    print_plan(groups, ops)

    # 5. Execute (unless --plan-only)
    if args.plan_only:
        print("\n  --plan-only: skipping execution.")
        print("  Remove --plan-only to send these moves to KiCad.")
        sys.exit(0)

    success = send_to_kicad(ops, project_dir)
    if not success:
        print("\nBridge execution failed. Is KiCad open with abIDE plugin?")
        sys.exit(1)


if __name__ == "__main__":
    main()
