"""
tests/test_parts_db.py -- Organic unit tests for local JLCPCB / EasyEDA sourcing engine & Golden Cache.
"""
import unittest

from kaibridge.sourcing.parts_db import (
    _GOLDEN_CACHE,
    lookup_by_lcsc,
    search_basic_passives,
)


class TestPartsDB(unittest.TestCase):

    def test_golden_cache_integrity(self):
        # Golden cache should contain essential passive components
        self.assertIn(("R", "10k", "0805"), _GOLDEN_CACHE)
        self.assertIn(("C", "100nF", "0805"), _GOLDEN_CACHE)
        self.assertIn(("R", "0R", "0603"), _GOLDEN_CACHE)

        res_10k = _GOLDEN_CACHE[("R", "10k", "0805")]
        self.assertEqual(res_10k["lcsc"], "C17414")
        self.assertEqual(res_10k["mfr"], "Uniroyal")

        cap_100n = _GOLDEN_CACHE[("C", "100nF", "0805")]
        self.assertEqual(cap_100n["lcsc"], "C1525")

    def test_lookup_by_lcsc_golden_cache(self):
        # Query 1k 0805 resistor C17513
        info = lookup_by_lcsc("C17513")
        self.assertIsNotNone(info)
        self.assertEqual(info["lcsc_id"], "C17513")
        self.assertEqual(info["part_class"], "Basic Part")
        self.assertEqual(info["package"], "0805")
        self.assertEqual(info["source"], "golden_cache")
        self.assertEqual(info["recommended_kicad_sym"], "Device:R")
        self.assertEqual(info["recommended_kicad_fp"], "Resistor_SMD:R_0805_2012Metric")

    def test_search_basic_passives(self):
        # Search 10k 0805 resistor
        results = search_basic_passives("R", "10k", "0805")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["lcsc_id"], "C17414")
        self.assertEqual(top["package"], "0805")

        # Search 100nF 0805 capacitor
        cap_results = search_basic_passives("C", "100nF", "0805")
        self.assertGreater(len(cap_results), 0)
        self.assertEqual(cap_results[0]["lcsc_id"], "C1525")


if __name__ == "__main__":
    unittest.main()
