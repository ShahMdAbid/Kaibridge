"""
Kaibridge Live SWIG API & Architecture Oracle (oracle.py):
Reflection, static inspection, and architectural constraint engine for KiCad pcbnew SWIG bindings.
Provides zero-hallucination ground-truth API method signatures, argument types,
class constructor inspection, module constants, and production rules directly from host pcbnew.
"""
from __future__ import annotations

import os
import sys
import re
import difflib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

_PCBNEW_CACHE: Optional[str] = None
_PCBNEW_SOURCE_PATH: Optional[Path] = None

#Ground-truth architectural knowledge base for Kaibridge / KiCad 10 / JLCPCB production
_RULES_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "drc_rules": {
        "topic": "JLCPCB Production DRC Rules & Constraints",
        "description": "Standard JLCPCB manufacturing capabilities to embed in .kicad_pro design_settings.rules",
        "values": {
            "min_copper_edge_clearance": "0.15mm (prevents false DRC errors on USB-C & edge connectors; default KiCad 0.50mm is too strict)",
            "min_clearance": "0.15mm (6 mil standard)",
            "min_track_width": "0.15mm (6 mil standard)",
            "min_hole_clearance": "0.25mm",
            "min_hole_to_hole": "0.25mm",
            "min_via_diameter": "0.5mm",
            "min_via_drill": "0.3mm",
            "min_through_hole_clearance": "0.2mm",
            "min_text_height": "0.8mm",
            "min_text_thickness": "0.08mm"
        },
        "kicad_pro_snippet": {
            "board": {
                "design_settings": {
                    "rules": {
                        "min_clearance": 0.15,
                        "min_track_width": 0.15,
                        "min_copper_edge_clearance": 0.15,
                        "min_hole_clearance": 0.25,
                        "min_hole_to_hole": 0.25,
                        "min_via_diameter": 0.5
                    }
                }
            }
        }
    },
    "swig_memory": {
        "topic": "KiCad pcbnew SWIG Memory Lifecycle & Safety",
        "description": "Rules to avoid SwigPyObject pointer invalidation and memory leaks in Python",
        "rules": [
            "1. Always run gc.collect() before and after calling pcbnew.LoadBoard().",
            "2. Always explicitly delete the board variable (del board) at the end of functions to release C++ pointers.",
            "3. Never keep a module-level or global board reference across multiple tool calls or operations.",
            "4. Verify hasattr(board, 'GetFootprints') before accessing board attributes.",
            "5. For heavy batch operations, run them in an isolated subprocess via load_kicad_python() to ensure clean OS process teardown."
        ],
        "example_pattern": "import gc, pcbnew\ngc.collect()\nboard = pcbnew.LoadBoard(pcb_path)\ntry:\n    # operations\n    pcbnew.SaveBoard(pcb_path, board)\nfinally:\n    del board\n    gc.collect()"
    },
    "zone_filling": {
        "topic": "Ground Plane Pouring & Post-Routing Refill Protocol",
        "description": "Mandatory steps for DRC-clean copper zones in KiCad 10",
        "rules": [
            "1. Exact Outline: Use zone.SetOutline(poly) where poly is obtained from board.GetBoardPolygonOutlines(poly, True) to avoid edge overflow.",
            "2. Thermal Connections: Use zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL) for solid connections to prevent starved_thermal DRC errors.",
            "3. Mandatory Refill: Immediately after importing tracks from Freerouting (SES), MUST instantiate pcbnew.ZONE_FILLER(board) and call filler.Fill(board.Zones()).",
            "4. Connectivity: Always call board.BuildListOfNets() and board.BuildConnectivity() after zone operations."
        ]
    },
    "power_flags": {
        "topic": "Power Flags & Switched Rail ERC Rules",
        "description": "Prevention of [pin_not_driven] ERC errors on power ingest and switched nets",
        "rules": [
            "1. KiCad ERC requires every power net connected to a power_in pin to have a power driver (power_out pin or PWR_FLAG).",
            "2. Switched rails (e.g. VBUS_SW after a switch, VIN after a series diode) have NO power_out pin because switches/diodes are passive.",
            "3. In design.json, declare all such nets in 'power_flags': ['VBUS', 'VBUS_SW', 'VIN', 'GND'].",
            "4. Never put power_flags on actively driven regulator output pins (e.g. AMS1117 VOUT) to avoid pin_to_pin collision errors."
        ]
    }
}


def find_pcbnew_source() -> Optional[Path]:
    """Locates the live pcbnew.py file installed on the host machine."""
    global _PCBNEW_SOURCE_PATH
    if _PCBNEW_SOURCE_PATH and _PCBNEW_SOURCE_PATH.is_file():
        return _PCBNEW_SOURCE_PATH

    # 1. Try active imported pcbnew module
    try:
        import pcbnew
        mod_file = getattr(pcbnew, "__file__", None)
        if mod_file:
            p = Path(mod_file)
            if p.suffix in (".pyc", ".pyo"):
                p = p.with_suffix(".py")
            if p.is_file():
                _PCBNEW_SOURCE_PATH = p
                return p
    except Exception:
        pass

    # 2. Try standard KiCad 10 / 9 / 8 Windows paths
    candidates = [
        Path(r"C:\Program Files\KiCad\10.0\bin\Lib\site-packages\pcbnew.py"),
        Path(r"C:\Program Files\KiCad\9.0\bin\Lib\site-packages\pcbnew.py"),
        Path(r"C:\Program Files\KiCad\8.0\bin\Lib\site-packages\pcbnew.py"),
        Path(r"C:\Program Files\KiCad\10.0\lib\python3\dist-packages\pcbnew.py"),
        Path(r"C:\Program Files\KiCad\10.0\bin\pcbnew.py"),
    ]
    for cand in candidates:
        if cand.is_file():
            _PCBNEW_SOURCE_PATH = cand
            return cand

    return None


def _load_pcbnew_content() -> str:
    """Loads and caches the contents of pcbnew.py."""
    global _PCBNEW_CACHE
    if _PCBNEW_CACHE is not None:
        return _PCBNEW_CACHE

    src = find_pcbnew_source()
    if not src or not src.is_file():
        return ""

    try:
        _PCBNEW_CACHE = src.read_text(encoding="utf-8", errors="replace")
    except Exception:
        _PCBNEW_CACHE = ""
    return _PCBNEW_CACHE


def _extract_docstring(method_body: str) -> str:
    """Extracts def line, signature, and attached docstrings/aliases from a method block."""
    doc_match = re.search(
        r"^[ \t]*def[^\n]+:\s*r?(?:\"\"\"|\'\'\')[\s\S]*?(?:\"\"\"|\'\'\')",
        method_body,
        re.MULTILINE
    )
    if doc_match:
        return doc_match.group(0).strip()

    lines = method_body.strip().splitlines()
    if len(lines) > 2:
        return "\n".join(lines[:3]).strip()
    return lines[0].strip() if lines else ""


def _find_similar_names(all_names: List[str], query: str, limit: int = 6) -> List[str]:
    """Finds fuzzy suggestions for misspelled or partially matched names."""
    q_lower = query.lower()
    exact_substr = [n for n in all_names if q_lower in n.lower()]
    if exact_substr:
        return sorted(exact_substr, key=len)[:limit]
    
    close = difflib.get_close_matches(query, all_names, n=limit, cutoff=0.45)
    return close


def query_oracle(query: str, class_name: Optional[str] = None) -> Dict[str, Any]:
    """Queries the KiCad pcbnew SWIG oracle for exact signatures, docstrings, classes, constants, and rules.
    
    Args:
        query: Method name, class name, constant name, or rule topic.
               Examples: 'ExportSpecctraDSN', 'ZONE_FILLER', 'ZONE_CONNECTION_FULL', 'drc_rules', 'swig_memory'.
        class_name: Optional class name (e.g. 'BOARD', 'ZONE', 'FOOTPRINT', 'GLOBAL').
    """
    q_clean = query.strip()
    c_clean = class_name.strip() if class_name else None

    # 1. Architectural & Production Rules Knowledge Base Match
    q_rule_key = q_clean.lower().replace("-", "_").replace(" ", "_")
    for key, data in _RULES_KNOWLEDGE_BASE.items():
        if key == q_rule_key or key in q_rule_key or q_rule_key in key:
            return {
                "success": True,
                "type": "RULE",
                "topic": data.get("topic"),
                "description": data.get("description"),
                "details": data
            }

    content = _load_pcbnew_content()
    if not content:
        return {
            "success": False,
            "error": "pcbnew.py source file could not be located on host system.",
            "source_path": None
        }

    # Collect top-level functions and classes
    global_func_names = list(set(re.findall(r"\ndef\s+([A-Za-z0-9_]+)\s*\(", content)))
    class_names = list(set(re.findall(r"\nclass\s+([A-Za-z0-9_]+)\b", content)))

    # 2. Class Query (when query matches a class name or class_name is requested without method)
    if (q_clean in class_names and not c_clean) or (c_clean and q_clean.lower() in ("class", "overview", "__init__", "")):
        target_cls = c_clean if c_clean else q_clean
        cls_pat = rf"\nclass\s+{re.escape(target_cls)}\b(?:\(([^)]+)\))?:([\s\S]*?)(?=\nclass |\Z)"
        cls_match = re.search(cls_pat, content)
        if cls_match:
            parents = cls_match.group(1) or "object"
            body = cls_match.group(2)
            
            # Extract class docstring
            doc_m = re.search(r"^[ \t]*r?(?:\"\"\"|\'\'\')([\s\S]*?)(?:\"\"\"|\'\'\')", body.strip(), re.MULTILINE)
            class_doc = doc_m.group(1).strip() if doc_m else f"Proxy of C++ {target_cls} class."
            
            # Extract __init__ constructor
            init_m = re.search(r"\n[ \t]+def\s+__init__\s*\([\s\S]*?(?=(?:\n[ \t]+def |\Z))", body)
            ctor_sig = _extract_docstring(init_m.group(0)) if init_m else f"def __init__(self, *args):"
            
            # Extract public methods
            methods = sorted(set(m for m in re.findall(r"\n[ \t]+def\s+([A-Za-z0-9_]+)\s*\(", body) if not m.startswith("_")))
            
            return {
                "success": True,
                "type": "CLASS",
                "class": target_cls,
                "parents": parents.strip(),
                "constructor": ctor_sig,
                "docstring": class_doc,
                "methods_count": len(methods),
                "methods": methods[:50],
                "source_path": str(_PCBNEW_SOURCE_PATH)
            }

    # 3. Constant or Enum Query
    const_pat = rf"(?:^|\n)[ \t]*{re.escape(q_clean)}\s*=\s*([^\n]+)"
    const_match = re.search(const_pat, content)
    if const_match:
        val_expr = const_match.group(1).strip()
        return {
            "success": True,
            "type": "CONSTANT",
            "name": q_clean,
            "assignment": f"{q_clean} = {val_expr}",
            "source_path": str(_PCBNEW_SOURCE_PATH)
        }

    # 4. Global Function Query
    if not c_clean or c_clean.upper() in ("GLOBAL", "NONE", ""):
        pat = rf"(?:^|\n)def\s+{re.escape(q_clean)}\s*\([\s\S]*?(?=(?:\n[ \t]*def |\n[ \t]*class |\Z))"
        m = re.search(pat, content)
        if m:
            sig = _extract_docstring(m.group(0))
            return {
                "success": True,
                "type": "FUNCTION",
                "scope": f"GLOBAL.{q_clean}",
                "exact_signature": sig,
                "class": "GLOBAL",
                "method": q_clean,
                "source_path": str(_PCBNEW_SOURCE_PATH)
            }
        
        # If class was not specified, search across all classes for this method
        if not c_clean:
            class_matches = []
            for cls_match in re.finditer(r"\nclass\s+([A-Za-z0-9_]+)\b(?:\(([^)]+)\))?:", content):
                cls_name = cls_match.group(1)
                cls_start = cls_match.start()
                next_cls = content.find("\nclass ", cls_start + 6)
                cls_block = content[cls_start:next_cls] if next_cls != -1 else content[cls_start:]
                if re.search(rf"\n[ \t]+def\s+{re.escape(q_clean)}\s*\(", cls_block):
                    class_matches.append(cls_name)

            if class_matches:
                best_cls = class_matches[0]
                return query_oracle(query=q_clean, class_name=best_cls)

    # 5. Class Method Query with Inheritance Resolution
    target_class = c_clean if c_clean and c_clean.upper() not in ("GLOBAL", "NONE") else "BOARD"
    queue = [target_class]
    visited = set()
    class_method_names = set()

    while queue:
        curr_cls = queue.pop(0)
        if curr_cls in visited or curr_cls in ("object", ""):
            continue
        visited.add(curr_cls)

        cls_pat = rf"\nclass\s+{re.escape(curr_cls)}\b(?:\(([^)]+)\))?:"
        cls_match = re.search(cls_pat, content)
        if not cls_match:
            continue

        parents_raw = cls_match.group(1)
        if parents_raw:
            parents = [p.strip().split(".")[-1] for p in parents_raw.split(",") if p.strip()]
            for p in parents:
                if p not in visited:
                    queue.append(p)

        cls_start = cls_match.start()
        next_cls = content.find("\nclass ", cls_start + 6)
        cls_block = content[cls_start:next_cls] if next_cls != -1 else content[cls_start:]

        # Collect method names for fuzzy matching
        for meth in re.findall(r"\n[ \t]+def\s+([A-Za-z0-9_]+)\s*\(", cls_block):
            class_method_names.add(meth)

        # Check for exact method match in this class block
        meth_pat = rf"\n[ \t]+def\s+{re.escape(q_clean)}\s*\([\s\S]*?(?=(?:\n[ \t]+def |\nclass |\Z))"
        meth_match = re.search(meth_pat, cls_block)
        if meth_match:
            sig = _extract_docstring(meth_match.group(0))
            return {
                "success": True,
                "type": "METHOD",
                "scope": f"{target_class}.{q_clean}" if curr_cls == target_class else f"{target_class}.{q_clean} (inherited from {curr_cls})",
                "exact_signature": sig,
                "class": target_class,
                "defined_in_class": curr_cls,
                "method": q_clean,
                "source_path": str(_PCBNEW_SOURCE_PATH)
            }

    # 6. Not Found -> Compute Fuzzy Suggestions across methods, classes, and global defs
    all_candidates = list(class_method_names) if class_method_names else (global_func_names + class_names)
    suggestions = _find_similar_names(all_candidates, q_clean, limit=6)

    return {
        "success": False,
        "scope": f"{target_class}.{q_clean}" if c_clean else q_clean,
        "error": f"Symbol, method, class, or constant '{q_clean}' not found in {target_class if c_clean else 'pcbnew'}.",
        "suggestions": suggestions,
        "source_path": str(_PCBNEW_SOURCE_PATH)
    }
