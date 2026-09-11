#!/usr/bin/env python3
"""
kicad_layout.py -- Declarative Component Placement & Layout Engine CLI.
Delegates to kaibridge.pcb.layout.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.layout import main

if __name__ == "__main__":
    sys.exit(main())
