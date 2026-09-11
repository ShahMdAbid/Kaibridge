"""
tests/test_e2e_pipeline.py -- Automated End-to-End Synthesis Pipeline Integration Test.
Validates the complete hardware synthesis loop:
Bootstrap -> Design Spec -> Compile Schematic -> Sync Netlist -> Planar Placement -> Gatekeeper Audit -> JLCPCB Export.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from kaibridge.core.init import init_libraries
from kaibridge.schematic.compiler import compile_schematic
from kaibridge.pcb.sync import sync_schematic_to_pcb
from kaibridge.pcb.planar_optimizer import optimize_planar_layout
from kaibridge.pcb.gatekeeper import placement_audit
from kaibridge.pcb.export import export_production_files


class TestEndToEndSynthesisPipeline:
    """Tests the complete end-to-end hardware synthesis chain in an isolated temporary project."""

    def test_full_hardware_synthesis_lifecycle(self, tmp_path: Path):
        project_name = "e2e_node"
        project_dir = tmp_path / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # ---------------------------------------------------------
        # Step 0: Bootstrap Project & Libraries
        # ---------------------------------------------------------
        init_res = init_libraries(project_dir, name="kaibridge", layers=2)
        assert init_res.get("success") is True, f"Project initialization failed: {init_res}"
        assert (project_dir / f"{project_name}.kicad_pro").exists()
        assert (project_dir / f"{project_name}.kicad_pcb").exists()
        assert (project_dir / "libs" / "kaibridge.kicad_sym").exists()
        assert (project_dir / "libs" / "kaibridge.pretty").exists()

        # ---------------------------------------------------------
        # Step 1 & 5: Circuit Specification (design.json)
        # Using native KiCad components for zero-network deterministic testing
        # ---------------------------------------------------------
        dump_dir = project_dir / "kaibridge_dump"
        dump_dir.mkdir(parents=True, exist_ok=True)

        design_data = {
            "schema": 3,
            "meta": {
                "name": project_name,
                "version": "1.0",
                "title": "E2E Automated Test Circuit"
            },
            "board": {
                "layers": 2,
                "thickness_mm": 1.6,
                "width_mm": 35.0,
                "height_mm": 25.0
            },
            "netclasses": {
                "Default": {
                    "track_width": 0.25,
                    "clearance": 0.2,
                    "via_diameter": 0.6,
                    "via_drill": 0.3
                },
                "Power": {
                    "track_width": 0.5,
                    "clearance": 0.25,
                    "via_diameter": 0.8,
                    "via_drill": 0.4
                }
            },
            "power_flags": ["VCC", "GND"],
            "parts": {
                "R1": {
                    "lib_id": "Device:R",
                    "footprint": "Resistor_SMD:R_0805_2012Metric",
                    "value": "10k",
                    "fields": {"LCSC": "C17414"}
                },
                "R2": {
                    "lib_id": "Device:R",
                    "footprint": "Resistor_SMD:R_0805_2012Metric",
                    "value": "10k",
                    "fields": {"LCSC": "C17414"}
                },
                "D1": {
                    "lib_id": "Device:LED",
                    "footprint": "LED_SMD:LED_0805_2012Metric",
                    "value": "RED",
                    "fields": {"LCSC": "C2286"}
                }
            },
            "nets": {
                "VCC": {
                    "class": "Power",
                    "connections": ["R1.1"]
                },
                "MID": {
                    "class": "Default",
                    "connections": ["R1.2", "R2.1", "D1.2"]
                },
                "GND": {
                    "class": "Power",
                    "connections": ["R2.2", "D1.1"]
                }
            }
        }
        (dump_dir / "design.json").write_text(json.dumps(design_data, indent=2), encoding="utf-8")

        # ---------------------------------------------------------
        # Step 6: Compile Schematic & ERC
        # ---------------------------------------------------------
        compile_res = compile_schematic(project_dir, run_erc=False)
        assert compile_res.get("success") is True, f"Schematic compilation failed: {compile_res}"
        sch_file = project_dir / f"{project_name}.kicad_sch"
        assert sch_file.exists(), f"Expected schematic file {sch_file} does not exist"

        # ---------------------------------------------------------
        # Step 7: Synchronize Schematic Netlist to PCB Layout
        # ---------------------------------------------------------
        sync_res = sync_schematic_to_pcb(project_dir)
        assert sync_res.get("success") is True, f"PCB sync failed: {sync_res}"

        # ---------------------------------------------------------
        # Step 8: Planar Placement & Simulated Annealing Floorplan
        # ---------------------------------------------------------
        opt_res = optimize_planar_layout(project_dir, steps=500, initial_temp=50.0, commit=True)
        assert opt_res.get("success") is True, f"Planar layout optimization failed: {opt_res}"
        assert (dump_dir / "ops.json").exists()
        assert opt_res.get("overlaps", 0) == 0, f"Expected 0 overlaps after placement: {opt_res}"

        # ---------------------------------------------------------
        # Step 9: Gatekeeper Route-Readiness Proof Audit
        # ---------------------------------------------------------
        audit_res = placement_audit(project_dir)
        assert audit_res.get("success") is True, f"Gatekeeper audit failed: {audit_res}"
        assert audit_res.get("overlap_count", 0) == 0

        # ---------------------------------------------------------
        # Step 11: Export Manufacturing Release (Gerber, Drill, BOM, CPL)
        # ---------------------------------------------------------
        export_res = export_production_files(project_dir)
        assert export_res.get("success") is True, f"JLCPCB export failed: {export_res}"

        prod_dir = project_dir / "production_output"
        assert (prod_dir / f"{project_name}_gerbers.zip").exists()
        assert (prod_dir / f"{project_name}_bom_jlcpcb.csv").exists()
        assert (prod_dir / f"{project_name}_cpl_jlcpcb.csv").exists()
