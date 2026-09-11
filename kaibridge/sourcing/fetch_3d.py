"""Kaibridge Non-Blocking 3D Model Downloader with Pacing (kaibridge.sourcing.fetch_3d).
Downloads component 3D STEP/WRL models from EasyEDA/LCSC in background with rate pacing.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List


def download_3d_worker(project_dir: Path, lcsc_ids: List[str], interval: float = 5.0):
    libs_dir = project_dir / "libs" / "kaibridge"
    dump_dir = project_dir / "kaibridge_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    log_file = dump_dir / "3d_fetch.log"

    easyeda_exe = shutil.which("easyeda2kicad")
    base_cmd = [easyeda_exe] if easyeda_exe else [sys.executable, "-m", "easyeda2kicad"]

    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting 3D model background download for: {', '.join(lcsc_ids)}\n")
        log.flush()

        for i, cid in enumerate(lcsc_ids):
            clean_id = str(cid).strip().upper()
            if not clean_id.startswith("C"):
                clean_id = f"C{clean_id}"

            if i > 0 and interval > 0:
                time.sleep(interval)

            log.write(f"[{time.strftime('%H:%M:%S')}] Fetching 3D model for {clean_id}...\n")
            log.flush()

            # 1. Primary Engine: JLC2KiCadLib for modern KiCad 10 STEP/WRL models
            jlc_bin = shutil.which("JLC2KiCadLib") or "JLC2KiCadLib"
            jlc_cmd = [
                jlc_bin,
                clean_id,
                "-dir", str(project_dir / "libs"),
                "-symbol_lib_dir", ".",
                "-symbol_lib", "kaibridge",
                "-footprint_lib", "kaibridge.pretty",
                "-model_dir", "kaibridge.3dshapes",
                "-model_base_variable", "KIPRJMOD",
                "-models", "STEP", "WRL",
            ]
            try:
                jlc_res = subprocess.run(jlc_cmd, capture_output=True, text=True, timeout=60, check=False)
                if jlc_res.returncode == 0:
                    log.write(f"  [OK] Successfully saved modern 3D model for {clean_id} via JLC2KiCadLib\n")
                    pretty_3d = project_dir / "libs" / "kaibridge.pretty" / "kaibridge.3dshapes"
                    libs_3d = project_dir / "libs" / "kaibridge.3dshapes"
                    if pretty_3d.exists():
                        libs_3d.mkdir(parents=True, exist_ok=True)
                        for f in pretty_3d.glob("*.*"):
                            shutil.copy2(f, libs_3d / f.name)
                    log.flush()
                    continue
                else:
                    log.write(f"  [INFO] JLC2KiCadLib 3D fetch missed for {clean_id}; trying easyeda2kicad fallback...\n")
            except Exception as e:
                log.write(f"  [WARN] JLC2KiCadLib error for {clean_id}: {e}; falling back to easyeda2kicad...\n")

            # 2. Fallback Engine: easyeda2kicad
            cmd = base_cmd + [
                "--lcsc_id", clean_id,
                "--3d",
                "--output", str(libs_dir),
                "--overwrite",
                "--project-relative"
            ]

            try:
                res = subprocess.run(cmd, cwd=str(project_dir), capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    log.write(f"  [OK] Successfully saved 3D model for {clean_id} via easyeda2kicad\n")
                else:
                    log.write(f"  [WARN] 3D model not available for {clean_id} (safely skipped)\n")
            except subprocess.TimeoutExpired:
                log.write(f"  [TIMEOUT] 3D server timed out for {clean_id}\n")
            except Exception as e:
                log.write(f"  [ERROR] {e}\n")
            log.flush()

        log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 3D fetch batch completed.\n")
        log.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kaibridge Non-Blocking 3D Model Downloader")
    ap.add_argument("project_dir", help="KiCad project directory")
    ap.add_argument("lcsc_ids", nargs="+", help="LCSC part numbers (e.g. C6186 C99652)")
    ap.add_argument("--interval", type=float, default=5.0, help="Interval in seconds between requests (default: 5.0)")
    ap.add_argument("--bg", action="store_true", help="Run detached in the background and return immediately")
    args = ap.parse_args(argv)

    proj = Path(args.project_dir).expanduser().resolve()
    if not proj.exists():
        print(f"Error: Project directory {proj} does not exist.", file=sys.stderr)
        return 1

    if args.bg:
        cmd = [
            sys.executable, "-m", "kaibridge.sourcing.fetch_3d",
            str(proj),
            *args.lcsc_ids,
            "--interval", str(args.interval)
        ]
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(cmd, start_new_session=True)
        print(f"[*] 3D model download started in background for: {', '.join(args.lcsc_ids)} ({args.interval}s pacing)")
        return 0

    download_3d_worker(proj, args.lcsc_ids, interval=args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
