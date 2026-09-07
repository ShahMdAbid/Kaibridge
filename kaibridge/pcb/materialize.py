"""
kaibridge/pcb/materialize.py -- Procedural Materializer for Characterized Circuit Motifs.

Translates high-level CircuitMotifInstance objects (DecouplingEnvelope, CrystalTankEnvelope, EscapeStub)
into declarative, locked layout operations (ops.json) executed via layout.py.
All pre-routed local copper and vias are flagged with locked: True to ensure Freerouting
treats them as immutable obstacles and never rips them up.
"""
from __future__ import annotations

from typing import Dict, List, Any
from kaibridge.core.ir import nm_to_mm, Point2D
from kaibridge.core.motifs import DecouplingEnvelope, CrystalTankEnvelope, EscapeStub


def materialize_decoupling_envelope(
    envelope: DecouplingEnvelope,
    supply_net: str,
    ground_net: str = "GND",
    track_width_mm: float = 0.25,
    via_dia_mm: float = 0.60,
    via_drill_mm: float = 0.30
) -> List[Dict[str, Any]]:
    """
    Generates declarative ops to instantiate a collinear shunt decoupling capacitor,
    including pre-routed power branch and companion ground return via.
    """
    ox, oy = envelope.cap_origin.to_mm()
    qs_x, qs_y = envelope.supply_pad_pos.to_mm()
    qg_x, qg_y = envelope.ground_pad_pos.to_mm()
    vx, vy = envelope.ground_via_pos.to_mm()

    ops: List[Dict[str, Any]] = [
        # 1. Place & Lock Decoupling Capacitor
        {
            "op": "footprint.place",
            "ref": envelope.cap_ref,
            "x": ox,
            "y": oy,
            "rot": envelope.cap_rotation_deg,
            "layer": "F.Cu",
            "locked": True
        },
        # 2. Add Ground Return Via adjacent to Ground Pad
        {
            "op": "via.add",
            "x": vx,
            "y": vy,
            "diameter": via_dia_mm,
            "drill": via_drill_mm,
            "net": ground_net
        },
        # 3. Pre-route short low-inductance connection from Ground Pad to Ground Via
        {
            "op": "track.add",
            "x1": qg_x,
            "y1": qg_y,
            "x2": vx,
            "y2": vy,
            "width": track_width_mm,
            "layer": "F.Cu",
            "net": ground_net
        }
    ]

    return ops


def materialize_crystal_tank(
    envelope: CrystalTankEnvelope,
    osc_in_net: str,
    osc_out_net: str,
    ground_net: str = "GND",
    track_width_mm: float = 0.20,
    via_dia_mm: float = 0.60,
    via_drill_mm: float = 0.30
) -> List[Dict[str, Any]]:
    """
    Generates declarative ops to instantiate a symmetrical crystal tank:
    Crystal + 2 Load Capacitors + central GND return via.
    """
    yx, yy = envelope.crystal_origin.to_mm()
    c1x, c1y = envelope.c_load1_origin.to_mm()
    c2x, c2y = envelope.c_load2_origin.to_mm()
    vx, vy = envelope.gnd_via_pos.to_mm()

    ops: List[Dict[str, Any]] = [
        # 1. Place & Lock Crystal
        {
            "op": "footprint.place",
            "ref": envelope.crystal_ref,
            "x": yx,
            "y": yy,
            "rot": envelope.crystal_rotation_deg,
            "layer": "F.Cu",
            "locked": True
        },
        # 2. Place & Lock Load Capacitor C1
        {
            "op": "footprint.place",
            "ref": envelope.c_load1_ref,
            "x": c1x,
            "y": c1y,
            "rot": 90.0,
            "layer": "F.Cu",
            "locked": True
        },
        # 3. Place & Lock Load Capacitor C2
        {
            "op": "footprint.place",
            "ref": envelope.c_load2_ref,
            "x": c2x,
            "y": c2y,
            "rot": 90.0,
            "layer": "F.Cu",
            "locked": True
        },
        # 4. Central Ground Return Via
        {
            "op": "via.add",
            "x": vx,
            "y": vy,
            "diameter": via_dia_mm,
            "drill": via_drill_mm,
            "net": ground_net
        },
        # 5. Connect C1 Ground to Central Via
        {
            "op": "track.add",
            "x1": c1x,
            "y1": c1y,
            "x2": vx,
            "y2": vy,
            "width": track_width_mm,
            "layer": "F.Cu",
            "net": ground_net
        },
        # 6. Connect C2 Ground to Central Via
        {
            "op": "track.add",
            "x1": c2x,
            "y1": c2y,
            "x2": vx,
            "y2": vy,
            "width": track_width_mm,
            "layer": "F.Cu",
            "net": ground_net
        }
    ]

    return ops


def materialize_escape_stubs(
    stubs: List[EscapeStub],
    net_map: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Generates pre-routed necked-down escape tracks for fine-pitch pads.
    """
    ops: List[Dict[str, Any]] = []
    for stub in stubs:
        x1, y1 = stub.neck_start.to_mm()
        x2, y2 = stub.neck_end.to_mm()
        net_name = net_map.get(stub.pad_num, "")

        ops.append({
            "op": "track.add",
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": nm_to_mm(stub.neck_width_nm),
            "layer": "F.Cu",
            "net": net_name
        })

    return ops
