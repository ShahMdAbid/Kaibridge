#!/usr/bin/env python3
"""
kicad_route.py -- Headless Autorouting, Ground Pour & DRC Execution CLI.
Delegates to kaibridge.pcb.router.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.router import main

if __name__ == "__main__":
    sys.exit(main())
