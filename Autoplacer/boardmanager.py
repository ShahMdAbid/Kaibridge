"""
boardmanager.py — PCB Board Management & Execution Interface.

Exposes the board_engine package (state extraction, 16 ops, geometry gate, backups).
"""

import os
import sys
import json

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from board_engine import *

if __name__ == "__main__":
    _b = resolve_board()
    print(json.dumps(get_full_board_state(_b), indent=2, default=safe_json_default))
