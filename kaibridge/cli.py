"""Kaibridge Master CLI Dispatcher (kaibridge.cli).
Provides a unified, single-command entry point (kaibridge <subcommand>) for all
hardware synthesis, placement, routing, inspection, and manufacturing operations.
"""
from __future__ import annotations

import difflib
import sys
from typing import Callable, Dict, Tuple

from . import __version__

# Registry of subcommands: command_name -> (module_path, function_name, help_description)
COMMANDS: Dict[str, Tuple[str, str, str]] = {
    "init": (
        "kaibridge.core.init",
        "main",
        "Bootstrap new KiCad project, .kicad_pro, .kicad_pcb, and library tables (Step 0)"
    ),
    "3d": (
        "kaibridge.sourcing.fetch_3d",
        "main",
        "Background non-blocking 3D model downloader with rate pacing (Step 2)"
    ),
    "pins": (
        "kaibridge.sourcing.pins",
        "main",
        "Extract and verify symbol pins and physical footprint pad counts (Step 3)"
    ),
    "build": (
        "kaibridge.schematic.compiler",
        "main",
        "Compile design.json into KiCad hierarchical schematics, netclasses, and ERC (Step 6)"
    ),
    "sync": (
        "kaibridge.pcb.sync",
        "main",
        "Headless F8 schematic-to-PCB netlist and footprint synchronizer (Step 7)"
    ),
    "layout": (
        "kaibridge.pcb.layout",
        "main",
        "Declarative placement engine, bounding box, and push-and-shove relaxation (Step 8)"
    ),
    "snapshot": (
        "kaibridge.pcb.snapshot_cli",
        "main",
        "Export 2D vector SVG renders and 9-angle 3D vision perspective suite (Step 8F)"
    ),
    "opt": (
        "kaibridge.pcb.swap_optimizer",
        "main",
        "Deterministic ISRRO-X physics-preserving pin escape & ratsnest optimizer (Step 9B)"
    ),
    "planar-opt": (
        "kaibridge.pcb.planar_optimizer",
        "main",
        "Simulated annealing planar placement optimizer with Kruskal MST wirelength"
    ),
    "inspect": (
        "kaibridge.pcb.inspector",
        "main",
        "Live PCB state inspection & fail-closed Gatekeeper Route-Readiness Proof (Step 9E)"
    ),
    "route": (
        "kaibridge.pcb.router",
        "main",
        "Headless Freerouting autorouter, solid GND copper pour & DRC verification gate (Step 10)"
    ),
    "diff-pair": (
        "kaibridge.pcb.diff_pair",
        "main",
        "Differential pair detection, 3D trace length audit & serpentine skew tuner (Step 10E)"
    ),
    "export": (
        "kaibridge.pcb.export",
        "main",
        "Export 100% JLCPCB manufacturing release (Gerber ZIP, Drill, BOM, CPL CSV) (Step 11)"
    ),
    "oracle": (
        "kaibridge.oracle.swig_oracle",
        "main",
        "Live KiCad pcbnew SWIG C++ reflection probe & JLCPCB DFM rule catalog (<4ms)"
    ),
    "check": (
        "kaibridge.sourcing.check_cli",
        "main",
        "Query live JLCPCB inventory stock, Basic/Extended SMT fees, and datasheets"
    ),
    "fetch": (
        "kaibridge.sourcing.jlc_api",
        "fetch_cli_main",
        "Pre-flight stock verification and modern KiCad CAD ingestion via JLC2KiCadLib"
    ),
}


def print_help():
    print(f"""\
Kaibridge Hardware Synthesis Engine (v{__version__})
Unified CLI for Headless KiCad 10 & JLCPCB Manufacturing.

Usage:
  kaibridge <command> [options] [arguments]
  python -m kaibridge <command> [options] [arguments]

Available Commands:""")
    col_width = 14
    for cmd, (_, _, desc) in sorted(COMMANDS.items()):
        print(f"  {cmd.ljust(col_width)} {desc}")

    print("""
Common Workflow Pipeline:
  kaibridge init "projects/demo"             # Step 0: Bootstrap project & libs
  kaibridge pins "projects/demo" -s ESP32   # Step 3: Inspect symbol pins
  kaibridge build "projects/demo" --erc      # Step 6: Compile schematic & run ERC
  kaibridge sync "projects/demo"             # Step 7: Update PCB from schematic (F8)
  kaibridge layout "projects/demo" --shove   # Step 8: Apply placement & push-and-shove
  kaibridge opt "projects/demo" --commit     # Step 9B: Optimize pin escapes & crossings
  kaibridge inspect "projects/demo" --audit  # Step 9E: Verify Gatekeeper route-readiness
  kaibridge route "projects/demo" --pour-gnd # Step 10: Autoroute traces & pour ground plane
  kaibridge export "projects/demo"           # Step 11: Generate JLCPCB manufacturing bundle

Help on any command:
  kaibridge <command> --help
""")


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    if argv[0] in ("-v", "--version", "version"):
        print(f"kaibridge v{__version__}")
        return 0

    cmd_name = argv[0].lower().strip()
    sub_argv = argv[1:]

    if cmd_name not in COMMANDS:
        # Check for fuzzy match
        close = difflib.get_close_matches(cmd_name, list(COMMANDS.keys()), n=1, cutoff=0.6)
        print(f"Error: Unknown command '{cmd_name}'.", file=sys.stderr)
        if close:
            print(f"Did you mean: kaibridge {close[0]}?", file=sys.stderr)
        print("Run 'kaibridge --help' for a list of available commands.", file=sys.stderr)
        return 2

    mod_name, func_name, _ = COMMANDS[cmd_name]
    try:
        import importlib
        mod = importlib.import_module(mod_name)
        target_fn: Callable = getattr(mod, func_name)
        result = target_fn(sub_argv)
        return int(result) if isinstance(result, int) else 0
    except SystemExit as se:
        return int(se.code) if se.code is not None else 0
    except Exception as e:
        print(f"Error executing 'kaibridge {cmd_name}': {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
