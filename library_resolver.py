"""
library_resolver.py -- Resolves KiCad library nicknames to filesystem paths.

Merges global + project lib tables exactly like KiCad does:
    effective_libraries = global_table ∪ project_table
    (project shadows global on same nickname)

Adapted for KiCad 10 which uses:
  - ${KICAD10_FOOTPRINT_DIR} and ${KICAD10_SYMBOL_DIR} env vars
  - A meta (type "Table") entry pointing to the template tables
  - Config at %APPDATA%/kicad/10.0/ on Windows
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# KiCad version detection
KICAD_VER = os.environ.get("KICAD_VERSION_MAJOR", "10")

def _kicad_config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", "")) / "kicad"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences" / "kicad"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kicad"
    for v in (KICAD_VER, "10.0", "9.0", "8.0", "7.0"):
        p = base / (v if "." in v else f"{v}.0")
        if p.is_dir():
            return p
    return base


def _kicad_install_dir() -> Path:
    """Find the KiCad installation share directory."""
    candidates = [
        Path("C:/Program Files/KiCad/10.0/share/kicad"),
        Path("C:/Program Files/KiCad/9.0/share/kicad"),
        Path("C:/Program Files/KiCad/8.0/share/kicad"),
        Path("/usr/share/kicad"),
        Path("/usr/local/share/kicad"),
    ]
    for p in candidates:
        if p.is_dir():
            return p
    return candidates[0]


# Regex to extract lib entries from s-expression tables
_LIB_RE = re.compile(
    r'\(lib\s+\(name\s+"?([^")]+)"?\)\s*\(type\s+"?([^")]+)"?\)\s*\(uri\s+"?([^")]+)"?\)'
)


class LibraryResolver:
    """Merge global + project lib tables exactly like KiCad does."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self.cfg = _kicad_config_dir()
        self.install = _kicad_install_dir()
        self.env = self._load_env_vars()
        self.fp: Dict[str, Path] = self._merge("fp-lib-table")
        self.sym: Dict[str, Path] = self._merge("sym-lib-table")
        self._preflight()

    # ---- table loading ---------------------------------------------------
    def _merge(self, fname: str) -> Dict[str, Path]:
        table: Dict[str, Path] = {}
        # Global first (includes resolving Table-type indirection)
        table.update(self._parse(self.cfg / fname))
        # Project shadows global on same nickname
        table.update(self._parse(self.project_dir / fname))
        return table

    def _parse(self, path: Path) -> Dict[str, Path]:
        out: Dict[str, Path] = {}
        if not path.exists():
            return out
        text = path.read_text(encoding="utf-8", errors="ignore")
        for nick, typ, uri in _LIB_RE.findall(text):
            if typ.lower() == "table":
                # KiCad 10 uses (type "Table") to point to the template table
                resolved_uri = self._expand(uri)
                table_path = Path(resolved_uri)
                if table_path.exists():
                    out.update(self._parse(table_path))
            else:
                out[nick] = Path(self._expand(uri))
        return out

    def _load_env_vars(self) -> Dict[str, str]:
        env = dict(os.environ)
        env["KIPRJMOD"] = str(self.project_dir)

        # KiCad 10 standard env vars
        share = self.install
        env.setdefault("KICAD10_FOOTPRINT_DIR", str(share / "footprints"))
        env.setdefault("KICAD10_SYMBOL_DIR", str(share / "symbols"))
        env.setdefault("KICAD10_3DMODEL_DIR", str(share / "3dmodels"))
        env.setdefault("KICAD10_TEMPLATE_DIR", str(share / "template"))
        # Legacy compat
        env.setdefault("KICAD8_FOOTPRINT_DIR", env["KICAD10_FOOTPRINT_DIR"])
        env.setdefault("KICAD8_SYMBOL_DIR", env["KICAD10_SYMBOL_DIR"])
        env.setdefault("KISYSMOD", env["KICAD10_FOOTPRINT_DIR"])
        env.setdefault("KICAD_SYMBOL_DIR", env["KICAD10_SYMBOL_DIR"])

        # Read kicad_common.json for any user-defined env vars
        common = self.cfg / "kicad_common.json"
        if common.exists():
            try:
                data = json.loads(common.read_text(encoding="utf-8"))
                user_vars = (data.get("environment", {}).get("vars", {}) or {})
                env.update({k: str(v) for k, v in user_vars.items()})
            except Exception:
                pass
        return env

    def _expand(self, uri: str) -> str:
        def sub(m):
            return self.env.get(m.group(1), m.group(0))
        return re.sub(r"\$\{([A-Za-z0-9_]+)\}", sub, uri)

    # ---- preflight -------------------------------------------------------
    def _preflight(self) -> None:
        must_have = ["Device"]
        missing = [n for n in must_have if n not in self.sym]
        if missing:
            raise RuntimeError(
                f"Global KiCad symbol libs unavailable: {missing}. "
                f"Looked in {self.cfg}. "
                f"Native parts cannot be built. "
                f"Either install the KiCad libraries or set every component "
                f"to source: lcsc."
            )

    # ---- lookups ---------------------------------------------------------
    def footprint_path(self, fp_id: str) -> Tuple[Path, str]:
        """Return (library_dir, footprint_name) for a qualified ID like
        'Resistor_SMD:R_0603_1608Metric'."""
        nick, name = fp_id.split(":", 1)
        if nick not in self.fp:
            raise KeyError(f"footprint library nickname '{nick}' not registered")
        return self.fp[nick], name

    def footprint_exists(self, fp_id: str) -> Tuple[bool, str]:
        try:
            lib, name = self.footprint_path(fp_id)
        except (KeyError, ValueError) as e:
            return False, str(e)
        if not lib.is_dir():
            return False, f"library dir missing: {lib}"
        if not (lib / f"{name}.kicad_mod").exists():
            return False, f"footprint '{name}' not found in {lib.name}"
        return True, ""

    def footprint_pad_count(self, fp_id: str) -> int:
        try:
            lib, name = self.footprint_path(fp_id)
        except Exception:
            return 0
        f = lib / f"{name}.kicad_mod"
        if not f.exists():
            return 0
        return f.read_text(encoding="utf-8", errors="ignore").count("(pad ")

    def symbol_exists(self, sym_id: str) -> Tuple[bool, str]:
        nick, name = sym_id.split(":", 1)
        if nick not in self.sym:
            return False, f"symbol library nickname '{nick}' not registered"
        f = self.sym[nick]
        if not f.exists():
            return False, f"symbol library file missing: {f}"
        text = f.read_text(encoding="utf-8", errors="ignore")
        if f'(symbol "{name}"' not in text:
            return False, f"symbol '{name}' not found in {nick}"
        return True, ""

    def suggest_footprint(self, fp_id: str, n: int = 3) -> str:
        import difflib
        try:
            lib, name = self.footprint_path(fp_id)
        except Exception:
            return ""
        if not lib.is_dir():
            return ""
        names = [p.stem for p in lib.glob("*.kicad_mod")]
        hits = difflib.get_close_matches(name, names, n=n, cutoff=0.6)
        return ", ".join(f"{lib.name}:{h}" for h in hits)

    def list_libraries(self, kind: str = "fp") -> List[str]:
        """List all available library nicknames."""
        table = self.fp if kind == "fp" else self.sym
        return sorted(table.keys())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Resolve KiCad library paths.")
    ap.add_argument("project_dir", type=Path, help="KiCad project directory")
    ap.add_argument("--check-fp", help="Check if footprint exists, e.g. Resistor_SMD:R_0603_1608Metric")
    ap.add_argument("--check-sym", help="Check if symbol exists, e.g. Device:R")
    ap.add_argument("--list-fp", action="store_true", help="List footprint library nicknames")
    ap.add_argument("--list-sym", action="store_true", help="List symbol library nicknames")
    args = ap.parse_args()

    libs = LibraryResolver(args.project_dir)

    if args.list_fp:
        for name in libs.list_libraries("fp"):
            print(f"  {name}: {libs.fp[name]}")
    elif args.list_sym:
        for name in libs.list_libraries("sym"):
            print(f"  {name}: {libs.sym[name]}")
    elif args.check_fp:
        ok, why = libs.footprint_exists(args.check_fp)
        print(f"{'OK' if ok else 'FAIL'}: {args.check_fp} -- {why or 'exists'}")
        if not ok:
            sugg = libs.suggest_footprint(args.check_fp)
            if sugg:
                print(f"  Did you mean: {sugg}")
        sys.exit(0 if ok else 1)
    elif args.check_sym:
        ok, why = libs.symbol_exists(args.check_sym)
        print(f"{'OK' if ok else 'FAIL'}: {args.check_sym} -- {why or 'exists'}")
        sys.exit(0 if ok else 1)
    else:
        print(f"Footprint libs: {len(libs.fp)}")
        print(f"Symbol libs:    {len(libs.sym)}")
