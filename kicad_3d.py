#!/usr/bin/env python3
"""
kicad_3d.py -- Non-blocking background 3D model downloader with pacing.

Usage:
    # Detached background execution (returns instantly in <0.1s):
    python kicad_3d.py "<PROJECT_DIR>" C6186 C99652 --bg --interval 5

    # Direct execution (foreground):
    python kicad_3d.py "<PROJECT_DIR>" C6186 --interval 5
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def download_3d_worker(project_dir: Path, lcsc_ids: list[str], interval: float = 5.0):
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
                    log.write(f"  [OK] Successfully saved 3D model for {clean_id}\n")
                else:
                    log.write(f"  [WARN] 3D model not available for {clean_id} (safely skipped)\n")
            except subprocess.TimeoutExpired:
                log.write(f"  [TIMEOUT] EasyEDA 3D server timed out for {clean_id}\n")
            except Exception as e:
                log.write(f"  [ERROR] {e}\n")
            log.flush()

        log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 3D fetch batch completed.\n")
        log.flush()


def main():
    ap = argparse.ArgumentParser(description="Kaibridge Non-Blocking 3D Model Downloader")
    ap.add_argument("project_dir", help="KiCad project directory")
    ap.add_argument("lcsc_ids", nargs="+", help="LCSC part numbers (e.g. C6186 C99652)")
    ap.add_argument("--interval", type=float, default=5.0, help="Interval in seconds between requests (default: 5.0)")
    ap.add_argument("--bg", action="store_true", help="Run detached in the background and return immediately")
    args = ap.parse_args()

    proj = Path(args.project_dir).expanduser().resolve()
    if not proj.exists():
        print(f"Error: Project directory {proj} does not exist.", file=sys.stderr)
        sys.exit(1)

    if args.bg:
        worker_script = Path(__file__).resolve()
        cmd = [
            sys.executable, str(worker_script),
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
        return

    download_3d_worker(proj, args.lcsc_ids, interval=args.interval)


if __name__ == "__main__":
    main()
