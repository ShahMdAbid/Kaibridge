#!/usr/bin/env python3
"""
json2sch.py -- compile design.json into KiCad hierarchical schematics.
Delegates to kaibridge.schematic.compiler.main.
"""
from __future__ import annotations

import sys
from kaibridge.schematic.compiler import main

if __name__ == "__main__":
    sys.exit(main())
