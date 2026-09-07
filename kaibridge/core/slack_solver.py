"""
kaibridge/core/slack_solver.py -- Analytical Slack Optimization & QP Throat Displacement.

Implements Milestone C, Section 8.4 from Superbrain Specification:
- Calculates exact analytical displacement vector Delta_X* to resolve corridor bottlenecks:
    min 1/2 Delta_X^T W Delta_X  s.t.  g^T Delta_X >= d
    Delta_X* = (d * W^-1 * g) / (g^T * W^-1 * g)
- Displaces entire functional envelopes along the analytical gradient of bottleneck width B(X).
- Replaces blind stochastic LLM coordinate guessing with exact mathematical widening before routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from kaibridge.core.ir import Point2D, mm_to_nm, nm_to_mm


@dataclass(frozen=True)
class CorridorSlackResult:
    """Analytical widening solution for a bottleneck throat."""
    initial_throat_width_nm: int
    required_throat_width_nm: int
    deficit_nm: int
    delta_left_nm: int
    delta_right_nm: int
    final_throat_width_nm: int
    is_feasible: bool
    explanation: str


def solve_analytical_throat_widening(
    left_pos_nm: int,
    right_pos_nm: int,
    required_width_nm: int,
    left_is_locked: bool = False,
    right_is_locked: bool = False,
    weight_left: float = 1.0,
    weight_right: float = 1.0,
    max_displacement_nm: Optional[int] = None
) -> CorridorSlackResult:
    """
    Computes exact minimum-weighted displacement Delta_X = [Delta_xL, Delta_xR]
    to satisfy throat width constraint: (xR + Delta_xR) - (xL + Delta_xL) >= B_required.
    
    Gradient of opening width B = xR - xL is:
      g = [-1, +1]^T
    
    Formula:
      Delta_X* = (d * W^-1 * g) / (g^T * W^-1 * g)
    """
    initial_b = right_pos_nm - left_pos_nm
    deficit = required_width_nm - initial_b

    if deficit <= 0:
        return CorridorSlackResult(
            initial_throat_width_nm=initial_b,
            required_throat_width_nm=required_width_nm,
            deficit_nm=0,
            delta_left_nm=0,
            delta_right_nm=0,
            final_throat_width_nm=initial_b,
            is_feasible=True,
            explanation="Corridor already satisfies required capacity (zero deficit)."
        )

    # Both locked -> Infeasible without altering constraints
    if left_is_locked and right_is_locked:
        return CorridorSlackResult(
            initial_throat_width_nm=initial_b,
            required_throat_width_nm=required_width_nm,
            deficit_nm=deficit,
            delta_left_nm=0,
            delta_right_nm=0,
            final_throat_width_nm=initial_b,
            is_feasible=False,
            explanation=f"Both corridor boundaries are mechanically locked; cannot widen deficit of {nm_to_mm(deficit):.3f}mm."
        )

    # Gradient g = [-1, 1]
    # W^-1 diagonal elements:
    w_inv_left = 0.0 if left_is_locked else (1.0 / max(1e-6, weight_left))
    w_inv_right = 0.0 if right_is_locked else (1.0 / max(1e-6, weight_right))

    # g^T * W^-1 * g = (-1)^2 * w_inv_left + (1)^2 * w_inv_right = w_inv_left + w_inv_right
    denom = w_inv_left + w_inv_right
    if denom <= 0:
        return CorridorSlackResult(
            initial_throat_width_nm=initial_b,
            required_throat_width_nm=required_width_nm,
            deficit_nm=deficit,
            delta_left_nm=0,
            delta_right_nm=0,
            final_throat_width_nm=initial_b,
            is_feasible=False,
            explanation="Zero degrees of freedom to resolve bottleneck."
        )

    # Delta_xL = -d * w_inv_left / denom
    # Delta_xR = +d * w_inv_right / denom
    delta_l = round(-deficit * (w_inv_left / denom))
    delta_r = round(deficit * (w_inv_right / denom))

    # Verify max displacement limit if specified
    if max_displacement_nm is not None:
        if abs(delta_l) > max_displacement_nm or abs(delta_r) > max_displacement_nm:
            return CorridorSlackResult(
                initial_throat_width_nm=initial_b,
                required_throat_width_nm=required_width_nm,
                deficit_nm=deficit,
                delta_left_nm=delta_l,
                delta_right_nm=delta_r,
                final_throat_width_nm=initial_b + delta_r - delta_l,
                is_feasible=False,
                explanation=f"Required displacement exceeds maximum allowed limit {nm_to_mm(max_displacement_nm):.3f}mm."
            )

    final_b = (right_pos_nm + delta_r) - (left_pos_nm + delta_l)

    return CorridorSlackResult(
        initial_throat_width_nm=initial_b,
        required_throat_width_nm=required_width_nm,
        deficit_nm=deficit,
        delta_left_nm=delta_l,
        delta_right_nm=delta_r,
        final_throat_width_nm=final_b,
        is_feasible=True,
        explanation=f"Analytically widened corridor by moving Left {nm_to_mm(delta_l):.3f}mm, Right +{nm_to_mm(delta_r):.3f}mm."
    )
