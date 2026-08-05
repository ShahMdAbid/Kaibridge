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
    """Load and validate design.json from the project directory."""
    path = os.path.join(project_dir, "design.json")
    if not os.path.exists(path):
        print(f"Error: design.json not found in {project_dir}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        design = json.load(f)

    # Validate minimum structure
    if "parts" not in design:
        print("Error: design.json has no 'parts' section.")
        sys.exit(1)

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
                      part_gap=15.0, group_gap=35.0):
    """
    Lay out groups left-to-right.  Within each group, arrange parts in a
    roughly-square grid.  Returns a list of apply_ops-compatible dicts.

    Coordinates are in mm.  KiCad Y-axis points DOWN.
    """
    ops = []
    cursor_x = start_x      # left edge of current group zone

    for group in groups:
        refs = group["refs"]
        if not refs:
            continue

        # Compute grid dimensions (aim for roughly square)
        n = len(refs)
        cols = max(1, round(n ** 0.5))
        rows = (n + cols - 1) // cols       # ceiling division

        for i, ref in enumerate(refs):
            row = i // cols
            col = i % cols
            ops.append({
                "op":  "footprint.move",
                "ref": ref,
                "x":   round(cursor_x + col * part_gap, 2),
                "y":   round(start_y  + row * part_gap, 2),
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

def send_to_kicad(ops):
    """
    Build a tiny Python script that calls apply_ops() with our ops list,
    then send it to KiCad through kicad_agent_bridge.py.

    The ops JSON is base64-encoded to avoid any quoting/escaping issues
    when embedding it inside a Python string.
    """
    autoplacer_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path    = os.path.join(autoplacer_dir, "kicad_agent_bridge.py")

    ops_b64 = base64.b64encode(json.dumps(ops).encode()).decode()

    # This code string will be exec'd inside KiCad's Python environment
    # where pcbnew is already available.
    code = (
        "import sys, json, base64\n"
        f"sys.path.insert(0, r'{autoplacer_dir}')\n"
        "from currentboardfetcher import apply_ops\n"
        "\n"
        f"ops = json.loads(base64.b64decode('{ops_b64}').decode())\n"
        "print(f'Macro Placer: Moving {len(ops)} footprints...')\n"
        "result = apply_ops(ops, dry_run=False, save=True, refill=False, verify=True)\n"
        "if result.get('applied'):\n"
        "    print('\\nSUCCESS: All footprints placed into group clusters!')\n"
        "else:\n"
        "    print('\\nFAILED:', result.get('problems', []))\n"
    )

    print("\nSending to KiCad via bridge...")
    result = subprocess.run(
        [sys.executable, bridge_path, "--code", code, "--timeout", "30"],
        capture_output=True, text=True,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode == 0


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

    success = send_to_kicad(ops)
    if not success:
        print("\nBridge execution failed. Is KiCad open with abIDE plugin?")
        sys.exit(1)


if __name__ == "__main__":
    main()
