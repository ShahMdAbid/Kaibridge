from __future__ import annotations

import unittest
from kaibridge.pcb import swap_optimizer as mod


def rect(w: float, h: float):
    return ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))


def crossed_problem(lock_r1: bool = False):
    Pad = mod.PadSite
    Component = mod.Component
    comps = {
        "U1": Component(
            "U1", "MCU", "F.Cu", 5.0, 15.0, 0.0, rect(2.0, 10.0),
            (Pad("U1:1", "1", "N1", (1.0, -4.0)), Pad("U1:2", "2", "N2", (1.0, 4.0))),
            "mcu-geometry", locked=True, role="ic", allowed_rotations=(0.0,), geometry_source="test",
        ),
        "R1": Component(
            "R1", "R_0603", "F.Cu", 20.0, 20.0, 0.0, rect(2.0, 1.0),
            (Pad("R1:1", "1", "N1", (-0.5, 0.0)), Pad("R1:2", "2", "GND", (0.5, 0.0))),
            "r0603-geometry", locked=lock_r1, group="core", role="passive", anchor="U1",
            max_anchor_distance=30.0, allowed_rotations=(0.0, 90.0, 180.0, 270.0), geometry_source="test",
        ),
        "R2": Component(
            "R2", "R_0603", "F.Cu", 20.0, 10.0, 0.0, rect(2.0, 1.0),
            (Pad("R2:1", "1", "N2", (-0.5, 0.0)), Pad("R2:2", "2", "GND", (0.5, 0.0))),
            "r0603-geometry", group="core", role="passive", anchor="U1",
            max_anchor_distance=30.0, allowed_rotations=(0.0, 90.0, 180.0, 270.0), geometry_source="test",
        ),
    }
    return mod.PlacementProblem(
        comps,
        ((0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)),
        excluded_nets={"GND"},
        source={"fixture": "crossed_pair"},
    )


class GeometryTests(unittest.TestCase):
    def test_proper_intersection(self):
        self.assertTrue(mod.segments_properly_intersect((0, 0), (2, 2), (0, 2), (2, 0)))
        self.assertFalse(mod.segments_properly_intersect((0, 0), (1, 1), (1, 1), (2, 0)))

    def test_polygon_distance(self):
        a = mod.transform_polygon(rect(2, 2), 0, 0, 0)
        b = mod.transform_polygon(rect(2, 2), 3, 0, 0)
        self.assertAlmostEqual(mod.polygon_distance(a, b), 1.0, places=7)


class OptimizerTests(unittest.TestCase):
    def config(self):
        return mod.OptimizerConfig(
            clearance_mm=0.2,
            grid_mm=0.1,
            max_passes=3,
            max_evaluations=1000,
            time_limit_s=5.0,
            enable_single_rotation=True,
            enable_three_cycles=False,
            escape_length_mm=0.1,
            route_pitch_mm=0.1,
            rudy_limit=1.0e9,
        )

    def test_crossed_isomorphic_pair_is_swapped(self):
        problem = crossed_problem()
        evaluator = mod.PlacementEvaluator(problem, self.config())
        before = evaluator.evaluate(problem.initial_state())
        self.assertEqual(before.score.crossings, 1)

        state, report = mod.IsomorphicSwapRotateOptimizer(problem, self.config()).optimize()
        self.assertEqual(report["after"]["crossings"], 0)
        self.assertGreaterEqual(report["accepted_move_count"], 1)
        self.assertAlmostEqual(state["R1"].y, 10.0)
        self.assertAlmostEqual(state["R2"].y, 20.0)
        self.assertTrue(report["certificate"]["strict_lexicographic_improvement"])

    def test_locked_member_prevents_swap_class(self):
        problem = crossed_problem(lock_r1=True)
        cfg = self.config()
        cfg.enable_single_rotation = False
        state, report = mod.IsomorphicSwapRotateOptimizer(problem, cfg).optimize()
        self.assertEqual(report["accepted_move_count"], 0)
        self.assertEqual(state["R1"], problem.initial_state()["R1"])
        self.assertEqual(report["after"]["crossings"], 1)

    def test_hard_violation_precedes_crossing_proxy(self):
        problem = crossed_problem()
        cfg = self.config()
        evaluator = mod.PlacementEvaluator(problem, cfg)
        state = problem.initial_state()
        bad = dict(state)
        bad["R1"] = mod.Transform(31.0, 20.0, 0.0)
        good_score = evaluator.evaluate(state).score
        bad_score = evaluator.evaluate(bad).score
        self.assertGreater(bad_score.hard_violations, good_score.hard_violations)
        self.assertGreater(bad_score.key(), good_score.key())


if __name__ == "__main__":
    unittest.main()
