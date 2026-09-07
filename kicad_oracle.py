#!/usr/bin/env python3
"""
kicad_oracle.py -- Live KiCad pcbnew SWIG C++ Oracle CLI (<4ms).
Directly introspects KiCad's host pcbnew C++ SWIG wrapper to query methods,
signatures, classes, constants, and architectural rules. Eliminates API hallucination.

Usage:
    python kicad_oracle.py "ExportSpecctraDSN"
    python kicad_oracle.py "GetFootprints" -c BOARD
    python kicad_oracle.py "ZONE_CONNECTION_FULL" --json
    python kicad_oracle.py "drc_rules"
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.core.oracle import query_oracle


def main():
    ap = argparse.ArgumentParser(description="Live KiCad pcbnew SWIG C++ Oracle Inspector (<4ms)")
    ap.add_argument("query", help="Method, class, constant, or architectural rule to query (e.g. ExportSpecctraDSN, GetFootprints, ZONE_CONNECTION_FULL)")
    ap.add_argument("-c", "--class-name", dest="class_name", default=None, help="Target class name (e.g. BOARD, ZONE, FOOTPRINT, GLOBAL)")
    ap.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = ap.parse_args()

    res = query_oracle(args.query, args.class_name)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("success"):
            print(f"[+] Found {res.get('type')}: {res.get('scope')}")
            if "exact_signature" in res:
                print(f"\nSignature / Definition:\n{res['exact_signature']}")
            elif "description" in res:
                print(f"\nTopic: {res.get('topic')}\n{res.get('description')}")
                if "values" in res.get("details", {}):
                    print("\nValues / Constraints:")
                    for k, v in res["details"]["values"].items():
                        print(f"  - {k}: {v}")
            elif "constant" in res:
                print(f"\nConstant Value: {res.get('constant')}")
            elif "assignment" in res:
                print(f"\nAssignment: {res.get('assignment')}")
        else:
            print(f"[-] Not found: {res.get('error')}")
            if res.get("suggestions"):
                print(f"Did you mean: {', '.join(res['suggestions'])}?")


if __name__ == "__main__":
    main()
