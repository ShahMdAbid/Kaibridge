#!/usr/bin/env python3
"""
kicad_pcb_sync.py -- Headless Schematic-to-PCB Synchronization (Programmatic F8).
Delegates to kaibridge.pcb.sync.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.sync import main

if __name__ == "__main__":
    sys.exit(main())
