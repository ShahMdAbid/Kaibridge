"""
tests/test_ir.py -- Organic tests for Integer Nanometer BoardIR and Pre-Flight Proof Gates (E0-E3).
"""
import unittest

from kaibridge.core.ir import (
    BoardIR,
    Certificate,
    ComponentInstance,
    LayerType,
    NetHyperedge,
    PadGeometry,
    Point2D,
    ProcessProfile,
    ReservationType,
    mm_to_nm,
    mm_to_um,
    nm_to_mm,
    um_to_mm,
    verify_e0_requirements_complete,
    verify_e1_netlist_parity,
    verify_e2_process_compatibility,
    verify_e3_local_entry_solvability,
)


class TestBoardIR(unittest.TestCase):

    def test_unit_conversions(self):
        self.assertEqual(mm_to_nm(1.0), 1_000_000)
        self.assertEqual(nm_to_mm(1_000_000), 1.0)
        self.assertEqual(mm_to_nm(0.25), 250_000)
        self.assertAlmostEqual(nm_to_mm(250_000), 0.25)
        self.assertEqual(mm_to_um(1.5), 1500)
        self.assertEqual(um_to_mm(1500), 1.5)

    def test_point2d_exactness(self):
        pt = Point2D.from_mm(10.5, 20.25)
        self.assertEqual(pt.x, 10_500_000)
        self.assertEqual(pt.y, 20_250_000)
        mm_coords = pt.to_mm()
        self.assertEqual(mm_coords, (10.5, 20.25))

    def test_preflight_gate_e0_empty_board(self):
        board = BoardIR(
            design_id="test_board",
            revision=1,
            process=ProcessProfile.jlcpcb_2layer_standard(),
            outline_polygon_nm=(Point2D(0, 0), Point2D(50_000_000, 0), Point2D(50_000_000, 40_000_000), Point2D(0, 40_000_000)),
            components=(),
            nets=()
        )
        cert = verify_e0_requirements_complete(board)
        self.assertFalse(cert.passed)
        self.assertIn("no components", cert.error_message.lower())

    def test_preflight_gate_e0_valid_board(self):
        pad1 = PadGeometry("1", "rect", Point2D(0, 0), Point2D(1_000_000, 1_000_000), "NET_A")
        pad2 = PadGeometry("2", "rect", Point2D(2_000_000, 0), Point2D(1_000_000, 1_000_000), "NET_A")
        comp1 = ComponentInstance("R1", "Device:R", "Resistor_SMD:R_0603", Point2D(5_000_000, 5_000_000), 0.0, "top", (pad1, pad2), ())
        net1 = NetHyperedge("NET_A", (("R1", "1"), ("R1", "2")), 3.3, 10.0)

        board = BoardIR(
            design_id="valid_board",
            revision=1,
            process=ProcessProfile.jlcpcb_2layer_standard(),
            outline_polygon_nm=(Point2D(0, 0), Point2D(50_000_000, 0), Point2D(50_000_000, 40_000_000), Point2D(0, 40_000_000)),
            components=(comp1,),
            nets=(net1,)
        )
        cert = verify_e0_requirements_complete(board)
        self.assertTrue(cert.passed)

    def test_preflight_gate_e1_netlist_parity(self):
        pad1 = PadGeometry("1", "rect", Point2D(0, 0), Point2D(1_000_000, 1_000_000), "NET_A")
        pad2 = PadGeometry("2", "rect", Point2D(2_000_000, 0), Point2D(1_000_000, 1_000_000), "NET_A")
        comp1 = ComponentInstance("R1", "Device:R", "Resistor_SMD:R_0603", Point2D(5_000_000, 5_000_000), 0.0, "top", (pad1, pad2), ())

        # Valid net terminals
        net_valid = NetHyperedge("NET_A", (("R1", "1"), ("R1", "2")))
        board_valid = BoardIR("b1", 1, ProcessProfile.jlcpcb_2layer_standard(),
                              (Point2D(0, 0), Point2D(50_000_000, 0), Point2D(50_000_000, 40_000_000)),
                              (comp1,), (net_valid,))
        cert_valid = verify_e1_netlist_parity(board_valid)
        self.assertTrue(cert_valid.passed)

        # Invalid net terminals (nonexistent component R99)
        net_invalid = NetHyperedge("NET_B", (("R99", "1"),))
        board_invalid = BoardIR("b2", 1, ProcessProfile.jlcpcb_2layer_standard(),
                                (Point2D(0, 0), Point2D(50_000_000, 0), Point2D(50_000_000, 40_000_000)),
                                (comp1,), (net_invalid,))
        cert_invalid = verify_e1_netlist_parity(board_invalid)
        self.assertFalse(cert_invalid.passed)
        self.assertIn("R99", cert_invalid.error_message)

    def test_preflight_gate_e2_process_compatibility(self):
        board = BoardIR(
            design_id="compat_board",
            revision=1,
            process=ProcessProfile.jlcpcb_2layer_standard(),
            outline_polygon_nm=(Point2D(0, 0), Point2D(50_000_000, 0), Point2D(50_000_000, 40_000_000)),
            components=(),
            nets=()
        )
        cert_pass = verify_e2_process_compatibility(board, default_track_w_nm=mm_to_nm(0.25), default_clearance_nm=mm_to_nm(0.25))
        self.assertTrue(cert_pass.passed)

        cert_fail = verify_e2_process_compatibility(board, default_track_w_nm=mm_to_nm(0.05), default_clearance_nm=mm_to_nm(0.25))
        self.assertFalse(cert_fail.passed)

    def test_preflight_gate_e3_pitch_solvability(self):
        pad1 = PadGeometry("1", "rect", Point2D(0, 0), Point2D(400_000, 400_000), "NET_1")
        pad2 = PadGeometry("2", "rect", Point2D(800_000, 0), Point2D(400_000, 400_000), "NET_2")
        comp = ComponentInstance("U1", "IC", "SOIC-8", Point2D(0, 0), 0.0, "top", (pad1, pad2), ())

        passed, violations = verify_e3_local_entry_solvability(comp, track_w_nm=mm_to_nm(0.25), clearance_nm=mm_to_nm(0.127))
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

        passed_fail, violations_fail = verify_e3_local_entry_solvability(comp, track_w_nm=mm_to_nm(1.2), clearance_nm=mm_to_nm(0.127))
        self.assertFalse(passed_fail)
        self.assertGreater(len(violations_fail), 0)


if __name__ == "__main__":
    unittest.main()
