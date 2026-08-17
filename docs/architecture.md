# abIDE System Architecture


```text
                                        ┌──────────────────────────────────────────────────┐
                                        │               External AI Agent                  │
                                        │    ( Gemini via Antigravity IDE , Claude-code)   │
                                        └────────────────────────┬─────────────────────────┘
                                                                 │
                                  ┌──────────────────────────────┴──────────────────────────────┐
                                  │                REST API / Agent Protocol Layer              │
                                  │                                                             │
                                  │  • design.json: High-level circuit intent & components      │
                                  │  • ops.json: Semantic Placement Protocol (MOVE, ROTATE)     │
                                  │  • GET/POST endpoints for live board state & checkpoints    │
                                  └──────────────────────────────┬──────────────────────────────┘
                                                                 │
                                ┌────────────────────────────────┴────────────────────────────────┐
                                │                                                                 │
                                ▼                                                                 ▼
                ┌────────────────────────────────┐                               ┌────────────────────────────────┐
                │       Schematic Compiler       │                               │       KiCad Agent Bridge       │
                │        (json2sch.py)           │                               │    (kicad_agent_bridge.py)     │
                │                                │                               │                                │
                │ • Abstract Intent Resolution   │                               │ • REST HTTP Server (Local)     │
                │ • LCSC/EasyEDA Part Fetching   │                               │ • JSON ↔ Python Deserialization│
                │ • Hierarchical Sheet Routing   │                               │ • Semantic Instruction Parser  │
                │ • Pin & Netlist Verification   │                               │ • State & Sync Coordinator     │
                │ • Generates native .kicad_sch  │                               └───────────────┬────────────────┘
                └────────────────┬───────────────┘                                               │
                                 │                                                               ▼
                                 │                                               ┌────────────────────────────────┐
                                 │                                               │          Board Engine          │
                                 │                                               │                                │
                                 │                                               │ • Executes 14 Atomic Ops       │
                                 │                                               │ • Live Board Memory Proxy      │
                                 │                                               │ • Coordinate/Unit Conversion   │
                                 │                                               │ • SwigPyObject Management      │
                                 │                                               └───────────────┬────────────────┘
                                 │                                                               │
                                 │       ┌───────────────────────────────────────────────────────┴───────────────────────────────────────────────────────┐
                                 │       │                                                       │                                                       │
                                 ▼       ▼                                                       ▼                                                       ▼
                       ┌─────────────────────────┐                             ┌─────────────────────────┐                             ┌─────────────────────────┐
                       │       Enforcement       │                             │       Persistence       │                             │       Observation       │
                       │    (Geometry Gate)      │                             │     (Backup / Diff)     │                             │    (State Extraction)   │
                       ├─────────────────────────┤                             ├─────────────────────────┤                             ├─────────────────────────┤
                       │ • 2D MTV Collision Solver│                             │ • Pre-Op Snapshots      │                             │ • Track/Net Extraction  │
                       │ • Courtyard Boundaries  │                             │ • Auto-Rollback on Error│                             │ • Footprint Positions   │
                       │ • Board Edge Validation │                             │ • File Size Validation  │                             │ • JSON State Summaries  │
                       │ • Edge.Cuts Automation  │                             │ • 0-Byte Recovery       │                             │ • GUI Sync Triggers     │
                       └─────────┬───────────────┘                             └─────────┬───────────────┘                             └─────────┬───────────────┘
                                 │                                                       │                                                       │
                                 └───────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┘
                                                                                         ▼
                                                                            ┌─────────────────────────┐
                                                                            │      Native KiCad       │
                                                                            │       GUI Runtime       │
                                                                            │                         │
                                                                            │ • PCB Editor View       │
                                                                            │ • Live .kicad_pcb Data  │
                                                                            │ • Human Engineer In-Loop│
                                                                            └────────────┬────────────┘
                                                                                         │
                                         ┌───────────────────────────────────────────────┼───────────────────────────────────────────────┐
                                         │                                               │                                               │
                                         ▼                                               ▼                                               ▼
                           ┌───────────────────────────┐                   ┌───────────────────────────┐                   ┌───────────────────────────┐
                           │      Visual Feedback      │                   │      DRC Validation       │                   │    Board State Report     │
                           │                           │                   │                           │                   │                           │
                           │ • Live SVG Snapshots      │                   │ • Checks Open/Unrouted    │                   │ • Updated Coordinates     │
                           │ • Multimodal AI Critique  │                   │ • Checks Micro-clearances │                   │ • Clearance Violations    │
                           │ • Placement Verification  │                   │ • Rules Validation        │                   │ • Component Rotations     │
                           └─────────────┬─────────────┘                   └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                                         │                                               │                                               │
                                         └───────────────────────────────────────────────┴───────────────┬───────────────────────────────┘
                                                                                                         │
                                                                                                         ▼
                                                                                         ┌───────────────────────────────┐
                                                                                         │      Agent Re-evaluates       │
                                                                                         │ (Observe → Reason → Modify)   │
                                                                                         └───────────────┬───────────────┘
                                                                                                         │
                                                                                                         └────────► Next Iteration
```
