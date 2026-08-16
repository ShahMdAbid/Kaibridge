# abIDE (Agent Bridge IDE)

**abIDE** is an end-to-end KiCad plugin that connects external AI agents to architect circuits, source verified components, compile multi-sheet schematics, place components via closed-loop visual feedback, and route PCBs inside the native KiCad environment—operating alongside a human engineer.

A token-efficient, faster, and lighter atomic REST API based alternative to generic MCP servers.

[![Download abIDE (Windows)](https://img.shields.io/badge/Download_abIDE_(Windows)-v1.0-2EA043?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/ShahMdAbid/abIDE/releases/latest/download/abIDE-v1.0.zip) [![License](https://img.shields.io/badge/License-AGPL_v3.0-1D70B8?style=for-the-badge)](https://github.com/ShahMdAbid/abIDE/blob/main/LICENSE)

**System Requirements:**  
![KiCad](https://img.shields.io/badge/KiCad-10-blue?style=for-the-badge&logo=kicad) ![Java](https://img.shields.io/badge/Java-17%2B-EA2D2E?style=for-the-badge&logo=openjdk&logoColor=white) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)

## Architecture


```text
                         ┌──────────────────────────┐
                         │      External AI Agent   │
                         │                          │
                         └────────────┬─────────────┘
                                      │
                         Design Intent / Agent Actions
                                      │
                    ┌─────────────────▼─────────────────┐
                    │         Agent Protocol            │
                    │                                   │
                    │  design.json     ops.json         │
                    │  state queries   checkpoints      │
                    └───────────────┬───────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
                    ▼                                ▼
        ┌──────────────────────┐        ┌────────────────────────┐
        │  Schematic Compiler  │        │   KiCad Agent Bridge   │
        │                      │        │                        │
        │ • component resolve  │        │ External agent ↔ KiCad │
        │ • pin verification   │        │ communication layer    │
        │ • placement          │        └───────────┬────────────┘
        │ • .kicad_sch output  │                    │
        └──────────┬───────────┘                    ▼
                   │                     ┌────────────────────────┐
                   ▼                     │      Board Engine      │
             Native KiCad                │                        │
              Schematic                  │ • atomic board ops     │
                                         │ • UUID resolution      │
                                         │ • unit conversion      │
                                         │ • object manipulation  │
                                         └───────────┬────────────┘
                                                     │
                         ┌───────────────────────────┼───────────────────────────┐
                         │                           │                           │
                         ▼                           ▼                           ▼
                 ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
                 │  Enforcement  │           │  Persistence  │           │  Observation  │
                 ├───────────────┤           ├───────────────┤           ├───────────────┤
                 │ Geometry Gate │           │ Backup / Diff │           │ State Extract │
                 │               │           │               │           │               │
                 │ • collisions  │           │ • snapshots   │           │ • board state │
                 │ • boundaries  │           │ • rollback    │           │ • comparison  │
                 │ • route-ready │           │ • comparison  │           │ • nets/tracks │
                 └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
                         │                           │                           │
                         └───────────────────────────┼───────────────────────────┘
                                                     ▼
                                            ┌─────────────────┐
                                            │      KiCad      │
                                            │                 │
                                            │ Schematic / PCB │
                                            └────────┬────────┘
                                                     │
                         ┌───────────────────────────┼───────────────────────────┐
                         ▼                           ▼                           ▼
                  ┌────────────┐              ┌────────────┐              ┌────────────┐
                  │ SVG / View │              │    DRC     │              │ Board State│
                  │  Snapshot  │              │ Validation │              │  / Report  │
                  └──────┬─────┘              └──────┬─────┘              └──────┬─────┘
                         │                           │                           │
                         └───────────────────────────┼───────────────────────────┘
                                                     ▼
                                           ┌────────────────────┐
                                           │ Agent Re-evaluates │
                                           │                    │
                                           │ observe → reason → │
                                           │ modify → validate  │
                                           └─────────┬──────────┘
                                                     │
                                                     └───────► iteration
```


## Core Capabilities
* **Hierarchical Schematic Compilation:** Converts prompts > abstract JSON design intent > native, multi-sheet `.kicad_sch` files, complete with automated LCSC/EasyEDA footprint fetching and hierarchical sub-page routing.
* **Comprehensive PCB Automation:** Exposes 14 atomic operations via a local HTTP server, allowing real-time manipulation without locking files or restarting KiCad.
  * *(Note: An earlier SWIG-based API introspection layer was deprecated after instability under changing KiCad GUI state; the current architecture uses explicit operation contracts instead. See `legacyboardengine/` for the archived implementation.)*
* **AI Visual Thinking:** Automatically renders SVG snapshots of the live layout, allowing multimodal AI agents to visually critique component placement (e.g., decoupling proximity, signal flow) and iteratively refine the board.
* **Strict Human-in-the-Loop:** Halts autonomous execution at major checkpoints (Schematic Generation $\rightarrow$ Placement $\rightarrow$ Routing). Engineers can visually review the board in the KiCad GUI and provide explicit overrides before the agent proceeds.
* **Deterministic Geometry Gate:** Incorporates a 2D Minimum Translation Vector (MTV) collision solver to automatically detect overlaps, enforce courtyard boundaries, and resolve micro-clearances before committing to PCB.


## Quick Start

### 1. Installation

**Compatibility Note:** The abIDE PCB automation plugin and bridge are exclusively for **KiCad 10** (due to Python PCB API changes). The standalone schematic generator (`json2sch.py`) can optionally target KiCad 7+ via CLI flags.

Clone this repository into your KiCad 10 scripting plugins directory.

### 2. Configuration
Update the `kicad_paths.json` file in the root directory to point to your local `kicad-cli`, component libraries, and `freerouting.jar` .

### 3. Execution
1. Open your KiCad project and navigate to the PCB Editor.
2. Click **Tools > External Plugins > abIDE** to start the local REST API bridge.
3. Open this plugin directory (`abIDE-main`) in your preferred agent environment (e.g., **Antigravity IDE**). 
4. Provide the agent with the absolute path to your project directory alongside your initial prompt to begin the automated design flow.

## Other Routing Options

* **Cloud AI Routing:** After initial load in pcb editor give a edge cut and your board is ready for advanced cloud routing platforms such as [Quilter AI](https://app.quilter.ai).

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
You are free to use and modify this plugin. However, if you modify the code and make it available over a network (e.g., as a SaaS  or web tool), you **must** open-source your modified backend code under the same AGPL-3.0 license. 

See the `LICENSE` file for more details.
