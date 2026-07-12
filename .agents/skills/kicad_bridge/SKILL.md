---
name: Use KiCad abIDE (Agent Bridge & API Oracle)
description: CRITICAL instructions for AI agents on how to execute Python code in KiCad 10 and query the KiCad API Oracle without writing temporary files.
---

# abIDE Rules for AI Agents

You are operating within the **abIDE (Agent-Bridged IDE)** environment for KiCad 10. You must follow these strict rules to avoid API hallucinations and disk I/O bottlenecks.

## 1. Zero Temporary Files Policy
When executing Python scripts inside KiCad, **DO NOT** use `write_to_file` to create temporary `.py` files. 
You must pipe your generated code directly to the KiCad environment using the socket bridge via standard input.

**Correct Method (PowerShell Heredoc):**
```powershell
@'
import pcbnew
board = pcbnew.GetBoard()
print("Executed directly in KiCad memory!")
'@ | python kicad_agent_bridge.py --stdin
```

## 2. No API Hallucination (Use the Oracle)
KiCad 10's Python API (SWIG bindings) differs significantly from KiCad 5/6/7. Your internal training data is likely outdated. 
**DO NOT GUESS METHOD SIGNATURES.**

1. First, consult `API_method_names.md` to verify the method exists.
2. Then, query `oracle.py` to extract the exact C++ signature and docstring.

### Querying the Oracle (Batch Mode)
Always use `--batch` mode via standard input to look up multiple methods at once. This saves tokens and avoids multiple terminal executions.

```powershell
@'
BOARD Add
PCB_TRACK SetStart
PCB_TRACK SetEnd
GLOBAL ToMM
FOOTPRINT SetPosition
'@ | python oracle.py --batch
```

**Note:** The Oracle automatically handles single and multiple inheritance (e.g., checking `EDA_ITEM` or `EDA_TEXT` base classes), so the output you receive is the absolute source of truth.
