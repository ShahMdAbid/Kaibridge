#!/usr/bin/env python3
"""
kicad_planar_optimizer.py -- CLI runner for Simulated Annealing Planar Layout Optimizer.
Delegates execution to kaibridge.pcb.planar_optimizer.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.planar_optimizer import PlanarLayoutOptimizer, main

if __name__ == "__main__":
    sys.exit(main())
