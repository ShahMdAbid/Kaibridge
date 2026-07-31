# abIDE (Agent Bridged IDE) for automated PCB design using KiCad.

It connects external AI agents directly into KiCad (compatible with the latest version as of uploading this repo, i.e. KiCad 10) and solves the API hallucination problem.

### Key Features

- **YAML Blueprinting Protocol:** Enforces a strict YAML-based hardware definition protocol. AI agents must draft the components, nets, and design intent before touching code.
- **Built-in API Oracle:** Solves AI hallucination by querying exact KiCad 10 SWIG bindings via `oracle.py` rather than guessing.
- **Multiple Inheritance Support:** Flawlessly climbs the C++ object tree to find hidden base methods.
- **Iterative Development & State Fetching:** Agents can fetch exact component and unrouted net data in a token-optimized JSON format via `currentboardfetcher.py`.
- **Bypasses KiCad's Closed Terminal:** Pipe Python scripts from any external AI agent straight into KiCad via socket (`kicad_agent_bridge.py`). The included `.agents/` folder teaches your agentic IDE how to use the bridge and execute python scripts in KiCad.
- **abIDE UI Watchdog:** Actively monitors AI execution and kills any script running longer than 15 seconds to prevent freezing KiCad's UI thread.
- **No Temporary Files:** Code executes natively and instantly in memory without writing scratch files to disk.

### How to Use

**1. Installation**
- Clone or copy this entire folder into your KiCad 10 `scripting/plugins/` directory.
- Open KiCad (PCB Editor) and click the abIDE icon to start the bridge GUI.

**2. Querying the Oracle (For AI Agents)**
Search for method signatures using standard input:
```powershell
@'
BOARD Add
PCB_TRACK SetStart
FOOTPRINT SetPosition
'@ | python oracle.py --batch
```

**3. Fetching Board State (For AI Agents)**
Extract token-efficient board summaries before modifying existing layouts:
```powershell
@'
import currentboardfetcher as fetcher
import json
ctx = fetcher.ai_context(mode="summary")
print(json.dumps(ctx, indent=2, default=fetcher.safe_json_default))
'@ | python kicad_agent_bridge.py --stdin
```

**4. Executing Code (For AI Agents)**
Pipe your generated Python script directly into KiCad for real-time execution:
```powershell
@'
import pcbnew
board = pcbnew.GetBoard()
print("Executing live in KiCad!")
'@ | python kicad_agent_bridge.py --stdin
```
