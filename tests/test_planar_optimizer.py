"""
tests/test_planar_optimizer.py -- Unit tests for Kruskal MST and simulated annealing planar layout math.
"""
import math
import unittest

from kaibridge.pcb.planar_optimizer import get_mst


class TestPlanarOptimizer(unittest.TestCase):

    def test_mst_single_point(self):
        pts = [(10.0, 20.0)]
        mst = get_mst(pts)
        self.assertEqual(len(mst), 0)

    def test_mst_triangle(self):
        # 3-4-5 right triangle: (0,0), (3,0), (0,4)
        pts = [(0.0, 0.0), (3.0, 0.0), (0.0, 4.0)]
        mst = get_mst(pts)
        self.assertEqual(len(mst), 2)
        total_len = sum(d for u, v, d in mst)
        self.assertAlmostEqual(total_len, 7.0)

    def test_mst_square(self):
        # Square vertices: (0,0), (10,0), (10,10), (0,10)
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        mst = get_mst(pts)
        self.assertEqual(len(mst), 3)
        total_len = sum(d for u, v, d in mst)
        self.assertAlmostEqual(total_len, 30.0)

    def test_mst_collinear(self):
        # 4 collinear points: 0, 5, 12, 20
        pts = [(0.0, 0.0), (5.0, 0.0), (12.0, 0.0), (20.0, 0.0)]
        mst = get_mst(pts)
        self.assertEqual(len(mst), 3)
        total_len = sum(d for u, v, d in mst)
        self.assertAlmostEqual(total_len, 20.0)


if __name__ == "__main__":
    unittest.main()
