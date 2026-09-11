#!/usr/bin/env python3
"""
export_jlcpcb.py -- Automated Production Exporter for JLCPCB (Gerbers, Drill, BOM, CPL).
Delegates to kaibridge.pcb.export.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.export import main

if __name__ == "__main__":
    sys.exit(main())
