#!/usr/bin/env python3
"""
kicad_inspect.py -- Live KiCad PCB State Inspector CLI.
Delegates to kaibridge.pcb.inspector.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.inspector import main

if __name__ == "__main__":
    sys.exit(main())
