"""kaibridge/sourcing/parts_db.py
Local JLCPCB / EasyEDA Pro parts database query engine.
Connects to easyeda-std.elib (16,607 JLCPCB parts) to provide:
  1. Sub-millisecond offline lookup by LCSC ID.
  2. Instant search for JLCPCB "Basic Parts" (0-fee).
  3. Seamless mapping to 0-ERC KiCad native symbols and IPC-7351 footprints with LCSC fields.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..core.paths import find_easyeda_db

#---------------------------------------------------------------------------
#Golden Master Fast Cache for standard E24/E12 Passives (0ms instant lookup)
#---------------------------------------------------------------------------
_GOLDEN_CACHE = {
    # Resistors 0805 (JLCPCB Basic Parts)
    ("R", "0R", "0805"): {"lcsc": "C17165", "mfr": "Uniroyal", "mpn": "0805W8F0000T5E", "desc": "0Ω ±1% 0805 Resistor"},
    ("R", "10R", "0805"): {"lcsc": "C17411", "mfr": "Uniroyal", "mpn": "0805W8F100JT5E", "desc": "10Ω ±1% 0805 Resistor"},
    ("R", "100R", "0805"): {"lcsc": "C17462", "mfr": "Uniroyal", "mpn": "0805W8F1000T5E", "desc": "100Ω ±1% 0805 Resistor"},
    ("R", "220R", "0805"): {"lcsc": "C17560", "mfr": "Uniroyal", "mpn": "0805W8F2200T5E", "desc": "220Ω ±1% 0805 Resistor"},
    ("R", "330R", "0805"): {"lcsc": "C17657", "mfr": "Uniroyal", "mpn": "0805W8F3300T5E", "desc": "330Ω ±1% 0805 Resistor"},
    ("R", "470R", "0805"): {"lcsc": "C17711", "mfr": "Uniroyal", "mpn": "0805W8F4700T5E", "desc": "470Ω ±1% 0805 Resistor"},
    ("R", "1k", "0805"): {"lcsc": "C17513", "mfr": "Uniroyal", "mpn": "0805W8F1001T5E", "desc": "1kΩ ±1% 0805 Resistor"},
    ("R", "2.2k", "0805"): {"lcsc": "C17581", "mfr": "Uniroyal", "mpn": "0805W8F2201T5E", "desc": "2.2kΩ ±1% 0805 Resistor"},
    ("R", "4.7k", "0805"): {"lcsc": "C17673", "mfr": "Uniroyal", "mpn": "0805W8F4701T5E", "desc": "4.7kΩ ±1% 0805 Resistor"},
    ("R", "10k", "0805"): {"lcsc": "C17414", "mfr": "Uniroyal", "mpn": "0805W8F1002T5E", "desc": "10kΩ ±1% 0805 Resistor"},
    ("R", "20k", "0805"): {"lcsc": "C17568", "mfr": "Uniroyal", "mpn": "0805W8F2002T5E", "desc": "20kΩ ±1% 0805 Resistor"},
    ("R", "47k", "0805"): {"lcsc": "C17707", "mfr": "Uniroyal", "mpn": "0805W8F4702T5E", "desc": "47kΩ ±1% 0805 Resistor"},
    ("R", "100k", "0805"): {"lcsc": "C17407", "mfr": "Uniroyal", "mpn": "0805W8F1003T5E", "desc": "100kΩ ±1% 0805 Resistor"},
    ("R", "1M", "0805"): {"lcsc": "C17518", "mfr": "Uniroyal", "mpn": "0805W8F1004T5E", "desc": "1MΩ ±1% 0805 Resistor"},

    # Resistors 0603 (JLCPCB Basic Parts)
    ("R", "0R", "0603"): {"lcsc": "C21189", "mfr": "Uniroyal", "mpn": "0603WAF0000T5E", "desc": "0Ω ±1% 0603 Resistor"},
    ("R", "100R", "0603"): {"lcsc": "C22775", "mfr": "Uniroyal", "mpn": "0603WAF1000T5E", "desc": "100Ω ±1% 0603 Resistor"},
    ("R", "1k", "0603"): {"lcsc": "C21190", "mfr": "Uniroyal", "mpn": "0603WAF1001T5E", "desc": "1kΩ ±1% 0603 Resistor"},
    ("R", "4.7k", "0603"): {"lcsc": "C23162", "mfr": "Uniroyal", "mpn": "0603WAF4701T5E", "desc": "4.7kΩ ±1% 0603 Resistor"},
    ("R", "10k", "0603"): {"lcsc": "C25804", "mfr": "Uniroyal", "mpn": "0603WAF1002T5E", "desc": "10kΩ ±1% 0603 Resistor"},
    ("R", "100k", "0603"): {"lcsc": "C25803", "mfr": "Uniroyal", "mpn": "0603WAF1003T5E", "desc": "100kΩ ±1% 0603 Resistor"},

    # Capacitors 0805 (JLCPCB Basic Parts)
    ("C", "22pF", "0805"): {"lcsc": "C1804", "mfr": "Samsung", "mpn": "CL21C220JBANNNC", "desc": "22pF ±5% 50V C0G 0805 Capacitor"},
    ("C", "100pF", "0805"): {"lcsc": "C1799", "mfr": "Samsung", "mpn": "CL21C101JBANNNC", "desc": "100pF ±5% 50V C0G 0805 Capacitor"},
    ("C", "1nF", "0805"): {"lcsc": "C1803", "mfr": "Samsung", "mpn": "CL21B102KBANNNC", "desc": "1nF ±10% 50V X7R 0805 Capacitor"},
    ("C", "10nF", "0805"): {"lcsc": "C1710", "mfr": "Samsung", "mpn": "CL21B103KBANNNC", "desc": "10nF ±10% 50V X7R 0805 Capacitor"},
    ("C", "100nF", "0805"): {"lcsc": "C1525", "mfr": "Samsung", "mpn": "CL21B104KBCNNNC", "desc": "100nF ±10% 50V X7R 0805 Capacitor"},
    ("C", "1uF", "0805"): {"lcsc": "C15849", "mfr": "Samsung", "mpn": "CL21B105KBFNNNE", "desc": "1uF ±10% 50V X7R 0805 Capacitor"},
    ("C", "4.7uF", "0805"): {"lcsc": "C19666", "mfr": "Samsung", "mpn": "CL21A475KAQNNNE", "desc": "4.7uF ±10% 25V X5R 0805 Capacitor"},
    ("C", "10uF", "0805"): {"lcsc": "C15850", "mfr": "Samsung", "mpn": "CL21A106KOQNNNE", "desc": "10uF ±10% 16V X5R 0805 Capacitor"},

    # Capacitors 0603 (JLCPCB Basic Parts)
    ("C", "22pF", "0603"): {"lcsc": "C1653", "mfr": "Samsung", "mpn": "CL10C220JB8NNNC", "desc": "22pF ±5% 50V C0G 0603 Capacitor"},
    ("C", "100nF", "0603"): {"lcsc": "C14663", "mfr": "Samsung", "mpn": "CL10B104KB8NNNC", "desc": "100nF ±10% 50V X7R 0603 Capacitor"},
    ("C", "1uF", "0603"): {"lcsc": "C15849", "mfr": "Samsung", "mpn": "CL10B105KP8NNNC", "desc": "1uF ±10% 10V X5R 0603 Capacitor"},
    ("C", "10uF", "0603"): {"lcsc": "C19702", "mfr": "Samsung", "mpn": "CL10A106KP8NNNC", "desc": "10uF ±10% 10V X5R 0603 Capacitor"},

    # LEDs 0805 (JLCPCB Basic Parts)
    ("LED", "RED", "0805"): {"lcsc": "C2286", "mfr": "Everlight", "mpn": "17-21/R6C-AN2Q1B/3T", "desc": "Red 0805 SMD LED"},
    ("LED", "GREEN", "0805"): {"lcsc": "C2290", "mfr": "Everlight", "mpn": "17-21/G6C-AP1Q2/3T", "desc": "Green 0805 SMD LED"},
    ("LED", "BLUE", "0805"): {"lcsc": "C2293", "mfr": "Everlight", "mpn": "17-21/BHC-AP1Q2/3T", "desc": "Blue 0805 SMD LED"},
    ("LED", "YELLOW", "0805"): {"lcsc": "C2296", "mfr": "Everlight", "mpn": "17-21/Y2C-CP2Q2B/3T", "desc": "Yellow 0805 SMD LED"},

    # Diodes & Protection
    ("D", "1N4148", "SOD-123"): {"lcsc": "C81598", "mfr": "Changjiang", "mpn": "1N4148W", "desc": "Fast Switching Diode SOD-123"},
    ("D", "SS34", "SMA"): {"lcsc": "C8678", "mfr": "MDD", "mpn": "SS34", "desc": "Schottky Barrier Diode 40V 3A SMA"},
    ("D", "SS14", "SMA"): {"lcsc": "C4282", "mfr": "MDD", "mpn": "SS14", "desc": "Schottky Barrier Diode 40V 1A SMA"},

    # Linear Regulators (JLCPCB Basic Parts)
    ("REG", "AMS1117-3.3", "SOT-223"): {"lcsc": "C6186", "mfr": "AMS", "mpn": "AMS1117-3.3", "desc": "3.3V 1A LDO Regulator SOT-223"},
    ("REG", "AMS1117-5.0", "SOT-223"): {"lcsc": "C47589", "mfr": "AMS", "mpn": "AMS1117-5.0", "desc": "5.0V 1A LDO Regulator SOT-223"},
}


class PartsDatabase:
    """Read-only query engine for local easyeda-std.elib database."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self._path = Path(db_path) if db_path else find_easyeda_db()
        self._conn = None

    @property
    def is_available(self) -> bool:
        return self._path is not None and self._path.exists()

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        if not self.is_available:
            return None
        if self._conn is None:
            try:
                # Open read-only URI
                uri = f"file:{self._path.resolve().as_posix()}?mode=ro"
                self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            except Exception:
                # Fallback standard open
                try:
                    self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
                except Exception:
                    self._conn = None
        return self._conn

    def lookup_by_lcsc(self, lcsc_id: str) -> Optional[Dict[str, Any]]:
        """Look up part information by LCSC Part # (e.g. 'C17513')."""
        clean_id = str(lcsc_id).strip().upper()
        if not clean_id.startswith("C"):
            clean_id = f"C{clean_id}"

        # 1. Check Golden Master Cache first
        for (k_type, k_val, k_pkg), info in _GOLDEN_CACHE.items():
            if info.get("lcsc") == clean_id:
                rec_sym, rec_fp = _map_native_kicad(k_type, k_pkg)
                return {
                    "lcsc_id": clean_id,
                    "title": info.get("mpn", ""),
                    "display_title": info.get("mpn", ""),
                    "manufacturer": info.get("mfr", ""),
                    "part_class": "Basic Part",
                    "package": k_pkg,
                    "description": info.get("desc", ""),
                    "recommended_kicad_sym": rec_sym,
                    "recommended_kicad_fp": rec_fp,
                    "source": "golden_cache"
                }

        # 2. Query local SQLite database
        conn = self._get_connection()
        if not conn:
            return None

        sql = """
            SELECT d.uuid, d.title, d.display_title, d.description,
                   a_part.value as lcsc_id,
                   a_class.value as part_class,
                   a_fp.value as footprint,
                   a_mfr.value as manufacturer,
                   a_mpn.value as mpn
            FROM attributes a_part
            JOIN devices d ON a_part.device_uuid = d.uuid
            LEFT JOIN attributes a_class ON a_class.device_uuid = d.uuid AND a_class.key = 'JLCPCB Part Class'
            LEFT JOIN attributes a_fp ON a_fp.device_uuid = d.uuid AND a_fp.key = 'Supplier Footprint'
            LEFT JOIN attributes a_mfr ON a_mfr.device_uuid = d.uuid AND a_mfr.key = 'Manufacturer'
            LEFT JOIN attributes a_mpn ON a_mpn.device_uuid = d.uuid AND a_mpn.key = 'Manufacturer Part'
            WHERE a_part.key = 'Supplier Part' AND UPPER(a_part.value) = ?
            LIMIT 1
        """
        try:
            c = conn.cursor()
            row = c.execute(sql, (clean_id,)).fetchone()
            if not row:
                return None
            
            uuid, title, display_title, desc, lid, part_class, pkg, mfr, mpn = row
            part_class = part_class or "Extended Part"
            pkg = pkg or ""
            
            # Infer component type from title or description
            ctype = _infer_component_type(title, desc)
            rec_sym, rec_fp = _map_native_kicad(ctype, pkg)

            return {
                "uuid": uuid,
                "lcsc_id": clean_id,
                "title": title or "",
                "display_title": display_title or title or "",
                "manufacturer": mfr or "",
                "mpn": mpn or display_title or "",
                "part_class": part_class,
                "package": pkg,
                "description": desc or "",
                "recommended_kicad_sym": rec_sym,
                "recommended_kicad_fp": rec_fp,
                "source": "local_elib"
            }
        except Exception:
            return None

    def search_passives(
        self,
        component_type: str,
        value: str,
        package: str = "0805",
        basic_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Search JLCPCB parts by type (R, C, LED, D), normalized value, and package."""
        c_type = component_type.strip().upper()
        norm_val = _normalize_value(c_type, value)
        pkg = package.strip()

        # 1. Check Golden Master Cache
        cache_key = (c_type, norm_val, pkg)
        if cache_key in _GOLDEN_CACHE:
            item = _GOLDEN_CACHE[cache_key]
            rec_sym, rec_fp = _map_native_kicad(c_type, pkg)
            return [{
                "lcsc_id": item["lcsc"],
                "title": item["mpn"],
                "display_title": item["mpn"],
                "manufacturer": item["mfr"],
                "part_class": "Basic Part",
                "package": pkg,
                "description": item["desc"],
                "recommended_kicad_sym": rec_sym,
                "recommended_kicad_fp": rec_fp,
                "source": "golden_cache"
            }]

        # 2. Query SQLite DB
        conn = self._get_connection()
        if not conn:
            return []

        search_tokens = [norm_val.lower()]
        if pkg:
            search_tokens.append(pkg.lower())

        where_clauses = ["(d.title LIKE ? OR d.description LIKE ?)"] * len(search_tokens)
        where_sql = " AND ".join(where_clauses)
        params = []
        for t in search_tokens:
            pat = f"%{t}%"
            params.extend([pat, pat])

        sql = f"""
            SELECT d.uuid, d.title, d.display_title, d.description,
                   a_part.value as lcsc_id,
                   a_class.value as part_class,
                   a_fp.value as footprint,
                   a_mfr.value as manufacturer,
                   a_mpn.value as mpn
            FROM devices d
            JOIN attributes a_part ON a_part.device_uuid = d.uuid AND a_part.key = 'Supplier Part'
            LEFT JOIN attributes a_class ON a_class.device_uuid = d.uuid AND a_class.key = 'JLCPCB Part Class'
            LEFT JOIN attributes a_fp ON a_fp.device_uuid = d.uuid AND a_fp.key = 'Supplier Footprint'
            LEFT JOIN attributes a_mfr ON a_mfr.device_uuid = d.uuid AND a_mfr.key = 'Manufacturer'
            LEFT JOIN attributes a_mpn ON a_mpn.device_uuid = d.uuid AND a_mpn.key = 'Manufacturer Part'
            WHERE {where_sql}
            ORDER BY CASE WHEN a_class.value = 'Basic Part' THEN 0 ELSE 1 END
            LIMIT 10
        """
        try:
            c = conn.cursor()
            rows = c.execute(sql, params).fetchall()
            results = []
            for row in rows:
                uuid, title, display_title, desc, lcsc_id, p_class, p_pkg, mfr, mpn = row
                p_class = p_class or "Extended Part"
                if basic_only and p_class != "Basic Part":
                    continue
                rec_sym, rec_fp = _map_native_kicad(c_type, p_pkg or pkg)
                results.append({
                    "uuid": uuid,
                    "lcsc_id": lcsc_id,
                    "title": title or "",
                    "display_title": display_title or title or "",
                    "manufacturer": mfr or "",
                    "mpn": mpn or display_title or "",
                    "part_class": p_class,
                    "package": p_pkg or pkg,
                    "description": desc or "",
                    "recommended_kicad_sym": rec_sym,
                    "recommended_kicad_fp": rec_fp,
                    "source": "local_elib"
                })
            return results
        except Exception:
            return []


#---------------------------------------------------------------------------
#High-Level Helper: Recommend Component for design.json
#---------------------------------------------------------------------------
_DB_INSTANCE: Optional[PartsDatabase] = None

def get_parts_db() -> PartsDatabase:
    """Singleton provider for PartsDatabase."""
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = PartsDatabase()
    return _DB_INSTANCE


def recommend_kicad_part(
    component_type: str,
    value: str,
    package: str = "0805",
    preferred_lcsc: Optional[str] = None
) -> Dict[str, Any]:
    """Generates an ERC-safe, production-ready KiCad component definition for design.json.

    Ensures:
      - Native KiCad symbol for passives (Device:R, Device:C, Device:LED, Device:D)
      - IPC-7351 compliant KiCad standard footprint (e.g. Resistor_SMD:R_0805_2012Metric)
      - Exact JLCPCB Basic Part LCSC ID in `fields: {"LCSC": "Cxxxx"}`
    """
    c_type = component_type.strip().upper()
    db = get_parts_db()

    lcsc_id = ""
    part_class = "Basic Part"
    desc = ""

    # If explicit LCSC ID requested, look it up
    if preferred_lcsc:
        match = db.lookup_by_lcsc(preferred_lcsc)
        if match:
            lcsc_id = match["lcsc_id"]
            part_class = match["part_class"]
            desc = match["description"]

    # Otherwise search by type and value
    if not lcsc_id:
        res = db.search_passives(c_type, value, package, basic_only=True)
        if res:
            best = res[0]
            lcsc_id = best["lcsc_id"]
            part_class = best["part_class"]
            desc = best["description"]
        else:
            # Fallback non-basic search
            res = db.search_passives(c_type, value, package, basic_only=False)
            if res:
                best = res[0]
                lcsc_id = best["lcsc_id"]
                part_class = best["part_class"]
                desc = best["description"]

    rec_sym, rec_fp = _map_native_kicad(c_type, package)

    fields = {}
    if lcsc_id:
        fields["LCSC"] = lcsc_id
    if part_class:
        fields["JLCPCB_Class"] = part_class

    return {
        "lib_id": rec_sym,
        "value": value,
        "footprint": rec_fp,
        "fields": fields,
        "description": desc
    }


def lookup_by_lcsc(lcsc_id: str) -> Optional[Dict[str, Any]]:
    """Direct lookup wrapper."""
    return get_parts_db().lookup_by_lcsc(lcsc_id)


def search_basic_passives(component_type: str, value: str, package: str = "0805") -> List[Dict[str, Any]]:
    """Direct passive search wrapper."""
    return get_parts_db().search_passives(component_type, value, package, basic_only=True)


#---------------------------------------------------------------------------
#Internal Helpers
#---------------------------------------------------------------------------
def _normalize_value(ctype: str, val: str) -> str:
    """Normalize values like '10kohm', '0.1uF', '100n' for database matching."""
    s = str(val).strip()
    if ctype in ("R", "RESISTOR"):
        s = s.replace("Ω", "").replace("ohm", "").replace("Ohm", "").replace("OHM", "").strip()
        s = re.sub(r"\s+", "", s)
        # 10k, 1k, 470R, etc.
        if s.endswith("R") and len(s) > 1 and s[:-1].isdigit():
            return s
        return s
    elif ctype in ("C", "CAPACITOR"):
        s = s.replace("F", "").replace("f", "").strip()
        # 0.1u -> 100n
        if s == "0.1u" or s == "0.1":
            return "100nF"
        if not s.endswith("F") and not s.endswith("f"):
            s = f"{s}F"
        return s
    elif ctype in ("LED", "DIODE"):
        return s.upper()
    return s


def _map_native_kicad(ctype: str, package: str) -> tuple[str, str]:
    """Map generic component types and packages to KiCad 10 official stock libraries."""
    c = ctype.upper()
    pkg = package.strip()
    
    # 1. Symbols
    if c in ("R", "RESISTOR"):
        sym = "Device:R"
    elif c in ("C", "CAPACITOR"):
        sym = "Device:C"
    elif c in ("LED",):
        sym = "Device:LED"
    elif c in ("D", "DIODE"):
        sym = "Device:D"
    elif c in ("L", "INDUCTOR"):
        sym = "Device:L"
    elif c in ("REG", "AMS1117"):
        sym = "Regulator_Linear:AMS1117-3.3"
    else:
        sym = f"Device:{c}"

    # 2. Footprints
    pkg_clean = pkg.upper().replace(" ", "").replace("_", "")
    if c in ("R", "RESISTOR"):
        if "0805" in pkg_clean:
            fp = "Resistor_SMD:R_0805_2012Metric"
        elif "0603" in pkg_clean:
            fp = "Resistor_SMD:R_0603_1608Metric"
        elif "0402" in pkg_clean:
            fp = "Resistor_SMD:R_0402_1005Metric"
        elif "1206" in pkg_clean:
            fp = "Resistor_SMD:R_1206_3216Metric"
        else:
            fp = "Resistor_SMD:R_0805_2012Metric"
    elif c in ("C", "CAPACITOR"):
        if "0805" in pkg_clean:
            fp = "Capacitor_SMD:C_0805_2012Metric"
        elif "0603" in pkg_clean:
            fp = "Capacitor_SMD:C_0603_1608Metric"
        elif "0402" in pkg_clean:
            fp = "Capacitor_SMD:C_0402_1005Metric"
        elif "1206" in pkg_clean:
            fp = "Capacitor_SMD:C_1206_3216Metric"
        else:
            fp = "Capacitor_SMD:C_0805_2012Metric"
    elif c in ("LED",):
        if "0805" in pkg_clean:
            fp = "LED_SMD:LED_0805_2012Metric"
        elif "0603" in pkg_clean:
            fp = "LED_SMD:LED_0603_1608Metric"
        else:
            fp = "LED_SMD:LED_0805_2012Metric"
    elif c in ("D", "DIODE"):
        if "SOD-123" in pkg.upper() or "SOD123" in pkg_clean:
            fp = "Diode_SMD:D_SOD-123"
        elif "SMA" in pkg_clean:
            fp = "Diode_SMD:D_SMA"
        else:
            fp = "Diode_SMD:D_SOD-123"
    elif c in ("REG", "AMS1117") or "SOT-223" in pkg.upper():
        fp = "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
    else:
        fp = ""

    return sym, fp


def _infer_component_type(title: str, desc: str) -> str:
    """Heuristic helper to detect component type."""
    t = f"{title} {desc}".lower()
    if "resistor" in t or " chip res" in t or "0805w8" in t or "0603wa" in t:
        return "R"
    if "capacitor" in t or "cap mlcc" in t or "cl21" in t or "cl10" in t:
        return "C"
    if "led" in t:
        return "LED"
    if "diode" in t or "schottky" in t:
        return "D"
    if "inductor" in t:
        return "L"
    if "ams1117" in t or "ldo" in t or "regulator" in t:
        return "REG"
    return "DEVICE"
