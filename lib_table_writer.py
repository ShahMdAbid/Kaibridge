"""
lib_table_writer.py -- Safe upsert for KiCad project library tables.

Additively registers the easyeda2kicad local library into project-level
fp-lib-table and sym-lib-table WITHOUT touching or shadowing global libraries.

KiCad merges global + project tables:
    effective_libraries = global_table ∪ project_table
Only same-nickname entries shadow. We hard-ban a reserved nickname list
to prevent accidentally overriding Device, Resistor_SMD, etc.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

# Nicknames that belong to KiCad's global library set.
# We MUST NEVER write these into a project table -- doing so would shadow
# the real global lib and break native component resolution.
RESERVED_NICKNAMES = {
    "Device", "Resistor_SMD", "Capacitor_SMD", "Inductor_SMD", "Diode_SMD",
    "LED_SMD", "Transistor_SMD", "Connector_PinHeader_2.54mm",
    "Connector_PinHeader_2.00mm", "Connector_PinHeader_1.27mm",
    "Connector_PinSocket_2.54mm", "Connector_PinSocket_2.00mm",
    "Connector_Generic", "power", "Mechanical", "TestPoint",
    "Crystal", "Fuse", "LED_THT", "Diode_THT", "Resistor_THT",
    "Connector_PinSocket_1.27mm", "Buzzer_Beeper", "Switch",
    "KiCad",  # the meta-table nickname used in KiCad 10
}

MANAGED_NICK = "easyeda2kicad"
MANAGED_MARK = "abIDE-managed"

_LIB_LINE_RE = re.compile(r'\(lib\s+\(name\s+"?([^")]+)"?\)')


def write_project_tables(project_dir: Path) -> None:
    """Additively register the easyeda2kicad libs. Never touches globals."""
    project_dir = Path(project_dir)

    _upsert(
        project_dir / "fp-lib-table",
        "fp_lib_table",
        nick=MANAGED_NICK,
        uri="${KIPRJMOD}/libs/easyeda2kicad/easyeda2kicad.pretty",
    )
    _upsert(
        project_dir / "sym-lib-table",
        "sym_lib_table",
        nick=MANAGED_NICK,
        uri="${KIPRJMOD}/libs/easyeda2kicad/easyeda2kicad.kicad_sym",
    )


def _upsert(path: Path, root: str, nick: str, uri: str) -> None:
    assert nick not in RESERVED_NICKNAMES, f"refusing to shadow global lib {nick}"

    existing: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s.startswith("(lib "):
                continue
            # Drop our old managed row -- we will rewrite it below
            if f'(name "{nick}")' in s or f"(name {nick})" in s:
                continue
            existing.append(s)  # preserve everything the user or KiCad added

    row = (
        f'  (lib (name "{nick}")(type "KiCad")(uri "{uri}")'
        f'(options "")(descr "{MANAGED_MARK}"))'
    )

    body_lines = ["  " + e for e in existing] + [row]
    body = "\n".join(body_lines)
    path.write_text(f"({root}\n  (version 7)\n{body}\n)\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Write project lib tables safely.")
    ap.add_argument("project_dir", type=Path)
    args = ap.parse_args()
    write_project_tables(args.project_dir)
    print(f"[OK] Library tables written to {args.project_dir}")
