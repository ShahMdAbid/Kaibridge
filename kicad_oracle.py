#!/usr/bin/env python3
"""
kicad_oracle.py -- Live KiCad pcbnew SWIG C++ Oracle CLI (<4ms).
Delegates to kaibridge.oracle.swig_oracle.main.
"""
from __future__ import annotations

import sys
from kaibridge.oracle.swig_oracle import main

if __name__ == "__main__":
    sys.exit(main())
