"""
currentboardfetcher.py — Backward-compatible facade for Autoplacer/board_engine.

This file re-exports all functions, classes, and constants from the modular
board_engine package (common, gatekeeper, backup, fetcher, applier) so existing
callers, bridges, and scripts continue to work without any modifications.
"""

import os
import sys
import json

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from board_engine.common import *
from board_engine.gatekeeper import *
from board_engine.backup import *
from board_engine.fetcher import *
from board_engine.applier import *

if __name__ == "__main__":
    _b = resolve_board()
    print(json.dumps(get_full_board_state(_b), indent=2, default=safe_json_default))
