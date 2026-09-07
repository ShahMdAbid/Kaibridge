"""
kaibridge/core/compiler.py -- 4-Stage Staged Compiler & Proof-Carrying Hardware Synthesis.

Implements Milestone E from Superbrain Specification:
- Section 7.3: Four physical synthesis stages, one residual job:
    Stage 1: Critical circuit construction (decoupling loops, crystals, switching cells).
    Stage 2: Escape and bridge construction (stubs and <= 3.0mm B.Cu bridges).
    Stage 3: Constrained residual autorouting (single bounded Freerouting job).
    Stage 4: Plane realization and release verification (KiCad DRC).
- Section 8.6: compile_board() with fail-closed invariant certificates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from kaibridge.core.ir import (
    BoardIR, Certificate, ProcessProfile, mm_to_nm, nm_to_mm,
    verify_e0_requirements_complete,
    verify_e1_netlist_parity,
    verify_e2_process_compatibility,
    verify_e3_local_entry_solvability
)
from kaibridge.pcb.layout import apply_ops
from kaibridge.pcb.router import route_board, add_ground_plane
from kaibridge.pcb.drc import run_drc


@dataclass(frozen=True)
class CompilationResult:
    """Atomic proof-carrying compilation outcome."""
    success: bool
    stage_reached: int
    drc_clean: bool
    unconnected_count: int
    clearance_errors: int
    warnings_count: int
    certificates: Tuple[Certificate, ...]
    execution_time_sec: float
    message: str


def compile_board(
    project_dir: str | Path,
    board_ir: BoardIR,
    stage1_ops: Optional[List[Dict[str, Any]]] = None,
    stage2_ops: Optional[List[Dict[str, Any]]] = None,
    layers: int = 2,
    pour_gnd: bool = True,
    via_costs: int = 1000,
    router_timeout_sec: int = 180
) -> CompilationResult:
    """
    Compiles hardware through the 4-stage Proof-Carrying Compiler pipeline.
    
    1. Pre-Flight Verification: Evaluates E0, E1, E2, E3. Fail-closed if violated.
    2. Stage 1: Materializes critical circuit motifs (locked: True).
    3. Stage 2: Materializes fine-pitch escape stubs & approved 2-layer bridges.
    4. Stage 3: Dispatches single bounded residual routing job to Freerouting.
    5. Stage 4: Pours reference planes and runs KiCad DRC release gate.
    """
    t_start = time.time()
    proj_path = Path(project_dir).resolve()
    certificates: List[Certificate] = []

    # -----------------------------------------------------------------------
    # Pre-Flight Invariant Gates (E0 - E3)
    # -----------------------------------------------------------------------
    # E0: Requirements Completeness
    c_e0 = verify_e0_requirements_complete(board_ir)
    certificates.append(c_e0)
    if not c_e0.passed:
        return CompilationResult(
            success=False,
            stage_reached=0,
            drc_clean=False,
            unconnected_count=-1,
            clearance_errors=-1,
            warnings_count=-1,
            certificates=tuple(certificates),
            execution_time_sec=time.time() - t_start,
            message=f"Pre-flight E0 failed: {c_e0.error_message}"
        )

    # E1: Netlist Parity
    c_e1 = verify_e1_netlist_parity(board_ir)
    certificates.append(c_e1)
    if not c_e1.passed:
        return CompilationResult(
            success=False,
            stage_reached=0,
            drc_clean=False,
            unconnected_count=-1,
            clearance_errors=-1,
            warnings_count=-1,
            certificates=tuple(certificates),
            execution_time_sec=time.time() - t_start,
            message=f"Pre-flight E1 failed: {c_e1.error_message}"
        )

    # E2: Process Compatibility
    c_e2 = verify_e2_process_compatibility(
        board_ir,
        default_track_w_nm=mm_to_nm(0.25),
        default_clearance_nm=mm_to_nm(0.20)
    )
    certificates.append(c_e2)
    if not c_e2.passed:
        return CompilationResult(
            success=False,
            stage_reached=0,
            drc_clean=False,
            unconnected_count=-1,
            clearance_errors=-1,
            warnings_count=-1,
            certificates=tuple(certificates),
            execution_time_sec=time.time() - t_start,
            message=f"Pre-flight E2 failed: {c_e2.error_message}"
        )

    # E3: Pad-Pitch Escape Solvability
    for comp in board_ir.components:
        passed_e3, e3_errs = verify_e3_local_entry_solvability(
            comp,
            track_w_nm=mm_to_nm(0.25),
            clearance_nm=mm_to_nm(0.20)
        )
        c_e3 = Certificate(
            invariant_id=f"E3_{comp.ref}",
            passed=passed_e3,
            witness_data={"ref": comp.ref},
            error_message="; ".join(e3_errs) if not passed_e3 else None
        )
        certificates.append(c_e3)
        if not passed_e3:
            return CompilationResult(
                success=False,
                stage_reached=0,
                drc_clean=False,
                unconnected_count=-1,
                clearance_errors=-1,
                warnings_count=-1,
                certificates=tuple(certificates),
                execution_time_sec=time.time() - t_start,
                message=f"Pre-flight E3 failed at {comp.ref}: {c_e3.error_message}"
            )

    # -----------------------------------------------------------------------
    # Stage 1: Materialize Critical Circuits (Decoupling, Crystals, Switching)
    # -----------------------------------------------------------------------
    if stage1_ops:
        res1 = apply_ops(proj_path, stage1_ops)
        if not res1.get("success", False):
            return CompilationResult(
                success=False,
                stage_reached=1,
                drc_clean=False,
                unconnected_count=-1,
                clearance_errors=-1,
                warnings_count=-1,
                certificates=tuple(certificates),
                execution_time_sec=time.time() - t_start,
                message=f"Stage 1 motif application failed: {res1.get('error')}"
            )

    # -----------------------------------------------------------------------
    # Stage 2: Materialize Escapes & Bridges
    # -----------------------------------------------------------------------
    if stage2_ops:
        res2 = apply_ops(proj_path, stage2_ops)
        if not res2.get("success", False):
            return CompilationResult(
                success=False,
                stage_reached=2,
                drc_clean=False,
                unconnected_count=-1,
                clearance_errors=-1,
                warnings_count=-1,
                certificates=tuple(certificates),
                execution_time_sec=time.time() - t_start,
                message=f"Stage 2 escape/bridge application failed: {res2.get('error')}"
            )

    # -----------------------------------------------------------------------
    # Stage 3: Constrained Residual Autorouting (Single Bounded Job)
    # -----------------------------------------------------------------------
    route_res = route_board(
        project_dir=proj_path,
        track_width_mm=0.25,
        timeout_sec=router_timeout_sec,
        copper_edge_clearance_um=150,
        strict_drc=True,
        via_costs=via_costs,
        use_daemon=True
    )

    if not route_res.get("success", False):
        return CompilationResult(
            success=False,
            stage_reached=3,
            drc_clean=False,
            unconnected_count=-1,
            clearance_errors=-1,
            warnings_count=-1,
            certificates=tuple(certificates),
            execution_time_sec=time.time() - t_start,
            message=f"Stage 3 Freerouting execution failed: {route_res.get('error')}"
        )

    # -----------------------------------------------------------------------
    # Stage 4: Plane Realization & DRC Release Verification
    # -----------------------------------------------------------------------
    if pour_gnd:
        if layers == 4:
            add_ground_plane(proj_path, net="GND", layer="In1.Cu", clearance_mm=0.3)
            p_net = "+3V3"
            for c in ("+3V3", "3V3", "+5V", "5V", "VCC", "VDD", "VBUS", "VIN", "VBAT"):
                if c in ir.nets:
                    p_net = c
                    break
            add_ground_plane(proj_path, net=p_net, layer="In2.Cu", clearance_mm=0.3)
            add_ground_plane(proj_path, net="GND", layer="B.Cu", clearance_mm=0.3)
        else:
            add_ground_plane(proj_path, net="GND", layer="B.Cu", clearance_mm=0.3)

    drc_res = run_drc(proj_path)
    drc_clean = drc_res.get("success", False)
    unconnected = drc_res.get("unconnected_count", 0)
    clearances = drc_res.get("clearance_errors", 0)
    warnings = len(drc_res.get("warnings", []))

    total_time = time.time() - t_start

    return CompilationResult(
        success=drc_clean and (unconnected == 0) and (clearances == 0),
        stage_reached=4,
        drc_clean=drc_clean,
        unconnected_count=unconnected,
        clearance_errors=clearances,
        warnings_count=warnings,
        certificates=tuple(certificates),
        execution_time_sec=round(total_time, 2),
        message="Board successfully compiled and verified with 0 DRC violations!" if (unconnected == 0 and clearances == 0) else f"DRC completed with {unconnected} unconnected, {clearances} clearance errors."
    )
