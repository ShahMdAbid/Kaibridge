"""Physics-preserving isomorphic swap/rotate detailed placer for Kaibridge.

ISRRO-X is a post-placement optimizer.  It never rewires the schematic and it
never mutates pcbnew objects during search.  The board is extracted into plain
Python geometry, searched deterministically, independently re-evaluated, and
only then (optionally) committed in one transaction.

The implementation deliberately calls crossings, HPWL, MST length, RUDY and
escape blockage *routing proxies*.  A lower proxy score is not proof that a
specific detailed router will use fewer vias.  The report is designed so a
router-in-the-loop benchmark can test that hypothesis.
"""
from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import math
import os
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

Point = Tuple[float, float]
EPS = 1.0e-9


# ---------------------------------------------------------------------------
# Robust, dependency-free 2-D geometry
# ---------------------------------------------------------------------------

def _angle(value: float) -> float:
    a = float(value) % 360.0
    return 0.0 if abs(a - 360.0) < 1.0e-8 else a


def rotate_point(p: Point, degrees: float) -> Point:
    a = _angle(degrees)
    if abs(a - 0.0) < 1.0e-8:
        return p
    if abs(a - 90.0) < 1.0e-8:
        return (-p[1], p[0])
    if abs(a - 180.0) < 1.0e-8:
        return (-p[0], -p[1])
    if abs(a - 270.0) < 1.0e-8:
        return (p[1], -p[0])
    r = math.radians(a)
    c, s = math.cos(r), math.sin(r)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def inverse_rotate_point(p: Point, degrees: float) -> Point:
    return rotate_point(p, -degrees)


def orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _same_point(a: Point, b: Point, eps: float = 1.0e-7) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _on_segment(a: Point, b: Point, p: Point, eps: float = 1.0e-9) -> bool:
    return (
        abs(orient(a, b, p)) <= eps
        and min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def segments_intersect_inclusive(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    ):
        return True
    return (
        (abs(o1) <= EPS and _on_segment(a, b, c))
        or (abs(o2) <= EPS and _on_segment(a, b, d))
        or (abs(o3) <= EPS and _on_segment(c, d, a))
        or (abs(o4) <= EPS and _on_segment(c, d, b))
    )


def segments_properly_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True only for a proper X crossing; shared/touching endpoints are excluded."""
    if any(_same_point(x, y) for x in (a, b) for y in (c, d)):
        return False
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    )


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    denom = vx * vx + vy * vy
    if denom <= EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / denom))
    q = (a[0] + t * vx, a[1] + t * vy)
    return math.hypot(p[0] - q[0], p[1] - q[1])


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_intersect_inclusive(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def polygon_edges(poly: Sequence[Point]) -> Iterable[Tuple[Point, Point]]:
    for i, p in enumerate(poly):
        yield p, poly[(i + 1) % len(poly)]


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    if len(poly) < 3:
        return False
    for a, b in polygon_edges(poly):
        if _on_segment(a, b, p):
            return True
    inside = False
    x, y = p
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def convex_hull(points: Sequence[Point]) -> Tuple[Point, ...]:
    pts = sorted(set((round(float(x), 9), round(float(y), 9)) for x, y in points))
    if len(pts) <= 1:
        return tuple(pts)

    def half(seq: Sequence[Point]) -> List[Point]:
        h: List[Point] = []
        for p in seq:
            while len(h) >= 2 and orient(h[-2], h[-1], p) <= EPS:
                h.pop()
            h.append(p)
        return h

    return tuple(half(pts)[:-1] + half(list(reversed(pts)))[:-1])


def transform_polygon(poly: Sequence[Point], x: float, y: float, rot: float) -> Tuple[Point, ...]:
    return tuple((x + q[0], y + q[1]) for q in (rotate_point(p, rot) for p in poly))


def polygon_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    if not a or not b:
        return float("inf")
    if point_in_polygon(a[0], b) or point_in_polygon(b[0], a):
        return 0.0
    best = float("inf")
    for a0, a1 in polygon_edges(a):
        for b0, b1 in polygon_edges(b):
            best = min(best, segment_distance(a0, a1, b0, b1))
            if best <= EPS:
                return 0.0
    return best


def polygon_inside_outline(poly: Sequence[Point], outline: Sequence[Point]) -> bool:
    if not poly or not outline or any(not point_in_polygon(p, outline) for p in poly):
        return False
    # Vertex inclusion alone is insufficient for a concave outline.
    for a, b in polygon_edges(poly):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if not point_in_polygon(mid, outline):
            return False
    return True


def bbox(poly: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Plain-Python placement model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PadSite:
    uid: str
    number: str
    net: str
    local: Point
    width: float = 0.0
    height: float = 0.0
    drill: float = 0.0


@dataclass
class Component:
    ref: str
    fpid: str
    layer: str
    initial_x: float
    initial_y: float
    initial_rotation: float
    envelope: Tuple[Point, ...]
    pads: Tuple[PadSite, ...]
    geometry_hash: str
    locked: bool = False
    through_hole: bool = False
    group: str = ""
    role: str = ""
    anchor: Optional[str] = None
    max_anchor_distance: Optional[float] = None
    max_displacement: Optional[float] = None
    allowed_rotations: Tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    swap_class: Optional[str] = None
    optimizer_opt_in: bool = False
    geometry_source: str = "unknown"


@dataclass(frozen=True)
class Transform:
    x: float
    y: float
    rotation: float


@dataclass(frozen=True)
class SeparationRule:
    a: str
    b: str
    min_distance: float


@dataclass
class PlacementProblem:
    components: Dict[str, Component]
    board_outline: Tuple[Point, ...]
    net_weights: Dict[str, float] = field(default_factory=dict)
    excluded_nets: Set[str] = field(default_factory=set)
    keepouts: Tuple[Tuple[Point, ...], ...] = ()
    separation_rules: Tuple[SeparationRule, ...] = ()
    source: Dict[str, Any] = field(default_factory=dict)

    def initial_state(self) -> Dict[str, Transform]:
        return {
            ref: Transform(c.initial_x, c.initial_y, _angle(c.initial_rotation))
            for ref, c in self.components.items()
        }


@dataclass
class OptimizerConfig:
    clearance_mm: float = 0.25
    grid_mm: float = 0.1
    allowed_rotations: Tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    max_passes: int = 8
    max_evaluations: int = 12000
    max_pairs_per_class: int = 250
    time_limit_s: float = 20.0
    strict_same_anchor: bool = True
    preserve_group: bool = True
    enable_single_rotation: bool = True
    enable_three_cycles: bool = True
    three_cycle_class_limit: int = 7
    three_cycle_triple_limit: int = 20
    escape_length_mm: float = 1.5
    route_pitch_mm: float = 0.35
    rudy_bins_x: int = 18
    rudy_bins_y: int = 14
    rudy_limit: float = 1.0
    nonworsening_anchor_tolerance_mm: float = 0.05
    ignore_plane_nets: bool = True
    allow_routed_board: bool = False
    commit: bool = False
    locked_refs: Tuple[str, ...] = ()
    report_name: str = "isrro_report.json"

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "OptimizerConfig":
        if not raw:
            return cls()
        valid = {f.name for f in dataclasses.fields(cls)}
        data = {k: v for k, v in dict(raw).items() if k in valid}
        for key in ("allowed_rotations", "locked_refs"):
            if key in data and isinstance(data[key], list):
                data[key] = tuple(data[key])
        return cls(**data)


@dataclass(frozen=True)
class Segment:
    a: Point
    b: Point
    net: str
    refs: Tuple[str, str]


@dataclass(frozen=True)
class Score:
    hard_violations: int
    hard_magnitude: float
    physics_violations: int
    physics_penalty: float
    blocked_escapes: int
    rudy_overflow: float
    weighted_crossings: float
    crossings: int
    rudy_peak: float
    weighted_hpwl: float
    weighted_mst: float
    displacement: float

    def key(self) -> Tuple[Any, ...]:
        # True lexicographic ordering: no arbitrary giant scalar weights.
        return (
            self.hard_violations,
            round(self.hard_magnitude, 7),
            self.physics_violations,
            round(self.physics_penalty, 7),
            self.blocked_escapes,
            round(self.rudy_overflow, 7),
            round(self.weighted_crossings, 7),
            self.crossings,
            round(self.rudy_peak, 7),
            round(self.weighted_hpwl, 7),
            round(self.weighted_mst, 7),
            round(self.displacement, 7),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    score: Score
    segments: Tuple[Segment, ...]
    crossing_culprits: Set[str]
    blocked_culprits: Set[str]
    details: Dict[str, Any]


@dataclass
class Move:
    kind: str
    refs: Tuple[str, ...]
    transforms: Dict[str, Transform]
    evaluation: Evaluation


# ---------------------------------------------------------------------------
# Deterministic evaluator
# ---------------------------------------------------------------------------

class PlacementEvaluator:
    def __init__(self, problem: PlacementProblem, config: OptimizerConfig):
        self.problem = problem
        self.config = config
        self.initial = problem.initial_state()
        self.terminals_by_net: Dict[str, List[Tuple[str, PadSite]]] = defaultdict(list)
        for ref, comp in problem.components.items():
            for pad in comp.pads:
                if pad.net and pad.net not in problem.excluded_nets:
                    self.terminals_by_net[pad.net].append((ref, pad))
        self._initial_anchor_distances: Dict[str, float] = {}
        for ref, comp in problem.components.items():
            if comp.anchor and comp.anchor in problem.components:
                self._initial_anchor_distances[ref] = self.anchor_distance(ref, comp.anchor, self.initial)

    def abs_pad(self, ref: str, pad: PadSite, state: Mapping[str, Transform]) -> Point:
        t = state[ref]
        q = rotate_point(pad.local, t.rotation)
        return (t.x + q[0], t.y + q[1])

    def transformed_envelopes(self, state: Mapping[str, Transform]) -> Dict[str, Tuple[Point, ...]]:
        return {
            ref: transform_polygon(c.envelope, state[ref].x, state[ref].y, state[ref].rotation)
            for ref, c in self.problem.components.items()
        }

    def anchor_distance(self, ref: str, anchor: str, state: Mapping[str, Transform]) -> float:
        c, a = self.problem.components[ref], self.problem.components[anchor]
        shared = {p.net for p in c.pads if p.net} & {p.net for p in a.pads if p.net}
        candidates: List[float] = []
        for p in c.pads:
            if p.net not in shared:
                continue
            pp = self.abs_pad(ref, p, state)
            for q in a.pads:
                if q.net == p.net:
                    qq = self.abs_pad(anchor, q, state)
                    candidates.append(math.hypot(pp[0] - qq[0], pp[1] - qq[1]))
        if candidates:
            return min(candidates)
        tr, ta = state[ref], state[anchor]
        return math.hypot(tr.x - ta.x, tr.y - ta.y)

    @staticmethod
    def _mst(points: Sequence[Tuple[Point, str]]) -> List[Tuple[int, int, float]]:
        n = len(points)
        if n <= 1:
            return []
        used = [False] * n
        used[0] = True
        best = [float("inf")] * n
        parent = [-1] * n
        for j in range(1, n):
            best[j] = math.hypot(points[j][0][0] - points[0][0][0], points[j][0][1] - points[0][0][1])
            parent[j] = 0
        edges: List[Tuple[int, int, float]] = []
        for _ in range(n - 1):
            choices = [(best[j], j) for j in range(n) if not used[j]]
            if not choices:
                break
            dist, j = min(choices, key=lambda z: (z[0], points[z[1]][1], z[1]))
            used[j] = True
            edges.append((parent[j], j, dist))
            for k in range(n):
                if used[k]:
                    continue
                d = math.hypot(points[k][0][0] - points[j][0][0], points[k][0][1] - points[j][0][1])
                if d < best[k] - EPS or (abs(d - best[k]) <= EPS and j < parent[k]):
                    best[k], parent[k] = d, j
        return edges

    def _net_geometry(self, state: Mapping[str, Transform]) -> Tuple[List[Segment], float, float, Dict[str, Tuple[float, float, float, float]]]:
        segments: List[Segment] = []
        weighted_hpwl = 0.0
        weighted_mst = 0.0
        net_boxes: Dict[str, Tuple[float, float, float, float]] = {}
        for net in sorted(self.terminals_by_net):
            terminals = self.terminals_by_net[net]
            points = [(self.abs_pad(ref, pad, state), f"{ref}:{pad.uid}") for ref, pad in terminals]
            if len(points) < 2:
                continue
            xs, ys = [p[0][0] for p in points], [p[0][1] for p in points]
            box = (min(xs), min(ys), max(xs), max(ys))
            net_boxes[net] = box
            weight = float(self.problem.net_weights.get(net, 1.0))
            weighted_hpwl += weight * ((box[2] - box[0]) + (box[3] - box[1]))
            for u, v, d in self._mst(points):
                ru = terminals[u][0]
                rv = terminals[v][0]
                segments.append(Segment(points[u][0], points[v][0], net, (ru, rv)))
                weighted_mst += weight * d
        return segments, weighted_hpwl, weighted_mst, net_boxes

    def _rudy(self, net_boxes: Mapping[str, Tuple[float, float, float, float]]) -> Tuple[float, float]:
        x0, y0, x1, y1 = bbox(self.problem.board_outline)
        nx, ny = max(2, self.config.rudy_bins_x), max(2, self.config.rudy_bins_y)
        dx, dy = max(EPS, (x1 - x0) / nx), max(EPS, (y1 - y0) / ny)
        bins = [0.0] * (nx * ny)
        pitch = max(0.05, self.config.route_pitch_mm)
        for net, (ax0, ay0, ax1, ay1) in net_boxes.items():
            sx, sy = max(pitch, ax1 - ax0), max(pitch, ay1 - ay0)
            density = self.problem.net_weights.get(net, 1.0) * (sx + sy) / (sx * sy)
            ix0 = max(0, min(nx - 1, int((ax0 - x0) / dx)))
            ix1 = max(0, min(nx - 1, int((ax1 - x0) / dx)))
            iy0 = max(0, min(ny - 1, int((ay0 - y0) / dy)))
            iy1 = max(0, min(ny - 1, int((ay1 - y0) / dy)))
            for iy in range(iy0, iy1 + 1):
                by0, by1 = y0 + iy * dy, y0 + (iy + 1) * dy
                oy = max(0.0, min(ay1, by1) - max(ay0, by0))
                if sy <= pitch + EPS:
                    oy = min(dy, pitch)
                for ix in range(ix0, ix1 + 1):
                    bx0, bx1 = x0 + ix * dx, x0 + (ix + 1) * dx
                    ox = max(0.0, min(ax1, bx1) - max(ax0, bx0))
                    if sx <= pitch + EPS:
                        ox = min(dx, pitch)
                    bins[iy * nx + ix] += density * max(ox * oy, pitch * pitch)
        peak = max(bins, default=0.0)
        overflow = sum(max(0.0, v - self.config.rudy_limit) for v in bins)
        return peak, overflow

    def _escape_blockage(
        self,
        state: Mapping[str, Transform],
        envelopes: Mapping[str, Sequence[Point]],
    ) -> Tuple[int, Set[str]]:
        blocked = 0
        culprits: Set[str] = set()
        radius = self.config.route_pitch_mm / 2.0
        length = self.config.escape_length_mm
        for ref, comp in self.problem.components.items():
            t = state[ref]
            for pad in comp.pads:
                if not pad.net or pad.net in self.problem.excluded_nets:
                    continue
                norm = math.hypot(pad.local[0], pad.local[1])
                if norm < 0.05:  # Center/exposed pads need a characterized via motif, not a guessed radial ray.
                    continue
                local_dir = (pad.local[0] / norm, pad.local[1] / norm)
                direction = rotate_point(local_dir, t.rotation)
                start = self.abs_pad(ref, pad, state)
                end = (start[0] + direction[0] * length, start[1] + direction[1] * length)
                hit = False
                for other, other_comp in self.problem.components.items():
                    if other == ref:
                        continue
                    if comp.layer != other_comp.layer and not (comp.through_hole or other_comp.through_hole):
                        continue
                    poly = envelopes[other]
                    if point_in_polygon(start, poly) or point_in_polygon(end, poly):
                        hit = True
                    else:
                        for a, b in polygon_edges(poly):
                            if segment_distance(start, end, a, b) < radius - EPS:
                                hit = True
                                break
                    if hit:
                        blocked += 1
                        culprits.update((ref, other))
                        break
        return blocked, culprits

    def quick_legal(self, state: Mapping[str, Transform], changed: Set[str]) -> bool:
        """Fast rejection of moves that introduce a local hard violation."""
        envelopes = {
            r: transform_polygon(self.problem.components[r].envelope, state[r].x, state[r].y, state[r].rotation)
            for r in self.problem.components
        }
        for ref in changed:
            c, t = self.problem.components[ref], state[ref]
            if c.locked and t != self.initial[ref]:
                return False
            if not any(abs((_angle(t.rotation) - _angle(a) + 180.0) % 360.0 - 180.0) < 1.0e-6 for a in c.allowed_rotations):
                return False
            if not polygon_inside_outline(envelopes[ref], self.problem.board_outline):
                return False
            if c.max_displacement is not None:
                d = math.hypot(t.x - c.initial_x, t.y - c.initial_y)
                if d > c.max_displacement + EPS:
                    return False
            for keepout in self.problem.keepouts:
                if polygon_distance(envelopes[ref], keepout) < self.config.clearance_mm - EPS:
                    return False
            for other, oc in self.problem.components.items():
                if other == ref:
                    continue
                if c.layer != oc.layer and not (c.through_hole or oc.through_hole):
                    continue
                if polygon_distance(envelopes[ref], envelopes[other]) < self.config.clearance_mm - EPS:
                    return False
        return True

    def evaluate(self, state: Mapping[str, Transform]) -> Evaluation:
        envelopes = self.transformed_envelopes(state)
        hard_count = 0
        hard_magnitude = 0.0
        hard_details: List[str] = []

        refs = sorted(self.problem.components)
        for ref in refs:
            comp, t, poly = self.problem.components[ref], state[ref], envelopes[ref]
            if comp.locked and t != self.initial[ref]:
                hard_count += 1
                hard_magnitude += math.hypot(t.x - comp.initial_x, t.y - comp.initial_y) + abs(t.rotation - comp.initial_rotation) / 90.0
                hard_details.append(f"locked:{ref}")
            if not any(abs((_angle(t.rotation) - _angle(a) + 180.0) % 360.0 - 180.0) < 1.0e-6 for a in comp.allowed_rotations):
                hard_count += 1
                hard_magnitude += 1.0
                hard_details.append(f"rotation:{ref}")
            if not polygon_inside_outline(poly, self.problem.board_outline):
                hard_count += 1
                hard_magnitude += 1.0
                hard_details.append(f"outline:{ref}")
            if comp.max_displacement is not None:
                d = math.hypot(t.x - comp.initial_x, t.y - comp.initial_y)
                if d > comp.max_displacement + EPS:
                    hard_count += 1
                    hard_magnitude += d - comp.max_displacement
                    hard_details.append(f"displacement:{ref}")
            for k, keepout in enumerate(self.problem.keepouts):
                d = polygon_distance(poly, keepout)
                if d < self.config.clearance_mm - EPS:
                    hard_count += 1
                    hard_magnitude += self.config.clearance_mm - d
                    hard_details.append(f"keepout:{ref}:{k}")

        for i, a in enumerate(refs):
            ca = self.problem.components[a]
            for b in refs[i + 1 :]:
                cb = self.problem.components[b]
                if ca.layer != cb.layer and not (ca.through_hole or cb.through_hole):
                    continue
                d = polygon_distance(envelopes[a], envelopes[b])
                if d < self.config.clearance_mm - EPS:
                    hard_count += 1
                    hard_magnitude += self.config.clearance_mm - d
                    hard_details.append(f"collision:{a}:{b}")

        for rule in self.problem.separation_rules:
            if rule.a in envelopes and rule.b in envelopes:
                d = polygon_distance(envelopes[rule.a], envelopes[rule.b])
                if d < rule.min_distance - EPS:
                    hard_count += 1
                    hard_magnitude += rule.min_distance - d
                    hard_details.append(f"separation:{rule.a}:{rule.b}")

        physics_count = 0
        physics_penalty = 0.0
        physics_details: List[str] = []
        for ref, comp in self.problem.components.items():
            if not comp.anchor or comp.anchor not in self.problem.components:
                continue
            d = self.anchor_distance(ref, comp.anchor, state)
            limit = comp.max_anchor_distance
            if limit is None and ref in self._initial_anchor_distances:
                limit = self._initial_anchor_distances[ref] + self.config.nonworsening_anchor_tolerance_mm
            if limit is not None and d > limit + EPS:
                physics_count += 1
                physics_penalty += (d - limit) ** 2
                physics_details.append(f"anchor:{ref}:{comp.anchor}:{d:.4f}>{limit:.4f}")

        segments, hpwl, mst, net_boxes = self._net_geometry(state)
        crossings = 0
        weighted_crossings = 0.0
        crossing_culprits: Set[str] = set()
        for i, s1 in enumerate(segments):
            for s2 in segments[i + 1 :]:
                if s1.net == s2.net:
                    continue
                if segments_properly_intersect(s1.a, s1.b, s2.a, s2.b):
                    crossings += 1
                    w = max(self.problem.net_weights.get(s1.net, 1.0), self.problem.net_weights.get(s2.net, 1.0))
                    weighted_crossings += w
                    crossing_culprits.update(s1.refs)
                    crossing_culprits.update(s2.refs)

        rudy_peak, rudy_overflow = self._rudy(net_boxes)
        blocked, blocked_culprits = self._escape_blockage(state, envelopes)
        displacement = sum(
            math.hypot(state[r].x - c.initial_x, state[r].y - c.initial_y)
            for r, c in self.problem.components.items()
        )
        score = Score(
            hard_count,
            hard_magnitude,
            physics_count,
            physics_penalty,
            blocked,
            rudy_overflow,
            weighted_crossings,
            crossings,
            rudy_peak,
            hpwl,
            mst,
            displacement,
        )
        return Evaluation(
            score=score,
            segments=tuple(segments),
            crossing_culprits=crossing_culprits,
            blocked_culprits=blocked_culprits,
            details={
                "hard": hard_details,
                "physics": physics_details,
                "segment_count": len(segments),
                "net_count": len(net_boxes),
            },
        )


# ---------------------------------------------------------------------------
# Conflict-directed joint swap/rotation search
# ---------------------------------------------------------------------------

class IsomorphicSwapRotateOptimizer:
    """Deterministic best-improvement search over safe geometry classes.

    Search neighborhoods:
      1. single-component legal rotations;
      2. pair position exchange x all joint rotations;
      3. bounded three-cycle exchange to cross pairwise local minima.

    Every accepted move strictly improves the complete lexicographic score.
    """

    ALGORITHM = "ISRRO-X/1.0"

    def __init__(self, problem: PlacementProblem, config: Optional[OptimizerConfig] = None):
        self.problem = problem
        self.config = config or OptimizerConfig()
        self.evaluator = PlacementEvaluator(problem, self.config)
        self.evaluations = 0
        self.reject_counts: Dict[str, int] = defaultdict(int)
        self.started = 0.0
        self.classes = self._build_classes()

    def _class_key(self, comp: Component) -> Tuple[str, ...]:
        if comp.swap_class:
            return ("explicit", comp.swap_class, comp.layer)
        anchor = comp.anchor or ""
        group = comp.group or ""
        return (
            "geometry",
            comp.geometry_hash,
            comp.layer,
            comp.role,
            anchor if self.config.strict_same_anchor and anchor else "",
            group if self.config.preserve_group and group else "",
        )

    def _build_classes(self) -> Dict[Tuple[str, ...], Tuple[str, ...]]:
        classes: Dict[Tuple[str, ...], List[str]] = defaultdict(list)
        for ref, comp in self.problem.components.items():
            if comp.locked:
                continue
            classes[self._class_key(comp)].append(ref)
        return {k: tuple(sorted(v)) for k, v in classes.items() if len(v) >= 2}

    def _budget_ok(self) -> bool:
        return self.evaluations < self.config.max_evaluations and (time.perf_counter() - self.started) < self.config.time_limit_s

    def _snap(self, value: float) -> float:
        g = max(1.0e-6, self.config.grid_mm)
        return round(value / g) * g

    def _candidate(self, state: Mapping[str, Transform], replacements: Mapping[str, Transform], changed: Set[str]) -> Optional[Evaluation]:
        if not self._budget_ok():
            return None
        candidate = dict(state)
        candidate.update(replacements)
        if not self.evaluator.quick_legal(candidate, changed):
            self.reject_counts["quick_hard_constraint"] += 1
            return None
        self.evaluations += 1
        return self.evaluator.evaluate(candidate)

    @staticmethod
    def _better(a: Evaluation, b: Evaluation) -> bool:
        return a.score.key() < b.score.key()

    def _best_rotation_move(self, state: Mapping[str, Transform], current: Evaluation) -> Optional[Move]:
        if not self.config.enable_single_rotation:
            return None
        best: Optional[Move] = None
        culprits = current.crossing_culprits | current.blocked_culprits
        refs = sorted(
            (r for r, c in self.problem.components.items() if not c.locked),
            key=lambda r: (r not in culprits, r),
        )
        for ref in refs:
            c, old = self.problem.components[ref], state[ref]
            for rot in sorted({_angle(r) for r in c.allowed_rotations}):
                if abs((_angle(old.rotation) - rot + 180.0) % 360.0 - 180.0) < 1.0e-6:
                    continue
                t = Transform(old.x, old.y, rot)
                ev = self._candidate(state, {ref: t}, {ref})
                if ev is None or not self._better(ev, current):
                    continue
                move = Move("rotate", (ref,), {ref: t}, ev)
                if best is None or self._better(ev, best.evaluation):
                    best = move
        return best

    def _pair_order(self, refs: Sequence[str], culprits: Set[str]) -> List[Tuple[str, str]]:
        pairs = list(itertools.combinations(refs, 2))
        pairs.sort(
            key=lambda p: (
                not (p[0] in culprits or p[1] in culprits),
                -(int(p[0] in culprits) + int(p[1] in culprits)),
                p,
            )
        )
        return pairs[: self.config.max_pairs_per_class]

    def _best_pair_move(self, state: Mapping[str, Transform], current: Evaluation) -> Optional[Move]:
        best: Optional[Move] = None
        culprits = current.crossing_culprits | current.blocked_culprits
        for key in sorted(self.classes, key=str):
            refs = self.classes[key]
            for a, b in self._pair_order(refs, culprits):
                ta, tb = state[a], state[b]
                ca, cb = self.problem.components[a], self.problem.components[b]
                for ra in sorted({_angle(r) for r in ca.allowed_rotations}):
                    for rb in sorted({_angle(r) for r in cb.allowed_rotations}):
                        replacements = {
                            a: Transform(self._snap(tb.x), self._snap(tb.y), ra),
                            b: Transform(self._snap(ta.x), self._snap(ta.y), rb),
                        }
                        ev = self._candidate(state, replacements, {a, b})
                        if ev is None or not self._better(ev, current):
                            continue
                        move = Move("swap_rotate", (a, b), replacements, ev)
                        if best is None or self._better(ev, best.evaluation):
                            best = move
                if not self._budget_ok():
                    return best
        return best

    def _best_three_cycle(self, state: Mapping[str, Transform], current: Evaluation) -> Optional[Move]:
        if not self.config.enable_three_cycles:
            return None
        best: Optional[Move] = None
        culprits = current.crossing_culprits | current.blocked_culprits
        for key in sorted(self.classes, key=str):
            refs = self.classes[key]
            if len(refs) < 3 or len(refs) > self.config.three_cycle_class_limit:
                continue
            triples = list(itertools.combinations(refs, 3))
            triples.sort(key=lambda t: (not any(r in culprits for r in t), t))
            for triple in triples[: self.config.three_cycle_triple_limit]:
                positions = [(state[r].x, state[r].y) for r in triple]
                for direction in (1, -1):
                    targets = positions[direction:] + positions[:direction]
                    rotations = [sorted({_angle(x) for x in self.problem.components[r].allowed_rotations}) for r in triple]
                    for rots in itertools.product(*rotations):
                        replacements = {
                            r: Transform(self._snap(targets[i][0]), self._snap(targets[i][1]), rots[i])
                            for i, r in enumerate(triple)
                        }
                        ev = self._candidate(state, replacements, set(triple))
                        if ev is None or not self._better(ev, current):
                            continue
                        move = Move("three_cycle_rotate", tuple(triple), replacements, ev)
                        if best is None or self._better(ev, best.evaluation):
                            best = move
                        if not self._budget_ok():
                            return best
        return best

    def optimize(self) -> Tuple[Dict[str, Transform], Dict[str, Any]]:
        self.started = time.perf_counter()
        state = self.problem.initial_state()
        before = self.evaluator.evaluate(state)
        current = before
        moves: List[Dict[str, Any]] = []

        for pass_no in range(1, self.config.max_passes + 1):
            if not self._budget_ok():
                break
            rotation = self._best_rotation_move(state, current)
            pair = self._best_pair_move(state, current)
            candidates = [m for m in (rotation, pair) if m is not None]
            best = min(candidates, key=lambda m: m.evaluation.score.key()) if candidates else None
            if best is None:
                best = self._best_three_cycle(state, current)
            if best is None or not self._better(best.evaluation, current):
                break

            old_score = current.score
            state.update(best.transforms)
            current = self.evaluator.evaluate(state)  # independent full recomputation after acceptance
            moves.append(
                {
                    "pass": pass_no,
                    "kind": best.kind,
                    "refs": list(best.refs),
                    "transforms": {r: asdict(t) for r, t in best.transforms.items()},
                    "before": old_score.to_dict(),
                    "after": current.score.to_dict(),
                }
            )

        elapsed = time.perf_counter() - self.started
        final = self.evaluator.evaluate(state)
        report: Dict[str, Any] = {
            "success": True,
            "algorithm": self.ALGORITHM,
            "committed": False,
            "elapsed_s": round(elapsed, 6),
            "evaluations": self.evaluations,
            "termination": (
                "evaluation_budget" if self.evaluations >= self.config.max_evaluations else
                "time_budget" if elapsed >= self.config.time_limit_s else
                "local_optimum_or_pass_limit"
            ),
            "config": asdict(self.config),
            "problem": {
                "component_count": len(self.problem.components),
                "net_count": len(self.evaluator.terminals_by_net),
                "equivalence_class_count": len(self.classes),
                "equivalence_classes": [list(v) for _, v in sorted(self.classes.items(), key=lambda kv: str(kv[0]))],
                "source": self.problem.source,
            },
            "before": before.score.to_dict(),
            "after": final.score.to_dict(),
            "before_details": before.details,
            "after_details": final.details,
            "moves": moves,
            "rejections": dict(self.reject_counts),
            "accepted_move_count": len(moves),
            "changed_refs": sorted(r for r in state if state[r] != self.evaluator.initial[r]),
            "final_transforms": {r: asdict(t) for r, t in sorted(state.items())},
            "replay_ops": [
                {
                    "op": "footprint.place",
                    "ref": r,
                    "x": state[r].x,
                    "y": state[r].y,
                    "rot": state[r].rotation,
                }
                for r in sorted(state)
                if state[r] != self.evaluator.initial[r]
            ],
            "certificate": {
                "lexicographic_nonworsening": final.score.key() <= before.score.key(),
                "strict_lexicographic_improvement": final.score.key() < before.score.key(),
                "hard_violations_not_increased": final.score.hard_violations <= before.score.hard_violations,
                "physics_violations_not_increased": (
                    final.score.physics_violations,
                    final.score.physics_penalty,
                ) <= (
                    before.score.physics_violations,
                    before.score.physics_penalty,
                ),
                "full_score_recomputed_after_last_move": True,
            },
            "interpretation_limits": [
                "Ratsnest crossings, HPWL, MST, RUDY, and escape rays are placement proxies, not a routed-board proof.",
                "Thermal, SI, PI, EMI, enclosure, and assembly constraints are enforced only when encoded or locked.",
                "Final claims require router-in-the-loop DRC/connectivity/via/wirelength evaluation and hardware validation.",
            ],
        }
        return state, report


# ---------------------------------------------------------------------------
# KiCad 10 adapter and transactional public API
# ---------------------------------------------------------------------------

def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _mm(value: Any) -> float:
    return float(value) / 1.0e6


def _role(ref: str, part: Mapping[str, Any], pads: Sequence[PadSite]) -> str:
    explicit = part.get("placement_role") or part.get("role")
    if explicit:
        return str(explicit)
    u = ref.upper()
    lib = str(part.get("lib_id", "")).upper()
    value = str(part.get("value", "")).upper()
    nets = {p.net.upper() for p in pads if p.net}
    if u.startswith(("J", "CON", "P")) or "CONNECTOR" in lib or "USB" in lib:
        return "connector"
    if u.startswith(("Y", "X")) or "CRYSTAL" in lib or "RESONATOR" in lib or "MHZ" in value:
        return "resonator"
    if u.startswith("C") and any("GND" in n or n in ("0V", "VSS") for n in nets) and any(
        k in n for n in nets for k in ("VCC", "VDD", "VBUS", "VIN", "3V3", "5V", "+")
    ):
        return "decoupling"
    if u.startswith(("R", "C", "L", "D")):
        return "passive"
    if u.startswith(("U", "IC")) or len(pads) >= 4:
        return "ic"
    return "other"


def _plane_net(name: str) -> bool:
    n = name.strip().upper()
    return n in {"GND", "0V", "VSS", "VSSA", "AGND", "DGND", "PGND"}


def _part_catalog(design: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    if isinstance(design.get("parts"), dict):
        return {str(k): v for k, v in design["parts"].items() if isinstance(v, dict)}
    out: Dict[str, Mapping[str, Any]] = {}
    for c in design.get("components", []) if isinstance(design.get("components"), list) else []:
        if isinstance(c, dict) and c.get("ref"):
            out[str(c["ref"])] = c
    return out


def _groups(design: Mapping[str, Any], parts: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for g in design.get("groups", []) if isinstance(design.get("groups"), list) else []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id", ""))
        for ref in g.get("parts", g.get("refs", [])):
            result[str(ref)] = gid
    for ref, p in parts.items():
        if p.get("group"):
            result[ref] = str(p["group"])
    return result


def _outline_points(polyset: Any) -> Tuple[Point, ...]:
    """Defensive KiCad polyset reader; returns empty tuple if the host API differs."""
    count = _try(lambda: int(polyset.OutlineCount()), 0)
    if count <= 0:
        return ()
    chain = None
    for name in ("COutline", "Outline", "Polygon"):
        chain = _try(lambda n=name: getattr(polyset, n)(0))
        if chain is not None:
            break
    if chain is None:
        return ()
    n = _try(lambda: int(chain.PointCount()), None)
    if n is None:
        n = _try(lambda: int(chain.Size()), 0)
    pts: List[Point] = []
    for i in range(int(n or 0)):
        p = None
        for name in ("CPoint", "Point"):
            p = _try(lambda n=name, i=i: getattr(chain, n)(i))
            if p is not None:
                break
        if p is not None:
            pts.append((_mm(p.x), _mm(p.y)))
    return tuple(pts)


def _find_design(project: Path) -> Dict[str, Any]:
    for p in (project / "kaibridge_dump" / "design.json", project / "design.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError(f"Invalid design JSON at {p}: {exc}") from exc
    return {}


def _find_board(project: Path) -> Path:
    pros = sorted(project.glob("*.kicad_pro"))
    if len(pros) == 1:
        candidate = project / f"{pros[0].stem}.kicad_pcb"
        if candidate.exists():
            return candidate
    pcbs = sorted(project.glob("*.kicad_pcb"))
    if len(pcbs) != 1:
        raise FileNotFoundError(f"Expected exactly one resolvable .kicad_pcb in {project}; found {len(pcbs)}")
    return pcbs[0]


def _extract_problem(board: Any, design: Mapping[str, Any], config: OptimizerConfig) -> PlacementProblem:
    import pcbnew  # type: ignore

    parts = _part_catalog(design)
    group_of = _groups(design, parts)
    pc = design.get("placement_constraints", {}) if isinstance(design.get("placement_constraints"), dict) else {}
    component_rules = pc.get("components", {}) if isinstance(pc.get("components"), dict) else {}
    locked_refs = set(config.locked_refs)

    polyset = pcbnew.SHAPE_POLY_SET()
    has_outline = bool(_try(lambda: board.GetBoardPolygonOutlines(polyset, True), False))
    outline = _outline_points(polyset) if has_outline else ()
    if len(outline) < 3:
        if has_outline and _try(lambda: polyset.OutlineCount(), 0):
            bb = polyset.BBox()
        else:
            bb = board.ComputeBoundingBox()
        x0, y0 = _mm(bb.GetLeft()), _mm(bb.GetTop())
        x1, y1 = _mm(bb.GetRight()), _mm(bb.GetBottom())
        outline = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        outline_source = "outline_bbox_fallback"
    else:
        outline_source = "exact_outline_chain"

    components: Dict[str, Component] = {}
    raw_for_anchor: Dict[str, Dict[str, Any]] = {}
    for fp in board.GetFootprints():
        ref = str(fp.GetReference())
        pos = fp.GetPosition()
        x, y = _mm(pos.x), _mm(pos.y)
        rot = float(_try(lambda: fp.GetOrientationDegrees(), 0.0))
        part = parts.get(ref, {})
        rule = component_rules.get(ref, {}) if isinstance(component_rules.get(ref), dict) else {}
        placement = part.get("placement", {}) if isinstance(part.get("placement"), dict) else {}
        merged = {**placement, **rule}

        pads: List[PadSite] = []
        pad_shape_signature: List[Any] = []
        absolute_boxes: List[Tuple[float, float, float, float]] = []
        through_hole = False
        for idx, pad in enumerate(fp.Pads()):
            p = pad.GetPosition()
            local = inverse_rotate_point((_mm(p.x) - x, _mm(p.y) - y), rot)
            size = _try(lambda: pad.GetSize())
            drill_size = _try(lambda: pad.GetDrillSize())
            pw = _mm(size.x) if size is not None else 0.0
            ph = _mm(size.y) if size is not None else 0.0
            drill = max(_mm(drill_size.x), _mm(drill_size.y)) if drill_size is not None else 0.0
            through_hole = through_hole or drill > 0.0
            number = str(_try(lambda: pad.GetNumber(), _try(lambda: pad.GetName(), "")))
            net = str(_try(lambda: pad.GetNetname(), "") or "")
            uid = f"{ref}:{number}:{idx}"
            pads.append(PadSite(uid, number, net, local, pw, ph, drill))
            pad_shape_signature.append((round(local[0], 4), round(local[1], 4), round(pw, 4), round(ph, 4), round(drill, 4)))
            pb = pad.GetBoundingBox()
            absolute_boxes.append((_mm(pb.GetLeft()), _mm(pb.GetTop()), _mm(pb.GetRight()), _mm(pb.GetBottom())))

        courtyard_box = None
        layer_ids = (pcbnew.F_CrtYd, pcbnew.B_CrtYd)
        for lid in layer_ids:
            poly = _try(lambda lid=lid: fp.GetCourtyard(lid))
            if poly is not None and _try(lambda: poly.OutlineCount(), 0):
                cb = poly.BBox()
                courtyard_box = (_mm(cb.GetLeft()), _mm(cb.GetTop()), _mm(cb.GetRight()), _mm(cb.GetBottom()))
                break
        if courtyard_box:
            absolute_boxes.append(courtyard_box)
            geometry_source = "courtyard_bbox_plus_pad_hull"
        elif absolute_boxes:
            geometry_source = "pad_hull"
        else:
            fb = fp.GetBoundingBox()
            absolute_boxes.append((_mm(fb.GetLeft()), _mm(fb.GetTop()), _mm(fb.GetRight()), _mm(fb.GetBottom())))
            geometry_source = "footprint_bbox_fallback"

        ax0 = min(z[0] for z in absolute_boxes)
        ay0 = min(z[1] for z in absolute_boxes)
        ax1 = max(z[2] for z in absolute_boxes)
        ay1 = max(z[3] for z in absolute_boxes)
        local_corners = [
            inverse_rotate_point((px - x, py - y), rot)
            for px, py in ((ax0, ay0), (ax1, ay0), (ax1, ay1), (ax0, ay1))
        ]
        envelope = convex_hull(local_corners)
        fpid = str(_try(lambda: fp.GetFPIDAsString(), "") or _try(lambda: fp.GetFPID().GetUniStringLibId(), ""))
        geo_raw = json.dumps(
            {"fpid": fpid, "pads": sorted(pad_shape_signature), "envelope": sorted((round(a, 4), round(b, 4)) for a, b in envelope)},
            sort_keys=True,
        )
        geometry_hash = hashlib.sha256(geo_raw.encode("utf-8")).hexdigest()[:20]
        role = _role(ref, part, pads)
        explicit_opt_in = bool(merged.get("optimizer_opt_in", merged.get("allow_swap_rotate", False)))
        critical_default = role in {"connector", "resonator"} or "RF" in str(part.get("footprint", "")).upper()
        locked = bool(_try(lambda: fp.IsLocked(), False)) or ref in locked_refs or bool(merged.get("locked", False))
        if critical_default and not explicit_opt_in:
            locked = True

        raw_rots = merged.get("allowed_rotations", config.allowed_rotations)
        allowed = tuple(sorted({_angle(float(v)) for v in raw_rots})) if isinstance(raw_rots, (list, tuple)) else config.allowed_rotations
        if locked:
            allowed = (_angle(rot),)
        near = merged.get("anchor", part.get("near"))
        anchor = str(near).split(".", 1)[0] if near else None
        max_anchor = merged.get("max_anchor_pad_distance_mm", merged.get("max_distance_mm"))
        max_disp = merged.get("max_displacement_mm")

        components[ref] = Component(
            ref=ref,
            fpid=fpid,
            layer=str(_try(lambda: fp.GetLayerName(), "F.Cu")),
            initial_x=x,
            initial_y=y,
            initial_rotation=_angle(rot),
            envelope=envelope,
            pads=tuple(pads),
            geometry_hash=geometry_hash,
            locked=locked,
            through_hole=through_hole,
            group=group_of.get(ref, ""),
            role=role,
            anchor=anchor,
            max_anchor_distance=float(max_anchor) if max_anchor is not None else None,
            max_displacement=float(max_disp) if max_disp is not None else None,
            allowed_rotations=allowed,
            swap_class=str(merged["swap_class"]) if merged.get("swap_class") else None,
            optimizer_opt_in=explicit_opt_in,
            geometry_source=geometry_source,
        )
        raw_for_anchor[ref] = {"part": part, "merged": merged}

    # Conservative automatic anchor inference for decouplers only.  The limit is
    # baseline-nonworsening unless the design supplies a stricter value.
    for ref, comp in components.items():
        if comp.anchor or comp.role != "decoupling":
            continue
        nets = {p.net for p in comp.pads if p.net and not _plane_net(p.net)}
        candidates: List[Tuple[int, str]] = []
        for other, oc in components.items():
            if other == ref or oc.role != "ic":
                continue
            shared = nets & {p.net for p in oc.pads if p.net}
            if shared:
                candidates.append((0 if comp.group and comp.group == oc.group else 1, other))
        if candidates:
            comp.anchor = min(candidates)[1]

    excluded: Set[str] = set()
    if config.ignore_plane_nets:
        excluded = {p.net for c in components.values() for p in c.pads if p.net and _plane_net(p.net)}
    for n in pc.get("exclude_nets", []) if isinstance(pc.get("exclude_nets"), list) else []:
        excluded.add(str(n))

    net_weights: Dict[str, float] = {}
    design_nets = design.get("nets", {}) if isinstance(design.get("nets"), dict) else {}
    for name, data in design_nets.items():
        if isinstance(data, dict):
            value = data.get("placement_weight", data.get("weight"))
            if value is not None:
                net_weights[str(name)] = float(value)
    for name, value in (pc.get("net_weights", {}) if isinstance(pc.get("net_weights"), dict) else {}).items():
        net_weights[str(name)] = float(value)

    keepouts: List[Tuple[Point, ...]] = []
    for item in pc.get("keepouts", []) if isinstance(pc.get("keepouts"), list) else []:
        pts = item.get("polygon", item) if isinstance(item, dict) else item
        if isinstance(pts, list) and len(pts) >= 3:
            keepouts.append(tuple((float(p[0]), float(p[1])) for p in pts))

    separations: List[SeparationRule] = []
    for item in pc.get("separations", []) if isinstance(pc.get("separations"), list) else []:
        if isinstance(item, dict) and item.get("a") in components and item.get("b") in components:
            separations.append(SeparationRule(str(item["a"]), str(item["b"]), float(item.get("min_mm", item.get("min_distance_mm", 0.0)))))

    geometry_sources: Dict[str, int] = defaultdict(int)
    for c in components.values():
        geometry_sources[c.geometry_source] += 1
    return PlacementProblem(
        components=components,
        board_outline=tuple(outline),
        net_weights=net_weights,
        excluded_nets=excluded,
        keepouts=tuple(keepouts),
        separation_rules=tuple(separations),
        source={
            "outline_source": outline_source,
            "geometry_sources": dict(geometry_sources),
            "excluded_nets": sorted(excluded),
        },
    )


def _set_orientation(fp: Any, degrees: float, pcbnew: Any) -> None:
    if hasattr(fp, "SetOrientationDegrees"):
        fp.SetOrientationDegrees(float(degrees))
        return
    if hasattr(pcbnew, "EDA_ANGLE") and hasattr(pcbnew, "DEGREES_T"):
        fp.SetOrientation(pcbnew.EDA_ANGLE(float(degrees), pcbnew.DEGREES_T))
        return
    raise RuntimeError("Host KiCad API exposes no supported footprint orientation setter")


def _in_process(project_dir: str | Path, config: OptimizerConfig) -> Dict[str, Any]:
    import pcbnew  # type: ignore

    project = Path(project_dir).expanduser().resolve()
    if not project.is_dir():
        return {"success": False, "error": f"Project directory not found: {project}"}
    board_path = _find_board(project)
    board = pcbnew.LoadBoard(str(board_path))
    tracks = list(board.GetTracks())
    if tracks and not config.allow_routed_board:
        return {
            "success": False,
            "error": f"Board contains {len(tracks)} track/via objects. Run pre-route or set allow_routed_board=true explicitly.",
        }
    design = _find_design(project)
    problem = _extract_problem(board, design, config)
    optimizer = IsomorphicSwapRotateOptimizer(problem, config)
    final_state, report = optimizer.optimize()
    report["pcb_file"] = str(board_path)

    dump = project / "kaibridge_dump"
    dump.mkdir(parents=True, exist_ok=True)
    report_path = dump / config.report_name

    if config.commit and report["certificate"]["strict_lexicographic_improvement"]:
        if report["after"]["hard_violations"] > 0:
            report["success"] = False
            report["error"] = "Refusing commit: final placement still has hard violations."
        elif report["after"]["physics_violations"] > report["before"]["physics_violations"]:
            report["success"] = False
            report["error"] = "Refusing commit: physics constraint violations increased."
        else:
            backup = dump / f"{board_path.stem}.pre_isrro_{int(time.time())}.kicad_pcb"
            shutil.copy2(board_path, backup)
            fp_map = {str(fp.GetReference()): fp for fp in board.GetFootprints()}
            try:
                for ref in report["changed_refs"]:
                    t = final_state[ref]
                    fp = fp_map[ref]
                    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(t.x), pcbnew.FromMM(t.y)))
                    _set_orientation(fp, t.rotation, pcbnew)
                board.BuildListOfNets()
                board.BuildConnectivity()
                pcbnew.SaveBoard(str(board_path), board)

                check_board = pcbnew.LoadBoard(str(board_path))
                check_problem = _extract_problem(check_board, design, config)
                check_eval = PlacementEvaluator(check_problem, config).evaluate(check_problem.initial_state())
                report["post_commit_recomputed"] = check_eval.score.to_dict()
                if check_eval.score.hard_violations > 0 or check_eval.score.physics_violations > report["before"]["physics_violations"]:
                    shutil.copy2(backup, board_path)
                    report["success"] = False
                    report["committed"] = False
                    report["rolled_back"] = True
                    report["error"] = "Post-commit verification failed; original board restored."
                else:
                    report["committed"] = True
                    report["backup_file"] = str(backup)
            except Exception as exc:
                shutil.copy2(backup, board_path)
                report["success"] = False
                report["committed"] = False
                report["rolled_back"] = True
                report["error"] = f"Commit failed and was rolled back: {exc}"

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    report["report_file"] = str(report_path)
    return report


def _worker(request_path: str, response_path: str) -> None:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    config = OptimizerConfig.from_mapping(request.get("config"))
    result = _in_process(request["project_dir"], config)
    Path(response_path).write_text(json.dumps(result, indent=2), encoding="utf-8")


def optimize_placement(
    project_dir: str | Path,
    config: Optional[Mapping[str, Any] | OptimizerConfig] = None,
) -> Dict[str, Any]:
    """Public API; automatically isolates pcbnew in KiCad's bundled Python."""
    cfg = config if isinstance(config, OptimizerConfig) else OptimizerConfig.from_mapping(config)
    try:
        import pcbnew  # type: ignore  # noqa: F401
        return _in_process(project_dir, cfg)
    except ImportError:
        from ..core.paths import load_kicad_python

        project = Path(project_dir).expanduser().resolve()
        dump = project / "kaibridge_dump"
        dump.mkdir(parents=True, exist_ok=True)
        token = f"{os.getpid()}_{int(time.time() * 1000)}"
        request_path = dump / f"isrro_request_{token}.json"
        response_path = dump / f"isrro_response_{token}.json"
        request_path.write_text(
            json.dumps({"project_dir": str(project), "config": asdict(cfg)}),
            encoding="utf-8",
        )
        root = Path(__file__).resolve().parents[2]
        runner = (
            "import sys;"
            f"sys.path.insert(0, {str(root)!r});"
            "from kaibridge.pcb.swap_optimizer import _worker;"
            f"_worker({str(request_path)!r}, {str(response_path)!r})"
        )
        proc = subprocess.run(
            [load_kicad_python(), "-c", runner],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            if response_path.exists():
                return json.loads(response_path.read_text(encoding="utf-8"))
            return {
                "success": False,
                "error": proc.stderr.strip() or proc.stdout.strip() or f"KiCad worker exited {proc.returncode}",
            }
        finally:
            for p in (request_path, response_path):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass


__all__ = [
    "Component",
    "Evaluation",
    "IsomorphicSwapRotateOptimizer",
    "OptimizerConfig",
    "PadSite",
    "PlacementEvaluator",
    "PlacementProblem",
    "Score",
    "SeparationRule",
    "Transform",
    "optimize_placement",
]
