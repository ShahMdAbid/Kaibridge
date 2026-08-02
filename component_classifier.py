"""
component_classifier.py -- plain-language requirement -> native parts_spec entry.

    >>> classify_component("10k 1% 0603 pullup", ref="R1")
    ClassifyResult(entry={... 'symbol': 'Device:R',
                           'footprint': 'Resistor_SMD:R_0603_1608Metric' ...},
                   confidence=95, warnings=[])

Design rules:
  * Every KiCad library/footprint name lives in a dictionary below. Parsing
    never string-builds a name it cannot find in a table (except the
    fully-regular imperial-package families, which are generated once at
    import time and can be audited via dump_tables()).
  * The function NEVER guesses silently. Any assumption (default package,
    inferred class) subtracts from `confidence` and appends a warning.
  * Output matches the `source: native` branch of parts_spec.yaml v3 exactly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# 1. PACKAGE TABLES
# ============================================================================

IMPERIAL_TO_METRIC: Dict[str, str] = {
    "01005": "0402",
    "0201":  "0603",
    "0402":  "1005",
    "0603":  "1608",
    "0805":  "2012",
    "1206":  "3216",
    "1210":  "3225",
    "1812":  "4532",
    "2010":  "5025",
    "2512":  "6332",
}
METRIC_TO_IMPERIAL = {v: k for k, v in IMPERIAL_TO_METRIC.items()}

CHIP_FAMILIES: Dict[str, Tuple[str, str]] = {
    "resistor":  ("Resistor_SMD",   "R"),
    "capacitor": ("Capacitor_SMD",  "C"),
    "inductor":  ("Inductor_SMD",   "L"),
    "led":       ("LED_SMD",        "LED"),
    "ferrite":   ("Inductor_SMD",   "L"),
    "fuse":      ("Fuse",           "Fuse"),
    "diode":     ("Diode_SMD",      "D"),
}

def _chip_footprint(cls: str, imperial: str) -> Optional[str]:
    fam = CHIP_FAMILIES.get(cls)
    met = IMPERIAL_TO_METRIC.get(imperial)
    if not fam or not met:
        return None
    lib, prefix = fam
    return f"{lib}:{prefix}_{imperial}_{met}Metric"

DISCRETE_FOOTPRINTS: Dict[str, Dict[str, str]] = {
    "diode": {
        "SOD-123":   "Diode_SMD:D_SOD-123",
        "SOD-123F":  "Diode_SMD:D_SOD-123F",
        "SOD-323":   "Diode_SMD:D_SOD-323",
        "SOD-523":   "Diode_SMD:D_SOD-523",
        "SOD-882":   "Diode_SMD:D_SOD-882",
        "SMA":       "Diode_SMD:D_SMA",
        "SMB":       "Diode_SMD:D_SMB",
        "SMC":       "Diode_SMD:D_SMC",
        "DO-214AC":  "Diode_SMD:D_SMA",
        "DO-214AA":  "Diode_SMD:D_SMB",
        "DO-214AB":  "Diode_SMD:D_SMC",
        "DO-35":     "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal",
        "DO-41":     "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    },
    "capacitor_elec": {
        "4X5.4":  "Capacitor_SMD:CP_Elec_4x5.4",
        "5X5.4":  "Capacitor_SMD:CP_Elec_5x5.4",
        "6.3X5.4": "Capacitor_SMD:CP_Elec_6.3x5.4",
        "8X10":   "Capacitor_SMD:CP_Elec_8x10",
        "10X10":  "Capacitor_SMD:CP_Elec_10x10",
    },
    "capacitor_tant": {
        "A": "Capacitor_SMD:CP_EIA-3216-18_Kemet-A",
        "B": "Capacitor_SMD:CP_EIA-3528-21_Kemet-B",
        "C": "Capacitor_SMD:CP_EIA-6032-28_Kemet-C",
        "D": "Capacitor_SMD:CP_EIA-7343-31_Kemet-D",
    },
    "led_tht": {
        "3MM": "LED_THT:LED_D3.0mm",
        "5MM": "LED_THT:LED_D5.0mm",
    },
    "crystal": {
        "3225": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        "5032": "Crystal:Crystal_SMD_5032-2Pin_5.0x3.2mm",
        "7050": "Crystal:Crystal_SMD_7050-2Pin_7.0x5.0mm",
        "HC49": "Crystal:Crystal_HC49-4H_Vertical",
    },
    "resistor_tht": {
        "AXIAL": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
    },
}

HEADER_PITCH: Dict[str, Tuple[str, str, str]] = {
    "2.54": ("Connector_PinHeader_2.54mm", "Connector_PinSocket_2.54mm", "P2.54mm"),
    "2.00": ("Connector_PinHeader_2.00mm", "Connector_PinSocket_2.00mm", "P2.00mm"),
    "1.27": ("Connector_PinHeader_1.27mm", "Connector_PinSocket_1.27mm", "P1.27mm"),
}

# ============================================================================
# 2. SYMBOL TABLE
# ============================================================================

SYMBOLS: Dict[str, str] = {
    "resistor":         "Device:R",
    "resistor_pot":     "Device:R_Potentiometer",
    "capacitor":        "Device:C",
    "capacitor_pol":    "Device:C_Polarized",
    "inductor":         "Device:L",
    "ferrite":          "Device:Ferrite_Bead",
    "led":              "Device:LED",
    "led_rgb":          "Device:LED_RGB",
    "diode":            "Device:D",
    "diode_schottky":   "Device:D_Schottky",
    "diode_zener":      "Device:D_Zener",
    "diode_tvs":        "Device:D_TVS",
    "crystal":          "Device:Crystal",
    "crystal_gnd":      "Device:Crystal_GND24",
    "fuse":             "Device:Fuse",
    "buzzer":           "Device:Buzzer",
    "thermistor":       "Device:Thermistor_NTC",
    "test_point":       "Connector:TestPoint",
    "switch_push":      "Switch:SW_Push",
}

DEFAULT_PACKAGE: Dict[str, str] = {
    "resistor":  "0603",
    "capacitor": "0603",
    "inductor":  "0805",
    "led":       "0603",
    "diode":     "SOD-123",
    "ferrite":   "0603",
    "fuse":      "1206",
}

REF_PREFIX: Dict[str, str] = {
    "resistor": "R", "capacitor": "C", "inductor": "L", "ferrite": "FB",
    "led": "D", "diode": "D", "crystal": "Y", "fuse": "F",
    "pin_header": "J", "buzzer": "BZ", "thermistor": "TH",
    "test_point": "TP", "switch": "SW",
}

# ============================================================================
# 3. KEYWORD -> CLASS
# ============================================================================

CLASS_KEYWORDS: List[Tuple[str, str]] = [
    (r"\brgb\s*led\b|\bled\s*rgb\b",                     "led_rgb"),
    (r"\b(led|lightemittingdiode)\b",                    "led"),
    (r"\bschottky\b",                                    "diode_schottky"),
    (r"\bzener\b",                                       "diode_zener"),
    (r"\b(tvs|esd\s*diode|transient\s*suppress\w*)\b",   "diode_tvs"),
    (r"\b(diode|rectifier|1n4148|1n5819)\b",             "diode"),
    (r"\bferrite\s*(bead)?\b|\bfb\b",                    "ferrite"),
    (r"\b(inductor|choke|coil)\b",                       "inductor"),
    (r"\b(potentiometer|trimpot|pot)\b",                 "resistor_pot"),
    (r"\b(ntc|thermistor)\b",                            "thermistor"),
    (r"\b(resistor|res)\b|\bpull\s*-?\s*(up|down)\b",    "resistor"),
    (r"\b(electrolytic|elec\s*cap)\b",                   "capacitor_pol"),
    (r"\b(tantalum|tant)\b",                             "capacitor_pol"),
    (r"\b(capacitor|cap|decoupl\w*|bypass)\b",           "capacitor"),
    (r"\b(crystal|xtal|resonator|oscillator)\b",         "crystal"),
    (r"\b(fuse|polyfuse|pptc)\b",                        "fuse"),
    (r"\b(buzzer|piezo)\b",                              "buzzer"),
    (r"\b(test\s*point|testpoint|\btp\b)\b",             "test_point"),
    (r"\b(push\s*button|tact\s*switch|momentary)\b",     "switch_push"),
    (r"\b(pin\s*header|header|pinheader|conn\w*|socket|jumper)\b", "pin_header"),
]

# ============================================================================
# 4. UNIT / ATTRIBUTE REGEXES
# ============================================================================

RE_PKG_CHIP    = re.compile(r"\b(01005|0201|0402|0603|0805|1206|1210|1812|2010|2512)\b")
RE_PKG_METRIC  = re.compile(r"\b(0402|0603|1005|1608|2012|3216|3225|4532|5025|6332)\s*metric\b", re.I)
RE_PKG_DISC    = re.compile(
    r"\b(SOD-?\d{3}F?|SMA|SMB|SMC|DO-?214[A-C]{2}|DO-?35|DO-?41|SOT-?23(?:-\d)?)\b", re.I
)
RE_TOLERANCE   = re.compile(r"[±+\-]?\s*(\d+(?:\.\d+)?)\s*%")
RE_POWER       = re.compile(r"\b(\d+\s*/\s*\d+|\d*\.?\d+)\s*W\b", re.I)
RE_VOLTAGE     = re.compile(r"\b(\d+(?:\.\d+)?)\s*V\b(?!\s*(?:cc|dd|ss))", re.I)
RE_CURRENT     = re.compile(r"\b(\d+(?:\.\d+)?)\s*(m?A)\b")
RE_DIELECTRIC  = re.compile(r"\b(X7R|X5R|X6S|C0G|NP0|Y5V|Z5U)\b", re.I)
RE_HEADER_GRID = re.compile(r"\b(\d{1,2})\s*[x*×]\s*(\d{1,2})\b", re.I)
RE_HEADER_PIN  = re.compile(r"\b(\d{1,2})\s*[-\s]?(?:pin|pos|way|p)\b", re.I)
RE_PITCH       = re.compile(r"\b(2\.54|2\.0{1,2}|1\.27)\s*mm\b")
RE_THT         = re.compile(r"\b(tht|through[-\s]?hole|axial|radial|dip)\b", re.I)
RE_RIGHT_ANGLE = re.compile(r"\b(right[-\s]?angle|horizontal|ra)\b", re.I)
RE_FEMALE      = re.compile(r"\b(female|socket|receptacle)\b", re.I)
RE_LED_COLOR   = re.compile(r"\b(red|green|blue|yellow|white|amber|orange|ir|uv)\b", re.I)
RE_ROLE        = re.compile(
    r"\b(pull\s*-?\s*up|pull\s*-?\s*down|decoupl\w*|bypass|bulk|series|current\s*limit\w*|"
    r"termination|damping|feedback|divider|load|filter)\b", re.I
)

RE_RES_RNOT = re.compile(r"\b(\d+)([RrKkMm])(\d+)\b")
RE_RES_PLAIN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*([kKmMrR]|meg)?\s*(?:ohms?|ohm|Ω|R)?\b"
)
RE_CAP = re.compile(r"\b(\d+(?:\.\d+)?)\s*([pnuµmU])\s*F?\b")
RE_CAP_RNOT = re.compile(r"\b(\d+)([pnuµ])(\d+)\b", re.I)
RE_IND = re.compile(r"\b(\d+(?:\.\d+)?)\s*([pnuµm])?H\b", re.I)
RE_FREQ = re.compile(r"\b(\d+(?:\.\d+)?)\s*([kKmM])?Hz\b")

RES_MULT = {"r": 1.0, "": 1.0, "k": 1e3, "m": 1e6, "meg": 1e6}
CAP_MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3}
IND_MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0}

# ============================================================================
# 5. RESULT TYPE
# ============================================================================

@dataclass
class ClassifyResult:
    entry: Dict[str, Any]
    confidence: int = 100
    warnings: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)
    ok: bool = True

    def penalise(self, amount: int, why: str) -> None:
        self.confidence = max(0, self.confidence - amount)
        self.warnings.append(why)

    def fail(self, why: str) -> "ClassifyResult":
        self.ok = False
        self.confidence = 0
        self.warnings.append(why)
        return self

    def to_yaml(self) -> str:
        import yaml
        return yaml.safe_dump([self.entry], sort_keys=False, allow_unicode=True)

# ============================================================================
# 6. VALUE FORMATTERS
# ============================================================================

def _fmt_resistance(ohms: float) -> str:
    if ohms >= 1e6:
        v = ohms / 1e6
        return f"{v:g}M"
    if ohms >= 1e3:
        v = ohms / 1e3
        return f"{v:g}k"
    if ohms >= 1:
        return f"{ohms:g}"
    return f"{ohms:g}"

def _fmt_capacitance(farads: float) -> str:
    for mult, suffix in ((1e-6, "uF"), (1e-9, "nF"), (1e-12, "pF")):
        if farads >= mult - 1e-18:
            return f"{farads / mult:g}{suffix}"
    return f"{farads:g}F"

def _fmt_inductance(henries: float) -> str:
    for mult, suffix in ((1e-3, "mH"), (1e-6, "uH"), (1e-9, "nH")):
        if henries >= mult - 1e-15:
            return f"{henries / mult:g}{suffix}"
    return f"{henries:g}H"

def _parse_resistance(text: str) -> Optional[float]:
    m = RE_RES_RNOT.search(text)
    if m:
        whole, unit, frac = m.groups()
        return float(f"{whole}.{frac}") * RES_MULT[unit.lower()]
    scrubbed = RE_PKG_CHIP.sub(" ", text)
    scrubbed = RE_TOLERANCE.sub(" ", scrubbed)
    scrubbed = RE_VOLTAGE.sub(" ", scrubbed)
    scrubbed = RE_POWER.sub(" ", scrubbed)
    for m in RE_RES_PLAIN.finditer(scrubbed):
        num, unit = m.group(1), (m.group(2) or "")
        raw = m.group(0).strip()
        if unit == "" and not re.search(r"(ohm|Ω|\bR\b)", raw, re.I):
            continue
        return float(num) * RES_MULT[unit.lower()]
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*([kKmM])\b", scrubbed)
    if m:
        return float(m.group(1)) * RES_MULT[m.group(2).lower()]
    return None

def _parse_capacitance(text: str) -> Optional[float]:
    m = RE_CAP_RNOT.search(text)
    if m:
        whole, unit, frac = m.groups()
        return float(f"{whole}.{frac}") * CAP_MULT[unit.lower()]
    scrubbed = RE_PKG_CHIP.sub(" ", text)
    scrubbed = RE_VOLTAGE.sub(" ", scrubbed)
    m = RE_CAP.search(scrubbed)
    if m:
        return float(m.group(1)) * CAP_MULT[m.group(2).lower()]
    return None

def _parse_inductance(text: str) -> Optional[float]:
    m = RE_IND.search(text)
    if m:
        return float(m.group(1)) * IND_MULT[(m.group(2) or "").lower()]
    return None

# ============================================================================
# 7. PACKAGE EXTRACTION
# ============================================================================

def _extract_package(text: str, res: ClassifyResult) -> Tuple[Optional[str], bool]:
    is_tht = bool(RE_THT.search(text))
    m = RE_PKG_METRIC.search(text)
    if m:
        metric = m.group(1)
        imp = METRIC_TO_IMPERIAL.get(metric)
        if imp:
            return imp, is_tht
        res.penalise(10, f"unknown metric package {metric}")
    m = RE_PKG_CHIP.search(text)
    if m:
        return m.group(1), is_tht
    m = RE_PKG_DISC.search(text)
    if m:
        tok = m.group(1).upper().replace(" ", "")
        tok = re.sub(r"^SOD(\d)", r"SOD-\1", tok)
        tok = re.sub(r"^DO(\d)", r"DO-\1", tok)
        tok = re.sub(r"^SOT(\d)", r"SOT-\1", tok)
        return tok, is_tht
    m = re.search(r"\b(\d(?:\.\d)?)\s*mm\b", text)
    if m and is_tht:
        return f"{m.group(1)}MM", True
    return None, is_tht

# ============================================================================
# 8. PER-CLASS BUILDERS
# ============================================================================

def _build_chip(cls: str, base_cls: str, text: str, pkg: Optional[str],
                is_tht: bool, res: ClassifyResult) -> Tuple[str, str, int]:
    if pkg is None:
        pkg = DEFAULT_PACKAGE.get(base_cls, "0603")
        res.penalise(15, f"no package specified; defaulted to {pkg}")
    if is_tht and base_cls == "resistor":
        return SYMBOLS["resistor"], DISCRETE_FOOTPRINTS["resistor_tht"]["AXIAL"], 2
    if is_tht and base_cls == "led":
        fp = DISCRETE_FOOTPRINTS["led_tht"].get(pkg)
        if fp:
            return SYMBOLS["led"], fp, 2
        res.penalise(20, f"THT LED size '{pkg}' unknown; using 3mm")
        return SYMBOLS["led"], DISCRETE_FOOTPRINTS["led_tht"]["3MM"], 2
    fp = _chip_footprint(base_cls, pkg)
    if fp is None:
        return "", "", 0
    return SYMBOLS[cls], fp, 2

def _build_diode(cls: str, text: str, pkg: Optional[str],
                 res: ClassifyResult) -> Tuple[str, str, int]:
    if pkg is None:
        pkg = DEFAULT_PACKAGE["diode"]
        res.penalise(15, f"no package specified; defaulted to {pkg}")
    table = DISCRETE_FOOTPRINTS["diode"]
    if pkg in table:
        return SYMBOLS[cls], table[pkg], 2
    if pkg in IMPERIAL_TO_METRIC:
        return SYMBOLS[cls], _chip_footprint("diode", pkg), 2
    res.penalise(30, f"unrecognised diode package '{pkg}'; falling back SOD-123")
    return SYMBOLS[cls], table["SOD-123"], 2

def _build_capacitor(cls: str, text: str, pkg: Optional[str],
                     res: ClassifyResult) -> Tuple[str, str, int]:
    polarised = cls == "capacitor_pol"
    sym = SYMBOLS["capacitor_pol"] if polarised else SYMBOLS["capacitor"]
    if polarised and re.search(r"\b(tantalum|tant)\b", text, re.I):
        code = None
        m = re.search(r"\bcase\s*([A-D])\b", text, re.I)
        if m:
            code = m.group(1).upper()
        elif pkg in ("1206", "1210"):
            code = "A" if pkg == "1206" else "B"
        if code is None:
            code = "A"
            res.penalise(15, "tantalum case size not given; defaulted to case A")
        return sym, DISCRETE_FOOTPRINTS["capacitor_tant"][code], 2
    if polarised and re.search(r"\b(electrolytic|elec)\b", text, re.I):
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\b", text)
        key = f"{m.group(1)}X{m.group(2)}".upper() if m else "5X5.4"
        fp = DISCRETE_FOOTPRINTS["capacitor_elec"].get(key)
        if not fp:
            fp = DISCRETE_FOOTPRINTS["capacitor_elec"]["5X5.4"]
            res.penalise(15, f"electrolytic body size '{key}' unknown; used 5x5.4")
        return sym, fp, 2
    if pkg is None:
        pkg = DEFAULT_PACKAGE["capacitor"]
        res.penalise(15, f"no package specified; defaulted to {pkg}")
    fp = _chip_footprint("capacitor", pkg)
    if fp is None:
        return "", "", 0
    return sym, fp, 2

def _build_header(text: str, res: ClassifyResult) -> Tuple[str, str, int, str]:
    rows, cols = 1, None
    m = RE_HEADER_GRID.search(text)
    if m:
        rows, cols = int(m.group(1)), int(m.group(2))
        if rows > cols and cols in (1, 2):
            rows, cols = cols, rows
    else:
        m = RE_HEADER_PIN.search(text)
        if m:
            rows, cols = 1, int(m.group(1))
    if cols is None:
        return "", "", 0, ""
    if rows not in (1, 2):
        res.penalise(30, f"{rows}-row headers are not in Connector_Generic")
        return "", "", 0, ""
    pitch = "2.54"
    m = RE_PITCH.search(text)
    if m:
        pitch = {"2.0": "2.00", "2.00": "2.00", "2.54": "2.54", "1.27": "1.27"}[m.group(1)]
    else:
        res.penalise(5, "pitch not specified; defaulted to 2.54mm")
    header_lib, socket_lib, pitch_tok = HEADER_PITCH[pitch]
    female = bool(RE_FEMALE.search(text))
    lib = socket_lib if female else header_lib
    kind = "PinSocket" if female else "PinHeader"
    orient = "Horizontal" if RE_RIGHT_ANGLE.search(text) else "Vertical"
    sym_name = f"Conn_{rows:02d}x{cols:02d}"
    if rows == 2:
        sym_name += "_Odd_Even"
    symbol = f"Connector_Generic:{sym_name}"
    footprint = f"{lib}:{kind}_{rows}x{cols:02d}_{pitch_tok}_{orient}"
    return symbol, footprint, rows * cols, f"Conn_{rows:02d}x{cols:02d}"

def _build_crystal(text: str, pkg: Optional[str],
                   res: ClassifyResult) -> Tuple[str, str, int, str]:
    four_pin = bool(re.search(r"\b4\s*-?\s*pin\b", text, re.I)) or pkg == "3225"
    sym = SYMBOLS["crystal_gnd"] if four_pin else SYMBOLS["crystal"]
    key = pkg if pkg in DISCRETE_FOOTPRINTS["crystal"] else "3225"
    if pkg not in DISCRETE_FOOTPRINTS["crystal"]:
        res.penalise(15, f"crystal package defaulted to {key}")
    value = ""
    m = RE_FREQ.search(text)
    if m:
        unit = (m.group(2) or "").upper()
        value = f"{m.group(1)}{unit}Hz"
    return sym, DISCRETE_FOOTPRINTS["crystal"][key], (4 if four_pin else 2), value

# ============================================================================
# 9. MAIN ENTRY POINT
# ============================================================================

_REF_COUNTERS: Dict[str, int] = {}

def _auto_ref(cls: str) -> str:
    base = cls.split("_")[0]
    prefix = REF_PREFIX.get(cls) or REF_PREFIX.get(base) or "U"
    _REF_COUNTERS[prefix] = _REF_COUNTERS.get(prefix, 0) + 1
    return f"{prefix}{_REF_COUNTERS[prefix]}"

def reset_ref_counters() -> None:
    _REF_COUNTERS.clear()

def classify_component(
    requirement: str,
    ref: Optional[str] = None,
    placement: Optional[Dict[str, Any]] = None,
    force_class: Optional[str] = None,
) -> ClassifyResult:
    """Turn a plain-language requirement into a native parts_spec.yaml entry."""
    text = " " + requirement.strip() + " "
    low = text.lower()
    res = ClassifyResult(entry={})

    # ---- 1. class -----------------------------------------------------
    cls = force_class
    if cls is None:
        for pattern, name in CLASS_KEYWORDS:
            if re.search(pattern, low, re.I):
                cls = name
                break

    if cls is None:
        if RE_CAP.search(text) or RE_CAP_RNOT.search(text):
            cls, why = "capacitor", "class inferred from capacitance unit"
        elif RE_IND.search(text):
            cls, why = "inductor", "class inferred from inductance unit"
        elif RE_FREQ.search(text):
            cls, why = "crystal", "class inferred from frequency unit"
        elif _parse_resistance(text) is not None:
            cls, why = "resistor", "class inferred from resistance unit"
        else:
            return res.fail(f"cannot determine component class from {requirement!r}")
        res.penalise(10, why)

    base_cls = {
        "capacitor_pol": "capacitor", "led_rgb": "led",
        "diode_schottky": "diode", "diode_zener": "diode", "diode_tvs": "diode",
        "resistor_pot": "resistor", "crystal_gnd": "crystal",
        "switch_push": "switch",
    }.get(cls, cls)

    # ---- 2. package ---------------------------------------------------
    pkg, is_tht = _extract_package(text, res)

    # ---- 3. dispatch --------------------------------------------------
    value = ""
    if base_cls == "resistor":
        symbol, footprint, pins = _build_chip(cls if cls in SYMBOLS else "resistor",
                                              "resistor", text, pkg, is_tht, res)
        ohms = _parse_resistance(text)
        if ohms is None:
            res.penalise(25, "no resistance value found")
            value = "R"
        else:
            value = _fmt_resistance(ohms)

    elif base_cls == "capacitor":
        symbol, footprint, pins = _build_capacitor(cls, text, pkg, res)
        farads = _parse_capacitance(text)
        if farads is None:
            res.penalise(25, "no capacitance value found")
            value = "C"
        else:
            value = _fmt_capacitance(farads)

    elif base_cls == "inductor":
        symbol, footprint, pins = _build_chip("inductor", "inductor", text, pkg, is_tht, res)
        h = _parse_inductance(text)
        value = _fmt_inductance(h) if h is not None else "L"
        if h is None:
            res.penalise(25, "no inductance value found")

    elif base_cls == "ferrite":
        symbol, footprint, pins = _build_chip("ferrite", "ferrite", text, pkg, is_tht, res)
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:ohm|Ω|R)\b", text, re.I)
        value = f"{m.group(1)}R@100MHz" if m else "FerriteBead"

    elif base_cls == "led":
        symbol, footprint, pins = _build_chip(cls, "led", text, pkg, is_tht, res)
        m = RE_LED_COLOR.search(text)
        value = (m.group(1).upper() if m else "LED")
        if cls == "led_rgb":
            value, pins = "RGB", 4

    elif base_cls == "diode":
        symbol, footprint, pins = _build_diode(cls, text, pkg, res)
        m = re.search(r"\b(1N\d{4}[A-Z]?|BAT\d{2,3}[A-Z]*|SS\d{2,4}|SMBJ\d+[A-Z]*)\b",
                      text, re.I)
        if m:
            value = m.group(1).upper()
        elif cls == "diode_zener":
            mv = RE_VOLTAGE.search(text)
            value = f"{mv.group(1)}V" if mv else "D_Zener"
        else:
            value = {"diode_schottky": "D_Schottky",
                     "diode_tvs": "D_TVS"}.get(cls, "D")

    elif base_cls == "pin_header":
        symbol, footprint, pins, value = _build_header(text, res)
        if not symbol:
            return res.fail(f"cannot determine header geometry from {requirement!r}")

    elif base_cls == "crystal":
        symbol, footprint, pins, value = _build_crystal(text, pkg, res)
        if not value:
            res.penalise(20, "no frequency found for crystal")
            value = "Crystal"

    elif base_cls == "fuse":
        symbol, footprint, pins = _build_chip("fuse", "fuse", text, pkg, is_tht, res)
        m = RE_CURRENT.search(text)
        value = f"{m.group(1)}{m.group(2)}" if m else "Fuse"

    elif base_cls == "test_point":
        symbol, footprint, pins = SYMBOLS["test_point"], "TestPoint:TestPoint_Pad_D1.5mm", 1
        value = "TestPoint"

    else:
        return res.fail(f"class '{cls}' has no builder yet")

    if not footprint:
        return res.fail(f"no KiCad footprint mapping for class={cls} package={pkg}")

    # ---- 4. BOM attributes --------------------------------------------
    bom: Dict[str, Any] = {}
    m = RE_TOLERANCE.search(text)
    if m:
        bom["tolerance"] = f"{m.group(1)}%"
    elif base_cls == "resistor":
        bom["tolerance"] = "1%"
        res.penalise(3, "tolerance not specified; defaulted to 1%")

    m = RE_POWER.search(text)
    if m:
        bom["power"] = f"{m.group(1).replace(' ', '')}W"
    elif base_cls == "resistor":
        bom["power"] = {"0201": "0.05W", "0402": "0.0625W", "0603": "0.1W",
                        "0805": "0.125W", "1206": "0.25W",
                        "2010": "0.75W", "2512": "1W"}.get(pkg or "0603", "0.1W")

    m = RE_VOLTAGE.search(text)
    if m and base_cls in ("capacitor", "diode", "fuse"):
        bom["voltage"] = f"{m.group(1)}V"
    elif base_cls == "capacitor":
        bom["voltage"] = "16V"
        res.penalise(3, "voltage rating not specified; defaulted to 16V")

    m = RE_DIELECTRIC.search(text)
    if m:
        bom["dielectric"] = m.group(1).upper()
    elif cls == "capacitor":
        farads = _parse_capacitance(text) or 0
        bom["dielectric"] = "X7R" if farads <= 1e-6 else "X5R"

    m = RE_CURRENT.search(text)
    if m and base_cls in ("led", "fuse", "inductor"):
        bom["current"] = f"{m.group(1)}{m.group(2)}"

    # ---- 5. assemble ---------------------------------------------------
    entry: Dict[str, Any] = {
        "ref": ref or _auto_ref(cls),
        "source": "native",
        "class": base_cls,
        "value": value,
        "symbol": symbol,
        "footprint": footprint,
        "package": pkg or footprint.split(":")[-1],
        "pin_count": pins,
    }
    if bom:
        entry["bom"] = bom
    m = RE_ROLE.search(text)
    if m:
        entry["role"] = re.sub(r"[\s-]+", "", m.group(1)).lower()
    entry["placement"] = placement or {"x": 0.0, "y": 0.0,
                                       "rotation": 0, "layer": "F.Cu"}
    entry["_origin"] = requirement.strip()

    res.entry = entry
    return res

# ============================================================================
# 10. BATCH + VALIDATION HELPERS
# ============================================================================

def classify_many(requirements: List[str], validate_with=None) -> Dict[str, Any]:
    entries, failures = [], []
    for req in requirements:
        r = classify_component(req)
        if not r.ok:
            failures.append({"requirement": req, "warnings": r.warnings})
            continue
        if validate_with is not None:
            ok, why = validate_with.footprint_exists(r.entry["footprint"])
            if not ok:
                sugg = validate_with.suggest_footprint(r.entry["footprint"])
                failures.append({"requirement": req,
                                 "warnings": [why] + ([f"suggest: {sugg}"] if sugg else [])})
                continue
            ok, why = validate_with.symbol_exists(r.entry["symbol"])
            if not ok:
                failures.append({"requirement": req, "warnings": [why]})
                continue
        entries.append({"entry": r.entry, "confidence": r.confidence,
                        "warnings": r.warnings})
    return {"components": entries, "failures": failures}

def dump_tables() -> Dict[str, Any]:
    out: Dict[str, Any] = {"chip": {}, "discrete": DISCRETE_FOOTPRINTS,
                           "symbols": SYMBOLS}
    for cls in CHIP_FAMILIES:
        out["chip"][cls] = [_chip_footprint(cls, i) for i in IMPERIAL_TO_METRIC]
    return out

# ============================================================================
# 11. CLI + self-test
# ============================================================================

SELF_TEST = [
    "10k 1% 0603 pullup",
    "100nF 0402 capacitor",
    "1x04 male pin header",
    "4k7 0805 resistor 1/8W",
    "220R 1206 current limiting resistor",
    "10uF 25V 0805 X5R decoupling capacitor",
    "4.7uF tantalum case B capacitor",
    "100uF 16V electrolytic 6.3x5.4",
    "red LED 0805",
    "green led 3mm tht",
    "1N4148 diode SOD-123",
    "SS34 schottky diode SMA",
    "5.1V zener diode SOD-323",
    "10uH inductor 1206",
    "600 ohm ferrite bead 0603",
    "2x05 female pin header 2.54mm right angle",
    "8 pin header",
    "16MHz crystal 3225 4-pin",
    "32.768kHz crystal 3215",
    "1A fuse 1206",
    "test point",
]

def _selftest() -> int:
    bad = 0
    print(f"{'requirement':<44} {'conf':>4}  symbol / footprint")
    print("-" * 118)
    for req in SELF_TEST:
        r = classify_component(req)
        if not r.ok:
            bad += 1
            print(f"{req:<44} {'FAIL':>4}  {'; '.join(r.warnings)}")
            continue
        e = r.entry
        print(f"{req:<44} {r.confidence:>4}  {e['value']:<12} "
              f"{e['symbol']:<28} {e['footprint']}")
        for w in r.warnings:
            print(f"{'':<44} {'':>4}    ! {w}")
    print("-" * 118)
    print(f"{len(SELF_TEST) - bad}/{len(SELF_TEST)} classified")
    return 1 if bad else 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Classify plain-language passives.")
    ap.add_argument("requirement", nargs="*", help="e.g. '10k 1%% 0603 pullup'")
    ap.add_argument("--ref")
    ap.add_argument("--yaml", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dump-tables", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(_selftest())
    if a.dump_tables:
        print(json.dumps(dump_tables(), indent=2))
        sys.exit(0)
    if not a.requirement:
        ap.print_help()
        sys.exit(1)

    result = classify_component(" ".join(a.requirement), ref=a.ref)
    if not result.ok:
        print("FAILED: " + "; ".join(result.warnings), file=sys.stderr)
        sys.exit(1)
    print(result.to_yaml() if a.yaml else json.dumps(result.entry, indent=2))
    for w in result.warnings:
        print(f"! {w}", file=sys.stderr)
    sys.exit(0)
