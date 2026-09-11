#!/usr/bin/env python3
"""
kicad_lib_init.py -- add project-scoped library plumbing to an existing KiCad project.
Delegates to kaibridge.core.init.main.
"""
from __future__ import annotations

import sys
from kaibridge.core.init import main, init_libraries

if __name__ == "__main__":
    sys.exit(main())
