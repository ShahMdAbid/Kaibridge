"""
kaibridge/core/geometry.py -- Unified 2D Computational Geometry Engine for Kaibridge.

Eliminates code duplication across swap optimizer, planar optimizer,
and hierarchical floorplanner with robust floating-point epsilon handling.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

Point = Tuple[float, float]
Polygon = Tuple[Point, ...]
EPS = 1.0e-7


def rotate_point(p: Point, degrees: float) -> Point:
    """Rotates coordinate p=(x, y) by degrees around the origin."""
    a = degrees % 360.0
    if abs(a) < 1.0e-8:
        return (p[0], p[1])
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
    """Inverse rotate coordinate p=(x, y) by degrees."""
    return rotate_point(p, -degrees)


def orient(a: Point, b: Point, c: Point) -> float:
    """Orientation test / 2D cross product of (b - a) and (c - a)."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def ccw(a: Point, b: Point, c: Point) -> float:
    """Counter-clockwise test (alias of orient with standard signed cross product)."""
    return orient(a, b, c)


def same_point(a: Point, b: Point, eps: float = 1.0e-7) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def on_segment(a: Point, b: Point, p: Point, eps: float = 1.0e-9) -> bool:
    return (
        abs(orient(a, b, p)) <= eps
        and min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Standard 2D segment intersection test including collinear touching."""
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    ):
        return True
    return (
        (abs(o1) <= EPS and on_segment(a, b, c))
        or (abs(o2) <= EPS and on_segment(a, b, d))
        or (abs(o3) <= EPS and on_segment(c, d, a))
        or (abs(o4) <= EPS and on_segment(c, d, b))
    )


def segments_properly_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True only for a proper X crossing; shared/touching endpoints are excluded."""
    if any(same_point(x, y) for x in (a, b) for y in (c, d)):
        return False
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    )


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Shortest Euclidean distance from point p to segment [a, b]."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    denom = vx * vx + vy * vy
    if denom <= EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / denom))
    q = (a[0] + t * vx, a[1] + t * vy)
    return math.hypot(p[0] - q[0], p[1] - q[1])


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    """Shortest distance between two line segments [a, b] and [c, d]."""
    if segments_intersect(a, b, c, d):
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
        if on_segment(a, b, p):
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
    """Applies rotation and 2D translation (x, y) to a polygon."""
    return tuple((x + q[0], y + q[1]) for q in (rotate_point(p, rot) for p in poly))


def polygon_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Shortest Euclidean distance between two convex or simple polygons."""
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


def rect(w: float, h: float) -> Tuple[Point, ...]:
    """Generates an origin-centered rectangular polygon."""
    hw, hh = w / 2.0, h / 2.0
    return ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
