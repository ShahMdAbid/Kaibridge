"""
tests/test_model.py -- Organic unit tests for design.json validation and AST model parsing.
"""
import unittest

from kaibridge.core.model import (
    DesignError,
    _next_index,
    _split_pin,
    _read_parts,
)


class TestModel(unittest.TestCase):

    def test_split_pin_valid(self):
        ref, pin = _split_pin("U1.3", "nets.VCC")
        self.assertEqual(ref, "U1")
        self.assertEqual(pin, "3")

        ref2, pin2 = _split_pin("R1.2", "nets.SIG")
        self.assertEqual(ref2, "R1")
        self.assertEqual(pin2, "2")

    def test_split_pin_invalid_format(self):
        with self.assertRaises(DesignError) as ctx:
            _split_pin("INVALID_PIN", "nets.SIG")
        self.assertIn("must be REF.PIN", str(ctx.exception))

    def test_next_index(self):
        parts = {"C1": None, "C2": None, "C5": None, "R1": None}
        next_c = _next_index(parts, "C")
        self.assertEqual(next_c, 6)

        next_r = _next_index(parts, "R")
        self.assertEqual(next_r, 2)

        next_u = _next_index(parts, "U")
        self.assertEqual(next_u, 1)

    def test_read_parts_empty_raises(self):
        with self.assertRaises(DesignError) as ctx:
            _read_parts({}, None)
        self.assertIn("needs a non-empty 'parts' object", str(ctx.exception))

    def test_read_parts_missing_lib_id_raises(self):
        raw = {
            "parts": {
                "R1": {"value": "10k"}  # missing lib_id
            }
        }
        with self.assertRaises(DesignError) as ctx:
            _read_parts(raw, None)
        self.assertIn("'lib_id' (or 'symbol') is required", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
