"""
tests/test_diff_pair.py — Unit tests for differential pair detection, DSN injection, and skew auditing.
"""
import unittest
import tempfile
import json
import os
from pathlib import Path

from kaibridge.pcb.diff_pair import (
    DiffPairSpec,
    detect_differential_pairs,
    inject_diff_pair_dsn_rules,
    sync_diff_pair_netclasses,
    format_diff_pair_table,
    PS_PER_MM_FR4
)


class TestDiffPair(unittest.TestCase):

    def test_diff_pair_spec_initialization(self):
        spec = DiffPairSpec(
            name="CAN",
            pos_net="CANH",
            neg_net="CANL",
            target_impedance=120.0,
            max_skew_mm=0.50,
            track_width_mm=0.25,
            gap_mm=0.25
        )
        self.assertEqual(spec.name, "CAN")
        self.assertEqual(spec.pos_net, "CANH")
        self.assertEqual(spec.neg_net, "CANL")
        self.assertEqual(spec.target_impedance, 120.0)
        self.assertEqual(spec.max_skew_mm, 0.50)

    def test_detection_from_design_dict_explicit(self):
        design = {
            "diff_pairs": [
                {
                    "name": "CUSTOM_BUS",
                    "pos": "BUS_P",
                    "neg": "BUS_N",
                    "target_impedance": 100.0,
                    "max_skew_mm": 0.20,
                    "track_width_mm": 0.22,
                    "gap_mm": 0.18
                }
            ],
            "nets": {
                "BUS_P": {},
                "BUS_N": {}
            }
        }
        specs = detect_differential_pairs(".", design_dict=design)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].name, "CUSTOM_BUS")
        self.assertEqual(specs[0].pos_net, "BUS_P")
        self.assertEqual(specs[0].neg_net, "BUS_N")
        self.assertEqual(specs[0].target_impedance, 100.0)
        self.assertEqual(specs[0].max_skew_mm, 0.20)
        self.assertEqual(specs[0].track_width_mm, 0.22)
        self.assertEqual(specs[0].gap_mm, 0.18)

    def test_detection_heuristics_can_and_usb(self):
        design = {
            "nets": {
                "CANH": {},
                "CANL": {},
                "USB_D+": {},
                "USB_D-": {},
                "GND": {},
                "+3.3V": {},
                "SPI_SCK": {}
            }
        }
        specs = detect_differential_pairs(".", design_dict=design)
        self.assertEqual(len(specs), 2)
        names = {s.name: s for s in specs}
        self.assertIn("CAN", names)
        self.assertIn("USB", names)

        can_spec = names["CAN"]
        self.assertEqual(can_spec.pos_net, "CANH")
        self.assertEqual(can_spec.neg_net, "CANL")
        self.assertEqual(can_spec.target_impedance, 120.0)
        self.assertEqual(can_spec.max_skew_mm, 0.50)

        usb_spec = names["USB"]
        self.assertEqual(usb_spec.pos_net, "USB_D+")
        self.assertEqual(usb_spec.neg_net, "USB_D-")
        self.assertEqual(usb_spec.target_impedance, 90.0)
        self.assertEqual(usb_spec.max_skew_mm, 0.15)

    def test_detection_heuristics_generic_suffix(self):
        design = {
            "nets": {
                "ETH_TX_P": {},
                "ETH_TX_N": {},
                "PCIE_RX+": {},
                "PCIE_RX-": {}
            }
        }
        specs = detect_differential_pairs(".", design_dict=design)
        self.assertEqual(len(specs), 2)
        names = {s.name: s for s in specs}
        self.assertIn("ETH_TX", names)
        self.assertIn("PCIE_RX", names)

    def test_dsn_injection(self):
        with tempfile.TemporaryDirectory() as td:
            dsn_file = Path(td) / "test.dsn"
            dsn_content = """(pcb test
  (network
    (net CANH (pins U1-1 J1-1))
    (net CANL (pins U1-2 J1-2))
  )
  (wiring
  )
)"""
            dsn_file.write_text(dsn_content, encoding="utf-8")
            specs = [
                DiffPairSpec(
                    name="CAN",
                    pos_net="CANH",
                    neg_net="CANL",
                    gap_mm=0.25,
                    track_width_mm=0.25
                )
            ]
            ok = inject_diff_pair_dsn_rules(dsn_file, specs)
            self.assertTrue(ok)

            updated = dsn_file.read_text(encoding="utf-8")
            self.assertIn("(pair (net CANH CANL)", updated)
            self.assertIn("(clearance 250)", updated)

    def test_netclass_sync(self):
        with tempfile.TemporaryDirectory() as td:
            pro_file = Path(td) / "test.kicad_pro"
            pro_content = {
                "net_settings": {
                    "classes": [],
                    "netclass_patterns": []
                }
            }
            pro_file.write_text(json.dumps(pro_content), encoding="utf-8")
            specs = [
                DiffPairSpec(
                    name="USB",
                    pos_net="USB_D+",
                    neg_net="USB_D-",
                    track_width_mm=0.22,
                    gap_mm=0.15,
                    class_name="USB_DIFF"
                )
            ]
            ok = sync_diff_pair_netclasses(pro_file, specs)
            self.assertTrue(ok)

            data = json.loads(pro_file.read_text(encoding="utf-8"))
            classes = data["net_settings"]["classes"]
            self.assertEqual(len(classes), 1)
            self.assertEqual(classes[0]["name"], "USB_DIFF")
            self.assertEqual(classes[0]["track_width"], 0.22)
            self.assertEqual(classes[0]["diff_pair_gap"], 0.15)

            pats = data["net_settings"]["netclass_patterns"]
            self.assertEqual(len(pats), 2)
            patterns_set = {p["pattern"] for p in pats}
            self.assertEqual(patterns_set, {"USB_D+", "USB_D-"})

    def test_format_diff_pair_table(self):
        audit_results = [
            {
                "name": "CAN",
                "pos_net": "CANH",
                "neg_net": "CANL",
                "pos_len_3d_mm": 22.79,
                "neg_len_3d_mm": 16.22,
                "skew_3d_mm": 6.57,
                "skew_ps": 45.0,
                "pos_vias": 1,
                "neg_vias": 0,
                "status": "FAIL",
                "remedy": "Skew exceeds max tolerance (0.50mm)."
            },
            {
                "name": "USB",
                "pos_net": "USB_D+",
                "neg_net": "USB_D-",
                "pos_len_3d_mm": 12.45,
                "neg_len_3d_mm": 12.40,
                "skew_3d_mm": 0.05,
                "skew_ps": 0.3,
                "pos_vias": 0,
                "neg_vias": 0,
                "status": "PASS",
                "remedy": "Coupled pair meets all skew requirements."
            }
        ]
        table_str = format_diff_pair_table(audit_results)
        self.assertIn("[DIFFERENTIAL PAIR LENGTH & SKEW AUDIT]", table_str)
        self.assertIn("CAN", table_str)
        self.assertIn("CANH", table_str)
        self.assertIn("CANL", table_str)
        self.assertIn("[FAIL]", table_str)
        self.assertIn("[PASS]", table_str)
        self.assertIn("45.0ps", table_str)

    def test_generate_meander_polyline(self):
        from kaibridge.pcb.diff_pair import generate_meander_polyline
        p_start = (10.0, 10.0)
        p_end = (10.0, 20.0)
        pts = generate_meander_polyline(p_start, p_end, h=1.5, num_loops=2, pitch=1.3, gap=0.8)
        self.assertGreater(len(pts), 10)
        self.assertEqual(pts[0], p_start)
        self.assertEqual(pts[-1], p_end)

    def test_solve_meander_sub_micrometer_precision(self):
        from kaibridge.pcb.diff_pair import solve_meander
        p_start = (261.41, 112.71)
        p_end = (261.41, 119.50)
        delta_l = 6.161
        pts, h, added_l = solve_meander(p_start, p_end, delta_l, num_loops=3, pitch=1.3, gap=0.8)
        # Verify added length matches target within 0.005 mm (5 micrometers)
        self.assertAlmostEqual(added_l, delta_l, places=2)
        self.assertGreater(h, 0.5)


if __name__ == "__main__":
    unittest.main()

