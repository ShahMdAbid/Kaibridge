"""kaibridge/core/paths.py -- Central KiCad path discovery & configuration.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Optional, List

_POSSIBLE_ROOTS = [
    Path(__file__).resolve().parents[1],
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[3],
]

CONFIG = None
for r in _POSSIBLE_ROOTS:
    cand = r / "kicad_paths.json"
    if cand.exists():
        CONFIG = cand
        break

if CONFIG is None:
    CONFIG = _POSSIBLE_ROOTS[1] / "kicad_paths.json"

HOWTO = f"""
Fix {CONFIG.name} (plugin root). It must contain:
{{
  "kicad_config_dir":    "<folder holding your global sym-lib-table>",
  "kicad_symbol_dir":    "<KiCad stock symbols folder>",
  "kicad_footprint_dir": "<KiCad stock footprints folder>"
}}
"""


def load_paths(*required) -> Dict[str, Path]:
    """Read kicad_paths.json -> {key: Path} for non-empty existing entries."""
    global CONFIG
    if not CONFIG.exists():
        for r in _POSSIBLE_ROOTS:
            cand = r / "kicad_paths.json"
            if cand.exists():
                CONFIG = cand
                break

    if not CONFIG.exists():
        default_cfg = {
            "kicad_config_dir": Path(os.path.expandvars(r"%APPDATA%\kicad\10.0")),
            "kicad_symbol_dir": Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols"),
            "kicad_footprint_dir": Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
        }
        return {k: v for k, v in default_cfg.items() if v.exists()}

    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{CONFIG.name} is not valid JSON ({e}).{HOWTO}")

    cfg = {}
    for key, value in raw.items():
        if not str(value).strip():
            continue
        path = Path(value).expanduser()
        if not path.is_dir():
            raise ValueError(f"{CONFIG.name}: '{key}' is not an existing folder -> {path}{HOWTO}")
        cfg[key] = path

    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(f"{CONFIG.name} is missing required keys: {', '.join(missing)}.{HOWTO}")
    return cfg


def load_cli() -> Optional[Path]:
    """Find the kicad-cli executable."""
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    cands = [
        Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
        Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"),
        Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
        Path("/usr/bin/kicad-cli")
    ]
    for c in cands:
        if c.exists():
            return c
    return None


def load_kicad_python() -> str:
    """Find KiCad's bundled Python interpreter (containing pcbnew)."""
    cands = [
        Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
        Path(r"C:\Program Files\KiCad\9.0\bin\python.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\python.exe"),
        Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"),
        Path("/usr/bin/python3")
    ]
    for c in cands:
        if c.exists():
            return str(c)
    return "python"


def find_freerouting_jar() -> Optional[Path]:
    """Find the Freerouting JAR binary (prioritizes v2.4.1)."""
    root_dir = Path(__file__).resolve().parents[2]
    candidates = [
        root_dir / "freerouting-2.4.1.jar",
        root_dir / "freerouting.jar",
        Path.home() / "Downloads" / "freerouting-2.4.1.jar",
        Path.home() / "Downloads" / "freerouting.jar",
        Path(r"C:\Program Files\Freerouting\freerouting.jar")
    ]
    for c in candidates:
        if c.exists():
            return c
    jars = sorted(root_dir.glob("freerouting*.jar"), reverse=True)
    if jars:
        return jars[0]
    return None


def find_easyeda_db() -> Optional[Path]:
    """Find the local EasyEDA Pro standard parts SQLite database (easyeda-std.elib)."""
    env_path = os.environ.get("EASYEDA_ELIB_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    project_data = Path(__file__).resolve().parents[2] / "data" / "easyeda-std.elib"
    candidates = [
        project_data,
        Path(r"D:\Program Files\easyeda-pro\resources\app\assets\db\easyeda-std.elib"),
        Path(r"C:\Program Files\easyeda-pro\resources\app\assets\db\easyeda-std.elib"),
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\easyeda-pro\resources\app\assets\db\easyeda-std.elib")),
        Path(os.path.expandvars(r"%APPDATA%\easyeda-pro\resources\app\assets\db\easyeda-std.elib")),
    ]
    for c in candidates:
        if c.exists():
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
