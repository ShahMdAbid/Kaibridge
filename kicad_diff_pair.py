#!/usr/bin/env python3
"""
kicad_diff_pair.py -- Differential Pair Synthesizer, Netclass Sync & Length/Skew Auditor CLI.
Delegates to kaibridge.pcb.diff_pair.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.diff_pair import main

if __name__ == "__main__":
    sys.exit(main())
