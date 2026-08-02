"""
hybrid_pipeline.py -- Unified native + LCSC component resolution pipeline.

Splits components by source:
  - native: validates against local KiCad libraries (zero network)
  - lcsc:   resolves via part_resolver + easyeda2kicad download

Outputs a unified build_manifest.json for downstream builders.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from component_classifier import classify_component, ClassifyResult
from library_resolver import LibraryResolver
from lib_table_writer import write_project_tables

# Only import part_resolver if we have LCSC parts
_part_resolver = None
def _get_part_resolver():
    global _part_resolver
    if _part_resolver is None:
        import part_resolver
        _part_resolver = part_resolver
    return _part_resolver

# ============================================================================
# Data types
# ============================================================================

@dataclass
class ResolvedPart:
    ref: str
    source: str                 # "native" | "lcsc"
    value: str
    symbol_id: str              # "Device:R"  |  "easyeda2kicad:C2040"
    footprint_id: str           # "Resistor_SMD:R_0603_1608Metric" | "easyeda2kicad:C2040"
    package: str = ""
    pin_count: int = 0
    lcsc_id: Optional[str] = None
    bom_lcsc: Optional[str] = None
    manufacturer: str = ""
    mpn: str = ""
    placement: Optional[Dict] = None
    notes: List[str] = field(default_factory=list)

NATIVE_AUTO_MIN = 85

# ============================================================================
# Native validation
# ============================================================================

def validate_native(c: Dict, libs: LibraryResolver) -> tuple[bool, str]:
    """Validate a native component against the local KiCad installation."""
    for key in ("symbol", "footprint", "value", "ref"):
        if not c.get(key):
            return False, f"missing required field '{key}'"

    ok, why = libs.footprint_exists(c["footprint"])
    if not ok:
        sugg = libs.suggest_footprint(c["footprint"])
        return False, f"{why}" + (f" (did you mean {sugg}?)" if sugg else "")

    ok, why = libs.symbol_exists(c["symbol"])
    if not ok:
        return False, why

    want = c.get("pin_count")
    if want:
        got = libs.footprint_pad_count(c["footprint"])
        if got and got != want:
            return False, f"footprint has {got} pads, spec says {want} pins"

    return True, ""


# ============================================================================
# Main pipeline
# ============================================================================

def build(project_dir: Path, spec_path: Path) -> int:
    """Run the full hybrid pipeline. Returns exit code (0/1/2)."""
    project_dir = Path(project_dir).resolve()
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    comps = spec.get("components", [])

    if not comps:
        print("[FAIL] No components found in spec.", file=sys.stderr)
        return 1

    # Write library tables safely
    write_project_tables(project_dir)

    libs = LibraryResolver(project_dir)

    natives = [c for c in comps if c.get("source") == "native"]
    lcscs = [c for c in comps if c.get("source") == "lcsc"]

    resolved: List[ResolvedPart] = []
    errors: List[str] = []

    # ---- NATIVE branch: validate locally, zero network ----
    for c in natives:
        ok, why = validate_native(c, libs)
        if not ok:
            errors.append(f"[NATIVE] {c.get('ref', '?')}: {why}")
            continue
        resolved.append(ResolvedPart(
            ref=c["ref"], source="native", value=c["value"],
            symbol_id=c["symbol"], footprint_id=c["footprint"],
            package=c.get("package", ""), pin_count=c.get("pin_count", 0),
            lcsc_id=None,
            bom_lcsc=(c.get("bom") or {}).get("lcsc_hint"),
            placement=c.get("placement"),
            notes=["native KiCad library"],
        ))
        print(f"[OK] {c['ref']}: {c['symbol']} / {c['footprint']} (native)")

    # ---- LCSC branch: resolve + verify + download ----
    to_download: List[str] = []
    pending: List[tuple] = []

    if lcscs:
        pr = _get_part_resolver()
        for c in lcscs:
            req = c.get("requirements") or {}
            ps = pr.PartSpec(ref=c["ref"], **req)
            report = pr.resolve(ps)

            if report["status"] == "AUTO":
                chosen = report["chosen"]
                c["lcsc_id"] = chosen["lcsc"]
                to_download.append(chosen["lcsc"])
                pending.append((c, chosen))
                print(f"[OK] {c['ref']}: {chosen['lcsc']} ({chosen.get('mpn', '?')}) — resolved")
            elif report["status"] == "AMBIGUOUS":
                errors.append(f"[LCSC] {c['ref']}: AMBIGUOUS — {report['message']}")
                # Print alternatives
                for alt in ([report["chosen"]] if report["chosen"] else []) + report.get("alternatives", []):
                    if alt:
                        print(f"      {alt.get('lcsc_id', alt.get('lcsc', '?')):<10} "
                              f"{alt.get('mpn', '?'):<24} "
                              f"score={alt.get('score', '?')}", file=sys.stderr)
            else:
                errors.append(f"[LCSC] {c['ref']}: REJECT — {report['message']}")

    if errors:
        print("\n" + "=" * 60, file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        # Determine exit code
        has_reject = any("REJECT" in e for e in errors)
        return 1 if has_reject else 2

    # Batch download LCSC parts (ONE invocation, only LCSC refs)
    if to_download:
        libs_dir = project_dir / "libs" / "easyeda2kicad"
        libs_dir.mkdir(parents=True, exist_ok=True)

        unique_ids = sorted(set(to_download))
        cmd = [
            sys.executable, "-m", "easyeda2kicad",
            "--lcsc_id", *unique_ids,
            "--full", "--overwrite",
            "--output", str(libs_dir / "easyeda2kicad"),
        ]
        print(f"\n[DOWNLOAD] easyeda2kicad for {', '.join(unique_ids)} ...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"[FAIL] easyeda2kicad failed:\n{proc.stderr}", file=sys.stderr)
            return 1
        print(proc.stdout)

    # Build resolved entries for LCSC parts
    for c, chosen in pending:
        lcsc = c["lcsc_id"]
        facts = chosen.get("facts", {})
        resolved.append(ResolvedPart(
            ref=c["ref"], source="lcsc",
            value=c.get("value") or chosen.get("mpn", lcsc),
            symbol_id=f"easyeda2kicad:{lcsc}",
            footprint_id=f"easyeda2kicad:{lcsc}",
            package=facts.get("package", ""),
            pin_count=facts.get("pin_count", 0),
            lcsc_id=lcsc, bom_lcsc=lcsc,
            manufacturer=facts.get("manufacturer", ""),
            mpn=facts.get("mpn", chosen.get("mpn", "")),
            placement=c.get("placement"),
            notes=[f"verified via {facts.get('source', 'resolver')}"],
        ))

    # Write back resolved lcsc_ids into the spec (makes it reproducible)
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True),
                         encoding="utf-8")

    # Write unified manifest
    manifest = project_dir / "build_manifest.json"
    manifest.write_text(
        json.dumps([asdict(r) for r in resolved], indent=2), encoding="utf-8"
    )
    print(f"\n[OK] {len(resolved)} parts resolved -> {manifest}")
    return 0


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Hybrid native/LCSC component pipeline.")
    ap.add_argument("--project", type=Path, required=True, help="KiCad project directory")
    ap.add_argument("--spec", type=Path, required=True, help="parts_spec.yaml path")
    args = ap.parse_args()

    sys.exit(build(args.project, args.spec))
