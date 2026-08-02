"""
easyeda_client.py — Resilient, multi-backend EasyEDA CAD verification.

Never depends on a single HTTP path. Ordered backend chain:
  1. easyeda2kicad's own API client (in-process import)
  2. requests + easyeda2kicad headers + cookie warm-up
  3. curl_cffi with real Chrome TLS fingerprint (optional dep)
  4. trial download via easyeda2kicad CLI into a temp dir  <-- ground truth
  5. offline jlcparts SQLite dump (catalog-level only)

Usage:
    from easyeda_client import get_cad_facts, CadFacts
    facts = get_cad_facts("C2040")

Doctor mode (find out which backends work on YOUR machine/network):
    python easyeda_client.py --doctor C2040
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("EASYEDA_CACHE_DIR", Path.cwd() / ".part_cache"))
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL = 7 * 24 * 3600
TIMEOUT = 25

# jlcparts offline dump (download once):
#   https://github.com/yaqwsx/jlcparts/releases -> cache.sqlite3.gz
JLCPARTS_DB = Path(os.environ.get("JLCPARTS_DB", HERE / "jlcparts.sqlite3"))

PROXY = os.environ.get("EASYEDA_PROXY")  # e.g. http://127.0.0.1:8080

API_URL = "https://easyeda.com/api/products/{lcsc}/components?version=6.4.19.5"

# EXACTLY what easyeda2kicad sends. Do NOT put a Chrome UA here -- a Chrome UA
# without a Chrome TLS fingerprint is what triggers the Cloudflare 403.
EDA_HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "User-Agent": "easyeda2kicad v0.8.0",
}

VERBOSE = os.environ.get("EASYEDA_VERBOSE") == "1"

def _log(msg: str) -> None:
    if VERBOSE:
        print(f"[easyeda_client] {msg}", file=sys.stderr)

# ----------------------------------------------------------------------------
# Normalised result
# ----------------------------------------------------------------------------

@dataclass
class CadFacts:
    """Normalised verification facts about one LCSC part."""
    lcsc: str
    ok: bool = False
    # "cad"     -> real symbol+footprint geometry confirmed
    # "catalog" -> only catalogue metadata (package/mfr/pads), no geometry
    # "none"    -> nothing at all
    confidence: str = "none"
    source: str = ""            # which backend produced this
    mpn: str = ""
    manufacturer: str = ""
    package: str = ""
    pin_count: int = 0
    pad_count: int = 0
    has_symbol: bool = False
    has_footprint: bool = False
    has_3d: bool = False
    error: str = ""
    tried: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")

def _cache_get(key: str) -> Optional[dict]:
    p = _cache_path(key)
    if p.exists() and (time.time() - p.stat().st_mtime) < CACHE_TTL:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _cache_put(key: str, value: dict) -> None:
    try:
        _cache_path(key).write_text(json.dumps(value), encoding="utf-8")
    except Exception:
        pass

# ----------------------------------------------------------------------------
# Shared parser: raw EasyEDA API JSON -> CadFacts
# ----------------------------------------------------------------------------

def _facts_from_api_json(lcsc: str, data: dict, source: str) -> CadFacts:
    f = CadFacts(lcsc=lcsc, source=source)

    if not data or not data.get("success"):
        f.error = "EasyEDA API returned success=false"
        return f

    res = data.get("result") or {}
    data_str = res.get("dataStr") or {}
    head = data_str.get("head") or {}
    c_para = head.get("c_para") or {}
    shapes = data_str.get("shape") or []

    f.mpn = str(c_para.get("Manufacturer Part") or "").strip()
    f.manufacturer = str(c_para.get("Manufacturer") or "").strip()
    f.package = str(c_para.get("package") or "").strip()

    f.pin_count = sum(1 for s in shapes if isinstance(s, str) and s.startswith("P~"))
    f.has_symbol = f.pin_count > 0

    pkg_detail = res.get("packageDetail") or {}
    pkg_shapes = ((pkg_detail.get("dataStr") or {}).get("shape") or [])
    f.has_footprint = len(pkg_shapes) > 0
    f.pad_count = sum(
        1 for s in pkg_shapes if isinstance(s, str) and s.startswith("PAD~")
    )
    if not f.package:
        f.package = str(
            ((pkg_detail.get("dataStr") or {}).get("head") or {})
            .get("c_para", {})
            .get("package", "")
        ).strip()

    f.has_3d = any(
        isinstance(s, str) and "SVGNODE" in s for s in pkg_shapes
    )

    f.ok = f.has_symbol and f.has_footprint
    f.confidence = "cad" if f.ok else "catalog"
    if not f.ok:
        missing = []
        if not f.has_symbol:
            missing.append("symbol")
        if not f.has_footprint:
            missing.append("footprint")
        f.error = "missing " + "+".join(missing)
    return f

# ----------------------------------------------------------------------------
# Backend 1: easyeda2kicad's own in-process API client
# ----------------------------------------------------------------------------

def _backend_lib(lcsc: str) -> CadFacts:
    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi  # type: ignore
    except Exception as e:
        return CadFacts(lcsc=lcsc, source="lib", error=f"import failed: {e}")

    try:
        api = EasyedaApi()
        data = api.get_info_from_easyeda_api(lcsc_id=lcsc)
        if not data:
            return CadFacts(lcsc=lcsc, source="lib", error="empty response")
        # Older versions already unwrap 'result'; normalise both shapes.
        if "success" not in data and "dataStr" in data:
            data = {"success": True, "result": data}
        return _facts_from_api_json(lcsc, data, "lib")
    except Exception as e:
        return CadFacts(lcsc=lcsc, source="lib", error=f"{type(e).__name__}: {e}")

# ----------------------------------------------------------------------------
# Backend 2: requests with the correct headers + cookie warm-up
# ----------------------------------------------------------------------------

_SESSION = None

def _get_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    import requests

    s = requests.Session()
    s.headers.update(EDA_HEADERS)
    if PROXY:
        s.proxies.update({"http": PROXY, "https": PROXY})
    # Warm-up: pick up any Cloudflare clearance cookies from the plain site.
    try:
        s.get("https://easyeda.com/", timeout=TIMEOUT)
    except Exception as e:
        _log(f"warm-up failed (non-fatal): {e}")
    _SESSION = s
    return s

def _backend_requests(lcsc: str) -> CadFacts:
    try:
        s = _get_session()
        r = s.get(
            API_URL.format(lcsc=lcsc),
            timeout=TIMEOUT,
            headers={"Referer": f"https://easyeda.com/component/{lcsc}"},
        )
        if r.status_code != 200:
            return CadFacts(
                lcsc=lcsc, source="requests", error=f"HTTP {r.status_code}"
            )
        return _facts_from_api_json(lcsc, r.json(), "requests")
    except Exception as e:
        return CadFacts(
            lcsc=lcsc, source="requests", error=f"{type(e).__name__}: {e}"
        )

# ----------------------------------------------------------------------------
# Backend 3: curl_cffi -- real Chrome TLS/JA3 fingerprint (beats Cloudflare)
#   pip install curl_cffi
# ----------------------------------------------------------------------------

def _backend_curl_cffi(lcsc: str) -> CadFacts:
    try:
        from curl_cffi import requests as creq  # type: ignore
    except Exception as e:
        return CadFacts(lcsc=lcsc, source="curl_cffi", error=f"not installed: {e}")

    for imp in ("chrome124", "chrome120", "chrome110"):
        try:
            r = creq.get(
                API_URL.format(lcsc=lcsc),
                impersonate=imp,
                timeout=TIMEOUT,
                proxies={"http": PROXY, "https": PROXY} if PROXY else None,
                headers={"Referer": f"https://easyeda.com/component/{lcsc}"},
            )
            if r.status_code == 200:
                return _facts_from_api_json(lcsc, r.json(), f"curl_cffi:{imp}")
            _log(f"curl_cffi {imp} -> HTTP {r.status_code}")
        except Exception as e:
            _log(f"curl_cffi {imp} failed: {e}")
    return CadFacts(lcsc=lcsc, source="curl_cffi", error="all impersonations failed")

# ----------------------------------------------------------------------------
# Backend 4: trial download -- THE ground truth
#   If easyeda2kicad can produce a symbol + footprint, the part is real and
#   importable. This uses exactly the code path your pipeline uses in Rule 4.
# ----------------------------------------------------------------------------

_PIN_RE = re.compile(r"\(pin\s+\w+", re.IGNORECASE)

def _backend_trial_download(lcsc: str) -> CadFacts:
    f = CadFacts(lcsc=lcsc, source="trial_download")
    exe = shutil.which("easyeda2kicad")
    cmd_prefix = [exe] if exe else [sys.executable, "-m", "easyeda2kicad"]

    tmp = Path(tempfile.mkdtemp(prefix=f"probe_{lcsc}_"))
    try:
        out_base = tmp / "probe"
        # --symbol --footprint only: skip the slow 3D STEP download.
        cmd = cmd_prefix + [
            "--lcsc_id", lcsc,
            "--symbol", "--footprint",
            "--output", str(out_base),
            "--overwrite",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        _log(f"trial_download rc={proc.returncode}: {combined[:400]}")

        sym = out_base.with_suffix(".kicad_sym")
        pretty = Path(str(out_base) + ".pretty")

        if sym.exists():
            text = sym.read_text(encoding="utf-8", errors="ignore")
            f.has_symbol = True
            f.pin_count = len(_PIN_RE.findall(text))
            m = re.search(r'\(property\s+"Manufacturer"\s+"([^"]*)"', text)
            if m:
                f.manufacturer = m.group(1)
            m = re.search(r'\(property\s+"(?:MPN|Value)"\s+"([^"]*)"', text)
            if m and not f.mpn:
                f.mpn = m.group(1)
            m = re.search(r'\(property\s+"Footprint"\s+"([^"]*)"', text)
            if m:
                f.package = m.group(1).split(":")[-1]

        if pretty.is_dir():
            mods = list(pretty.glob("*.kicad_mod"))
            f.has_footprint = len(mods) > 0
            if mods:
                mtext = mods[0].read_text(encoding="utf-8", errors="ignore")
                f.pad_count = mtext.count("(pad ")
                if not f.package:
                    f.package = mods[0].stem

        f.ok = f.has_symbol and f.has_footprint
        f.confidence = "cad" if f.ok else "none"
        if not f.ok:
            f.error = (combined.strip().splitlines() or ["no output produced"])[-1][:200]
        return f
    except subprocess.TimeoutExpired:
        f.error = "easyeda2kicad timed out"
        return f
    except Exception as e:
        f.error = f"{type(e).__name__}: {e}"
        return f
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ----------------------------------------------------------------------------
# Backend 5: offline jlcparts SQLite dump (catalog-level, zero network)
# ----------------------------------------------------------------------------

def _backend_jlcparts(lcsc: str) -> CadFacts:
    f = CadFacts(lcsc=lcsc, source="jlcparts_offline")
    if not JLCPARTS_DB.exists():
        f.error = f"db not found at {JLCPARTS_DB}"
        return f
    try:
        num = int(lcsc.lstrip("Cc"))
    except ValueError:
        f.error = "bad lcsc id"
        return f
    try:
        con = sqlite3.connect(f"file:{JLCPARTS_DB}?mode=ro", uri=True)
        cur = con.execute(
            "SELECT mfr, package, joints, description, stock, basic "
            "FROM components WHERE lcsc = ?",
            (num,),
        )
        row = cur.fetchone()
        con.close()
    except Exception as e:
        f.error = f"{type(e).__name__}: {e}"
        return f

    if not row:
        f.error = "not in offline catalog"
        return f

    mfr, package, joints, _desc, _stock, _basic = row
    f.mpn = str(mfr or "").strip()
    f.package = str(package or "").strip()
    f.pad_count = int(joints or 0)
    f.pin_count = int(joints or 0)   # approximation: pads ~= pins
    f.has_symbol = False             # unknown offline
    f.has_footprint = False
    f.ok = True
    f.confidence = "catalog"
    f.error = "catalog-only (no CAD geometry verified)"
    return f

# ----------------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------------

BACKENDS_FAST = [
    ("lib", _backend_lib),
    ("requests", _backend_requests),
    ("curl_cffi", _backend_curl_cffi),
]
BACKENDS_HEAVY = [("trial_download", _backend_trial_download)]
BACKENDS_OFFLINE = [("jlcparts_offline", _backend_jlcparts)]

def get_cad_facts(
    lcsc: str,
    allow_download_probe: bool = True,
    offline_only: bool = False,
    use_cache: bool = True,
) -> CadFacts:
    """Return the best CadFacts obtainable for `lcsc`, trying every backend."""
    lcsc = lcsc.strip().upper()
    ck = f"cadfacts:v2:{lcsc}:{allow_download_probe}:{offline_only}"
    if use_cache:
        cached = _cache_get(ck)
        if cached:
            return CadFacts(**cached)

    chain = list(BACKENDS_OFFLINE) if offline_only else (
        BACKENDS_FAST
        + (BACKENDS_HEAVY if allow_download_probe else [])
        + BACKENDS_OFFLINE
    )

    tried: List[str] = []
    best: Optional[CadFacts] = None

    for name, fn in chain:
        res = fn(lcsc)
        tried.append(f"{name}={'ok' if res.ok else (res.error or 'fail')}")
        _log(f"{lcsc} via {name}: ok={res.ok} conf={res.confidence} err={res.error}")
        if res.ok and res.confidence == "cad":
            res.tried = tried
            if use_cache:
                _cache_put(ck, res.to_dict())
            return res
        if res.ok and best is None:
            best = res  # remember a catalog-level hit, keep trying for CAD

    if best is not None:
        best.tried = tried
        if use_cache:
            _cache_put(ck, best.to_dict())
        return best

    fail = CadFacts(lcsc=lcsc, ok=False, confidence="none",
                    source="none", error="all backends failed", tried=tried)
    # Do not cache hard failures for the full TTL -- network may recover.
    return fail

# ----------------------------------------------------------------------------
# Doctor
# ----------------------------------------------------------------------------

def doctor(lcsc: str = "C2040") -> int:
    print(f"EasyEDA backend doctor -- probing {lcsc}\n" + "=" * 60)
    all_backends = BACKENDS_FAST + BACKENDS_HEAVY + BACKENDS_OFFLINE
    any_cad = False
    for name, fn in all_backends:
        t0 = time.time()
        res = fn(lcsc)
        dt = time.time() - t0
        status = "OK " if res.ok else "FAIL"
        if res.ok and res.confidence == "cad":
            any_cad = True
        print(
            f"[{status}] {name:<18} {dt:5.1f}s  conf={res.confidence:<8} "
            f"pins={res.pin_count:<4} pkg={res.package or '-':<16} "
            f"{res.error}"
        )
    print("=" * 60)
    if any_cad:
        print("RESULT: at least one CAD-grade backend works. You are fine.")
        return 0
    print("RESULT: no CAD-grade backend. Try:")
    print("  pip install curl_cffi")
    print("  set EASYEDA_PROXY=http://<proxy>")
    print("  download jlcparts cache.sqlite3 for offline mode")
    return 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doctor", metavar="LCSC", nargs="?", const="C2040")
    ap.add_argument("--lcsc")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args()

    if a.doctor:
        sys.exit(doctor(a.doctor))
    if a.lcsc:
        facts = get_cad_facts(
            a.lcsc,
            allow_download_probe=not a.no_probe,
            offline_only=a.offline,
        )
        print(json.dumps(facts.to_dict(), indent=2))
        sys.exit(0 if facts.ok else 1)
    ap.print_help()
