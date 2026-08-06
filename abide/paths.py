"""
abide/paths.py -- the one place that knows about kicad_paths.json.

Moved out of kicad_pins.py so nothing inside abide/ ever has to import the
plugin root. kicad_pins.py re-exports these names, so every existing caller
(kicad_lib_init, oracle, pcb_snapshot, currentboardfetcher) is unaffected.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "kicad_paths.json"

HOWTO = f"""
Fix {CONFIG.name} (plugin root, next to json2sch.py). It must contain:
{{
  "kicad_config_dir":    "<folder holding your global sym-lib-table>",
  "kicad_symbol_dir":    "<KiCad stock symbols folder>",
  "kicad_footprint_dir": "<KiCad stock footprints folder>"
}}
Where to find them (copy the values, do not type them):
  symbol / footprint dir : KiCad -> Preferences -> Configure Paths...
                           (rows ending in _SYMBOL_DIR and _FOOTPRINT_DIR)
  config dir             : PCB editor -> Tools -> Scripting Console, then run
                           import pcbnew; print(pcbnew.SETTINGS_MANAGER.GetUserSettingsPath())
Use forward slashes.
"""

def load_paths(*required):
    """Read kicad_paths.json -> {key: Path} for the non-empty, existing entries."""
    if not CONFIG.exists():
        raise ValueError(f"{CONFIG} not found.{HOWTO}")
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
            raise ValueError(
                f"{CONFIG.name}: '{key}' is not an existing folder -> {path}{HOWTO}")
        cfg[key] = path
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(f"{CONFIG.name}: fill in {', '.join(missing)}.{HOWTO}")
    return cfg

def load_cli():
    """Absolute path to kicad-cli, or None if it cannot be found."""
    try:
        sym_dir = str(load_paths().get("kicad_symbol_dir", ""))
        if "share" in sym_dir:
            base = sym_dir.split("share")[0]
            for name in ("kicad-cli.exe", "kicad-cli"):
                exe = os.path.join(base, "bin", name)
                if os.path.exists(exe):
                    return exe
    except Exception:
        pass
    return shutil.which("kicad-cli")

_ENV_KEYS = (
    ("kicad_symbol_dir", "SYMBOL_DIR"),
    ("kicad_footprint_dir", "FOOTPRINT_DIR"),
    ("kicad_3dmodel_dir", "3DMODEL_DIR"),
    ("kicad_template_dir", "TEMPLATE_DIR"),
)

def env_dirs(project_dir=None):
    """${...} substitutions for sym-lib-table / fp-lib-table URIs.

    Real environment variables win. kicad_paths.json fills the gaps for every
    KiCad major version, so one config file works on 6 through 10.
    """
    subst = {k: v for k, v in os.environ.items() if k.startswith("KICAD")}
    try:
        cfg = load_paths()
    except ValueError:
        cfg = {}
    for key, suffix in _ENV_KEYS:
        folder = cfg.get(key)
        if not folder:
            continue
        subst.setdefault(f"KICAD_{suffix}", str(folder))
        for major in ("6", "7", "8", "9", "10"):
            subst.setdefault(f"KICAD{major}_{suffix}", str(folder))
    if project_dir is not None:
        subst["KIPRJMOD"] = str(Path(project_dir).resolve())
    return subst
