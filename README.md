# abIDE (Agent Bridged IDE) for automated PCB design using KiCad.

This plugin connects external AI agents directly into KiCad (compatible with the latest version as of uploading this repo, i.e. KiCad 10) and solves the API hallucination problem.

### Key Features

- **Bypasses KiCad's Closed Terminal:** Pipe Python scripts from any external AI agent straight into KiCad via socket (`kicad_agent_bridge.py`). The included `.agents/` folder teaches your agentic IDE how to use the bridge and execute python scripts in KiCad.
- **YAML Blueprinting Protocol:** Enforces a strict YAML-based hardware definition protocol. AI agents must draft the components, nets, and design intent before touching code. (Now uses a simplified, flat `nets` dictionary for optimal schematic generation).
- **Native Schematic Generation (NEW!):** Generates flawless `.kicad_sch` text files deterministically using `blueprint_to_sch.py` straight from YAML blueprints for loading components (v1.0.5). (Instead of of SWIG footprint injections of prev versions) 
- **Built-in API Oracle:** Solves AI hallucination by querying exact KiCad 10 SWIG bindings via `oracle.py` rather than guessing.
- **Multiple Inheritance Support:** Flawlessly climbs the C++ object tree to find hidden base methods.
- **Iterative Development & State Fetching:** Agents can fetch exact component and unrouted net data in a token-optimized JSON format via `currentboardfetcher.py`.
- **abIDE UI Watchdog:** Actively monitors AI execution and kills any script running longer than 15 seconds to prevent freezing KiCad's UI thread.
- **No Temporary Files:** Code executes natively and instantly in memory without writing scratch files to disk.
