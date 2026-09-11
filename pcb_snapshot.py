#!/usr/bin/env python3
"""pcb_snapshot.py -- Backward-compatible wrapper delegating to kaibridge.pcb.snapshot_cli."""
import sys
from kaibridge.pcb.snapshot_cli import main, export_snapshot, export_schematic_snapshot, export_3d_snapshot, resolve_board

if __name__ == "__main__":
    sys.exit(main())
