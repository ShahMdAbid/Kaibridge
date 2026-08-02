#!/usr/bin/env python3
"""
footprint_extractor.py — Extracts pin/pad data from downloaded KiCad libraries.

Scans a project's easyeda2kicad library directory and produces an AI-readable
report mapping each component's logical pin names (from .kicad_sym) to physical
pad numbers (from .kicad_mod).

The AI agent MUST use ONLY the pin names from this report when writing YAML
blueprints. Any pin not listed here does not exist and must not be referenced.

Usage:
    python footprint_extractor.py <path_to_easyeda2kicad_lib_dir>

Example:
    python footprint_extractor.py "C:\\MyProject\\libs\\easyeda2kicad"

This will scan:
    <dir>/easyeda2kicad.kicad_sym          (symbol pins)
    <dir>/easyeda2kicad.pretty/*.kicad_mod  (footprint pads)
"""

import os
import sys
import re
import glob


# ═══════════════════════════════════════════════════════════════════════════
# S-Expression Helpers
# ═══════════════════════════════════════════════════════════════════════════

from sexp_utils import _find_matching_close, _extract_blocks


# ═══════════════════════════════════════════════════════════════════════════
# .kicad_mod Parser  (Physical Footprint Pads)
# ═══════════════════════════════════════════════════════════════════════════

def extract_pads(filepath):
    """Parse a ``.kicad_mod`` file and return every pad entry.

    Returns
    -------
    list[dict]
        Each dict has keys: ``number``, ``type``, ``shape``.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    pads = []
    for block in _extract_blocks(content, 'pad'):
        # Inside a pad block the first tokens are:
        #   (pad "<number>" <type> <shape> ...)
        m = re.match(
            r'\(pad\s+"?([^"\s)]+)"?\s+'
            r'(smd|thru_hole|np_thru_hole|connect)\s+'
            r'(\w+)',
            block, re.IGNORECASE,
        )
        if m:
            pads.append({
                'number': m.group(1),
                'type':   m.group(2),
                'shape':  m.group(3),
            })
    return pads


# ═══════════════════════════════════════════════════════════════════════════
# .kicad_sym Parser  (Logical Symbol Pins)
# ═══════════════════════════════════════════════════════════════════════════

def extract_symbols(filepath):
    """Parse a ``.kicad_sym`` library file and return every symbol with its
    pins, reference designator, and value.

    Returns
    -------
    dict
        ``{ 'LCSC_ID': { 'reference': str, 'value': str, 'pins': [...] } }``
        Each pin dict has keys: ``name``, ``number``, ``type``.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    symbols = {}

    # ── Step 1: Extract every (symbol "...") block ──────────────────────
    all_symbol_blocks = _extract_blocks(content, 'symbol')

    # ── Step 2: Separate top-level symbols from sub-symbols ─────────────
    # easyeda2kicad names top-level symbols after the LCSC ID (e.g. "C2913202").
    # Sub-symbols carry a _N_N suffix (e.g. "C2913202_0_1") and contain the
    # actual pin definitions.  We collect top-level blocks which implicitly
    # contain all their sub-symbols.
    for block in all_symbol_blocks:
        name_match = re.match(r'\(symbol\s+"([^"]+)"', block)
        if not name_match:
            continue
        name = name_match.group(1)

        # Skip the library wrapper and sub-symbols
        if name == 'kicad_symbol_lib':
            continue
        if re.search(r'_\d+_\d+$', name):
            continue

        # ── Properties ──────────────────────────────────────────────────
        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', block)
        val_m = re.search(r'\(property\s+"Value"\s+"([^"]*)"', block)
        reference = ref_m.group(1) if ref_m else '?'
        value     = val_m.group(1) if val_m else name

        # ── Pins (inside sub-symbol blocks within this block) ───────────
        pins = []
        pin_blocks = _extract_blocks(block, 'pin')
        for pb in pin_blocks:
            type_m   = re.match(r'\(pin\s+(\w+)', pb)
            name_m   = re.search(r'\(name\s+"([^"]*)"', pb)
            number_m = re.search(r'\(number\s+"([^"]*)"', pb)
            if type_m and name_m and number_m:
                pins.append({
                    'name':   name_m.group(1),
                    'number': number_m.group(1),
                    'type':   type_m.group(1),
                })

        symbols[name] = {
            'reference': reference,
            'value':     value,
            'pins':      pins,
        }

    return symbols


# ═══════════════════════════════════════════════════════════════════════════
# Sort helper
# ═══════════════════════════════════════════════════════════════════════════

def _pad_sort_key(item):
    """Sort pads/pins by number: numeric first (ascending), then alpha."""
    n = item['number']
    try:
        return (0, int(n), '')
    except ValueError:
        return (1, 0, n)


# ═══════════════════════════════════════════════════════════════════════════
# Report Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(lib_dir):
    """Scan *lib_dir* and print the full AI-readable extraction report."""

    pretty_dir = os.path.join(lib_dir, "easyeda2kicad.pretty")
    sym_file   = os.path.join(lib_dir, "easyeda2kicad.kicad_sym")

    # ── Symbols ─────────────────────────────────────────────────────────
    symbols = {}
    if os.path.isfile(sym_file):
        symbols = extract_symbols(sym_file)
    else:
        print(f"WARNING: Symbol library not found: {sym_file}")

    # ── Footprints ──────────────────────────────────────────────────────
    footprints = {}
    if os.path.isdir(pretty_dir):
        for mod_file in sorted(glob.glob(os.path.join(pretty_dir, "*.kicad_mod"))):
            fp_name = os.path.splitext(os.path.basename(mod_file))[0]
            footprints[fp_name] = extract_pads(mod_file)
    else:
        print(f"WARNING: Footprint directory not found: {pretty_dir}")

    if not symbols and not footprints:
        print("ERROR: No symbol or footprint data found. "
              "Verify the path points to a valid easyeda2kicad library directory.")
        sys.exit(1)

    # ── Header ──────────────────────────────────────────────────────────
    SEP  = "=" * 68
    THIN = "─" * 68

    print(SEP)
    print("  FOOTPRINT EXTRACTOR REPORT")
    print(f"  Library : {lib_dir}")
    print(f"  Symbols : {len(symbols)}")
    print(f"  Footprints : {len(footprints)}")
    print(SEP)

    # ── Per-component report ────────────────────────────────────────────
    for sym_name, data in symbols.items():
        print(f"\n{SEP}")
        print(f"  COMPONENT : {sym_name}")
        print(f"  Reference : {data['reference']}  |  Value : {data['value']}")
        print(f"  Total Symbol Pins : {len(data['pins'])}")
        print(THIN)

        # Symbol pins
        print("  SYMBOL PINS (use these names in YAML source/destination fields):")
        if data['pins']:
            for pin in sorted(data['pins'], key=_pad_sort_key):
                print(f"    Pin \"{pin['name']:<20s}\" | Number: {pin['number']:>4s} | Type: {pin['type']}")
        else:
            print("    (no pins found — check the .kicad_sym file)")
        print(THIN)

        # Matching footprint pads
        if sym_name in footprints:
            pads = footprints[sym_name]
            print(f"  FOOTPRINT PADS ({sym_name}):")
            print(f"  Total Pads : {len(pads)}")
            for pad in sorted(pads, key=_pad_sort_key):
                print(f"    Pad {pad['number']:>4s} | Type: {pad['type']:<12s} | Shape: {pad['shape']}")
        else:
            print(f"  FOOTPRINT : No matching footprint found for '{sym_name}'")
            if footprints:
                print(f"  Available footprints: {', '.join(sorted(footprints.keys()))}")

        # Pin-to-pad cross-reference
        if sym_name in footprints:
            pads = footprints[sym_name]
            pad_numbers = {p['number'] for p in pads}
            pin_numbers = {p['number'] for p in data['pins']}
            print(THIN)
            print("  PIN-TO-PAD CROSS-REFERENCE:")

            # Pins that have a matching pad
            for pin in sorted(data['pins'], key=_pad_sort_key):
                if pin['number'] in pad_numbers:
                    print(f"    {pin['name']:<20s} → Pad {pin['number']}")
                else:
                    print(f"    {pin['name']:<20s} → ⚠ NO MATCHING PAD (number {pin['number']})")

            # Pads that have no matching pin (e.g. thermal/mounting pads)
            orphan_pads = pad_numbers - pin_numbers
            if orphan_pads:
                print(f"  EXTRA PADS (no symbol pin): {', '.join(sorted(orphan_pads, key=lambda x: (int(x) if x.isdigit() else float('inf'), x)))}")

    # ── Orphan footprints (no matching symbol) ──────────────────────────
    orphan_fps = set(footprints.keys()) - set(symbols.keys())
    if orphan_fps:
        print(f"\n{SEP}")
        print("  UNMATCHED FOOTPRINTS (no corresponding symbol found):")
        for fp_name in sorted(orphan_fps):
            pads = footprints[fp_name]
            print(f"    {fp_name}: {len(pads)} pads")

    print(f"\n{SEP}")
    print("  END OF REPORT")
    print(SEP)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python footprint_extractor.py <path_to_easyeda2kicad_lib_dir>")
        print()
        print("Example:")
        print('  python footprint_extractor.py "C:\\MyProject\\libs\\easyeda2kicad"')
        print()
        print("This will scan:")
        print("  <dir>/easyeda2kicad.kicad_sym          (symbol pins)")
        print("  <dir>/easyeda2kicad.pretty/*.kicad_mod  (footprint pads)")
        sys.exit(1)

    lib_dir = sys.argv[1]
    if not os.path.isdir(lib_dir):
        print(f"ERROR: Directory not found: {lib_dir}")
        sys.exit(1)

    generate_report(lib_dir)


if __name__ == "__main__":
    main()
