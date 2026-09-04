# Agentic Placement Architecture & Spatial Intent Pipeline

## The Core Concept: Vision-Guided Semantic Placement

LLMs lack continuous sub-millimeter geometric awareness. To overcome this limitation, Kaibridge operates on a two-tier division of responsibility:
- **The AI Agent (Lead Hardware Architect):** Dictates semantic and spatial intent via `ops.json` (functional clustering, perimeter outward connector orientation, heatsink tab facing, and IC pin alignment).
- **The Kaibridge Geometry Gate (Deterministic Mason):** Enforces strict 0.5mm grid quantization, verifies non-overlapping courtyards, and executes physics-based micro-relaxation (`kaibridge_auto_relax_layout`).

```mermaid
graph TD
    A["1. Circuit Intent & Pin Data<br/>kicad_pins.py --json / design.json"] --> B["2. Spatial Floorplan Architecture<br/>4-Zone Partitioning & Rotational Intent"]
    B --> H0["📋 Plan Alignment Gate:<br/>User Approves 4-Part Plan"]
    H0 --> C["3. Declarative Placement<br/>kicad_layout.py (ops.json) --dry-run"]
    C -->|Geometry Gate PASS| D["4. Vector Layout Snapshot<br/>pcb_snapshot.py"]
    C -->|Courtyard Collision| B2["Adjust Spacing / Relax Layout"]
    B2 --> C
    D --> E["5. Spatial Critique & Verification<br/>Inspect spacing, symmetry, corridors"]
    E --> H2["🧍 Checkpoint 2 Review:<br/>Placement Approval"]
    H2 -->|Approved| G["6. Prep for Routing<br/>Netclass validation & unroute orphaned tracks"]
    H2 -->|Feedback| F["Apply Adjustment ops.json"]
    F --> C
    G --> H["7. Headless Routing<br/>kicad_route.py (Freerouting 2.4.1)"]
    H --> I["8. Solid GND Copper Pour<br/>B.Cu Ground Plane (0.3mm clearance)"]
    I --> J["9. Automated DRC Verification<br/>KiCad DRC (0 Errors, 0 Unconnected)"]
    J --> H3["🧍 Checkpoint 3 Review:<br/>Routing & DRC Confirmation"]
    H3 -->|Approved| K["10. Factory Production Export<br/>export_jlcpcb.py (Gerber, BOM, CPL)"]
    H3 -->|Feedback| G
    J -->|DRC Violations| L["Diagnose & Fix via Failure Matrix"]
    L --> G
    K --> M["✅ 100% JLCPCB Ready"]
```

## Mandatory Rules Reference
Before formulating `ops.json`, consult canonical rulebases in `references/`:
1. [`references/pcb_placement_rules.md`](../references/pcb_placement_rules.md): 80-rule floorplanning doctrine, precedence ladder (§0.3), and proximity tolerances.
2. [`references/trackwidth_clearence_viasize.md`](../references/trackwidth_clearence_viasize.md): Netclasses, track widths, clearances, and via hole/pad sizing.
3. [`references/failure_recovery_matrix.md`](../references/failure_recovery_matrix.md): Exhaustive recovery procedures for layout, DRC, and routing faults.
