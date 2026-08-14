"""
currentboardfetcher.py — Backward-compatible alias for boardmanager.py.
"""

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from boardmanager import *
