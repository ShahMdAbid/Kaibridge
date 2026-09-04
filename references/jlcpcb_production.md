#JLCPCB Production Export in Kaibridge 2.0

When the user asks to prepare the board for manufacturing, ordering, or exporting to JLCPCB (e.g., "generate gerbers", "export fabrication files", "make JLCPCB bundle"), use the dedicated autonomous exporter tool `kaibridge_export_production`.

---

##1. Automated Output Bundle

Kaibridge 2.0 leverages `kicad-cli` and `pcbnew` to generate a 100% factory-compliant JLCPCB manufacturing bundle:

1. **Gerber ZIP (`<project_stem>_gerbers.zip`):**  
   Contains all necessary fabrication layers (`F.Cu`, `B.Cu`, `F.Paste`, `B.Paste`, `F.SilkS`, `B.SilkS`, `F.Mask`, `B.Mask`, `Edge.Cuts`) and Excellon drill files (`.drl` with drill map PDF).
2. **BOM CSV (`<project_stem>_bom_jlcpcb.csv`):**  
   Standard JLCPCB format: `Comment, Designator, Footprint, LCSC Part #`. Automatically resolves LCSC C-Part IDs from `design.json` fields, footprint fields, or verified basic parts catalog with auto-healing.
3. **CPL / Pick and Place CSV (`<project_stem>_cpl_jlcpcb.csv`):**  
   Format: `Designator, Val, Package, Mid X, Mid Y, Rotation, Layer`. Uses true physical centroid coordinates computed from courtyards/pads and formatted as clean numeric floats (no `'mm'` string suffixes) for automated SMT placement machines.

---

##2. Execution (CLI & MCP)

- **Mode A (Root CLI):**
  ```powershell
  python export_jlcpcb.py "projects/<Project_Name>"
  ```
- **Mode B (MCP Tool):**
  ```python
  kaibridge_export_production(project_dir="<PROJECT_DIR>")
  ```

###Output Location:
All production files are exported to `<PROJECT_DIR>/production_output/`:

```text
<PROJECT_DIR>/
└── production_output/
    ├── <stem>_gerbers.zip        # Upload to JLCPCB PCB Quotation
    ├── <stem>_bom_jlcpcb.csv     # Upload to SMT Assembly Step 1
    ├── <stem>_cpl_jlcpcb.csv     # Upload to SMT Assembly Step 2
    └── gerbers/                  # Uncompressed Gerber & Excellon files
```

---

##3. User Handoff & Ordering Guide

After export completes successfully:
1. Inspect the summary returned by `kaibridge_export_production`.
2. Present the exact file paths located inside `production_output/`.
3. Provide simple ordering steps:
   - Go to [jlcpcb.com/quote](https://jlcpcb.com/quote).
   - Upload `<stem>_gerbers.zip` for PCB Fabrication.
   - Select **PCB Assembly (SMT)**.
   - Upload `<stem>_bom_jlcpcb.csv` as the Bill of Materials.
   - Upload `<stem>_cpl_jlcpcb.csv` as the Component Placement List.
