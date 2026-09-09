#!/usr/bin/env python3
"""
kicad_oracle.py -- Live KiCad pcbnew SWIG C++ Oracle CLI (<4ms).
Directly introspects KiCad's host pcbnew C++ SWIG wrapper to query methods,
signatures, classes, constants, and architectural rules. Eliminates API hallucination.

Usage:
    python kicad_oracle.py "ExportSpecctraDSN"
    python kicad_oracle.py "GetFootprints" -c BOARD
    python kicad_oracle.py "BOARD" --filter "track"
    python kicad_oracle.py "ZONE_CONNECTION_FULL" --json
    python kicad_oracle.py "drc_rules"
    python kicad_oracle.py --list
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
    ap.add_argument("query", nargs="?", default=None, help="Method, class, constant, rule topic, or 'topics' to list (e.g. ExportSpecctraDSN, GetFootprints, BOARD, drc_rules)")
    ap.add_argument("-c", "--class-name", dest="class_name", default=None, help="Target class name (e.g. BOARD, ZONE, FOOTPRINT, GLOBAL)")
    ap.add_argument("-f", "--filter", dest="filter_str", default=None, help="Filter class methods by keyword (e.g. track, pad, net)")
    ap.add_argument("-l", "--list", action="store_true", help="List all available architectural and manufacturing rule topics")
    ap.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = ap.parse_args()

    target_query = args.query
    if args.list or (not target_query and not args.class_name):
        target_query = "topics"

    res = query_oracle(target_query, args.class_name, args.filter_str)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res.get("success"):
            rtype = res.get("type")
            scope_name = res.get("scope") or res.get("class") or res.get("topic") or res.get("name")
            print(f"[+] Found {rtype}: {scope_name}")

            if rtype == "TOPICS_LIST":
                print(f"\nAvailable Architectural & Manufacturing Rule Topics ({res.get('count', 0)} total):\n")
                col1_w = 22
                print(f"  {'Topic Key'.ljust(col1_w)} | Description")
                print(f"  {'-' * col1_w}-+-------------------------------------------------------------")
                for t in res.get("topics", []):
                    k = t.get("key", "")
                    d = t.get("description", "")
                    print(f"  {k.ljust(col1_w)} | {d}")
                print(f"\nTip: Run 'python kicad_oracle.py <topic_key>' to view full rules, constraints, and code patterns.")

            elif rtype == "CLASS":
                print(f"\nClass: {res.get('class')} (Inherits from: {res.get('parents')})")
                if res.get("constructor"):
                    print(f"\nConstructor:\n{res['constructor']}")
                if res.get("docstring"):
                    print(f"\nDocstring:\n  {res['docstring']}")
                methods = res.get("methods", [])
                total_m = res.get("methods_count", len(methods))
                filt_m = res.get("filtered_count", len(methods))
                filt_kw = res.get("filter")
                if filt_kw:
                    print(f"\nMethods matching '{filt_kw}' ({filt_m} matches):")
                else:
                    print(f"\nMethods ({total_m} total, showing first {len(methods)}):")

                if methods:
                    col_width = 30
                    for i in range(0, len(methods), 3):
                        chunk = methods[i:i+3]
                        print("  " + "".join(m.ljust(col_width) for m in chunk))
                else:
                    print(f"  (No methods matched filter '{filt_kw}')")

                if "code_example" in res:
                    ex = res["code_example"]
                    print(f"\nPractical Code Example ({ex.get('title')}):\n```python\n{ex.get('code')}\n```")

            elif rtype == "RULE":
                print(f"\nTopic: {res.get('topic')}\nDescription: {res.get('description')}")
                details = res.get("details", {})
                if "rules" in details:
                    print("\nMandatory Rules:")
                    for r in details["rules"]:
                        print(f"  {r}")
                if "values" in details:
                    print("\nValues / Constraints:")
                    for k, v in details["values"].items():
                        print(f"  - {k}: {v}")
                if "example_pattern" in details:
                    print(f"\nCode Usage Pattern:\n```python\n{details['example_pattern']}\n```")
                if "kicad_pro_snippet" in details:
                    print(f"\n.kicad_pro Configuration Snippet:\n{json.dumps(details['kicad_pro_snippet'], indent=2)}")

            elif "exact_signature" in res:
                print(f"\nSignature / Definition:\n{res['exact_signature']}")
                if "code_example" in res:
                    ex = res["code_example"]
                    print(f"\nPractical Code Example ({ex.get('title')}):\n```python\n{ex.get('code')}\n```")

            elif "assignment" in res:
                print(f"\nAssignment:\n  {res.get('assignment')}")
                if "code_example" in res:
                    ex = res["code_example"]
                    print(f"\nPractical Code Example ({ex.get('title')}):\n```python\n{ex.get('code')}\n```")

            elif "constant" in res:
                print(f"\nConstant Value:\n  {res.get('constant')}")
                if "code_example" in res:
                    ex = res["code_example"]
                    print(f"\nPractical Code Example ({ex.get('title')}):\n```python\n{ex.get('code')}\n```")
        else:
            print(f"[-] Not found: {res.get('error')}")
            if res.get("suggestions"):
                print(f"Did you mean: {', '.join(res['suggestions'])}?")


if __name__ == "__main__":
    main()
