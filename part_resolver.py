#!/usr/bin/env python3
"""
part_resolver.py — Autonomous LCSC part discovery + verification for abIDE.
"""

from __future__ import annotations
import argparse, json, os, re, sys, time, hashlib
from dataclasses import dataclass, field, asdict
from typing import Any
import requests
from easyeda_client import get_cad_facts, CadFacts

CACHE_DIR = os.environ.get("PART_RESOLVER_CACHE_DIR", os.path.join(os.getcwd(), ".part_cache"))
JLC_SEARCH = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
LCSC_SEARCH = "https://wmsc.lcsc.com/wmsc/search/global-search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
TIMEOUT = 20
RETRIES = 3
CACHE_TTL = 7 * 24 * 3600

def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return os.path.join(CACHE_DIR, f"{h}.json")

def _cache_get(key: str):
    p = _cache_path(key)
    if not os.path.isfile(p): return None
    if time.time() - os.path.getmtime(p) > CACHE_TTL: return None
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return None

def _cache_put(key: str, value) -> None:
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f: json.dump(value, f)
    except Exception: pass

def _http(method: str, url: str, **kw):
    last = None
    if "headers" not in kw:
        kw["headers"] = HEADERS
    if "timeout" not in kw:
        kw["timeout"] = TIMEOUT
    for attempt in range(RETRIES):
        try:
            r = requests.request(method, url, **kw)
            if r.status_code == 200: return r
            last = f"HTTP {r.status_code}"
        except Exception as e: last = f"{type(e).__name__}: {e}"
        time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"request failed after {RETRIES} tries ({url}): {last}")

@dataclass
class PartSpec:
    ref: str
    query: str
    must_include: list[str] = field(default_factory=list)
    must_exclude: list[str] = field(default_factory=list)
    package: str | None = None
    expected_pin_count: int | None = None
    min_stock: int = 100
    prefer_basic: bool = True
    mpn: str | None = None

@dataclass
class Candidate:
    lcsc: str
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    package: str = ""
    stock: int = 0
    is_basic: bool = False
    price: float | None = None
    source: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    facts: CadFacts = field(default_factory=lambda: CadFacts(""))

def search_jlcpcb(keyword: str, limit: int = 25) -> list[Candidate]:
    key = f"jlc::{keyword}::{limit}"
    cached = _cache_get(key)
    if cached is None:
        body = {"currentPage": 1, "pageSize": limit, "keyword": keyword, "searchSource": "search"}
        r = _http("POST", JLC_SEARCH, json=body, headers={**HEADERS, "Content-Type": "application/json"})
        cached = r.json()
        _cache_put(key, cached)
    out = []
    data = (cached or {}).get("data") or {}
    page = data.get("componentPageInfo") or {}
    for it in (page.get("list") or []):
        code = it.get("componentCode") or ""
        if not re.fullmatch(r"C\d+", code): continue
        prices = it.get("componentPrices") or []
        out.append(Candidate(
            lcsc=code,
            mpn=it.get("componentModelEn") or "",
            manufacturer=it.get("componentBrandEn") or "",
            description=it.get("describe") or "",
            package=it.get("componentSpecificationEn") or "",
            stock=int(it.get("stockCount") or 0),
            is_basic=(it.get("componentLibraryType") or "").lower() == "base",
            price=(prices[0].get("productPrice") if prices else None),
            source="jlcpcb"
        ))
    return out

def search_lcsc(keyword: str, limit: int = 25) -> list[Candidate]:
    key = f"lcsc::{keyword}::{limit}"
    cached = _cache_get(key)
    if cached is None:
        r = _http("GET", LCSC_SEARCH, params={"keyword": keyword})
        cached = r.json()
        _cache_put(key, cached)
    out = []
    result = (cached or {}).get("result") or {}
    rows = (result.get("productSearchResultVO") or {}).get("productList") or []
    for it in rows[:limit]:
        code = it.get("productCode") or ""
        if not re.fullmatch(r"C\d+", code): continue
        out.append(Candidate(
            lcsc=code,
            mpn=it.get("productModel") or "",
            manufacturer=(it.get("brandNameEn") or ""),
            description=it.get("productIntroEn") or "",
            package=it.get("encapStandard") or "",
            stock=int(it.get("stockNumber") or 0),
            source="lcsc"
        ))
    return out

def verify(cand: Candidate, allow_probe: bool = True) -> CadFacts:
    facts = get_cad_facts(cand.lcsc, allow_download_probe=allow_probe)
    cand.facts = facts
    return facts

def _norm_pkg(p: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (p or "").lower())

def score_candidate(cand: Candidate, spec: PartSpec) -> tuple[int, list[str]]:
    reasons: list[str] = []
    f: CadFacts = cand.facts
    score = 0

    if f.confidence == "none":
        return -1000, [f"no CAD data obtainable ({f.error})"]
    if f.confidence == "catalog":
        score -= 15
        reasons.append("catalog-only verification (no geometry confirmed)")
    else:
        if not f.has_symbol:
            return -1000, ["EasyEDA has no schematic symbol"]
        if not f.has_footprint:
            return -1000, ["EasyEDA has no footprint"]
        reasons.append(f"CAD verified via {f.source}")

    mpn_ref = (f.mpn or cand.mpn or "").upper()
    if spec.mpn:
        want = spec.mpn.upper()
        if want == mpn_ref:
            score += 50; reasons.append("exact MPN match")
        elif want in mpn_ref or mpn_ref in want:
            score += 25; reasons.append("partial MPN match")
        else:
            score -= 30; reasons.append(f"MPN mismatch ({mpn_ref})")

    hay = f"{cand.description} {mpn_ref} {f.package}".lower()
    for tok in spec.must_exclude:
        if tok.lower() in hay:
            return -1000, [f"excluded token present: {tok}"]
    for tok in spec.must_include:
        if tok.lower() not in hay:
            return -1000, [f"required token missing: {tok}"]
    toks = [t for t in re.split(r"[\s,]+", spec.query.lower()) if len(t) > 2]
    if toks:
        hit = sum(1 for t in toks if t in hay) / len(toks)
        score += int(30 * hit)

    if spec.package:
        a = _norm_pkg(spec.package); b = _norm_pkg(f.package or cand.package)
        if a and b:
            if a == b or a in b or b in a:
                score += 20; reasons.append("package match")
            else:
                score -= 25; reasons.append(f"package mismatch ({b} != {a})")

    if spec.expected_pin_count:
        n = f.pin_count or f.pad_count
        if n:
            if n == spec.expected_pin_count:
                score += (15 if f.confidence == "cad" else 8)
                reasons.append(f"pin count {n} matches")
            elif f.confidence == "cad":
                score -= 40; reasons.append(f"pin count {n} != {spec.expected_pin_count}")
            else:
                score -= 10; reasons.append(f"pad count {n} != expected (approx)")

    if cand.stock >= max(spec.min_stock, 1000): score += 10
    elif cand.stock <= 0:                        score -= 30; reasons.append("out of stock")
    elif cand.stock < spec.min_stock:            score -= 10
    if spec.prefer_basic and cand.is_basic:      score += 10

    return score, reasons

AUTO_MIN_SCORE  = 70
AUTO_MIN_MARGIN = 20

def gate(ranked: list[Candidate], spec: PartSpec) -> str:
    if not ranked: return "REJECT"
    top = ranked[0]
    if top.score < AUTO_MIN_SCORE:
        return "REJECT" if top.score < 0 else "AMBIGUOUS"
    margin = top.score - (ranked[1].score if len(ranked) > 1 else -999)
    if margin < AUTO_MIN_MARGIN: return "AMBIGUOUS"
    if top.facts.confidence == "catalog":
        exact_mpn = bool(spec.mpn) and spec.mpn.upper() == (top.facts.mpn or "").upper()
        pkg_ok = (not spec.package) or _norm_pkg(spec.package) in _norm_pkg(top.facts.package)
        if not (exact_mpn and pkg_ok): return "AMBIGUOUS"
    return "AUTO"

def resolve(spec: PartSpec) -> dict[str, Any]:
    errors = []
    candidates = []
    queries = [spec.query]
    if spec.mpn: queries.insert(0, spec.mpn)

    for q in queries:
        for backend in (search_jlcpcb, search_lcsc):
            try: candidates += backend(q)
            except Exception as e: errors.append(f"{backend.__name__}('{q}'): {e}")
        if candidates: break

    seen = {}
    for c in candidates:
        prev = seen.get(c.lcsc)
        if prev is None or len(c.description) > len(prev.description): seen[c.lcsc] = c
    pool = sorted(seen.values(), key=lambda c: -c.stock)[:8]

    if not pool:
        return {"ref": spec.ref, "status": "REJECT", "chosen": None, "alternatives": [], "errors": errors, "message": f"No LCSC candidates found for '{spec.query}'."}

    for c in pool:
        verify(c, allow_probe=False)
        c.score, c.reasons = score_candidate(c, spec)
    pool.sort(key=lambda c: (-c.score, -c.stock))

    for c in pool[:2]:
        if c.facts.confidence != "cad":
            verify(c, allow_probe=True)
            c.score, c.reasons = score_candidate(c, spec)
    pool.sort(key=lambda c: (-c.score, -c.stock))

    viable = [c for c in pool if c.score > -1000]
    if not viable:
        return {"ref": spec.ref, "status": "REJECT", "chosen": None, "alternatives": [{"lcsc_id": c.lcsc, **asdict(c)} for c in pool[:5]], "errors": errors, "message": "All candidates disqualified."}

    status = gate(viable, spec)
    best = viable[0]
    margin = best.score - (viable[1].score if len(viable) > 1 else -1000)
    
    if status == "AUTO":
        msg = f"{spec.ref}: {best.lcsc} ({best.mpn}) — score {best.score}, clear winner by {margin}."
    else:
        msg = f"{spec.ref}: top candidate {best.lcsc} scored {best.score} (margin {margin}). Status {status} — user must choose."

    def fmt_cand(c: Candidate):
        d = asdict(c)
        d["lcsc_id"] = c.lcsc
        d["facts"] = asdict(c.facts)
        return d

    return {"ref": spec.ref, "status": status, "chosen": fmt_cand(best), "alternatives": [fmt_cand(c) for c in viable[1:5]], "errors": errors, "message": msg}

def verify_downloaded(lcsc: str, lib_dir: str, expected_pin_count: int | None = None) -> dict[str, Any]:
    problems = []
    sym_file = os.path.join(lib_dir, "easyeda2kicad.kicad_sym")
    pretty = os.path.join(lib_dir, "easyeda2kicad.pretty")
    if not os.path.isfile(sym_file): problems.append(f"missing symbol library: {sym_file}")
    if not os.path.isdir(pretty): problems.append(f"missing footprint dir: {pretty}")
    if problems: return {"lcsc_id": lcsc, "ok": False, "problems": problems}

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from footprint_extractor import extract_symbols
        symbols = extract_symbols(sym_file)
        if lcsc not in symbols:
            problems.append(f"symbol '{lcsc}' not present in library")
            return {"lcsc_id": lcsc, "ok": False, "problems": problems}
        pins = symbols[lcsc]["pins"]
        if expected_pin_count is not None and len(pins) != expected_pin_count:
            problems.append(f"pin count mismatch: expected {expected_pin_count}, downloaded {len(pins)}")
        return {"lcsc_id": lcsc, "ok": not problems, "pin_count": len(pins), "pin_names": sorted(pins.keys()), "problems": problems}
    except Exception as e:
        return {"lcsc_id": lcsc, "ok": False, "problems": [f"Extraction failed: {e}"]}

def _load_specs(path: str) -> list[PartSpec]:
    import yaml
    with open(path, encoding="utf-8") as f: raw = yaml.safe_load(f) or {}
    items = raw.get("component_requirements") or raw.get("parts") or []
    return [PartSpec(**it) for it in items]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--query")
    ap.add_argument("--ref", default="PART1")
    ap.add_argument("--mpn")
    ap.add_argument("--package")
    ap.add_argument("--pins", type=int)
    ap.add_argument("--min-stock", type=int, default=100)
    ap.add_argument("--verify")
    ap.add_argument("--verify-download", nargs=2, metavar=("LCSC_ID", "LIB_DIR"))
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.verify:
        f = get_cad_facts(args.verify)
        print(json.dumps(f.to_dict(), indent=2))
        sys.exit(0)

    if args.verify_download:
        rep = verify_downloaded(args.verify_download[0], args.verify_download[1])
        print(json.dumps(rep, indent=2))
        sys.exit(0 if rep["ok"] else 1)

    if args.spec: specs = _load_specs(args.spec)
    elif args.query:
        specs = [PartSpec(ref=args.ref, query=args.query, mpn=args.mpn, package=args.package, expected_pin_count=args.pins, min_stock=args.min_stock)]
    else: ap.error("need --spec, --query, --verify or --verify-download")

    reports = [resolve(s) for s in specs]
    print("=" * 70)
    for r in reports:
        icon = {"AUTO": "[OK]", "AMBIGUOUS": "[??]", "REJECT": "[XX]"}[r["status"]]
        print(f"{icon} {r['message']}")
        if r["status"] != "AUTO":
            for alt in ([r["chosen"]] if r["chosen"] else []) + r["alternatives"]:
                if not alt: continue
                print(f"      {alt['lcsc_id']:<10} {alt['mpn']:<24} {alt['package']:<14} stock={alt['stock']:<8} score={alt['score']}")
                for why in alt.get("reasons", []): print(f"          - {why}")
    print("=" * 70)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f: json.dump(reports, f, indent=2)
        print(f"report -> {args.out}")

    if any(r["status"] == "REJECT" for r in reports): sys.exit(1)
    if any(r["status"] == "AMBIGUOUS" for r in reports): sys.exit(2)
    sys.exit(0)

if __name__ == "__main__": main()
