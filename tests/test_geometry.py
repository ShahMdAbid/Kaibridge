"""
tests/test_geometry.py -- Comprehensive unit tests for kaibridge.core.geometry.
"""
import math
import unittest

from kaibridge.core.geometry import (
    Point,
    ccw,
    convex_hull,
    inverse_rotate_point,
    orient,
    point_in_polygon,
    point_segment_distance,
    polygon_distance,
    rect,
    rotate_point,
    segment_distance,
    segments_intersect,
    segments_properly_intersect,
    transform_polygon,
)


class TestGeometry(unittest.TestCase):

    def test_rotate_point_cardinal_angles(self):
        p = (2.0, 3.0)
        # 0 deg
        p0 = rotate_point(p, 0.0)
        self.assertAlmostEqual(p0[0], 2.0)
        self.assertAlmostEqual(p0[1], 3.0)

        # 90 deg: (x, y) -> (-y, x)
        p90 = rotate_point(p, 90.0)
        self.assertAlmostEqual(p90[0], -3.0)
        self.assertAlmostEqual(p90[1], 2.0)

        # 180 deg: (x, y) -> (-x, -y)
        p180 = rotate_point(p, 180.0)
        self.assertAlmostEqual(p180[0], -2.0)
        self.assertAlmostEqual(p180[1], -3.0)

        # 270 deg: (x, y) -> (y, -x)
        p270 = rotate_point(p, 270.0)
        self.assertAlmostEqual(p270[0], 3.0)
        self.assertAlmostEqual(p270[1], -2.0)

        # Inverse rotation returns to original
        p_inv = inverse_rotate_point(p90, 90.0)
        self.assertAlmostEqual(p_inv[0], 2.0)
        self.assertAlmostEqual(p_inv[1], 3.0)

    def test_orientation_and_ccw(self):
        a = (0.0, 0.0)
        b = (2.0, 0.0)
        c_left = (1.0, 1.0)
        c_right = (1.0, -1.0)
        c_collinear = (4.0, 0.0)

        self.assertGreater(orient(a, b, c_left), 0.0)
        self.assertLess(orient(a, b, c_right), 0.0)
        self.assertAlmostEqual(orient(a, b, c_collinear), 0.0)
        self.assertAlmostEqual(ccw(a, b, c_left), orient(a, b, c_left))

    def test_segments_intersect(self):
        # Proper X-intersection
        self.assertTrue(segments_intersect((0, 0), (2, 2), (0, 2), (2, 0)))
        self.assertTrue(segments_properly_intersect((0, 0), (2, 2), (0, 2), (2, 0)))

        # Touching at an endpoint (inclusive: True, properly: False)
        self.assertTrue(segments_intersect((0, 0), (1, 1), (1, 1), (2, 0)))
        self.assertFalse(segments_properly_intersect((0, 0), (1, 1), (1, 1), (2, 0)))

        # Parallel non-intersecting
        self.assertFalse(segments_intersect((0, 0), (2, 0), (0, 1), (2, 1)))
        self.assertFalse(segments_properly_intersect((0, 0), (2, 0), (0, 1), (2, 1)))

    def test_point_segment_distance(self):
        a = (0.0, 0.0)
        b = (10.0, 0.0)

        # Perpendicular drop
        self.assertAlmostEqual(point_segment_distance((5.0, 5.0), a, b), 5.0)

        # Beyond endpoint a
        self.assertAlmostEqual(point_segment_distance((-3.0, 4.0), a, b), 5.0)

        # Beyond endpoint b
        self.assertAlmostEqual(point_segment_distance((13.0, 4.0), a, b), 5.0)

    def test_polygon_geometry_and_distance(self):
        poly_a = rect(2.0, 2.0)  # (-1, -1) to (1, 1)
        poly_b = transform_polygon(rect(2.0, 2.0), 5.0, 0.0, 0.0)  # (4, -1) to (6, 1)

        # Distance between poly_a (x=1) and poly_b (x=4) should be 3.0
        dist = polygon_distance(poly_a, poly_b)
        self.assertAlmostEqual(dist, 3.0)

        # Point containment
        self.assertTrue(point_in_polygon((0.0, 0.0), poly_a))
        self.assertFalse(point_in_polygon((5.0, 0.0), poly_a))
        self.assertTrue(point_in_polygon((5.0, 0.0), poly_b))

    def test_convex_hull(self):
        pts = [(0, 0), (1, 1), (2, 0), (1, -1), (1, 0)]
        hull = convex_hull(pts)
        self.assertEqual(len(hull), 4)
        self.assertNotIn((1, 0), hull)


if __name__ == "__main__":
    unittest.main()
