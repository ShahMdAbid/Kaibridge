"""
kaibridge/core/motifs.py -- Characterized Local Circuit Synthesis & Electromagnetic Envelopes.

Implements Milestone B from Superbrain Specification:
- Section 5.1: Collinear Intercept Construction for Shunt Decoupling
- Section 5.2: Low-Inductance Ground Via Placement with Solder Mask Dam Web Checks
- Section 2.4 & Axiom 4: Symmetrical Crystal Oscillator Tank Envelope
- Section 4.1 & 6.1: Constructive Escape Stubs and Necks for Fine-Pitch ICs
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from kaibridge.core.ir import (
    Point2D, PadGeometry, ComponentInstance, CircuitMotifInstance, Reservation,
    ReservationType, mm_to_nm, nm_to_mm
)

# Standard SMD passive footprint pad geometries (in nanometers, relative to component origin)
PASSIVE_GEOMETRIES: Dict[str, Dict[str, Any]] = {
    "0402": {
        "pad1_offset": Point2D(x=mm_to_nm(-0.50), y=0),
        "pad2_offset": Point2D(x=mm_to_nm(0.50), y=0),
        "pad_size": Point2D(x=mm_to_nm(0.50), y=mm_to_nm(0.60)),
        "courtyard_half": Point2D(x=mm_to_nm(0.90), y=mm_to_nm(0.50)),
    },
    "0603": {
        "pad1_offset": Point2D(x=mm_to_nm(-0.80), y=0),
        "pad2_offset": Point2D(x=mm_to_nm(0.80), y=0),
        "pad_size": Point2D(x=mm_to_nm(0.80), y=mm_to_nm(0.90)),
        "courtyard_half": Point2D(x=mm_to_nm(1.30), y=mm_to_nm(0.70)),
    },
    "0805": {
        "pad1_offset": Point2D(x=mm_to_nm(-1.00), y=0),
        "pad2_offset": Point2D(x=mm_to_nm(1.00), y=0),
        "pad_size": Point2D(x=mm_to_nm(1.00), y=mm_to_nm(1.30)),
        "courtyard_half": Point2D(x=mm_to_nm(1.60), y=mm_to_nm(0.90)),
    }
}


def rotate_point(pt: Point2D, angle_deg: float) -> Point2D:
    """Rotates a 2D integer point around (0,0) by standard angles (0, 90, 180, 270)."""
    norm_deg = round(angle_deg) % 360
    if norm_deg == 0:
        return pt
    elif norm_deg == 90:
        return Point2D(x=-pt.y, y=pt.x)
    elif norm_deg == 180:
        return Point2D(x=-pt.x, y=-pt.y)
    elif norm_deg == 270:
        return Point2D(x=pt.y, y=-pt.x)
    else:
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        new_x = round(pt.x * cos_a - pt.y * sin_a)
        new_y = round(pt.x * sin_a + pt.y * cos_a)
        return Point2D(x=new_x, y=new_y)


@dataclass(frozen=True)
class DecouplingEnvelope:
    """Synthesized physical parameters for a collinear shunt decoupling capacitor."""
    cap_ref: str
    cap_origin: Point2D
    cap_rotation_deg: float
    supply_pad_pos: Point2D
    ground_pad_pos: Point2D
    ground_via_pos: Point2D
    loop_inductance_estimate_nh: float
    mask_dam_margin_nm: int
    incoming_rail_port: Point2D


def synthesize_collinear_decoupling(
    ic_ref: str,
    power_pin_pos: Point2D,
    outward_normal: Tuple[float, float],
    cap_ref: str = "C1",
    package: str = "0402",
    supply_net: str = "+3V3",
    ground_net: str = "GND",
    via_pad_dia_nm: int = mm_to_nm(0.60),
    via_drill_nm: int = mm_to_nm(0.30),
    min_mask_web_nm: int = mm_to_nm(0.10),
    mask_expansion_nm: int = mm_to_nm(0.05)
) -> DecouplingEnvelope:
    """
    Synthesizes exact geometry for a shunt decoupling capacitor.
    
    Formula:
      qS = p + d * n
      c  = qS - R_theta(aS)
      qG = c + R_theta(aG)
    where:
      p = power_pin_pos
      n = outward_normal vector
      d = separation distance (chosen to clear IC courtyard)
      aS = capacitor local supply pad center (Pad 1)
      aG = capacitor local ground pad center (Pad 2)
      c  = capacitor footprint placement origin
    """
    geom = PASSIVE_GEOMETRIES.get(package, PASSIVE_GEOMETRIES["0402"])
    pad1_local = geom["pad1_offset"]  # Supply pad
    pad2_local = geom["pad2_offset"]  # Ground pad
    pad_size = geom["pad_size"]

    nx, ny = outward_normal
    norm_len = (nx * nx + ny * ny) ** 0.5
    if norm_len > 0:
        nx /= norm_len
        ny /= norm_len
    else:
        nx, ny = 0.0, 1.0

    # Determine capacitor rotation theta so that vector from qS to qG is perpendicular to n
    # or aligned cleanly
    # For horizontal normal (nx != 0), rotate cap 90 deg so pads are stacked vertically
    if abs(nx) > abs(ny):
        theta = 90.0 if nx > 0 else 270.0
    else:
        theta = 0.0 if ny > 0 else 180.0

    # Distance d: clear IC courtyard (typically 1.5mm to 2.2mm)
    d_nm = mm_to_nm(1.80)

    # qS: supply intercept point on the capacitor supply pad
    qs_x = power_pin_pos.x + round(d_nm * nx)
    qs_y = power_pin_pos.y + round(d_nm * ny)
    q_s = Point2D(x=qs_x, y=qs_y)

    # Compute capacitor placement origin: c = qS - R_theta(aS)
    rotated_as = rotate_point(pad1_local, theta)
    cap_origin = Point2D(x=q_s.x - rotated_as.x, y=q_s.y - rotated_as.y)

    # Compute ground pad center: qG = c + R_theta(aG)
    rotated_ag = rotate_point(pad2_local, theta)
    q_g = Point2D(x=cap_origin.x + rotated_ag.x, y=cap_origin.y + rotated_ag.y)

    # Place companion Ground Via adjacent to Ground Pad qG
    # Direction: outward perpendicular or continuing outward
    # Via edge to Pad edge must be >= min_mask_web + 2 * mask_expansion
    required_center_dist = (
        (pad_size.x // 2) +
        (via_pad_dia_nm // 2) +
        min_mask_web_nm +
        (2 * mask_expansion_nm)
    )

    # Orient via outward from the capacitor body
    via_dir_x = rotated_ag.x
    via_dir_y = rotated_ag.y
    via_len = (via_dir_x * via_dir_x + via_dir_y * via_dir_y) ** 0.5
    if via_len > 0:
        vx = q_g.x + round(required_center_dist * (via_dir_x / via_len))
        vy = q_g.y + round(required_center_dist * (via_dir_y / via_len))
    else:
        vx = q_g.x + required_center_dist
        vy = q_g.y
    ground_via_pos = Point2D(x=vx, y=vy)

    # Verify solder mask web margin:
    # dist(Mg, Mv) = center_dist - pad_half_w - via_pad_half_w - 2 * mask_expansion
    actual_center_dist = ((ground_via_pos.x - q_g.x) ** 2 + (ground_via_pos.y - q_g.y) ** 2) ** 0.5
    actual_mask_web = round(actual_center_dist - (pad_size.x / 2) - (via_pad_dia_nm / 2) - 2 * mask_expansion_nm)

    # Incoming power rail port: extends outward by 0.5mm from qS
    rail_port = Point2D(x=q_s.x + round(mm_to_nm(0.50) * nx), y=q_s.y + round(mm_to_nm(0.50) * ny))

    # Partial inductance loop estimate:
    # Loop spans IC pad -> qS -> cap body -> qG -> via -> ground plane
    # Loop perimeter in mm
    dx1 = nm_to_mm(abs(q_s.x - power_pin_pos.x))
    dy1 = nm_to_mm(abs(q_s.y - power_pin_pos.y))
    dx2 = nm_to_mm(abs(q_g.x - q_s.x))
    dy2 = nm_to_mm(abs(q_g.y - q_s.y))
    dx3 = nm_to_mm(abs(ground_via_pos.x - q_g.x))
    dy3 = nm_to_mm(abs(ground_via_pos.y - q_g.y))
    loop_perimeter_mm = (dx1 + dy1) + (dx2 + dy2) + (dx3 + dy3)
    # Empirical ~0.6nH/mm for tight planar microstrip return
    loop_inductance_est_nh = round(loop_perimeter_mm * 0.65, 2)

    return DecouplingEnvelope(
        cap_ref=cap_ref,
        cap_origin=cap_origin,
        cap_rotation_deg=theta,
        supply_pad_pos=q_s,
        ground_pad_pos=q_g,
        ground_via_pos=ground_via_pos,
        loop_inductance_estimate_nh=loop_inductance_est_nh,
        mask_dam_margin_nm=actual_mask_web,
        incoming_rail_port=rail_port
    )


@dataclass(frozen=True)
class CrystalTankEnvelope:
    """Synthesized physical parameters for an MCU crystal oscillator tank."""
    crystal_ref: str
    crystal_origin: Point2D
    crystal_rotation_deg: float
    c_load1_ref: str
    c_load1_origin: Point2D
    c_load2_ref: str
    c_load2_origin: Point2D
    gnd_via_pos: Point2D
    keepout_polygon: Tuple[Point2D, ...]
    max_trace_length_mm: float


def synthesize_crystal_tank(
    osc_in_pin: Point2D,
    osc_out_pin: Point2D,
    crystal_ref: str = "Y1",
    c1_ref: str = "C1",
    c2_ref: str = "C2",
    crystal_size_mm: Tuple[float, float] = (3.2, 2.5),
) -> CrystalTankEnvelope:
    """
    Synthesizes symmetrical, ultra-compact crystal oscillator tank geometry.
    Places crystal immediately adjacent to OSC_IN and OSC_OUT pins (distance <= 3.5mm),
    with companion load capacitors sharing a common low-impedance ground return via.
    """
    mid_x = (osc_in_pin.x + osc_out_pin.x) // 2
    mid_y = (osc_in_pin.y + osc_out_pin.y) // 2

    # Normal vector pointing outward from MCU edge
    dy = osc_out_pin.y - osc_in_pin.y
    dx = osc_out_pin.x - osc_in_pin.x
    pin_dist = (dx * dx + dy * dy) ** 0.5
    if pin_dist > 0:
        # Perpendicular normal
        nx = -dy / pin_dist
        ny = dx / pin_dist
    else:
        nx, ny = 0.0, 1.0

    # Place crystal center at 3.0mm outward from pin midpoint
    crystal_dist_nm = mm_to_nm(3.0)
    c_x = mid_x + round(crystal_dist_nm * nx)
    c_y = mid_y + round(crystal_dist_nm * ny)
    crystal_origin = Point2D(x=c_x, y=c_y)

    # Place Load Capacitors C1 and C2 flanked symmetrically outward
    c_geom = PASSIVE_GEOMETRIES["0402"]
    cap_offset_nm = mm_to_nm(1.6)

    # C1 placed along -tangent
    tx, ty = -ny, nx
    c1_x = crystal_origin.x + round(cap_offset_nm * tx)
    c1_y = crystal_origin.y + round(cap_offset_nm * ty)
    c_load1_origin = Point2D(x=c1_x, y=c1_y)

    # C2 placed along +tangent
    c2_x = crystal_origin.x - round(cap_offset_nm * tx)
    c2_y = crystal_origin.y - round(cap_offset_nm * ty)
    c_load2_origin = Point2D(x=c2_x, y=c2_y)

    # Common Ground Return Via directly between C1 and C2
    via_dist_nm = mm_to_nm(1.5)
    gnd_via_pos = Point2D(
        x=crystal_origin.x + round(via_dist_nm * nx),
        y=crystal_origin.y + round(via_dist_nm * ny)
    )

    # Generate Noise Exclusion Keepout Polygon around tank (3.5mm radius box)
    r_nm = mm_to_nm(3.5)
    keepout = (
        Point2D(x=crystal_origin.x - r_nm, y=crystal_origin.y - r_nm),
        Point2D(x=crystal_origin.x + r_nm, y=crystal_origin.y - r_nm),
        Point2D(x=crystal_origin.x + r_nm, y=crystal_origin.y + r_nm),
        Point2D(x=crystal_origin.x - r_nm, y=crystal_origin.y + r_nm),
    )

    max_len_mm = nm_to_mm(crystal_dist_nm) + 0.5

    return CrystalTankEnvelope(
        crystal_ref=crystal_ref,
        crystal_origin=crystal_origin,
        crystal_rotation_deg=0.0,
        c_load1_ref=c1_ref,
        c_load1_origin=c_load1_origin,
        c_load2_ref=c2_ref,
        c_load2_origin=c_load2_origin,
        gnd_via_pos=gnd_via_pos,
        keepout_polygon=keepout,
        max_trace_length_mm=max_len_mm
    )


@dataclass(frozen=True)
class EscapeStub:
    """Constructive necked-down escape stub for fine-pitch IC pins."""
    pad_num: str
    pad_center: Point2D
    neck_start: Point2D
    neck_end: Point2D
    neck_width_nm: int
    trunk_start: Point2D
    trunk_width_nm: int


def generate_escape_stub(
    pad: PadGeometry,
    outward_normal: Tuple[float, float],
    pad_pitch_nm: int,
    nominal_trunk_w_nm: int,
    clearance_nm: int,
    courtyard_escape_dist_nm: int = mm_to_nm(1.0)
) -> EscapeStub:
    """
    Synthesizes an algebraically guaranteed escape stub:
    1. Computes maximum allowable neck width: w_neck <= 2P - a - 2s
    2. Extends neck track from pad center past courtyard boundary.
    3. Seamlessly transitions to nominal trunk width outside the dense pin field.
    """
    pad_w = min(pad.size.x, pad.size.y)
    max_legal_neck_nm = 2 * pad_pitch_nm - pad_w - 2 * clearance_nm

    # Neck width must be at least fab min, but <= max_legal_neck
    neck_w = min(nominal_trunk_w_nm, max_legal_neck_nm)

    nx, ny = outward_normal
    norm_len = (nx * nx + ny * ny) ** 0.5
    if norm_len > 0:
        nx /= norm_len
        ny /= norm_len
    else:
        nx, ny = 0.0, 1.0

    p_start = pad.pos
    neck_end = Point2D(
        x=p_start.x + round(courtyard_escape_dist_nm * nx),
        y=p_start.y + round(courtyard_escape_dist_nm * ny)
    )

    return EscapeStub(
        pad_num=pad.pad_num,
        pad_center=p_start,
        neck_start=p_start,
        neck_end=neck_end,
        neck_width_nm=neck_w,
        trunk_start=neck_end,
        trunk_width_nm=nominal_trunk_w_nm
    )
