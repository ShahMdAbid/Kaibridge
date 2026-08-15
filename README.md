# abIDE (Agent Bridge IDE)

**abIDE** is an end to end KiCad plugin designed to provide autonomous AI agents with the ability to architect pcb from prompt, visually evaluate, and route within the native KiCad environment, operating alongside a human engineer.

## Core Capabilities
* **Hierarchical Schematic Compilation:** Converts prompts > abstract JSON design intent > native, multi-sheet `.kicad_sch` files, complete with automated LCSC/EasyEDA footprint fetching and hierarchical sub-page routing.
* **Comprehensive PCB Automation:** Exposes 16 atomic operations via a local HTTP server, allowing real-time manipulation without locking files or restarting KiCad.
  * *(Note: The original Phase 1 `oracle.py` approach—which relied on live C++ SWIG function introspection to prevent AI hallucination—has been deprecated due to severe memory corruption and `SwigPyObject` dangling pointers when the KiCad GUI state changes. It is archived in the `legacyboardengine/` directory.)*
* **AI Visual Thinking:** Automatically renders SVG snapshots of the live layout, allowing multimodal AI agents to visually critique component placement (e.g., decoupling proximity, signal flow) and iteratively refine the board.
* **Strict Human-in-the-Loop:** Halts autonomous execution at major checkpoints (Schematic Generation $\rightarrow$ Placement $\rightarrow$ Routing). Engineers can visually review the board in the KiCad GUI and provide explicit overrides before the agent proceeds.
* **Physics-Guided Relaxation:** Incorporates a Separating Axis Theorem collision solver to automatically resolve micro-collisions and enforce strict physical tolerances.



## Quick Start

### 1. Installation
Clone this repository into your KiCad 10 scripting plugins directory.

### 2. Configuration
Update the `kicad_paths.json` file in the root directory to point to your local `kicad-cli`, component libraries, and `freerouting.jar` .

### 3. Execution
1. Open your KiCad project and navigate to the PCB Editor.
2. Click **Tools > External Plugins > abIDE** to start the local REST API bridge.
3. Open this plugin directory (`abIDE-main`) in your preferred agent environment (e.g., **Antigravity IDE**). 
4. Provide the agent with the absolute path to your project directory alongside your initial prompt to begin the automated design flow.

## Routing Options

* **Local Autorouting (Default):** Download [Freerouting](https://github.com/freerouting/freerouting/releases) and utilize the included `freerouting_runner.py` script for rapid, headless local routing.
* **Cloud AI Routing:** After initial load in pcb editor give a edge cut and your board is ready for advanced cloud routing platforms such as [Quilter AI](https://app.quilter.ai).
