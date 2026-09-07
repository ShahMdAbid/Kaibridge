"""
kaibridge/core/channels.py -- Geometric Throat Capacity & Separating Cut Invariants.

Implements Milestone C from Superbrain Specification:
- Section 3.2: Channel Graph with Order and Capacity
- Section 3.3: Exact Capacity Equations:
    B_required = N*w + (N-1)*s + b_L + b_R
    C = max(0, floor((B - b_L - b_R + s) / (w + s)))
    B_required(pi) = b_L + b_R + sum(w_i) + sum(s_{i, i+1})
- Section 3.4: Separating Cut Capacity Gate E6: D(K) <= C(K)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from kaibridge.core.ir import (
    Point2D, Certificate, mm_to_nm, nm_to_mm
)


@dataclass(frozen=True)
class GeometricThroat:
    """A cross-section bottleneck corridor between two obstacle boundaries."""
    throat_id: str
    left_boundary_nm: int   # X or Y coordinate of left/bottom obstacle edge
    right_boundary_nm: int  # X or Y coordinate of right/top obstacle edge
    layer: str = "F.Cu"

    @property
    def raw_width_nm(self) -> int:
        """Raw physical throat opening B."""
        return max(0, self.right_boundary_nm - self.left_boundary_nm)

    @property
    def raw_width_mm(self) -> float:
        return nm_to_mm(self.raw_width_nm)


def compute_homogeneous_throat_capacity(
    raw_throat_width_nm: int,
    trace_width_nm: int,
    trace_spacing_nm: int,
    boundary_clearance_left_nm: int,
    boundary_clearance_right_nm: int
) -> Tuple[int, int]:
    """
    Computes maximum lane capacity C and required width for given traces.
    
    Formula from Superbrain Spec Section 3.3:
      B_required(N) = N * w + (N - 1) * s + b_L + b_R
      C = max(0, floor((B - b_L - b_R + s) / (w + s)))
    
    Returns:
      (capacity_lanes, pitch_unit_nm)
    """
    b_l = boundary_clearance_left_nm
    b_r = boundary_clearance_right_nm
    w = trace_width_nm
    s = trace_spacing_nm

    available = raw_throat_width_nm - b_l - b_r + s
    if available <= 0 or (w + s) <= 0:
        return 0, w + s

    c = available // (w + s)
    return max(0, c), w + s


def compute_required_throat_width(
    num_traces: int,
    trace_width_nm: int,
    trace_spacing_nm: int,
    boundary_clearance_left_nm: int,
    boundary_clearance_right_nm: int
) -> int:
    """Computes exact required raw throat width B_required for N traces."""
    if num_traces <= 0:
        return 0
    return (
        num_traces * trace_width_nm +
        (num_traces - 1) * trace_spacing_nm +
        boundary_clearance_left_nm +
        boundary_clearance_right_nm
    )


def compute_heterogeneous_throat_width(
    trace_widths_nm: Tuple[int, ...],
    spacings_nm: Tuple[int, ...],
    boundary_clearance_left_nm: int,
    boundary_clearance_right_nm: int
) -> int:
    """
    Computes required throat width for heterogeneous ordered trace bundle:
      B_required(pi) = b_L + b_R + sum(w_i) + sum(s_{i, i+1})
    """
    n = len(trace_widths_nm)
    if n == 0:
        return 0
    total_w = sum(trace_widths_nm)
    total_s = sum(spacings_nm[:n - 1]) if len(spacings_nm) >= n - 1 else 0
    return boundary_clearance_left_nm + boundary_clearance_right_nm + total_w + total_s


@dataclass(frozen=True)
class CutDemand:
    """Routing demand across a separating cut throat."""
    throat: GeometricThroat
    net_names: Tuple[str, ...]
    trace_width_nm: int
    trace_spacing_nm: int
    boundary_clearance_nm: int


def verify_e6_channel_cut_capacity(cut: CutDemand) -> Certificate:
    """
    Pre-flight Invariant Gate E6:
    Verifies that separating cut demand does not exceed geometric throat capacity:
      D(K) <= C(K)
    If D(K) > C(K), returns a concrete infeasibility certificate with exact deficit.
    """
    demand_n = len(cut.net_names)
    b_raw = cut.throat.raw_width_nm
    b_req = compute_required_throat_width(
        num_traces=demand_n,
        trace_width_nm=cut.trace_width_nm,
        trace_spacing_nm=cut.trace_spacing_nm,
        boundary_clearance_left_nm=cut.boundary_clearance_nm,
        boundary_clearance_right_nm=cut.boundary_clearance_nm
    )
    cap, _ = compute_homogeneous_throat_capacity(
        raw_throat_width_nm=b_raw,
        trace_width_nm=cut.trace_width_nm,
        trace_spacing_nm=cut.trace_spacing_nm,
        boundary_clearance_left_nm=cut.boundary_clearance_nm,
        boundary_clearance_right_nm=cut.boundary_clearance_nm
    )

    passed = demand_n <= cap
    deficit_nm = max(0, b_req - b_raw)

    witness = {
        "throat_id": cut.throat.throat_id,
        "raw_width_mm": nm_to_mm(b_raw),
        "required_width_mm": nm_to_mm(b_req),
        "capacity_lanes": cap,
        "demand_lanes": demand_n,
        "deficit_mm": nm_to_mm(deficit_nm)
    }

    if not passed:
        err = (
            f"Separating cut throat '{cut.throat.throat_id}' saturated: "
            f"demand={demand_n} lanes, capacity={cap} lanes "
            f"(raw width={nm_to_mm(b_raw):.3f}mm < required={nm_to_mm(b_req):.3f}mm, "
            f"deficit={nm_to_mm(deficit_nm):.3f}mm)"
        )
    else:
        err = None

    return Certificate(
        invariant_id="E6_CHANNEL_CUT_CAPACITY",
        passed=passed,
        witness_data=witness,
        error_message=err
    )
