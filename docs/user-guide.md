#User Guide

This guide explains how to set up and design printed circuit boards using Kaibridge 2.0 with an AI coding agent (e.g. Google Antigravity, Claude Desktop, Cursor).

---

##1. Setup & MCP Registration

###Automatic Configuration (Recommended for Antigravity IDE)
When opening this repository in **Antigravity IDE** for the first time, you can prompt the agent to automatically configure the MCP server:

> *"Configure this workspace as an MCP server named 'kaibridge' in my global mcp_config.json, pointing to server.py using the current workspace directory, and verify the connection."*

Antigravity will dynamically resolve the workspace directory and register Kaibridge without requiring manual path editing.

###Manual Configuration
Alternatively, add Kaibridge directly to your `mcp_config.json`:

```json
{
  "mcpServers": {
    "kaibridge": {
      "command": "python",
      "args": [
        "server.py"
      ]
    }
  }
}
```

Ensure KiCad 10, Java 17+ (or Java 25 LTS), and Python 3.10+ are installed.

### Download & Release Assets
For users downloading the release package directly from GitHub:
- **Kaibridge Source Code Suite:** Download [Kaibridge_v2.1.0.zip](https://github.com/ShahMdAbid/Kaibridge/releases/download/v2.1.0/Kaibridge_v2.1.0.zip) (~59 MB) and extract to your project location.
- **Offline Component Database (Optional):** Download [easyeda-std.elib.zip](https://github.com/ShahMdAbid/Kaibridge/releases/download/v2.1.0/easyeda-std.elib.zip) (~142 MB) and extract `easyeda-std.elib` directly into `Kaibridge/data/easyeda-std.elib` for sub-millisecond offline lookup across 16,600+ JLCPCB parts.
*(Note: If the offline database is not installed, Kaibridge automatically uses its embedded Golden Master cache and on-demand EasyEDA API).*

---

## 2. Standard Design Workflow

When designing a board, the AI agent and the human engineer interact through four key checkpoints:

```
[Prompt] ──► [Checkpoint 1: Plan Review] ──► [Checkpoint 2: Schematic & ERC] ──► [Checkpoint 3: Placement & Preview] ──► [Checkpoint 4: Route & DRC] ──► [Fabrication Files]
```

### Step 1: Implementation Plan Review
- **Prompt:** State your functional circuit requirements (power inputs, active ICs, communication interfaces, connectors, board dimensions).
- **Agent Action:** Generates `implementation_plan.md` featuring the adversarial Delta Table (Layer 0 requirements, Layer 1 DFM checklist, Layer 2 domain failure scenarios) and upfront BOM.
- **Human Action:** Review the plan and approve it before the agent initializes project files.

### Step 2: Schematic Generation & Electrical Rules Check
- **Agent Action:** 
  1. Queries the local SQLite catalog to resolve components and bind upfront LCSC C-Part IDs.
  2. Extracts exact pin numbers and footprint strings via `kicad_pins.py` (zero pin hallucinations).
  3. Compiles declarative `design.json` into multi-sheet `.kicad_sch`.
  4. Executes headless ERC to confirm 0 electrical errors and 0 warnings (Checkpoint 1).
  5. Synchronizes footprints and nets directly to `.kicad_pcb` (headless F8).

### Step 3: Two-Stage Placement & Visual Inspection
- **Agent Action:**
  1. Sets board boundaries on `Edge.Cuts`.
  2. **Stage 7A (Primary Engine — Planar Optimizer):** Executes simulated annealing via `kicad_planar_optimizer.py` (Kruskal MST and 2D CCW line intersections) to cut ratsnest crossings by >85% and resolve overlaps in memory.
  3. Commits placement via `kicad_layout.py` and exports vector SVG preview via `pcb_snapshot.py` to `<project_dir>/kaibridge_dump/`.
- **Human Action:** **Stage 7B (Secondary QA Inspector — Visual Audit):** Inspect the rendered board preview (Checkpoint 2) to confirm connector mating faces face outward (`CON-01`), silkscreen text is outside exposed SMD pads, and routing corridors remain open ($\ge 2.5\text{mm}$).

### Step 4: 3-Tier Hierarchical Routing, DRC & Manufacturing Export
- **Agent Action:**
  1. **Tier 1 (Dog-Bone Fanout First):** Places $0.6\text{mm}$ vias ($0.3\text{mm}$ drill) offset $1.0-1.2\text{mm}$ outside SMD GND pads with $0.25\text{mm}$ escape necks (zero via-in-pad for reflow safety).
  2. **Tier 2 (Planar F.Cu Signal Routing):** Strips GND from the Specctra DSN, harmonizes signal clearances to 250µm, and routes all signals planarly on `F.Cu` with zero signal vias.
  3. **Tier 3 (Solid Ground Flood):** Pours a continuous solid ground copper plane on `B.Cu` swallowing fanouts and through-hole pins.
  4. Runs `kicad-cli` DRC to verify 0 clearance violations and 0 unconnected airwires (Checkpoint 3).
  5. Packages factory-ready JLCPCB bundles into `<project_dir>/production_output/`.

---

## 3. Example Prompts

### Basic Power Supply
```text
Design a 5V to 3.3V LDO regulator board using an AMS1117-3.3 with USB-C ingest, 
reverse polarity protection diode, 10uF input/output decoupling caps, a power LED, 
and a 2.54mm 1x4 output header. Board size 35x25mm.
```

### Sensor Interface Board
```text
Design a breakout board for an I2C environmental sensor with 3.3V power, 
4.7k pull-up resistors on SDA/SCL, decoupling capacitor, and a JST-SH 4-pin connector.
```

---

## 4. Project File Structure

Every generated project maintains a clean directory layout:

```text
My_Project/
├── My_Project.kicad_pro       # KiCad project settings & netclasses
├── My_Project.kicad_sch       # Hierarchical schematic
├── My_Project.kicad_pcb       # Routed PCB layout
├── kaibridge_dump/            # Intermediate files & previews
│   ├── design.json            # Declarative circuit netlist
│   ├── ops.json               # Placement operations log
│   ├── erc_report.json        # Headless ERC output
│   ├── drc_report.json        # Headless DRC output
│   ├── preview_pcb.png        # Rendered top-view preview
│   └── preview_pcb.svg        # Vector layout snapshot
└── production_output/         # JLCPCB manufacturing bundle
    ├── Gerber_My_Project.zip  # RS-274X Gerbers & Excellon drill
    ├── BOM_My_Project.csv     # Populated BOM with LCSC IDs
    └── CPL_My_Project.csv     # Pick & Place placement file
```
