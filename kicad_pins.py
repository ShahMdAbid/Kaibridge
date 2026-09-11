#!/usr/bin/env python3
"""
kicad_pins.py -- read pins out of .kicad_sym files and verify their footprints.
Delegates to kaibridge.sourcing.pins.main.
"""
from __future__ import annotations

import sys
from kaibridge.sourcing.pins import main

if __name__ == "__main__":
    sys.exit(main())
