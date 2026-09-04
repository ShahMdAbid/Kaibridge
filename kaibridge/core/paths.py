"""kaibridge/core/paths.py -- Central KiCad path discovery & configuration.
Supports Windows environment variables (%APPDATA%, %PROGRAMFILES%), relative repo paths,
and automated fallback discovery for zero-setup execution on any Windows machine.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional, List

# Locate repository root
_POSSIBLE_ROOTS = [
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parents[1],
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[3],
]

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG = None
for r in _POSSIBLE_ROOTS:
    cand = r / "kicad_paths.json"
    if cand.exists():
        CONFIG = cand
        REPO_ROOT = r
        break

if CONFIG is None:
    CONFIG = REPO_ROOT / "kicad_paths.json"

HOWTO = f"""
Fix {CONFIG.name} (repository root). Example:
{{
  "kicad_config_dir":    "%APPDATA%/kicad/10.0",
  "kicad_symbol_dir":    "%PROGRAMFILES%/KiCad/10.0/share/kicad/symbols",
  "kicad_footprint_dir": "%PROGRAMFILES%/KiCad/10.0/share/kicad/footprints",
  "kicad_cli_path":      "%PROGRAMFILES%/KiCad/10.0/bin/kicad-cli.exe",
  "kicad_python_path":   "%PROGRAMFILES%/KiCad/10.0/bin/python.exe",
  "freerouting_jar":     "freerouting-2.4.1.jar",
  "easyeda_db_path":     "data/easyeda-std.elib"
}}
"""


def _expand_path_str(val: str, base_dir: Path) -> Path:
    """Expands Windows/Unix environment variables and resolves relative paths."""
    expanded = os.path.expandvars(str(val).strip())
    p = Path(expanded).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()
    return p


def _find_kicad_config_dir() -> Optional[Path]:
    """Auto-detects the KiCad config directory holding sym-lib-table."""
    appdata = os.environ.get("APPDATA", "")
    cands = []
    if appdata:
        for v in ("10.0", "9.0", "8.0", "7.0"):
            cands.append(Path(appdata) / "kicad" / v)
    cands.extend([
        Path.home() / ".config" / "kicad" / "10.0",
        Path.home() / ".config" / "kicad" / "9.0",
        Path.home() / ".config" / "kicad" / "8.0",
        Path.home() / "Library" / "Preferences" / "kicad" / "10.0",
        Path.home() / "Library" / "Preferences" / "kicad" / "9.0",
    ])
    for c in cands:
        if c.is_dir():
            return c
    return None


def _find_kicad_symbol_dir() -> Optional[Path]:
    """Auto-detects the KiCad stock symbol library directory."""
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    cands = [
        Path(f"{prog_files}/KiCad/10.0/share/kicad/symbols"),
        Path(f"{prog_files}/KiCad/9.0/share/kicad/symbols"),
        Path(f"{prog_files}/KiCad/8.0/share/kicad/symbols"),
        Path(r"D:\Program Files\KiCad\10.0\share\kicad\symbols"),
        Path(r"D:\Program Files\KiCad\9.0\share\kicad\symbols"),
        Path(r"C:\Program Files (x86)\KiCad\10.0\share\kicad\symbols"),
        Path("/usr/share/kicad/symbols"),
        Path("/usr/local/share/kicad/symbols"),
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
    ]
    for c in cands:
        if c.is_dir():
            return c
    return None


def _find_kicad_footprint_dir() -> Optional[Path]:
    """Auto-detects the KiCad stock footprint library directory."""
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    cands = [
        Path(f"{prog_files}/KiCad/10.0/share/kicad/footprints"),
        Path(f"{prog_files}/KiCad/9.0/share/kicad/footprints"),
        Path(f"{prog_files}/KiCad/8.0/share/kicad/footprints"),
        Path(r"D:\Program Files\KiCad\10.0\share\kicad\footprints"),
        Path(r"D:\Program Files\KiCad\9.0\share\kicad\footprints"),
        Path(r"C:\Program Files (x86)\KiCad\10.0\share\kicad\footprints"),
        Path("/usr/share/kicad/footprints"),
        Path("/usr/local/share/kicad/footprints"),
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
    ]
    for c in cands:
        if c.is_dir():
            return c
    return None


def load_paths(*required) -> Dict[str, Path]:
    """Reads kicad_paths.json -> {key: Path} with environment variable expansion
    and intelligent fallback discovery for any missing paths.
    """
    global CONFIG, REPO_ROOT

    # Ensure CONFIG is resolved
    if not CONFIG.exists():
        for r in _POSSIBLE_ROOTS:
            cand = r / "kicad_paths.json"
            if cand.exists():
                CONFIG = cand
                REPO_ROOT = r
                break

    cfg: Dict[str, Path] = {}

    if CONFIG.exists():
        try:
            raw = json.loads(CONFIG.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if not str(value).strip():
                    continue
                resolved = _expand_path_str(value, REPO_ROOT)
                if resolved.exists():
                    cfg[key] = resolved
        except Exception:
            pass

    # Dynamic fallback discovery for core directories
    if "kicad_config_dir" not in cfg or not cfg["kicad_config_dir"].exists():
        found = _find_kicad_config_dir()
        if found:
            cfg["kicad_config_dir"] = found

    if "kicad_symbol_dir" not in cfg or not cfg["kicad_symbol_dir"].exists():
        found = _find_kicad_symbol_dir()
        if found:
            cfg["kicad_symbol_dir"] = found

    if "kicad_footprint_dir" not in cfg or not cfg["kicad_footprint_dir"].exists():
        found = _find_kicad_footprint_dir()
        if found:
            cfg["kicad_footprint_dir"] = found

    missing = [key for key in required if key not in cfg or not cfg[key].exists()]
    if missing:
        raise ValueError(
            f"Missing required KiCad paths: {', '.join(missing)}.\n"
            f"Please configure them in {CONFIG.name} or ensure KiCad is installed in a standard directory.{HOWTO}"
        )

    return cfg


def load_cli() -> Optional[Path]:
    """Finds the kicad-cli executable."""
    # 1. Check kicad_paths.json
    try:
        cfg = load_paths()
        if "kicad_cli_path" in cfg and cfg["kicad_cli_path"].is_file():
            return cfg["kicad_cli_path"]
    except Exception:
        pass

    # 2. Check system PATH
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)

    # 3. Check standard locations
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    cands = [
        Path(f"{prog_files}/KiCad/10.0/bin/kicad-cli.exe"),
        Path(f"{prog_files}/KiCad/9.0/bin/kicad-cli.exe"),
        Path(f"{prog_files}/KiCad/8.0/bin/kicad-cli.exe"),
        Path(r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
        Path(r"D:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
        Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
        Path("/usr/bin/kicad-cli"),
        Path("/usr/local/bin/kicad-cli")
    ]
    for c in cands:
        if c.is_file():
            return c

    return None


def load_kicad_python() -> str:
    """Finds KiCad's bundled Python interpreter (containing pcbnew)."""
    # 1. Check kicad_paths.json
    try:
        cfg = load_paths()
        if "kicad_python_path" in cfg and cfg["kicad_python_path"].is_file():
            return str(cfg["kicad_python_path"])
    except Exception:
        pass

    # 2. Check standard locations
    prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    cands = [
        Path(f"{prog_files}/KiCad/10.0/bin/python.exe"),
        Path(f"{prog_files}/KiCad/9.0/bin/python.exe"),
        Path(f"{prog_files}/KiCad/8.0/bin/python.exe"),
        Path(r"D:\Program Files\KiCad\10.0\bin\python.exe"),
        Path(r"D:\Program Files\KiCad\9.0\bin\python.exe"),
        Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"),
        Path("/usr/bin/python3")
    ]
    for c in cands:
        if c.is_file():
            return str(c)

    # 3. Check if active interpreter has pcbnew
    try:
        import pcbnew  # type: ignore
        return sys.executable
    except ImportError:
        pass

    return "python"


def find_freerouting_jar() -> Optional[Path]:
    """Finds the Freerouting JAR binary (prioritizes v2.4.1)."""
    # 1. Check kicad_paths.json
    try:
        cfg = load_paths()
        if "freerouting_jar" in cfg and cfg["freerouting_jar"].is_file():
            return cfg["freerouting_jar"]
    except Exception:
        pass

    # 2. Check repository root
    candidates = [
        REPO_ROOT / "freerouting-2.4.1.jar",
        REPO_ROOT / "freerouting.jar",
        Path.home() / "Downloads" / "freerouting-2.4.1.jar",
        Path.home() / "Downloads" / "freerouting.jar",
        Path(r"C:\Program Files\Freerouting\freerouting.jar")
    ]
    for c in candidates:
        if c.is_file():
            return c

    jars = sorted(REPO_ROOT.glob("freerouting*.jar"), reverse=True)
    if jars:
        return jars[0]

    return None


def find_easyeda_db() -> Optional[Path]:
    """Finds the local EasyEDA Pro standard parts SQLite database (easyeda-std.elib)."""
    # 1. Check kicad_paths.json
    try:
        cfg = load_paths()
        if "easyeda_db_path" in cfg and cfg["easyeda_db_path"].is_file():
            return cfg["easyeda_db_path"]
    except Exception:
        pass

    # 2. Check environment variable
    env_path = os.environ.get("EASYEDA_ELIB_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 3. Check repository data/ folder
    project_data = REPO_ROOT / "data" / "easyeda-std.elib"
    if project_data.is_file():
        return project_data

    # 4. Check EasyEDA Pro installations on Windows
    cands = [
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\easyeda-pro\resources\app\assets\db\easyeda-std.elib")),
        Path(os.path.expandvars(r"%APPDATA%\easyeda-pro\resources\app\assets\db\easyeda-std.elib")),
        Path(r"C:\Program Files\easyeda-pro\resources\app\assets\db\easyeda-std.elib"),
        Path(r"D:\Program Files\easyeda-pro\resources\app\assets\db\easyeda-std.elib"),
    ]
    for c in cands:
        if c.is_file():
            return c

    return None


def env_dirs(project_dir: Path | str | None = None) -> dict[str, Path]:
    """Map ${KICAD10_SYMBOL_DIR} -> Path(...), ${KIPRJMOD} -> project_dir, etc."""
    try:
        cfg = load_paths()
    except Exception:
        cfg = {}
    out: dict[str, Path] = {}
    if project_dir is not None:
        p = Path(project_dir).resolve()
        out["KIPRJMOD"] = p
        out["KIPRJ_DIR"] = p
        out["PRJ_MOD"] = p
    if "kicad_symbol_dir" in cfg:
        for v in (10, 9, 8, 7, 6):
            out[f"KICAD{v}_SYMBOL_DIR"] = cfg["kicad_symbol_dir"]
        out["KICAD_SYMBOL_DIR"] = cfg["kicad_symbol_dir"]
    if "kicad_footprint_dir" in cfg:
        for v in (10, 9, 8, 7, 6):
            out[f"KICAD{v}_FOOTPRINT_DIR"] = cfg["kicad_footprint_dir"]
        out["KICAD_FOOTPRINT_DIR"] = cfg["kicad_footprint_dir"]
    if "kicad_3dmodel_dir" in cfg:
        for v in (10, 9, 8, 7, 6):
            out[f"KICAD{v}_3DMODEL_DIR"] = cfg["kicad_3dmodel_dir"]
        out["KICAD_3DMODEL_DIR"] = cfg["kicad_3dmodel_dir"]
    return out
