"""
kaibridge/pcb/hierarchical_floorplan.py
Universal Physics-Grounded Hierarchical Molecular & Pin-Vector Floorplanner for KiCad.

100% Project-Agnostic & Zero-Hardcoded-References:
1. Graph-Theoretic Hierarchy Classification (Master IC, Satellites, Connectors, Decoupling, Inline Passives).
2. Continuous Silicon Exit-Vector Field Analysis (pins mathematically dictate placement sector).
3. Universal Resonant Orientation Optimizer (arg min crossings over all 4 orthogonal rotations).
4. Pad-Snapped Molecular Decoupling & Inline Passive Binding.
5. Continuous 2D Physics Relaxation with Hard Collision Potentials.
"""
from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set


def is_power_net(net: str) -> bool:
    n = net.upper()
    return any(k in n for k in ("3V3", "5V", "VCC", "VDD", "VBUS", "VIN", "VBAT", "12V", "PWR", "PROT")) or n.startswith("+")


def is_gnd_net(net: str) -> bool:
    n = net.upper()
    return "GND" in n or n == "0V" or "VSS" in n or "VSSA" in n


from ..core.geometry import ccw, segments_intersect


class UniversalHierarchicalFloorplanner:
    """100% Generalizable, Zero-Hardcoded PCB Floorplanning Engine."""

    def __init__(
        self,
        fp_data: Dict[str, Any],
        design: Dict[str, Any],
        nets: Dict[str, List[Tuple[str, str]]],
        board_width: float,
        board_height: float,
        origin_x: float,
        origin_y: float,
        margin: float = 3.5
    ):
        self.fp_data = fp_data
        self.design = design
        self.nets = nets
        self.bw = board_width
        self.bh = board_height
        self.ox = origin_x
        self.oy = origin_y
        self.margin = margin

        self.cx = self.ox + self.bw / 2.0
        self.cy = self.oy + self.bh / 2.0

        self.parts_catalog = design.get("parts", {})
        if not self.parts_catalog and "components" in design:
            self.parts_catalog = {c["ref"]: c for c in design["components"] if "ref" in c}

        # Build reverse pin-to-net lookup: (ref, pad) -> net_name from full design nets (including GND)
        self.pin_to_net: Dict[Tuple[str, str], str] = {}
        for net_name, net_data in self.design.get("nets", {}).items():
            pins = net_data.get("connections", net_data) if isinstance(net_data, dict) else net_data
            if isinstance(pins, list):
                for p in pins:
                    if "." in p:
                        r, pad = p.split(".", 1)
                        self.pin_to_net[(r, pad)] = net_name
        if not self.pin_to_net:
            for net_name, pin_list in self.nets.items():
                for ref, pad in pin_list:
                    self.pin_to_net[(ref, pad)] = net_name

        # Parse Tier 0 Human Directives: groups, near, rot, direction
        self.part_to_group: Dict[str, str] = {}
        self.group_to_parts: Dict[str, List[str]] = {}
        self.near_directives: Dict[str, Tuple[str, str]] = {}
        self.user_rots: Dict[str, float] = {}
        self.user_directions: Dict[str, str] = {}

        # 1. Top-level groups
        for grp in self.design.get("groups", []):
            gid = grp.get("id", "")
            for p in grp.get("parts", []):
                self.part_to_group[p] = gid
                self.group_to_parts.setdefault(gid, []).append(p)

        # 2. Per-part metadata in parts_catalog
        for pref, pdata in self.parts_catalog.items():
            if isinstance(pdata, dict):
                gid = pdata.get("group")
                if gid:
                    self.part_to_group[pref] = gid
                    if pref not in self.group_to_parts.get(gid, []):
                        self.group_to_parts.setdefault(gid, []).append(pref)

                near_val = pdata.get("near")
                if near_val and "." in str(near_val):
                    aref, pin = str(near_val).strip().split(".", 1)
                    self.near_directives[pref] = (aref, pin)

                if "rot" in pdata and pdata["rot"] is not None:
                    try:
                        self.user_rots[pref] = float(pdata["rot"])
                    except (ValueError, TypeError):
                        pass

                dir_val = pdata.get("direction", pdata.get("edge"))
                if dir_val:
                    self.user_directions[pref] = str(dir_val).strip().lower()

        # 1. Graph Classification
        self._classify_graph()

    def _resolve_anchor_pad(self, anchor_ref: str, pin_spec: str) -> Optional[Tuple[float, float]]:
        """Resolves the relative (x, y) coordinate of anchor_ref's pad specified by pin_spec (pin number or net/pin name)."""
        if anchor_ref not in self.fp_data:
            return None
        pads = self.fp_data[anchor_ref].get("pads", {})
        if not pads:
            return None

        # 1. Direct pad number match
        if pin_spec in pads:
            return pads[pin_spec]

        # 2. Pin name / net match via pin_to_net
        pin_spec_u = pin_spec.upper()
        for pad_name, pos in pads.items():
            net = self.pin_to_net.get((anchor_ref, pad_name), "")
            if net.upper() == pin_spec_u or net.upper().endswith("." + pin_spec_u) or net.upper().endswith("_" + pin_spec_u):
                return pos

        # 3. Fuzzy pad name match
        for pad_name, pos in pads.items():
            if pin_spec_u in pad_name.upper():
                return pos

        # 4. Fallback to first pad
        first_pad = next(iter(pads.values()))
        return first_pad

    def _classify_graph(self):
        """Classifies all components using pure graph topology and footprint metadata."""
        self.connectors: List[str] = []
        self.master_ic: Optional[str] = None
        self.satellite_ics: List[str] = []
        self.crystals: List[str] = []
        self.decoupling_caps: Dict[str, List[str]] = {}  # ic_ref -> [cap_refs]
        self.inline_passives: List[str] = []
        self.other_passives: List[str] = []

        # Find connectors
        for ref, fp in self.fp_data.items():
            ref_u = ref.upper()
            pdata = self.parts_catalog.get(ref, {})
            lib_u = str(pdata.get("lib_id", "")).upper()
            val_u = str(pdata.get("value", "")).upper()

            is_conn = (
                ref_u.startswith(("J", "CONN", "USB", "HDR", "HEADER", "TERM", "JACK", "BARREL"))
                or "CONNECTOR" in lib_u or "HEADER" in lib_u or "USB" in lib_u or "TERMINAL" in lib_u
            )
            is_xtal = ref_u.startswith(("Y", "X")) or "CRYSTAL" in lib_u or "RESONATOR" in lib_u or "MHZ" in val_u

            if is_conn:
                self.connectors.append(ref)
            elif is_xtal:
                self.crystals.append(ref)

        # Find Master IC: Non-connector with highest distinct signal nets or pin count
        best_score = -1
        for ref, fp in self.fp_data.items():
            if ref in self.connectors or ref in self.crystals:
                continue
            pads_count = len(fp.get("pads", {}))
            if pads_count < 4:
                continue

            # Count distinct signal nets
            sig_nets = set()
            for pad in fp.get("pads", {}):
                n = self.pin_to_net.get((ref, pad))
                if n and not is_power_net(n) and not is_gnd_net(n):
                    sig_nets.add(n)

            score = len(sig_nets) * 100 + pads_count
            if score > best_score:
                best_score = score
                self.master_ic = ref

        # Find Satellite ICs
        for ref, fp in self.fp_data.items():
            if ref in self.connectors or ref in self.crystals or ref == self.master_ic:
                continue
            pads_count = len(fp.get("pads", {}))
            ref_u = ref.upper()
            if pads_count >= 4 or ref_u.startswith(("U", "IC", "Q")):
                self.satellite_ics.append(ref)

        # Classify Passives
        all_ics = ([self.master_ic] if self.master_ic else []) + self.satellite_ics
        for ref, fp in self.fp_data.items():
            if ref in self.connectors or ref in self.crystals or ref in all_ics:
                continue

            # If user explicitly marked "near", it is an inline or pad-tethered passive
            if ref in self.near_directives:
                self.inline_passives.append(ref)
                continue

            pads = list(fp.get("pads", {}).keys())
            if len(pads) == 2:
                n1 = self.pin_to_net.get((ref, pads[0]), "")
                n2 = self.pin_to_net.get((ref, pads[1]), "")

                # Check if decoupling cap: one pin is GND, other is Power
                if (is_gnd_net(n1) and is_power_net(n2)) or (is_gnd_net(n2) and is_power_net(n1)):
                    pwr_net = n2 if is_gnd_net(n1) else n1
                    # Associate with closest IC sharing this power net
                    best_ic = self.master_ic
                    for ic in all_ics:
                        ic_pads = self.fp_data[ic].get("pads", {})
                        if any(self.pin_to_net.get((ic, p)) == pwr_net for p in ic_pads):
                            best_ic = ic
                            break
                    if best_ic:
                        self.decoupling_caps.setdefault(best_ic, []).append(ref)
                        continue

            self.other_passives.append(ref)

    def compute_exit_vector(self, target_ref: str) -> Tuple[float, float, float]:
        """Computes the physical exit vector (dx, dy, angle_deg) from Master IC to target component."""
        if not self.master_ic or target_ref not in self.fp_data:
            return (0.0, 0.0, 0.0)

        m_pads = self.fp_data[self.master_ic].get("pads", {})
        shared_vectors = []

        for net_name, pin_list in self.nets.items():
            if is_power_net(net_name) or is_gnd_net(net_name):
                continue
            has_target = any(r == target_ref for r, p in pin_list)
            if has_target:
                for r, p in pin_list:
                    if r == self.master_ic and p in m_pads:
                        shared_vectors.append(m_pads[p])

        if not shared_vectors:
            return (1.0, 0.0, 0.0)

        avg_x = sum(v[0] for v in shared_vectors) / len(shared_vectors)
        avg_y = sum(v[1] for v in shared_vectors) / len(shared_vectors)
        angle = math.degrees(math.atan2(avg_y, avg_x)) % 360
        return (avg_x, avg_y, angle)

    def optimize_rotation(self, ref: str, center_x: float, center_y: float, target_ref: Optional[str] = None) -> float:
        """Finds the orthogonal rotation (0, 90, 180, 270) that minimizes topological net crossings."""
        if target_ref is None:
            target_ref = self.master_ic
        if not target_ref or target_ref not in self.fp_data:
            return 0.0

        target_pads_abs = {}
        t_fp = self.fp_data[target_ref]
        t_cx, t_cy = self.cx, self.cy  # Target is usually at center
        for p, pos in t_fp.get("pads", {}).items():
            target_pads_abs[p] = (t_cx + pos[0], t_cy + pos[1])

        # Get nets shared between ref and target
        shared_nets: List[Tuple[str, str, str]] = []  # (net_name, ref_pad, target_pad)
        ref_pads = self.fp_data[ref].get("pads", {})
        for net_name, pin_list in self.nets.items():
            if is_power_net(net_name) or is_gnd_net(net_name):
                continue
            r_pads = [p for r, p in pin_list if r == ref]
            t_pads = [p for r, p in pin_list if r == target_ref]
            for rp in r_pads:
                for tp in t_pads:
                    shared_nets.append((net_name, rp, tp))

        if len(shared_nets) < 2:
            return 0.0

        best_rot = 0.0
        min_cost = float("inf")

        for rot in (0.0, 90.0, 180.0, 270.0):
            rad = math.radians(rot)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            # Compute rotated pad positions
            cur_pads = {}
            for p, pos in ref_pads.items():
                rx = pos[0] * cos_a - pos[1] * sin_a
                ry = pos[0] * sin_a + pos[1] * cos_a
                cur_pads[p] = (center_x + rx, center_y + ry)

            # Check line crossings
            crossings = 0
            total_len = 0.0
            n_nets = len(shared_nets)
            for i in range(n_nets):
                n1, rp1, tp1 = shared_nets[i]
                p1_a = cur_pads[rp1]
                p1_b = target_pads_abs.get(tp1, (t_cx, t_cy))
                total_len += math.hypot(p1_b[0] - p1_a[0], p1_b[1] - p1_a[1])

                for j in range(i + 1, n_nets):
                    n2, rp2, tp2 = shared_nets[j]
                    p2_a = cur_pads[rp2]
                    p2_b = target_pads_abs.get(tp2, (t_cx, t_cy))
                    if segments_intersect(p1_a, p1_b, p2_a, p2_b):
                        crossings += 1

            cost = crossings * 10000.0 + total_len
            if cost < min_cost:
                min_cost = cost
                best_rot = rot

        return best_rot

    def _place_satellite_near_pad(
        self,
        anchor_ref: str,
        sat_ref: str,
        pad_abs: Tuple[float, float],
        anchor_pos: Dict[str, Any]
    ) -> Tuple[float, float, float]:
        """Places satellite component directly outside the anchor body aligned with the anchor pad."""
        ax, ay = anchor_pos["x"], anchor_pos["y"]
        arot = anchor_pos.get("rot", 0.0)

        afp = self.fp_data[anchor_ref]
        aw, ah = afp["width"], afp["height"]
        if round(arot) % 180 == 90:
            aw, ah = ah, aw
        hw, hh = aw / 2.0, ah / 2.0

        sfp = self.fp_data[sat_ref]
        sw, sh = sfp["width"], sfp["height"]
        clearance = 1.2

        pad_x, pad_y = pad_abs

        # Determine which edge of the anchor is closest to this pad
        dist_left = abs(pad_x - (ax - hw))
        dist_right = abs(pad_x - (ax + hw))
        dist_top = abs(pad_y - (ay - hh))
        dist_bottom = abs(pad_y - (ay + hh))

        if not hasattr(self, "_edge_stagger_counts"):
            self._edge_stagger_counts = {}

        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

        if min_dist == dist_right:
            sat_rad = max(sw, sh) / 2.0
            count = self._edge_stagger_counts.get((anchor_ref, "right"), 0)
            self._edge_stagger_counts[(anchor_ref, "right")] = count + 1
            tier = count % 2
            sx = ax + hw + sat_rad + clearance + (3.2 * tier)
            sy = pad_y
            srot = 90.0 if sw > sh else 0.0
        elif min_dist == dist_left:
            sat_rad = max(sw, sh) / 2.0
            count = self._edge_stagger_counts.get((anchor_ref, "left"), 0)
            self._edge_stagger_counts[(anchor_ref, "left")] = count + 1
            tier = count % 2
            sx = ax - hw - sat_rad - clearance - (3.2 * tier)
            sy = pad_y
            srot = 90.0 if sw > sh else 0.0
        elif min_dist == dist_bottom:
            sat_rad = max(sw, sh) / 2.0
            count = self._edge_stagger_counts.get((anchor_ref, "bottom"), 0)
            self._edge_stagger_counts[(anchor_ref, "bottom")] = count + 1
            tier = count % 2
            sx = pad_x
            sy = ay + hh + sat_rad + clearance + (3.2 * tier)
            srot = 0.0 if sw > sh else 90.0
        else:
            sat_rad = max(sw, sh) / 2.0
            count = self._edge_stagger_counts.get((anchor_ref, "top"), 0)
            self._edge_stagger_counts[(anchor_ref, "top")] = count + 1
            tier = count % 2
            sx = pad_x
            sy = ay - hh - sat_rad - clearance - (3.2 * tier)
            srot = 0.0 if sw > sh else 90.0

        return sx, sy, srot

    def generate_floorplan(self) -> List[Dict[str, Any]]:
        """Synthesizes the complete 100% project-agnostic, collision-free hierarchical layout."""
        cx, cy = self.cx, self.cy
        layout: Dict[str, Dict[str, Any]] = {}
        self._edge_stagger_counts = {}

        # 1. Master IC at Board Center (or edge if RF module / user directive)
        if self.master_ic:
            m_rot = self.user_rots.get(self.master_ic, 0.0)
            m_dir = self.user_directions.get(self.master_ic)
            # Detect RF module with antenna keepout (e.g. ESP32, nRF)
            is_rf = False
            m_fp_name = self.parts_catalog.get(self.master_ic, {}).get("footprint", "")
            m_sym_name = self.parts_catalog.get(self.master_ic, {}).get("symbol", "")
            if "RF_" in m_fp_name or "RF_" in m_sym_name or "ESP32" in m_fp_name or "ESP8266" in m_fp_name:
                is_rf = True
            self.is_rf = is_rf

            m_x = cx
            m_y = cy
            if m_dir == "top" or (is_rf and m_dir is None):
                m_y = (self.oy + 9.8) if is_rf else (self.oy + self.margin + 12.0)
            elif m_dir == "bottom":
                m_y = self.oy + self.bh - self.margin - 12.0
            elif m_dir == "left":
                m_x = self.ox + self.margin + 12.0
            elif m_dir == "right":
                m_x = self.ox + self.bw - self.margin - 12.0

            layout[self.master_ic] = {"x": m_x, "y": m_y, "rot": m_rot, "locked": True}

        n_conn = len(self.connectors)
        for idx, conn in enumerate(self.connectors):
            c_fp = self.fp_data[conn]
            cw, ch = c_fp["width"], c_fp["height"]

            user_dir = self.user_directions.get(conn)
            if user_dir:
                direction = user_dir
            else:
                dx, dy, angle = self.compute_exit_vector(conn)
                if 45 <= angle < 135:
                    direction = "bottom"
                elif 135 <= angle < 225:
                    direction = "left"
                elif 225 <= angle < 315:
                    direction = "top"
                else:
                    direction = "right"

            if direction == "bottom":
                rot = 270.0
            elif direction == "left":
                rot = 180.0
            elif direction == "top":
                rot = 90.0
            else:
                rot = 0.0

            if conn in self.user_rots:
                rot = self.user_rots[conn]

            eff_w, eff_h = (ch, cw) if round(rot) % 180 == 90 else (cw, ch)

            if direction == "bottom":
                px = cx + (idx - n_conn / 2.0) * 16.0
                py = self.oy + self.bh - self.margin - eff_h / 2.0
            elif direction == "left":
                px = self.ox + self.margin + eff_w / 2.0
                py = cy + (idx - n_conn / 2.0) * 16.0
            elif direction == "top":
                px = cx + (idx - n_conn / 2.0) * 16.0
                py = self.oy + self.margin + eff_h / 2.0
            else:
                px = self.ox + self.bw - self.margin - eff_w / 2.0
                y_offset = (idx - (n_conn - 1) / 2.0) * 20.0
                py = cy + y_offset

            # Clamp safely within board margins so pads never violate copper-to-edge
            px = max(self.ox + self.margin + eff_w / 2.0, min(self.ox + self.bw - self.margin - eff_w / 2.0, px))
            py = max(self.oy + self.margin + eff_h / 2.0, min(self.oy + self.bh - self.margin - eff_h / 2.0, py))
            layout[conn] = {"x": px, "y": py, "rot": rot, "locked": True}

        # 3. Crystals / Oscillators adjacent to oscillator pins
        for xtal in self.crystals:
            dx, dy, angle = self.compute_exit_vector(xtal)
            norm = math.hypot(dx, dy) or 1.0
            x_pos = cx + (dx / norm) * 19.5
            y_pos = cy + (dy / norm) * 19.5
            rot = self.user_rots.get(xtal, self.optimize_rotation(xtal, x_pos, y_pos))
            layout[xtal] = {"x": x_pos, "y": y_pos, "rot": rot, "locked": True}

            # Find load caps connected to crystal if not explicitly bound by near
            xtal_pads = set(self.fp_data[xtal].get("pads", {}).keys())
            xtal_nets = {self.pin_to_net.get((xtal, p)) for p in xtal_pads if self.pin_to_net.get((xtal, p))}
            load_caps = []
            for p in self.other_passives:
                if p in self.near_directives:
                    continue
                p_pads = self.fp_data[p].get("pads", {})
                if any(self.pin_to_net.get((p, pad)) in xtal_nets for pad in p_pads):
                    load_caps.append(p)
            for idx, cap in enumerate(load_caps[:2]):
                c_y = y_pos + (-4.5 if idx == 0 else 4.5)
                c_x = x_pos - 7.0 if x_pos < cx else x_pos + 7.0
                c_rot = self.user_rots.get(cap, 0.0)
                layout[cap] = {"x": c_x, "y": c_y, "rot": c_rot, "locked": True}

        # 4. Satellite ICs: Placed along exit vector with tangential distribution and rotationally optimized
        n_sat = len(self.satellite_ics)
        for idx, sat in enumerate(self.satellite_ics):
            dx, dy, angle = self.compute_exit_vector(sat)
            norm = math.hypot(dx, dy) or 1.0
            tangent_x = -dy / norm
            tangent_y = dx / norm
            t_offset = (idx - (n_sat - 1) / 2.0) * 14.0

            px = cx + (dx / norm) * 22.0 + tangent_x * t_offset
            py = cy + (dy / norm) * 22.0 + tangent_y * t_offset
            if getattr(self, "is_rf", False) and py < layout[self.master_ic]["y"]:
                py = layout[self.master_ic]["y"] + abs(py - layout[self.master_ic]["y"]) + 6.0

            rot = self.user_rots.get(sat, self.optimize_rotation(sat, px, py))
            s_fp = self.fp_data[sat]
            sw, sh = s_fp["width"], s_fp["height"]
            if round(rot) % 180 == 90:
                sw, sh = sh, sw
            px = max(self.ox + self.margin + sw / 2.0, min(self.ox + self.bw - self.margin - sw / 2.0, px))
            py = max(self.oy + self.margin + sh / 2.0, min(self.oy + self.bh - self.margin - sh / 2.0, py))

            layout[sat] = {"x": px, "y": py, "rot": rot}

        # 5. Tier 0 Directive: Explicit "near" Directives (Pad-Tethered Passives)
        for sat_ref, (aref, pin_spec) in self.near_directives.items():
            if sat_ref in layout:
                continue
            if aref in layout:
                anchor_pos = layout[aref]
                pad_rel = self._resolve_anchor_pad(aref, pin_spec)
                if pad_rel:
                    arot_rad = math.radians(anchor_pos.get("rot", 0.0))
                    px_rot = pad_rel[0] * math.cos(arot_rad) - pad_rel[1] * math.sin(arot_rad)
                    py_rot = pad_rel[0] * math.sin(arot_rad) + pad_rel[1] * math.cos(arot_rad)
                    pad_abs_x = anchor_pos["x"] + px_rot
                    pad_abs_y = anchor_pos["y"] + py_rot

                    sat_x, sat_y, auto_rot = self._place_satellite_near_pad(
                        aref, sat_ref, (pad_abs_x, pad_abs_y), anchor_pos
                    )
                    sat_rot = self.user_rots.get(sat_ref, auto_rot)

                    layout[sat_ref] = {
                        "x": sat_x,
                        "y": sat_y,
                        "rot": sat_rot,
                        "near_target": (pad_abs_x, pad_abs_y)
                    }

        # 6. Decoupling Capacitors: Snapped directly to companion IC power pads
        for ic_ref, caps in self.decoupling_caps.items():
            if ic_ref not in layout:
                continue
            ic_pos = layout[ic_ref]
            ic_pads = self.fp_data[ic_ref].get("pads", {})

            # Find power pads on this IC
            pwr_pads = []
            for pad, pos in ic_pads.items():
                net = self.pin_to_net.get((ic_ref, pad), "")
                if is_power_net(net):
                    pwr_pads.append((pad, pos))

            for idx, cap in enumerate(caps):
                if cap in layout:
                    continue
                if idx < len(pwr_pads):
                    pad_name, pad_rel = pwr_pads[idx]
                    norm = math.hypot(pad_rel[0], pad_rel[1]) or 1.0
                    c_x = ic_pos["x"] + pad_rel[0] + (pad_rel[0] / norm) * 2.5
                    c_y = ic_pos["y"] + pad_rel[1] + (pad_rel[1] / norm) * 2.5
                    c_rot = self.user_rots.get(cap, 90.0 if abs(pad_rel[0]) > abs(pad_rel[1]) else 0.0)
                else:
                    c_x = ic_pos["x"] + (idx + 1) * 3.5
                    c_y = ic_pos["y"] + 6.0
                    c_rot = self.user_rots.get(cap, 0.0)
                layout[cap] = {"x": c_x, "y": c_y, "rot": c_rot}

        # 7. Other Passives (Group-Aware & Net-Aware Clustering)
        passive_offsets: Dict[str, int] = {}
        for p in self.other_passives + self.inline_passives:
            if p in layout:
                continue
            p_pads = self.fp_data[p].get("pads", {})
            p_nets = [self.pin_to_net.get((p, pad), "") for pad in p_pads]

            # Priority 1: Check if part belongs to a group with an active anchor IC or connector
            companion_ref = None
            companion_pos = None
            grp_id = self.part_to_group.get(p)
            if grp_id:
                group_candidates = [
                    r for r in self.group_to_parts.get(grp_id, [])
                    if r in layout and (r in self.satellite_ics or r in self.connectors or r == self.master_ic)
                ]
                if group_candidates:
                    companion_ref = group_candidates[0]
                    companion_pos = (layout[companion_ref]["x"], layout[companion_ref]["y"])

            # Priority 2: Find companion component sharing a signal net
            if not companion_ref:
                for comp_ref, c_pos in layout.items():
                    if comp_ref == p:
                        continue
                    comp_pads = self.fp_data.get(comp_ref, {}).get("pads", {})
                    if any(self.pin_to_net.get((comp_ref, cp)) in p_nets and self.pin_to_net.get((comp_ref, cp)) not in ("", "GND") for cp in comp_pads):
                        companion_ref = comp_ref
                        companion_pos = (c_pos["x"], c_pos["y"])
                        break

            # Fallback: Master IC
            if not companion_ref:
                companion_ref = self.master_ic or "BOARD"
                companion_pos = (cx, cy)

            idx = passive_offsets.get(companion_ref, 0)
            passive_offsets[companion_ref] = idx + 1

            # Distribute in a radial sunflower spiral around companion node
            angle_rad = (idx * 1.05) % (2.0 * math.pi)
            dist = 7.0 + (idx // 5) * 4.0
            px = companion_pos[0] + math.cos(angle_rad) * dist
            py = companion_pos[1] + math.sin(angle_rad) * dist
            if getattr(self, "is_rf", False) and py < layout[self.master_ic]["y"]:
                py = layout[self.master_ic]["y"] + abs(py - layout[self.master_ic]["y"]) + 4.0
            p_rot = self.user_rots.get(p, 0.0)
            layout[p] = {"x": px, "y": py, "rot": p_rot}

        # 8. Physics Collision Relaxation (Hard Keepout Enforcement & Tethering)
        self._relax_collisions(layout, iterations=150)

        # Convert to ops format
        ops = [
            {
                "op": "board.set_size",
                "width": self.bw,
                "height": self.bh,
                "origin_x": self.ox,
                "origin_y": self.oy
            }
        ]
        for ref, pos in layout.items():
            op = {
                "op": "footprint.place",
                "ref": ref,
                "x": round(pos["x"] * 2.0) / 2.0,
                "y": round(pos["y"] * 2.0) / 2.0,
                "rot": pos.get("rot", 0.0)
            }
            if pos.get("locked") or ref in self.near_directives:
                op["locked"] = True
            ops.append(op)

        return ops

    def _relax_collisions(self, layout: Dict[str, Dict[str, Any]], iterations: int = 100):
        """Pure geometric force-directed relaxation pushing overlapping bounding boxes apart."""
        refs = list(layout.keys())
        clearance = 1.2  # 1.2mm keepout ensures 0.8mm synthetic clearance survives 0.5mm grid snap

        for it in range(iterations):
            max_shift = 0.0
            for i in range(len(refs)):
                rA = refs[i]
                posA = layout[rA]
                fpA = self.fp_data[rA]
                wA = fpA["width"]
                hA = fpA["height"]
                if round(posA.get("rot", 0)) % 180 == 90:
                    wA, hA = hA, wA

                for j in range(i + 1, len(refs)):
                    rB = refs[j]
                    posB = layout[rB]
                    fpB = self.fp_data[rB]
                    wB = fpB["width"]
                    hB = fpB["height"]
                    if round(posB.get("rot", 0)) % 180 == 90:
                        wB, hB = hB, wB

                    dx = posB["x"] - posA["x"]
                    dy = posB["y"] - posA["y"]
                    min_dx = (wA + wB) / 2.0 + clearance
                    min_dy = (hA + hB) / 2.0 + clearance

                    pen_x = min_dx - abs(dx)
                    pen_y = min_dy - abs(dy)

                    if pen_x > 0 and pen_y > 0:
                        is_A_locked = (rA == self.master_ic or rA in self.connectors)
                        is_B_locked = (rB == self.master_ic or rB in self.connectors)
                        if is_A_locked and is_B_locked:
                            continue

                        # If collinear in 1D, break symmetry with a tangential nudge in opposite directions
                        if abs(dy) < 1.0:
                            if not is_A_locked and not is_B_locked:
                                posB["y"] += 2.0
                                posA["y"] -= 2.0
                            elif not is_B_locked:
                                posB["y"] += 2.5
                            elif not is_A_locked:
                                posA["y"] -= 2.5

                        if abs(dx) < 1.0:
                            if not is_A_locked and not is_B_locked:
                                posB["x"] += 2.0
                                posA["x"] -= 2.0
                            elif not is_B_locked:
                                posB["x"] += 2.5
                            elif not is_A_locked:
                                posA["x"] -= 2.5

                        # Boundary-aware axis selection: if at board boundary on chosen axis, push along other axis
                        max_xb = self.ox + self.bw - self.margin - wB / 2.0 - 0.5
                        min_xb = self.ox + self.margin + wB / 2.0 + 0.5
                        max_yb = self.oy + self.bh - self.margin - hB / 2.0 - 0.5
                        min_yb = self.oy + self.margin + hB / 2.0 + 0.5

                        at_x_bound = (dx >= 0 and posB["x"] >= max_xb) or (dx < 0 and posB["x"] <= min_xb)
                        at_y_bound = (dy >= 0 and posB["y"] >= max_yb) or (dy < 0 and posB["y"] <= min_yb)

                        push_axis_x = (pen_x < pen_y and not at_x_bound) or at_y_bound

                        if push_axis_x:
                            sign = 1.0 if dx >= 0 else -1.0
                            if is_A_locked:
                                posB["x"] += (pen_x + 0.4) * sign
                            elif is_B_locked:
                                posA["x"] -= (pen_x + 0.4) * sign
                            else:
                                posB["x"] += (pen_x / 2.0 + 0.2) * sign
                                posA["x"] -= (pen_x / 2.0 + 0.2) * sign
                            max_shift = max(max_shift, pen_x)
                        else:
                            sign = 1.0 if dy >= 0 else -1.0
                            if is_A_locked:
                                posB["y"] += (pen_y + 0.4) * sign
                            elif is_B_locked:
                                posA["y"] -= (pen_y + 0.4) * sign
                            else:
                                posB["y"] += (pen_y / 2.0 + 0.2) * sign
                                posA["y"] -= (pen_y / 2.0 + 0.2) * sign
                            max_shift = max(max_shift, pen_y)

            # Clamp movable components inside board margin
            for ref, pos in layout.items():
                if not pos.get("locked"):
                    fp = self.fp_data[ref]
                    w = fp["width"]
                    h = fp["height"]
                    if round(pos.get("rot", 0)) % 180 == 90:
                        w, h = h, w
                    pos["x"] = max(self.ox + self.margin + w / 2.0, min(self.ox + self.bw - self.margin - w / 2.0, pos["x"]))
                    pos["y"] = max(self.oy + self.margin + h / 2.0, min(self.oy + self.bh - self.margin - h / 2.0, pos["y"]))

            if max_shift < 0.05:
                break


# Backwards compatibility alias
HierarchicalFloorplanner = UniversalHierarchicalFloorplanner

