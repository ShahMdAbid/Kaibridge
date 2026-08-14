"""
Autoplacer/board_engine — Modular KiCad Board Engine (State extraction, geometry gate, and ops application).
"""

from .common import (
    SCHEMA_VERSION, BUILD_VERSION, OpError,
    resolve_board, safe_json_default, to_mm, from_mm, deg, mk_point, pt,
    uuid_of, build_index
)
from .gatekeeper import (
    box_of, board_bounds, placement_report, _geometry_gate
)
from .backup import (
    snapshot, load_state, diff_states, print_diff, quick_diff
)
from .fetcher import (
    get_full_board_state, ai_context, ensure_intent, load_intent
)
from .applier import (
    OPS, apply_ops
)

__all__ = [
    "SCHEMA_VERSION", "BUILD_VERSION", "OpError",
    "resolve_board", "safe_json_default", "to_mm", "from_mm", "deg", "mk_point", "pt",
    "uuid_of", "build_index",
    "box_of", "board_bounds", "placement_report", "_geometry_gate",
    "snapshot", "load_state", "diff_states", "print_diff", "quick_diff",
    "get_full_board_state", "ai_context", "ensure_intent", "load_intent",
    "OPS", "apply_ops"
]
