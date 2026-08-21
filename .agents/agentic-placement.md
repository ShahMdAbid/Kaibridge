# Agentic Placement Architecture

**The Core Architecture (Vision-Guided Semantic Placer):**
To solve the problem of LLMs lacking sub-millimeter geometry awareness, you **MUST** strictly act as the **Lead Hardware Architect**. You provide the *Spatial Intent* via `ops.json`, and the Kaibridge Geometry Gate (`boardmanager.py` + `geometry.py`) acts as the deterministic *Mason* to perform micro-separation courtyard collision relaxation (`geometry.separate()`). The AI dictates *what* goes where; the Geometry Gate handles the *exact math*.

> [!IMPORTANT]
> **Skillset Loading (MANDATORY):** Before making ANY engineering decisions regarding component placement, trace widths, clearances, or CLI commands, you MUST consult the canonical rules inside the `<PLUGIN_DIR>\skillset\` directory (e.g., `pcb_placement_rules.md`, `trackwidth_clearence_viasize.md`, `command_help.md`). Do not rely on generic KiCad knowledge.

This is the complete closed-loop agentic pipeline from raw F8 import to a production-grade, beautifully placed, fully routed, DRC-clean PCB.

```mermaid
graph TD
    A["1. Dynamic Circuit Cognition<br/>Read --state summary / design.json"] --> B["2. AI Vision-Driven Plan<br/>Multimodal critique sense & spatial architecture"]
    B --> H0["🧍 Human Alignment Checkpoint:<br/>Confirm Design & Placement Intent"]
    H0 -->|User Directives| B2["Adopt User Symmetry / Directives"]
    B2 --> C["3. Generate & Apply ops.json<br/>--json-ops ops.json --commit"]
    H0 -->|Approved Default Plan| C
    C -->|Geometry Gate PASS| D["4. Visual Snapshot<br/>pcb_snapshot.py (Export SVG)"]
    C -->|Geometry Gate FAIL| B2
    D --> E["5. Multimodal Spatial Critique<br/>Agent inspects SVG: spacing, corridors, symmetry"]
    E --> H1["🧍 Human Checkpoint 1:<br/>Placement Approval"]
    H1 -->|Approved| G["6. Prep for Route<br/>board.prep_for_route op"]
    H1 -->|Feedback| F["Analyze SVG with AI Critique Brain + User Input<br/>Generate Adjustment ops.json"]
    F --> C
    G --> H["7. Headless Routing<br/>freerouting_runner.py"]
    H --> H2["🧍 Human Checkpoint 2:<br/>Routing Approval"]
    H2 -->|Approved| I["8. Solid GND Copper Pour<br/>zone.add (F.Cu & B.Cu GND)"]
    H2 -->|Feedback| G
    I --> J["9. DRC Verification<br/>board.drc_check op"]
    J -->|DRC Clean| K["10. Final Visual Snapshot<br/>pcb_snapshot.py"]
    J -->|DRC Violations| L["Diagnose & Fix via ops.json"]
    L --> G
    K --> M["✅ DONE (Production Grade A+)"]
```
