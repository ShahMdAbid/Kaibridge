"""
kaibridge/core/bus_order.py -- O(KN log N) Zero-Braid Bus Orientation Solver.

Implements Milestone C, Section 3.6 from Superbrain Specification:
- Fenwick Tree (Binary Indexed Tree) for O(N log N) permutation inversion counting.
- Evaluates K fixed discrete orientations (0, 90, 180, 270 degrees).
- Projects escape ports onto transverse strip axis.
- Finds optimal rotation theta* that achieves zero inversions (planar non-crossing bus routing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from kaibridge.core.ir import Point2D
from kaibridge.core.motifs import rotate_point


class FenwickTree:
    """Binary Indexed Tree (BIT) for efficient O(log N) prefix sums and point updates."""
    def __init__(self, size: int):
        self.size = size
        self.tree = [0] * (size + 2)

    def add(self, index: int, value: int = 1):
        """Adds value at 1-based index."""
        i = index
        while i <= self.size:
            self.tree[i] += value
            i += i & (-i)

    def query(self, index: int) -> int:
        """Returns sum of elements in [1, index]."""
        s = 0
        i = index
        while i > 0:
            s += self.tree[i]
            i -= i & (-i)
        return s


def count_inversions(perm: List[int]) -> int:
    """
    Counts number of inversions in permutation array in O(N log N) time using a Fenwick tree.
    An inversion is a pair (i, j) such that i < j and perm[i] > perm[j].
    """
    n = len(perm)
    if n <= 1:
        return 0

    # Coordinate compression to ensure elements are 1..N
    sorted_unique = sorted(set(perm))
    rank_map = {val: idx + 1 for idx, val in enumerate(sorted_unique)}
    ranks = [rank_map[x] for x in perm]

    bit = FenwickTree(len(sorted_unique))
    inversions = 0

    # Traverse from right to left
    for rank in reversed(ranks):
        # Query count of elements smaller than current rank already processed
        inversions += bit.query(rank - 1)
        bit.add(rank, 1)

    return inversions


@dataclass(frozen=True)
class BusOrientationResult:
    """Result of zero-braid bus orientation optimization."""
    best_orientation_deg: float
    min_inversions: int
    is_planar_zero_braid: bool
    orientation_inversion_table: Dict[float, int]
    source_order: Tuple[str, ...]
    dest_order: Tuple[str, ...]


def solve_zero_braid_orientation(
    source_ports: Dict[str, Point2D],       # Net name -> source pad coordinate
    dest_ports: Dict[str, Point2D],         # Net name -> destination pad coordinate
    transverse_axis: str = "Y",             # "X" or "Y" (axis perpendicular to bus flow)
    allowed_rotations: Tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
) -> BusOrientationResult:
    """
    Solves for the orientation of the source component that minimizes or eliminates bus crossings.
    
    Algorithm:
      1. For each rotation theta in allowed_rotations:
         a. Rotate source ports by theta around their centroid.
         b. Project source ports and destination ports onto transverse_axis.
         c. Sort both by projected coordinate in the same direction.
         d. Determine destination rank permutation of source nets.
         e. Count inversions in O(N log N) with Fenwick tree.
      2. Return rotation with minimum inversions (0 inversions = guaranteed non-crossing planar bus).
    """
    common_nets = sorted(set(source_ports.keys()).intersection(dest_ports.keys()))
    n = len(common_nets)
    if n <= 1:
        return BusOrientationResult(
            best_orientation_deg=0.0,
            min_inversions=0,
            is_planar_zero_braid=True,
            orientation_inversion_table={0.0: 0},
            source_order=tuple(common_nets),
            dest_order=tuple(common_nets)
        )

    # Destination ports sorted along transverse axis
    def get_coord(pt: Point2D) -> int:
        return pt.y if transverse_axis.upper() == "Y" else pt.x

    sorted_dest_nets = sorted(common_nets, key=lambda net: get_coord(dest_ports[net]))
    dest_rank_map = {net: rank for rank, net in enumerate(sorted_dest_nets)}

    # Centroid of source ports for rotation
    src_cx = sum(source_ports[net].x for net in common_nets) // n
    src_cy = sum(source_ports[net].y for net in common_nets) // n
    src_centroid = Point2D(src_cx, src_cy)

    inversion_table: Dict[float, int] = {}
    best_rot = 0.0
    min_inv = float("inf")
    best_src_order: Tuple[str, ...] = ()

    for rot in allowed_rotations:
        # Rotate source ports around centroid
        rotated_src: Dict[str, Point2D] = {}
        for net in common_nets:
            p = source_ports[net]
            # Center, rotate, uncenter
            rel = Point2D(p.x - src_centroid.x, p.y - src_centroid.y)
            rot_rel = rotate_point(rel, rot)
            rotated_src[net] = Point2D(rot_rel.x + src_centroid.x, rot_rel.y + src_centroid.y)

        # Sort source nets along transverse axis
        sorted_src_nets = sorted(common_nets, key=lambda net: get_coord(rotated_src[net]))
        # Derive permutation of destination ranks
        perm = [dest_rank_map[net] for net in sorted_src_nets]
        inv = count_inversions(perm)

        inversion_table[rot] = inv
        if inv < min_inv:
            min_inv = inv
            best_rot = rot
            best_src_order = tuple(sorted_src_nets)

    return BusOrientationResult(
        best_orientation_deg=best_rot,
        min_inversions=int(min_inv),
        is_planar_zero_braid=(min_inv == 0),
        orientation_inversion_table=inversion_table,
        source_order=best_src_order,
        dest_order=tuple(sorted_dest_nets)
    )
