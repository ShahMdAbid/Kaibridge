---
name: JLCPCB Production Export
description: Instructions for generating manufacturing (Gerber) and assembly (BOM, CPL) files for JLCPCB.
---

# JLCPCB Production Export

When the user asks to prepare the board for manufacturing, ordering, or exporting to JLCPCB (e.g., "generate gerbers", "make JLCPCB files", "order dewar jonno file"), use this automated skillset.

## Context
The `abIDE` plugin provides a built-in script, `export_jlcpcb.py`, located in the root of the plugin directory (`abIDE-main`). This script leverages `kicad-cli` to securely and cleanly export exactly what JLCPCB needs:
1.  **Gerber ZIP:** Cleaned production-ready zip containing only necessary fabrication layers and Excellon drill files.
2.  **BOM (Bill of Materials) CSV:** Merged components with standard JLCPCB headers (`Comment, Designator, Footprint, Quantity, LCSC Part #`). It automatically resolves LCSC part numbers from `design.json`, schematic fields, or common defaults.
3.  **CPL (Component Placement List / Pick and Place) CSV:** Precise centroid data formatted for JLCPCB (`Designator, Mid X, Mid Y, Layer, Rotation, Comment, Package`), filtering out non-SMD mechanical mounting holes.

## Execution

To generate the production files, execute the script on the target project directory.

**Command:**
```powershell
python "<PLUGIN_DIR>\export_jlcpcb.py" "<PROJECT_DIR>"
```

**Expected Outcome:**
The script will output progress to the terminal and create a folder named `jlcpcb_production` inside the `<PROJECT_DIR>`. Inside, you will find:
-   `Gerber_<project_stem>.zip`
-   `BOM_<project_stem>.csv`
-   `CPL_<project_stem>.csv`

## User Handoff & Presentation
After the script completes successfully:
1.  Read the generated `BOM_*.csv` and `CPL_*.csv` files (or their summaries) to understand the output.
2.  Create a clear summary for the user (in Bengali or English as appropriate).
3.  List the three generated files and explicitly state their paths.
4.  Provide simple ordering instructions:
    -   Go to [jlcpcb.com/quote](https://jlcpcb.com/quote).
    -   Upload the `Gerber_*.zip` file for PCB Fabrication.
    -   Toggle "PCB Assembly" and upload the BOM and CPL files during the SMT step.

> [!NOTE]
> Do **not** attempt to manually export Gerbers using `kicad-cli` directly unless `export_jlcpcb.py` fails. The script handles layer filtering and CSV formatting specific to JLCPCB's auto-DFM system.
