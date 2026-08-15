# abIDE (Agent Bridge IDE)

**abIDE** is an end to end KiCad plugin designed to provide autonomous AI agents with the ability to architect pcb from prompt, visually evaluate, and route within the native KiCad environment, operating alongside a human engineer.

## Core Capabilities
* **Hierarchical Schematic Compilation:** Converts prompts > abstract JSON design intent > native, multi-sheet `.kicad_sch` files, complete with automated LCSC/EasyEDA footprint fetching and hierarchical sub-page routing.
* **Comprehensive PCB Automation:** Exposes 16 atomic operations via a local HTTP server, allowing real-time manipulation without locking files or restarting KiCad.
* **AI Visual Thinking:** Automatically renders SVG snapshots of the live layout, allowing multimodal AI agents to visually critique component placement (e.g., decoupling proximity, signal flow) and iteratively refine the board.
* **Strict Human-in-the-Loop:** Halts autonomous execution at major checkpoints (Schematic Generation $\rightarrow$ Placement $\rightarrow$ Routing). Engineers can visually review the board in the KiCad GUI and provide explicit overrides before the agent proceeds.
* **Physics-Guided Relaxation:** Incorporates a Separating Axis Theorem (SAT) collision solver to automatically resolve micro-collisions and enforce strict physical tolerances.



## Quick Start

### 1. Installation
Clone this repository into your KiCad 10 scripting plugins directory.

### 2. Configuration
Update the `kicad_paths.json` file in the root directory to point to your local `kicad-cli`, component libraries, and `freerouting.jar` executable.

### 3. Execution
1. Open the plugin directory in your preferred agent environment (e.g., **Antigravity IDE**).
2. Open your project in the KiCad PCB Editor.
3. from pcb editor navigate to **Tools > External Plugins > abIDE** to initialize the REST API bridge.

## Routing Options

* **Local Autorouting (Default):** Download [Freerouting](https://github.com/freerouting/freerouting/releases) and utilize the included `freerouting_runner.py` script for rapid, headless local routing.
* **Cloud AI Routing:** Following layout approval within abIDE, the `.kicad_pcb` file is fully compatible with advanced cloud routing platforms such as [Quilter AI](https://app.quilter.ai).
