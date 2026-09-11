"""Kaibridge JLCPCB Sourcing Intelligence & CAD Fetcher Engine.

Combines real-time warehouse inventory queries (stock, price, Basic/Extended status,
and official manufacturer datasheet links) with modern KiCad CAD generation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

JLCPCB_SEARCH_API = (
    "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
)


def _decode_response(raw: bytes) -> str:
    """Decompresses gzip if required and returns UTF-8 decoded string."""
    if len(raw) >= 2 and raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw).decode("utf-8")
    return raw.decode("utf-8")


def query_jlcpcb_component(lcsc_id: str, timeout: float = 4.0) -> Dict[str, Any]:
    """Queries live JLCPCB SMT inventory for stock, price, datasheet, and classification.

    Args:
        lcsc_id: LCSC component code (e.g. 'C165948').
        timeout: Network timeout in seconds.

    Returns:
        Structured dictionary with component details or error message.
    """
    clean_id = str(lcsc_id).strip().upper()
    if not clean_id.startswith("C") or not clean_id[1:].isdigit():
        return {
            "success": False,
            "error": f"Invalid LCSC ID '{lcsc_id}'. Expected format 'C' followed by digits (e.g. C165948).",
            "lcsc": clean_id,
        }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": "https://jlcpcb.com",
        "Referer": "https://jlcpcb.com/parts",
    }

    payload = {
        "keyword": clean_id,
        "currentPage": 1,
        "pageSize": 5,
    }

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url=JLCPCB_SEARCH_API,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw_data = json.loads(_decode_response(resp.read()))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning(f"JLCPCB API query failed for {clean_id}: {e}")
        return {
            "success": False,
            "error": f"Network or API failure: {e}",
            "lcsc": clean_id,
        }

    data_block = raw_data.get("data") or {}
    page_info = data_block.get("componentPageInfo") or {}
    items: List[Dict[str, Any]] = page_info.get("list") or []

    # Find exact matching part
    matched_item = None
    for it in items:
        if str(it.get("componentCode", "")).strip().upper() == clean_id:
            matched_item = it
            break

    if not matched_item and items:
        matched_item = items[0]

    if not matched_item:
        return {
            "success": False,
            "error": f"Component {clean_id} not found in JLCPCB SMT inventory.",
            "lcsc": clean_id,
            "stock": 0,
            "in_stock": False,
        }

    stock_count = int(matched_item.get("stockCount") or 0)
    prices = matched_item.get("componentPrices") or []
    unit_price = float(prices[0].get("productPrice") or 0.0) if prices else 0.0
    price_breaks = [
        {
            "qty": int(p.get("startNumber") or 1),
            "price": float(p.get("productPrice") or 0.0),
        }
        for p in prices
    ]

    is_basic = matched_item.get("componentLibraryType") == "base"
    part_type = "Basic" if is_basic else "Extended"

    datasheet_url = matched_item.get("dataManualUrl") or ""
    if not datasheet_url:
        # Fallback to lcscGoodsUrl if specific datasheet not in primary field
        datasheet_url = matched_item.get("lcscGoodsUrl") or ""

    attributes = []
    for a in matched_item.get("attributes") or []:
        val = str(a.get("attribute_value_name") or "").strip()
        if val and val != "-":
            attributes.append({
                "name": str(a.get("attribute_name_en") or a.get("attribute_name") or ""),
                "value": val,
            })

    return {
        "success": True,
        "lcsc": clean_id,
        "name": matched_item.get("componentName", ""),
        "model": matched_item.get("componentModelEn") or matched_item.get("componentModel", ""),
        "brand": matched_item.get("componentBrandEn") or matched_item.get("componentBrand", ""),
        "package": matched_item.get("componentSpecificationEn") or matched_item.get("componentSpecification", ""),
        "category": matched_item.get("componentTypeEn") or matched_item.get("componentType", ""),
        "stock": stock_count,
        "in_stock": stock_count > 0,
        "type": part_type,
        "is_basic": is_basic,
        "unit_price_usd": unit_price,
        "price_breaks": price_breaks,
        "min_qty": int(matched_item.get("minPurchaseNum") or 1),
        "datasheet": datasheet_url,
        "description": matched_item.get("describe", ""),
        "product_url": matched_item.get("lcscGoodsUrl", ""),
        "attributes": attributes,
    }


def fetch_component_cad(
    lcsc_id: str,
    output_dir: str | Path,
    symbol_lib: str = "kaibridge",
    footprint_lib: str = "kaibridge.pretty",
    model_dir: str = "kaibridge.3dshapes",
    prefer_jlc2kicad: bool = True,
    include_3d: bool = False,
) -> Dict[str, Any]:
    """Fetches symbol, footprint, and optional 3D models into project libraries.

    Uses JLC2KiCadLib as the primary modern KiCad 10 generator, with automatic
    fallback to easyeda2kicad if needed.

    Args:
        lcsc_id: Component code (e.g. 'C165948').
        output_dir: Target project libraries root folder (e.g. 'projects/MyProject/libs').
        symbol_lib: Base name of the symbol library (default: 'kaibridge').
        footprint_lib: Relative folder name for footprints (default: 'kaibridge.pretty').
        model_dir: Relative folder name for 3D models (default: 'kaibridge.3dshapes').
        prefer_jlc2kicad: Whether to try JLC2KiCadLib first.
        include_3d: Whether to download 3D STEP/WRL models (default: False for fast synthesis).

    Returns:
        Dictionary with status, engine used, and generated asset paths.
    """
    clean_id = str(lcsc_id).strip().upper()
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Primary Engine: JLC2KiCadLib
    if prefer_jlc2kicad:
        import shutil
        jlc_bin = shutil.which("JLC2KiCadLib") or "JLC2KiCadLib"
        cmd = [
            jlc_bin,
            clean_id,
            "-dir",
            str(out_path),
            "-symbol_lib",
            symbol_lib,
            "-symbol_lib_dir",
            ".",
            "-footprint_lib",
            footprint_lib,
            "-model_dir",
            model_dir,
            "-model_base_variable",
            "KIPRJMOD",
        ]
        if include_3d:
            cmd.extend(["-models", "STEP", "WRL"])
        else:
            cmd.extend(["-models"])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return {
                "success": True,
                "engine": "JLC2KiCadLib",
                "lcsc": clean_id,
                "output_dir": str(out_path),
                "log": res.stdout.strip(),
            }
        logger.warning(
            f"JLC2KiCadLib failed for {clean_id} (code {res.returncode}): {res.stderr.strip()}; falling back to easyeda2kicad."
        )

    # 2. Fallback Engine: easyeda2kicad
    sym_file = out_path / f"{symbol_lib}.kicad_sym"
    mode_args = ["--full"] if include_3d else ["--symbol", "--footprint"]
    fallback_cmd = [
        "easyeda2kicad",
        "--lcsc_id",
        clean_id,
        *mode_args,
        "--output",
        str(sym_file),
        "--project-relative",
        "--overwrite",
    ]
    fb_res = subprocess.run(fallback_cmd, capture_output=True, text=True, check=False, cwd=str(out_path.parent if out_path.name == 'libs' else Path.cwd()))
    if fb_res.returncode == 0:
        return {
            "success": True,
            "engine": "easyeda2kicad (fallback)",
            "lcsc": clean_id,
            "output_dir": str(out_path),
            "log": fb_res.stdout.strip(),
        }

    return {
        "success": False,
        "engine": "None",
        "error": f"Both JLC2KiCadLib and easyeda2kicad failed for {clean_id}.\nStderr: {fb_res.stderr.strip()}",
        "lcsc": clean_id,
    }


def fetch_cli_main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for 'kaibridge fetch <C_ID> [C_ID ...]'."""
    ap = argparse.ArgumentParser(
        description="Pre-flight stock verification and modern KiCad CAD ingestion for JLCPCB/LCSC components."
    )
    ap.add_argument("parts", nargs="+", help="One or more LCSC component IDs (e.g. C165948 C6186)")
    ap.add_argument(
        "-d",
        "--dir",
        "--output-dir",
        dest="output_dir",
        default="libs",
        help="Target output library folder (default: 'libs')",
    )
    ap.add_argument("--skip-stock-check", action="store_true", help="Skip live inventory check before downloading")
    ap.add_argument("--with-3d", action="store_true", help="Download 3D STEP/WRL models alongside symbol and footprint")
    ap.add_argument("--prefer-easyeda", action="store_true", help="Force legacy easyeda2kicad instead of JLC2KiCadLib")
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = ap.parse_args(argv)

    results = []
    has_failure = False

    for part_id in args.parts:
        cid = part_id.strip().upper()
        if not args.skip_stock_check:
            info = query_jlcpcb_component(cid)
            if not info.get("success"):
                print(f"[-] Sourcing check failed for {cid}: {info.get('error')}", file=sys.stderr)
            elif not info.get("in_stock"):
                print(f"[!] WARNING: {cid} ({info.get('name')}) is currently STOCKOUT (0 pcs in warehouse)!", file=sys.stderr)
            else:
                stock_fmt = f"{info['stock']:,}"
                type_tag = "[BASIC]" if info["is_basic"] else "[EXTENDED]"
                print(f"[+] {cid} {type_tag} | In Stock: {stock_fmt} pcs | Unit Price: ${info['unit_price_usd']:.4f}")

        fetch_res = fetch_component_cad(
            cid,
            output_dir=args.output_dir,
            prefer_jlc2kicad=not args.prefer_easyeda,
            include_3d=args.with_3d,
        )
        results.append(fetch_res)

        if not fetch_res.get("success"):
            has_failure = True
            print(f"[-] Failed to fetch CAD assets for {cid}: {fetch_res.get('error')}", file=sys.stderr)
        else:
            print(f"[+] Successfully generated CAD library assets for {cid} via {fetch_res.get('engine')}.")

    if args.json:
        print(json.dumps(results, indent=2))

    return 1 if has_failure else 0
