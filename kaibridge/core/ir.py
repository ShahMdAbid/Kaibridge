"""
kaibridge/core/ir.py -- Formal Proof-Carrying Intermediate Representation (BoardIR)
and Pre-Flight Invariant Gates for Kaibridge 3.0.

Core Tenets:
- Exact integer database units (KiCad nanometers, 1 unit = 1 nm, 1 mm = 1,000,000 nm).
- Immutable, content-hashed domain models.
- Pre-flight algebraic invariant gates (E0 through E3).
- Contract-first placement envelopes and reservations.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any

# 1 mm in KiCad internal nanometer units
NM_PER_MM = 1_000_000
UM_PER_MM = 1_000


def mm_to_nm(mm: float) -> int:
    """Converts millimeters to integer nanometers."""
    return round(mm * NM_PER_MM)


def nm_to_mm(nm: int) -> float:
    """Converts integer nanometers to millimeters."""
    return float(nm) / NM_PER_MM


def mm_to_um(mm: float) -> int:
    """Converts millimeters to integer micrometers."""
    return round(mm * UM_PER_MM)


def um_to_mm(um: int) -> float:
    """Converts integer micrometers to millimeters."""
    return float(um) / UM_PER_MM


class ReservationType(str, Enum):
    ASSEMBLY_EXCLUSION = "assembly_exclusion"
    COPPER_EXCLUSION = "copper_exclusion"
    OWNED_ESCAPE_LANE = "owned_escape_lane"
    REFERENCE_COPPER_PRESERVE = "reference_copper_preserve"
    ALLOWED_THROUGH_VIA_CELL = "allowed_through_via_cell"
    ANTENNA_KEEPOUT = "antenna_keepout"
    ISOLATION_BARRIER = "isolation_barrier"


class LayerType(str, Enum):
    SIGNAL = "signal"
    POWER = "power"
    MIXED = "mixed"


@dataclass(frozen=True)
class Point2D:
    """Exact integer coordinate in nanometers."""
    x: int
    y: int

    @classmethod
    def from_mm(cls, x_mm: float, y_mm: float) -> Point2D:
        return cls(x=mm_to_nm(x_mm), y=mm_to_nm(y_mm))

    def to_mm(self) -> Tuple[float, float]:
        return (nm_to_mm(self.x), nm_to_mm(self.y))


@dataclass(frozen=True)
class PadGeometry:
    """Physical pad description in integer nanometers."""
    pad_num: str
    shape: str  # rect | circle | oval | roundrect
    pos: Point2D
    size: Point2D
    net_name: str
    pin_type: str = "passive"  # power_in | power_out | input | output | passive
    drill_nm: int = 0


@dataclass(frozen=True)
class ComponentInstance:
    """Physical component envelope in BoardIR."""
    ref: str
    symbol_id: str
    footprint_id: str
    pos: Point2D
    rotation_deg: float
    side: str  # top | bottom
    pads: Tuple[PadGeometry, ...]
    courtyard_polygon_nm: Tuple[Point2D, ...]
    mechanical_lock: bool = False
    manufacturer_keepouts: Tuple[Tuple[Point2D, ...], ...] = field(default_factory=tuple)

    @property
    def pad_dict(self) -> Dict[str, PadGeometry]:
        return {p.pad_num: p for p in self.pads}


@dataclass(frozen=True)
class NetHyperedge:
    """Logical & physical net contract."""
    name: str
    terminals: Tuple[Tuple[str, str], ...]  # Tuple of (Ref, PadNum)
    voltage_domain_v: float = 0.0
    dc_current_ma: float = 10.0
    is_power: bool = False
    is_ground: bool = False
    allowed_layers: Tuple[str, ...] = ("F.Cu", "B.Cu")
    required_reference_layer: str = "In1.Cu"


@dataclass(frozen=True)
class Reservation:
    """Layer-specific spatial reservation."""
    owner_ref: str
    layer: str
    reservation_type: ReservationType
    polygon_nm: Tuple[Point2D, ...]
    admitted_nets: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CircuitMotifInstance:
    """Electromagnetic circuit envelope (e.g. decoupling loop, crystal cell)."""
    motif_id: str
    motif_type: str  # decoupling_shunt | crystal_tank | switching_cell | diff_pair
    primary_ic_ref: str
    companion_refs: Tuple[str, ...]
    supply_net: str
    return_net: str
    target_loop_inductance_nh: float
    escape_ports: Tuple[Point2D, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProcessProfile:
    """Fabrication process constraints (e.g. JLCPCB 2/4-layer capabilities)."""
    name: str
    layers: int
    min_track_width_nm: int
    min_clearance_nm: int
    min_drill_nm: int
    min_annular_ring_nm: int
    board_edge_clearance_nm: int

    @classmethod
    def jlcpcb_4layer_standard(cls) -> ProcessProfile:
        return cls(
            name="JLCPCB_4Layer_Standard",
            layers=4,
            min_track_width_nm=mm_to_nm(0.09),    # 0.09mm
            min_clearance_nm=mm_to_nm(0.09),      # 0.09mm
            min_drill_nm=mm_to_nm(0.30),          # 0.30mm
            min_annular_ring_nm=mm_to_nm(0.13),   # 0.13mm
            board_edge_clearance_nm=mm_to_nm(0.20)
        )

    @classmethod
    def jlcpcb_2layer_standard(cls) -> ProcessProfile:
        return cls(
            name="JLCPCB_2Layer_Standard",
            layers=2,
            min_track_width_nm=mm_to_nm(0.127),   # 0.127mm
            min_clearance_nm=mm_to_nm(0.127),     # 0.127mm
            min_drill_nm=mm_to_nm(0.30),          # 0.30mm
            min_annular_ring_nm=mm_to_nm(0.13),   # 0.13mm
            board_edge_clearance_nm=mm_to_nm(0.20)
        )


@dataclass(frozen=True)
class Certificate:
    """Constructive cryptographic or algebraic proof certificate."""
    invariant_id: str  # E0, E1, E2, E3, etc.
    passed: bool
    witness_data: Dict[str, Any]
    error_message: Optional[str] = None


@dataclass(frozen=True)
class BoardIR:
    """Authoritative, immutable Proof-Carrying Board Intermediate Representation."""
    design_id: str
    revision: int
    process: ProcessProfile
    outline_polygon_nm: Tuple[Point2D, ...]
    components: Tuple[ComponentInstance, ...]
    nets: Tuple[NetHyperedge, ...]
    reservations: Tuple[Reservation, ...] = field(default_factory=tuple)
    motifs: Tuple[CircuitMotifInstance, ...] = field(default_factory=tuple)
    certificates: Tuple[Certificate, ...] = field(default_factory=tuple)

    @property
    def content_hash(self) -> str:
        """Deterministic SHA-256 fingerprint of the board state."""
        h = hashlib.sha256()
        h.update(self.design_id.encode("utf-8"))
        h.update(str(self.revision).encode("utf-8"))
        h.update(self.process.name.encode("utf-8"))
        for c in self.components:
            h.update(f"{c.ref}:{c.pos.x}:{c.pos.y}:{c.rotation_deg}:{c.side}".encode("utf-8"))
        for n in self.nets:
            h.update(f"{n.name}:{len(n.terminals)}".encode("utf-8"))
        return h.hexdigest()


# ---------------------------------------------------------------------------
# Pre-Flight Invariant Checkers (E0 - E3)
# ---------------------------------------------------------------------------

def verify_e0_requirements_complete(ir: BoardIR) -> Certificate:
    """E0: Operating requirement completeness."""
    missing: List[str] = []
    if not ir.design_id:
        missing.append("design_id is empty")
    if len(ir.outline_polygon_nm) < 3:
        missing.append("outline has fewer than 3 vertices")
    if len(ir.components) == 0:
        missing.append("no components instantiated")
    if len(ir.nets) == 0:
        missing.append("no nets defined")

    passed = len(missing) == 0
    return Certificate(
        invariant_id="E0_REQUIREMENTS_COMPLETE",
        passed=passed,
        witness_data={"component_count": len(ir.components), "net_count": len(ir.nets)},
        error_message="; ".join(missing) if not passed else None
    )


def verify_e1_netlist_parity(ir: BoardIR) -> Certificate:
    """E1: Netlist parity & pad mapping (every declared terminal must map to a physical pad)."""
    comp_map = {c.ref: c for c in ir.components}
    unmapped_terminals: List[str] = []

    for net in ir.nets:
        for ref, pad_num in net.terminals:
            if ref not in comp_map:
                unmapped_terminals.append(f"Component '{ref}' not found for net '{net.name}'")
            else:
                comp = comp_map[ref]
                if pad_num not in comp.pad_dict:
                    unmapped_terminals.append(f"Pad '{pad_num}' of '{ref}' not found for net '{net.name}'")

    passed = len(unmapped_terminals) == 0
    return Certificate(
        invariant_id="E1_NETLIST_PARITY",
        passed=passed,
        witness_data={"unmapped_count": len(unmapped_terminals)},
        error_message="; ".join(unmapped_terminals[:10]) if not passed else None
    )


def verify_e2_process_compatibility(ir: BoardIR, default_track_w_nm: int, default_clearance_nm: int) -> Certificate:
    """E2: Process capability constraints (widths & clearances must meet fab floors)."""
    violations: List[str] = []
    if default_track_w_nm < ir.process.min_track_width_nm:
        violations.append(
            f"Nominal track width {nm_to_mm(default_track_w_nm):.4f}mm < fab minimum {nm_to_mm(ir.process.min_track_width_nm):.4f}mm"
        )
    if default_clearance_nm < ir.process.min_clearance_nm:
        violations.append(
            f"Nominal clearance {nm_to_mm(default_clearance_nm):.4f}mm < fab minimum {nm_to_mm(ir.process.min_clearance_nm):.4f}mm"
        )

    passed = len(violations) == 0
    return Certificate(
        invariant_id="E2_PROCESS_COMPATIBILITY",
        passed=passed,
        witness_data={"process": ir.process.name, "min_track_mm": nm_to_mm(ir.process.min_track_width_nm)},
        error_message="; ".join(violations) if not passed else None
    )


def verify_e3_local_entry_solvability(
    comp: ComponentInstance,
    track_w_nm: int,
    clearance_nm: int
) -> Tuple[bool, List[str]]:
    """
    E3: Evaluates exact pad-pitch escape clearance feasibility.
    
    Formula from Superbrain Spec Section 6.1:
    1. Centered escape from a pad alongside a neighbor pad:
       w <= 2P - a - 2s
       where:
         P = center-to-center pad pitch
         a = neighbor pad width
         s = required clearance
         w = escape track width
    """
    violations: List[str] = []
    pads = comp.pads
    n = len(pads)
    if n < 2:
        return True, []

    # Sort pads by position to identify adjacent pairs on each edge
    for i in range(n):
        for j in range(i + 1, n):
            p1 = pads[i]
            p2 = pads[j]
            dx = abs(p1.pos.x - p2.pos.x)
            dy = abs(p1.pos.y - p2.pos.y)
            dist = (dx * dx + dy * dy) ** 0.5

            # If pads are adjacent (e.g. distance < 1.5mm)
            if 0 < dist < mm_to_nm(1.5):
                # Pitch P is center-to-center distance
                pitch = dist
                # Approximate pad width 'a' along direction of separation
                pad_width = min(p2.size.x, p2.size.y)
                # Max permissible escape track width
                max_w = 2 * pitch - pad_width - 2 * clearance_nm

                if track_w_nm > max_w:
                    violations.append(
                        f"Pad entry deadlock at {comp.ref}.{p1.pad_num} <-> {comp.ref}.{p2.pad_num}: "
                        f"pitch={nm_to_mm(int(pitch)):.3f}mm, pad_w={nm_to_mm(pad_width):.3f}mm, "
                        f"req_clearance={nm_to_mm(clearance_nm):.3f}mm => max allowable track={nm_to_mm(int(max_w)):.3f}mm, "
                        f"but actual track={nm_to_mm(track_w_nm):.3f}mm"
                    )

    passed = len(violations) == 0
    return passed, violations
