"""Kaibridge Component Sourcing & Live Inventory CLI (`kaibridge check`)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .jlc_api import query_jlcpcb_component


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Query live JLCPCB warehouse inventory, pricing, Basic/Extended status, and datasheets."
    )
    ap.add_argument("parts", nargs="+", help="One or more LCSC component IDs (e.g. C165948 C6186)")
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    ap.add_argument("--timeout", type=float, default=10.0, help="API query timeout in seconds (default: 10.0)")
    args = ap.parse_args(argv)

    results = []
    has_error = False

    for part_id in args.parts:
        data = query_jlcpcb_component(part_id, timeout=args.timeout)
        results.append(data)

        if not data.get("success"):
            has_error = True
            if not args.json:
                print(f"\n[-] Error for {part_id}: {data.get('error')}\n", file=sys.stderr)
            continue

        if not args.json:
            stock_val = data["stock"]
            stock_str = f"{stock_val:,} pcs"
            if stock_val > 0:
                stock_tag = f"\033[92m[IN STOCK: {stock_str}]\033[0m"
            else:
                stock_tag = f"\033[91m[STOCKOUT - 0 pcs available!]\033[0m"

            if data["is_basic"]:
                type_tag = "\033[92m[BASIC - $0 SMT Loading Fee]\033[0m"
            else:
                type_tag = "\033[93m[EXTENDED - $3/type SMT Loading Fee]\033[0m"

            print("\n================================================================================================")
            print(f" [JLCPCB SOURCING & INVENTORY INTELLIGENCE: {data['lcsc']}]")
            print("================================================================================================")
            print(f"  Component Name    : {data['name']}")
            print(f"  Manufacturer Model: {data['model']} ({data['brand']})")
            print(f"  Package / Footprint: {data['package']}")
            print(f"  Category          : {data['category']}")
            print(f"  Warehouse Stock   : {stock_tag}")
            print(f"  JLCPCB Part Type  : {type_tag}")
            print(f"  Unit Price (USD)  : ${data['unit_price_usd']:.4f}")

            breaks = data.get("price_breaks") or []
            if breaks:
                print("\n  Volume Price Breaks:")
                for pb in breaks[:6]:
                    print(f"    - Qty {pb['qty']:>5}+ : ${pb['price']:.4f}")

            ds = data.get("datasheet")
            print(f"\n  Official Datasheet: {ds if ds else 'Not available'}")
            prod_url = data.get("product_url")
            if prod_url:
                print(f"  LCSC Product Page : {prod_url}")

            attrs = data.get("attributes") or []
            if attrs:
                print("\n  Key Electrical / Mechanical Attributes:")
                for a in attrs[:8]:
                    print(f"    - {a['name']:<25}: {a['value']}")

            print("================================================================================================\n")

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))

    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
