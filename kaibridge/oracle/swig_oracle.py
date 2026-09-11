"""Live KiCad SWIG Oracle alias and CLI entry point (kaibridge.oracle.swig_oracle).
Introspects host pcbnew C++ SWIG wrapper to query methods, signatures, classes,
constants, and architectural rules. Eliminates API hallucination.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Dict, Any, List, Optional

from ..core.oracle import (
    query_oracle,
    find_pcbnew_source,
    _load_pcbnew_content,
    _RULES_KNOWLEDGE_BASE
)

BENCHMARK_PROMPTS = [
    "ExportSpecctraDSN",
    "GetFootprints",
    "ZONE_CONNECTION_FULL",
    "drc_rules",
    "jlcpcb_rules",
    "swig_memory",
    "zone_filling"
]


def resolve_api_symbol(symbol: str, class_name: Optional[str] = None) -> Dict[str, Any]:
    """Resolves an exact SWIG symbol, method, or constant."""
    return query_oracle(symbol, class_name=class_name)


def get_class_methods(class_name: str, filter_str: Optional[str] = None) -> Dict[str, Any]:
    """Inspects methods belonging to a given KiCad class."""
    return query_oracle("class", class_name=class_name, filter_str=filter_str)


def get_all_classes() -> List[str]:
    """Returns a list of all KiCad pcbnew class names available on the host system."""
    content = _load_pcbnew_content()
    if not content:
        return []
    return sorted(set(re.findall(r"\nclass\s+([A-Za-z0-9_]+)\b", content)))


def get_architecture_rules() -> Dict[str, Dict[str, Any]]:
    """Returns the dictionary of production DRC and architectural rules."""
    return dict(_RULES_KNOWLEDGE_BASE)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live KiCad pcbnew SWIG C++ Oracle Inspector (<4ms)")
    ap.add_argument("query", nargs="?", default=None, help="Method, class, constant, rule topic, or 'topics' to list (e.g. ExportSpecctraDSN, GetFootprints, BOARD, drc_rules)")
    ap.add_argument("-c", "--class-name", dest="class_name", default=None, help="Target class name (e.g. BOARD, ZONE, FOOTPRINT, GLOBAL)")
    ap.add_argument("-f", "--filter", dest="filter_str", default=None, help="Filter class methods by keyword (e.g. track, pad, net)")
    ap.add_argument("-l", "--list", action="store_true", help="List all available architectural and manufacturing rule topics")
    ap.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = ap.parse_args(argv)

    target_query = args.query
    if args.list or (not target_query and not args.class_name):
        target_query = "topics"

    res = query_oracle(target_query, args.class_name, args.filter_str)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

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
        return 0
    else:
        print(f"[-] Not found: {res.get('error')}")
        if res.get("suggestions"):
            print(f"Did you mean: {', '.join(res['suggestions'])}?")
        return 1


if __name__ == "__main__":
    sys.exit(main())
