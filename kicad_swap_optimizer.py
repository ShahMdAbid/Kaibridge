#!/usr/bin/env python3
"""CLI for the physics-preserving ISRRO-X post-placement optimizer.
Delegates to kaibridge.pcb.swap_optimizer.main.
"""
from __future__ import annotations

import sys
from kaibridge.pcb.swap_optimizer import main

if __name__ == "__main__":
    raise SystemExit(main())
