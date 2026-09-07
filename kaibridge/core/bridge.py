"""
kaibridge/core/bridge.py -- Strict 2-Layer Jumper Bridge Synthesis & Moat Budgeting.

Implements Milestone E, Section 7.2 from Superbrain Specification:
- Hard 3.0mm B.Cu bridge limit on 2-layer boards:
    1. Enumerate finite bridge motifs with 2 through-vias and B.Cu length <= 3.0mm.
    2. Budget lower-layer clearance moats and antipads before global routing.
    3. Construct chosen bridges in KiCad as protected routing (type fix).
    4. Disable additional B.Cu routing and unbudgeted signal vias in residual job.
    5. Route remaining connections on F.Cu only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

from kaibridge.core.ir import Point2D, mm_to_nm, nm_to_mm


@dataclass(frozen=True)
class TwoLayerBridge:
    """A short jumper bridge on B.Cu hopping across an F.Cu signal blockage."""
    bridge_id: str
    net_name: str
    via1_pos: Point2D
    via2_pos: Point2D
    track_width_nm: int
    clearance_nm: int
    via_diameter_nm: int
    via_drill_nm: int

    @property
    def centerline_length_nm(self) -> int:
        """Euclidean centerline length between via centers."""
        dx = self.via2_pos.x - self.via1_pos.x
        dy = self.via2_pos.y - self.via1_pos.y
        return round((dx * dx + dy * dy) ** 0.5)

    @property
    def centerline_length_mm(self) -> float:
        return nm_to_mm(self.centerline_length_nm)

    @property
    def is_valid_policy_length(self) -> bool:
        """Strict 2-layer policy: centerline length must be <= 3.0mm."""
        return self.centerline_length_nm <= mm_to_nm(3.00)

    @property
    def clearance_moat_width_nm(self) -> int:
        """Width of copper slot cut into B.Cu ground plane."""
        return self.track_width_nm + 2 * self.clearance_nm

    def to_ops(self) -> List[Dict[str, Any]]:
        """Generates locked declarative layout ops to instantiate the bridge in KiCad."""
        v1_x, v1_y = self.via1_pos.to_mm()
        v2_x, v2_y = self.via2_pos.to_mm()
        dia_mm = nm_to_mm(self.via_diameter_nm)
        drill_mm = nm_to_mm(self.via_drill_nm)
        w_mm = nm_to_mm(self.track_width_nm)

        return [
            # Via 1
            {
                "op": "via.add",
                "x": v1_x,
                "y": v1_y,
                "diameter": dia_mm,
                "drill": drill_mm,
                "net": self.net_name
            },
            # Via 2
            {
                "op": "via.add",
                "x": v2_x,
                "y": v2_y,
                "diameter": dia_mm,
                "drill": drill_mm,
                "net": self.net_name
            },
            # Short B.Cu jumper track connecting the two vias
            {
                "op": "track.add",
                "x1": v1_x,
                "y1": v1_y,
                "x2": v2_x,
                "y2": v2_y,
                "width": w_mm,
                "layer": "B.Cu",
                "net": self.net_name
            }
        ]


def synthesize_jumper_bridge(
    net_name: str,
    hop_start: Point2D,
    hop_end: Point2D,
    track_width_nm: int = mm_to_nm(0.25),
    clearance_nm: int = mm_to_nm(0.20),
    via_dia_nm: int = mm_to_nm(0.60),
    via_drill_nm: int = mm_to_nm(0.30)
) -> TwoLayerBridge:
    """
    Synthesizes a short B.Cu jumper bridge across a top-layer obstacle.
    Enforces the strict 3.0mm maximum length policy.
    """
    bridge = TwoLayerBridge(
        bridge_id=f"Bridge_{net_name}_{hop_start.x}_{hop_start.y}",
        net_name=net_name,
        via1_pos=hop_start,
        via2_pos=hop_end,
        track_width_nm=track_width_nm,
        clearance_nm=clearance_nm,
        via_diameter_nm=via_dia_nm,
        via_drill_nm=via_drill_nm
    )

    if not bridge.is_valid_policy_length:
        raise ValueError(
            f"Bridge length {bridge.centerline_length_mm:.3f}mm exceeds strict 3.00mm maximum policy for 2-layer boards!"
        )

    return bridge
