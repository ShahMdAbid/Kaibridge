"""Kaibridge Component Sourcing:
Fetches symbols, footprints (.kicad_mod), and 3D models (.step/.wrl) from LCSC / EasyEDA.
"""
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any

from ..core.paths import load_paths, load_kicad_python
from .klib import LibIndex, LibError

#Portable discovery of KiCad 3rd-party Python site-packages
_cands = [
    Path.home() / "Documents" / "KiCad" / "10.0" / "3rdparty" / "Python311" / "site-packages",
    Path.home() / "OneDrive" / "Documents" / "KiCad" / "10.0" / "3rdparty" / "Python311" / "site-packages",
    Path.home() / "Documents" / "KiCad" / "9.0" / "3rdparty" / "Python311" / "site-packages",
    Path.home() / "OneDrive" / "Documents" / "KiCad" / "9.0" / "3rdparty" / "Python311" / "site-packages"
]
for _sd in _cands:
    if _sd.exists() and str(_sd) not in sys.path:
        sys.path.insert(0, str(_sd))

_SOURCING_DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_lcsc(project_dir: str | Path, lcsc_id: str, lib_name: str = "kaibridge") -> Dict[str, Any]:
    """Downloads LCSC component and registers it in the project library tables."""
    proj_path = Path(project_dir).resolve()
    proj_path.mkdir(parents=True, exist_ok=True)
    libs_dir = proj_path / "libs"
    libs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ensure project-level sym-lib-table & fp-lib-table exist
    sym_table_file = proj_path / "sym-lib-table"
    fp_table_file = proj_path / "fp-lib-table"

    sym_entry = f'(sym_lib_table (lib (name "{lib_name}")(type "KiCad")(uri "${{KIPRJMOD}}/libs/{lib_name}.kicad_sym")(options "")(descr "Kaibridge LCSC Library")))'
    fp_entry = f'(fp_lib_table (lib (name "{lib_name}")(type "KiCad")(uri "${{KIPRJMOD}}/libs/{lib_name}.pretty")(options "")(descr "Kaibridge LCSC Footprints")))'

    if not sym_table_file.exists():
        sym_table_file.write_text(sym_entry + "\n", encoding="utf-8")
    else:
        text = sym_table_file.read_text(encoding="utf-8")
        if f'name "{lib_name}"' not in text:
            idx_close = text.rfind(')')
            if idx_close != -1:
                new_text = text[:idx_close] + f'\n  (lib (name "{lib_name}")(type "KiCad")(uri "${{KIPRJMOD}}/libs/{lib_name}.kicad_sym")(options "")(descr ""))\n)'
                sym_table_file.write_text(new_text, encoding="utf-8")

    if not fp_table_file.exists():
        fp_table_file.write_text(fp_entry + "\n", encoding="utf-8")
    else:
        text = fp_table_file.read_text(encoding="utf-8")
        if f'name "{lib_name}"' not in text:
            idx_close = text.rfind(')')
            if idx_close != -1:
                new_text = text[:idx_close] + f'\n  (lib (name "{lib_name}")(type "KiCad")(uri "${{KIPRJMOD}}/libs/{lib_name}.pretty")(options "")(descr ""))\n)'
                fp_table_file.write_text(new_text, encoding="utf-8")

    # 2. Run easyeda2kicad with unblocked mirror runner
    kicad_python = load_kicad_python()
    runner_script = os.path.join(_SOURCING_DIR, "lcsc_runner.py")
    output_target = str(libs_dir / lib_name)

    cmd = [
        kicad_python, runner_script,
        "--lcsc_id", lcsc_id,
        "--full",
        "--output", output_target,
        "--overwrite",
        "--project-relative"
    ]

    try:
        res = subprocess.run(cmd, cwd=str(proj_path), capture_output=True, text=True, timeout=35)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"LCSC download for {lcsc_id} timed out after 35s. EasyEDA server unresponsive."}
    except Exception as e:
        return {"success": False, "error": str(e)}
    combined = (res.stdout or "") + "\n" + (res.stderr or "")

    sym_name_match = re.search(r"Symbol name\s*:\s*([^\r\n]+)", combined)
    fp_name_match = re.search(r"Footprint name\s*:\s*([^\r\n]+)", combined)

    created_sym = sym_name_match.group(1).strip() if sym_name_match else None
    created_fp = fp_name_match.group(1).strip() if fp_name_match else None

    shapes_dir = libs_dir / f"{lib_name}.3dshapes"
    has_3d = shapes_dir.exists() and len(list(shapes_dir.glob("*.*"))) > 0

    pins_data = {}
    if created_sym:
        try:
            idx = LibIndex(proj_path)
            sym_obj = idx.symbol(f"{lib_name}:{created_sym}")
            for num, p in sym_obj.pins.items():
                pins_data[num] = {"name": p.name, "type": p.etype}
        except Exception:
            pass

    return {
        "success": res.returncode == 0 and bool(created_sym),
        "lcsc_id": lcsc_id,
        "lib_id": f"{lib_name}:{created_sym}" if created_sym else None,
        "footprint": f"{lib_name}:{created_fp}" if created_fp else None,
        "has_3d_model": has_3d,
        "pins": pins_data,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip()
    }


