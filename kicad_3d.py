#!/usr/bin/env python3
"""
kicad_3d.py -- Non-blocking background 3D model downloader with pacing.
Delegates to kaibridge.sourcing.fetch_3d.main.
"""
from __future__ import annotations

import sys
from kaibridge.sourcing.fetch_3d import main

if __name__ == "__main__":
    sys.exit(main())
