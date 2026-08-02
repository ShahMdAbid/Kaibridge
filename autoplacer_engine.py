import pcbnew  # type: ignore
import math
import random
import time
import os

# Safe import for PyYAML — not guaranteed in all KiCad Python bundles (§2.12)
try:
    import yaml
except ImportError:
    yaml = None

# ============================================================
# DEFAULT PHYSICS CONFIGURATION (overridden by YAML if present)
# ============================================================
DEFAULTS = {
    "k_spring":           1.0,
    "k_repulsion":        50.0,
    "clearance_mm":       2.0,
    "epsilon":            0.1,
    "initial_temp":       10.0,
    "cooling_rate":       0.95,
    "velocity_damping":   0.8,
    "max_displacement_mm": 2.0,
    "early_stop_mm":      0.1,
    "iterations":         100,
}

BOUNDS_DEFAULT = {"min_x": 50, "max_x": 150, "min_y": 50, "max_y": 150}

# Power net names that should always be filtered from adjacency graph,
# regardless of fanout count. Prevents blob-collapse on small boards (§2.12).
POWER_NET_NAMES = {"GND", "VCC", "VDD", "3V3", "3.3V", "5V", "12V", "VBUS", "VBAT"}

# Zone definitions as fractional bounding box regions
# Each zone: (x_frac_min, x_frac_max, y_frac_min, y_frac_max)
ZONE_MAP = {
    "EDGE_TOP":     (0.0,  1.0,  0.0,  0.15),
    "EDGE_BOTTOM":  (0.0,  1.0,  0.85, 1.0),
    "EDGE_LEFT":    (0.0,  0.15, 0.0,  1.0),
    "EDGE_RIGHT":   (0.85, 1.0,  0.0,  1.0),
    "CENTER":       (0.15, 0.85, 0.15, 0.85),
    "ANALOG_ZONE":  (0.15, 0.50, 0.15, 0.85),
    "DIGITAL_ZONE": (0.50, 0.85, 0.15, 0.85),
    "CORNER_TL":    (0.0,  0.10, 0.0,  0.10),
    "CORNER_TR":    (0.90, 1.0,  0.0,  0.10),
    "CORNER_BL":    (0.0,  0.10, 0.90, 1.0),
    "CORNER_BR":    (0.90, 1.0,  0.90, 1.0),
}

random.seed(42)

# ============================================================
# GEOMETRY HELPERS
# ============================================================

def get_bounding_radius(fp):
    """Returns half-diagonal of the bounding box as the collision radius."""
    bbox = fp.GetBoundingBox()
    w = pcbnew.ToMM(bbox.GetWidth())
    h = pcbnew.ToMM(bbox.GetHeight())
    return math.sqrt(w**2 + h**2) / 2.0

def get_half_extents(fp):
    """Returns (half_width, half_height) for tighter overlap checking."""
    bbox = fp.GetBoundingBox()
    return pcbnew.ToMM(bbox.GetWidth()) / 2.0, pcbnew.ToMM(bbox.GetHeight()) / 2.0

def dist_2d(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def clamp_to_bounds(p, bounds):
    x = max(bounds["min_x"], min(p[0], bounds["max_x"]))
    y = max(bounds["min_y"], min(p[1], bounds["max_y"]))
    return [x, y]

def zone_center(zone_name, bounds):
    """Return the center (mm) of a named zone within the board bounds."""
    if zone_name not in ZONE_MAP:
        return [
            (bounds["min_x"] + bounds["max_x"]) / 2.0,
            (bounds["min_y"] + bounds["max_y"]) / 2.0,
        ]
    xf0, xf1, yf0, yf1 = ZONE_MAP[zone_name]
    bw = bounds["max_x"] - bounds["min_x"]
    bh = bounds["max_y"] - bounds["min_y"]
    cx = bounds["min_x"] + (xf0 + xf1) / 2.0 * bw
    cy = bounds["min_y"] + (yf0 + yf1) / 2.0 * bh
    return [cx, cy]

def is_connector(fp):
    ref = fp.GetReference()
    return ref.startswith(("J", "P", "CON", "USB"))

def is_mounting_hole(fp):
    ref = str(fp.GetReference())
    lib = str(fp.GetFPID().GetLibItemName().wx_str())
    return "MountingHole" in ref or "Hole" in lib or ref.startswith(("H", "MH"))

def calculate_total_ratsnest(positions, adj_list):
    total = 0.0
    for u1, connected in adj_list.items():
        if u1 not in positions:
            continue
        p1 = positions[u1]
        for connected_fp, _ in connected:
            u2 = connected_fp.m_Uuid.AsString()
            if u2 in positions:
                total += dist_2d(p1, positions[u2])
    return total / 2.0

def calculate_overlapping_pairs(positions, radii):
    overlaps = 0
    uuids = list(positions.keys())
    for i in range(len(uuids)):
        u1 = uuids[i]
        for j in range(i+1, len(uuids)):
            u2 = uuids[j]
            min_sep = radii[u1] + radii[u2]
            if dist_2d(positions[u1], positions[u2]) < min_sep:
                overlaps += 1
    return overlaps

# ============================================================
# YAML CONSTRAINT LOADER
# ============================================================

class PlacementConstraints:
    """
    Parses the auto-placement YAML and exposes constraint data
    to the physics engine in a clean, lookup-friendly format.
    """

    def __init__(self, yaml_path: str, strict: bool = True):
        self.anchors = {}           # ref -> {zone, position_mm, locked, rotation_deg}
        self.zone_prefs = {}        # ref -> {zone, priority}
        self.tight_groups = {}      # group_id -> {anchor_ref, max_dist_mm, members, keep_clear_radius_mm}
        self.tight_member_of = {}   # ref -> group_id  (reverse index)
        self.tight_member_rotation = {}  # ref -> rotation_deg (§2.11)
        self.relative = {}          # ref -> {relative_to, direction, offset_mm}
        self.keep_clear = []        # list of {owner_ref?, center_mm?, radius_mm, margin_mm?}
        self.rotation_overrides = {}# ref -> rotation_deg
        self.physics = dict(DEFAULTS)
        self.board_bounds_override = None  # (§2.11) meta.board_bounds_mm
        self.valid = False
        self.unresolved_refs = []   # refs in YAML but not found on board (§3 logging)

        if yaml is None:
            msg = "[Constraints] PyYAML not installed. Cannot load constraints."
            print(msg)
            if strict:
                raise ImportError(msg)
            return

        if not yaml_path or not os.path.isfile(yaml_path):
            msg = f"[Constraints] No YAML found at '{yaml_path}'."
            print(msg)
            if strict:
                raise FileNotFoundError(msg)
            return

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            msg = f"[Constraints] YAML parse error: {e}"
            print(msg)
            if strict:
                raise
            return

        if not data or not isinstance(data, dict):
            msg = "[Constraints] YAML file is empty or not a dict."
            print(msg)
            if strict:
                raise ValueError(msg)
            return

        # Meta — board bounds override (§2.11)
        meta = data.get("meta", {})
        bb = meta.get("board_bounds_mm")
        if bb and all(k in bb for k in ("min_x", "max_x", "min_y", "max_y")):
            self.board_bounds_override = {
                "min_x": float(bb["min_x"]),
                "max_x": float(bb["max_x"]),
                "min_y": float(bb["min_y"]),
                "max_y": float(bb["max_y"]),
            }

        # Physics overrides
        pp = data.get("physics_params", {})
        for key in DEFAULTS:
            if key in pp:
                self.physics[key] = pp[key]

        # Anchors
        for entry in data.get("anchors", []):
            ref = entry.get("ref")
            if ref:
                self.anchors[ref] = entry

        # Zone preferences
        for entry in data.get("zone_preferences", []):
            ref = entry.get("ref")
            if ref:
                self.zone_prefs[ref] = entry

        # Tight groups (§2.11 — parse keep_clear_radius_mm and member rotation_deg)
        for group in data.get("tight_groups", []):
            gid = group.get("group_id")
            if not gid:
                continue
            self.tight_groups[gid] = group
            for member in group.get("members", []):
                mref = member.get("ref")
                if mref:
                    self.tight_member_of[mref] = gid
                    mrot = member.get("rotation_deg")
                    if mrot is not None:
                        self.tight_member_rotation[mref] = mrot

        # Relative constraints
        for entry in data.get("relative_constraints", []):
            ref = entry.get("ref")
            if ref:
                self.relative[ref] = entry

        # Keep-clear zones (§2.11 — parse center_mm/radius_mm)
        self.keep_clear = data.get("keep_clear_zones", [])

        # Rotation overrides
        for entry in data.get("rotation_overrides", []):
            ref = entry.get("ref")
            if ref:
                self.rotation_overrides[ref] = entry.get("rotation_deg", 0)

        self.valid = True
        print(f"[Constraints] Loaded: {len(self.anchors)} anchors, "
              f"{len(self.zone_prefs)} zone prefs, "
              f"{len(self.tight_groups)} tight groups, "
              f"{len(self.rotation_overrides)} rotation overrides.")

    def is_locked(self, ref: str) -> bool:
        return self.anchors.get(ref, {}).get("locked", False)

    def get_anchor_position(self, ref: str):
        """Returns [x, y] in mm if explicitly set, else None."""
        pos = self.anchors.get(ref, {}).get("position_mm")
        if pos and "x" in pos and "y" in pos:
            return [float(pos["x"]), float(pos["y"])]
        return None

    def get_zone(self, ref: str):
        """Returns the target zone name for a ref (anchor or zone pref)."""
        if ref in self.anchors:
            return self.anchors[ref].get("zone")
        if ref in self.zone_prefs:
            return self.zone_prefs[ref].get("zone")
        return None

    def get_zone_priority(self, ref: str) -> float:
        return self.zone_prefs.get(ref, {}).get("priority", 5.0)

    def get_tight_group_for(self, ref: str):
        """Returns the tight_group dict if ref is a member, else None."""
        gid = self.tight_member_of.get(ref)
        if gid:
            return self.tight_groups.get(gid)
        return None

    def get_keep_clear_radius(self, ref: str) -> float:
        """Returns extra clearance margin for a ref (from keep_clear_zones or tight_group)."""
        # Check keep_clear_zones with owner_ref
        for kc in self.keep_clear:
            if kc.get("owner_ref") == ref:
                return kc.get("margin_mm", 0.0)
        # Check tight_group keep_clear_radius_mm (§2.11)
        gid = self.tight_member_of.get(ref)
        if gid and gid in self.tight_groups:
            return self.tight_groups[gid].get("keep_clear_radius_mm", 0.0)
        return 0.0

    def get_positional_keep_clears(self):
        """Returns list of keep-clear zones defined by center_mm + radius_mm (§2.11)."""
        result = []
        for kc in self.keep_clear:
            center = kc.get("center_mm")
            radius = kc.get("radius_mm")
            if center and radius:
                result.append({
                    "cx": float(center["x"]),
                    "cy": float(center["y"]),
                    "radius": float(radius),
                    "label": kc.get("label", ""),
                })
        return result

# ============================================================
# MAIN PLACER
# ============================================================

def run_physics_placer(yaml_path: str = None, strict: bool = True):
    """
    Run the force-directed auto-placement engine.

    Args:
        yaml_path: Path to the placement_constraints.yaml file.
        strict: If True, raise on missing/invalid YAML. If False, run unconstrained.

    Returns:
        dict with structured result (§3 logging improvement):
        {converged, iterations_run, ratsnest_before, ratsnest_after,
         overlaps_before, overlaps_after, unresolved_refs, error}
    """
    result = {
        "converged": False,
        "iterations_run": 0,
        "ratsnest_before": 0.0,
        "ratsnest_after": 0.0,
        "overlaps_before": 0,
        "overlaps_after": 0,
        "unresolved_refs": [],
        "error": None,
    }

    start_time = time.time()

    board = pcbnew.GetBoard()
    footprints = list(board.GetFootprints())

    if not footprints:
        result["error"] = "No footprints found on board."
        print(result["error"])
        return result

    # Detect board bounds from Edge.Cuts
    bbox = board.GetBoardEdgesBoundingBox()
    if bbox.GetWidth() > 0 and bbox.GetHeight() > 0:
        bounds = {
            "min_x": pcbnew.ToMM(bbox.GetLeft()),
            "max_x": pcbnew.ToMM(bbox.GetRight()),
            "min_y": pcbnew.ToMM(bbox.GetTop()),
            "max_y": pcbnew.ToMM(bbox.GetBottom()),
        }
    else:
        bounds = dict(BOUNDS_DEFAULT)

    # Load YAML constraints
    if yaml_path is None:
        yaml_path = os.path.join(os.path.dirname(__file__), "placement_constraints.yaml")

    try:
        C = PlacementConstraints(yaml_path, strict=strict)
    except Exception as e:
        result["error"] = f"Failed to load constraints: {e}"
        print(result["error"])
        return result

    P = C.physics

    # Override bounds from YAML meta if provided (§2.11)
    if C.board_bounds_override:
        bounds = C.board_bounds_override
        print(f"[Bounds] Overridden from YAML: {bounds}")

    # Build ref -> footprint lookup
    ref_to_fp = {fp.GetReference(): fp for fp in footprints}

    # --------------------------------------------------------
    # STEP 0: UNLOCK engine-applied locks from previous runs (§2.3)
    # We track our locks via a custom property on the footprint.
    # --------------------------------------------------------
    for fp in footprints:
        try:
            if fp.HasProperty("_abide_engine_locked"):
                fp.SetLocked(False)
                fp.DeleteProperty("_abide_engine_locked")
        except Exception:
            pass  # Property API may differ across KiCad versions

    # --------------------------------------------------------
    # STEP 1: Apply rotation overrides (before physics)
    #         Including tight_group member rotations (§2.11)
    # --------------------------------------------------------
    for ref, rot_deg in C.rotation_overrides.items():
        fp = ref_to_fp.get(ref)
        if fp:
            fp.SetOrientationDegrees(rot_deg)
            print(f"[Rotation] {ref} -> {rot_deg}°")
        else:
            C.unresolved_refs.append(ref)

    for ref, rot_deg in C.tight_member_rotation.items():
        fp = ref_to_fp.get(ref)
        if fp:
            fp.SetOrientationDegrees(rot_deg)
            print(f"[Rotation/TightGroup] {ref} -> {rot_deg}°")

    # --------------------------------------------------------
    # STEP 2: Apply anchor positions & lock them (§2.2 fix)
    #  If locked=True but no position_mm, snap to zone center.
    # --------------------------------------------------------
    for ref, anchor_data in C.anchors.items():
        fp = ref_to_fp.get(ref)
        if not fp:
            print(f"[Anchor] WARNING: ref '{ref}' not found on board.")
            C.unresolved_refs.append(ref)
            continue

        pos = anchor_data.get("position_mm")
        zone = anchor_data.get("zone")
        is_locked = anchor_data.get("locked", False)

        if pos and "x" in pos and "y" in pos:
            # Explicit position provided
            fp.SetPosition(pcbnew.VECTOR2I(
                pcbnew.FromMM(float(pos["x"])),
                pcbnew.FromMM(float(pos["y"]))
            ))
        elif is_locked and zone:
            # §2.2 FIX: locked but no position → snap to zone center
            zc = zone_center(zone, bounds)
            fp.SetPosition(pcbnew.VECTOR2I(
                pcbnew.FromMM(zc[0]),
                pcbnew.FromMM(zc[1])
            ))
            print(f"[Anchor] {ref}: no position_mm, snapped to zone '{zone}' center ({zc[0]:.1f}, {zc[1]:.1f})")

        if is_locked:
            fp.SetLocked(True)
            try:
                fp.SetProperty("_abide_engine_locked", "true")
            except Exception:
                pass

        rot = anchor_data.get("rotation_deg")
        if rot is not None:
            fp.SetOrientationDegrees(rot)

        print(f"[Anchor] {ref} placed zone={zone} locked={is_locked}")

    # --------------------------------------------------------
    # STEP 3: Determine movable vs. locked sets (§2.3 fix)
    #  No fallback locking — it causes cumulative side effects.
    # --------------------------------------------------------
    locked_uuids = set()
    for fp in footprints:
        if fp.IsLocked():
            locked_uuids.add(fp.m_Uuid.AsString())

    movable = [fp for fp in footprints if fp.m_Uuid.AsString() not in locked_uuids]
    anchors_fp = [fp for fp in footprints if fp.m_Uuid.AsString() in locked_uuids]

    if not movable:
        print("[Physics] All footprints are locked. Nothing to place.")
        result["error"] = "All footprints are locked."
        return result

    # --------------------------------------------------------
    # STEP 4: High-fanout net filtering (§2.12 fix)
    #  Lower threshold + always filter known power net names.
    # --------------------------------------------------------
    net_pad_count = {}
    for fp in footprints:
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                net_pad_count[nn] = net_pad_count.get(nn, 0) + 1

    FANOUT_THRESHOLD = max(6, int(len(footprints) * 0.20))
    high_fanout_nets = set()
    for nn, cnt in net_pad_count.items():
        if cnt > FANOUT_THRESHOLD:
            high_fanout_nets.add(nn)
    # Always filter well-known power nets by name (§2.12)
    for nn in net_pad_count:
        if nn.upper().replace("_", "").replace("-", "").replace("NET", "") in POWER_NET_NAMES:
            high_fanout_nets.add(nn)

    # --------------------------------------------------------
    # STEP 5: Build adjacency list (ratsnest graph)
    # --------------------------------------------------------
    fp_nets = {}
    for fp in footprints:
        uuid = fp.m_Uuid.AsString()
        fp_nets[uuid] = {
            pad.GetNetname()
            for pad in fp.Pads()
            if pad.GetNetname() and pad.GetNetname() not in high_fanout_nets
        }

    adj_list = {fp.m_Uuid.AsString(): [] for fp in footprints}
    for i, fp1 in enumerate(footprints):
        u1 = fp1.m_Uuid.AsString()
        for fp2 in footprints[i+1:]:
            u2 = fp2.m_Uuid.AsString()
            shared = fp_nets[u1] & fp_nets[u2]
            if shared:
                w = len(shared)
                adj_list[u1].append((fp2, w))
                adj_list[u2].append((fp1, w))

    # --------------------------------------------------------
    # STEP 6: Initialize positions, velocities, radii
    # --------------------------------------------------------
    positions = {}
    velocities = {}
    radii = {}
    ref_to_uuid = {fp.GetReference(): fp.m_Uuid.AsString() for fp in footprints}

    for fp in footprints:
        uuid = fp.m_Uuid.AsString()
        ref = fp.GetReference()
        pos = fp.GetPosition()
        positions[uuid] = [
            pcbnew.ToMM(pos.x) + random.uniform(-0.1, 0.1),
            pcbnew.ToMM(pos.y) + random.uniform(-0.1, 0.1),
        ]
        velocities[uuid] = [0.0, 0.0]
        radii[uuid] = get_bounding_radius(fp) + C.get_keep_clear_radius(ref)

    # Positional keep-clear zones (§2.11)
    positional_keep_clears = C.get_positional_keep_clears()

    # Pre-metrics
    initial_ratsnest = calculate_total_ratsnest(positions, adj_list)
    initial_overlaps = calculate_overlapping_pairs(positions, radii)
    result["ratsnest_before"] = initial_ratsnest
    result["overlaps_before"] = initial_overlaps

    # --------------------------------------------------------
    # STEP 7: Force-Directed Physics Loop
    #   All forces are now Hookean (§2.4 fix)
    #   Repulsion is size-aware (§2.5 fix)
    # --------------------------------------------------------
    K_SPRING    = P["k_spring"]
    K_REPULSION = P["k_repulsion"]
    CLEARANCE   = P["clearance_mm"]
    EPSILON     = P["epsilon"]
    MAX_DISP    = P["max_displacement_mm"]
    EARLY_STOP  = P["early_stop_mm"]
    DAMP        = P["velocity_damping"]

    temp = P["initial_temp"]
    opt_start = time.time()
    iterations_run = 0

    for iteration in range(P["iterations"]):
        iterations_run = iteration + 1
        max_movement = 0.0
        forces = {u: [0.0, 0.0] for u in positions}

        for fp1 in movable:
            u1   = fp1.m_Uuid.AsString()
            ref1 = fp1.GetReference()
            p1   = positions[u1]
            r1   = radii[u1]

            # --- A. Repulsion (all pairs) — SIZE-AWARE (§2.5 fix) ---
            for fp2 in footprints:
                u2 = fp2.m_Uuid.AsString()
                if u1 == u2:
                    continue
                p2 = positions[u2]
                r2 = radii[u2]
                dx = p1[0] - p2[0]
                dy = p1[1] - p2[1]
                dist_sq = dx**2 + dy**2
                dist = math.sqrt(dist_sq)
                if dist < EPSILON:
                    dx, dy = random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5)
                    dist = math.sqrt(dx**2 + dy**2)
                    if dist < EPSILON:
                        dist = EPSILON
                # Size-aware: repulsion scales with combined radii
                min_sep = r1 + r2 + CLEARANCE
                # Stronger repulsion when overlapping, decays with distance²
                fm = K_REPULSION * min_sep / (dist_sq + EPSILON)
                forces[u1][0] += fm * (dx / dist)
                forces[u1][1] += fm * (dy / dist)

            # --- B. Spring Attraction (ratsnest) — already Hookean ✅ ---
            for connected_fp, weight in adj_list[u1]:
                u2 = connected_fp.m_Uuid.AsString()
                p2 = positions[u2]
                r2 = radii[u2]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                dist = math.sqrt(dx**2 + dy**2)
                if dist < EPSILON:
                    continue
                optimal = r1 + r2 + CLEARANCE
                displacement = dist - optimal
                if displacement > 0:
                    fm = K_SPRING * weight * displacement
                    forces[u1][0] += fm * (dx / dist)
                    forces[u1][1] += fm * (dy / dist)

            # --- C. Zone Attraction — HOOKEAN (§2.4 fix) ---
            target_zone = C.get_zone(ref1)
            if target_zone:
                zc = zone_center(target_zone, bounds)
                dx = zc[0] - p1[0]
                dy = zc[1] - p1[1]
                dist = math.sqrt(dx**2 + dy**2)
                if dist > EPSILON:
                    priority = C.get_zone_priority(ref1)
                    # Hookean: force proportional to distance from target
                    fm = K_SPRING * priority * 0.3 * dist
                    forces[u1][0] += fm * (dx / dist)
                    forces[u1][1] += fm * (dy / dist)

            # --- D. Tight Group Attraction — HOOKEAN (§2.4 fix) ---
            group = C.get_tight_group_for(ref1)
            if group:
                anchor_ref = group.get("anchor_ref")
                anchor_uuid = ref_to_uuid.get(anchor_ref)
                if anchor_uuid and anchor_uuid in positions:
                    p_anchor = positions[anchor_uuid]
                    max_dist = group.get("max_dist_mm", 4.0)
                    dx = p_anchor[0] - p1[0]
                    dy = p_anchor[1] - p1[1]
                    dist = math.sqrt(dx**2 + dy**2)
                    if dist > EPSILON:
                        # Hookean: only pull when beyond max_dist
                        displacement = dist - max_dist
                        if displacement > 0:
                            fm = K_SPRING * 4.0 * displacement
                            forces[u1][0] += fm * (dx / dist)
                            forces[u1][1] += fm * (dy / dist)
                        # Gentle centering pull even when within max_dist
                        else:
                            fm = K_SPRING * 0.5 * dist
                            forces[u1][0] += fm * (dx / dist)
                            forces[u1][1] += fm * (dy / dist)

            # --- E. Relative Constraint — HOOKEAN (§2.4 fix) ---
            rel = C.relative.get(ref1)
            if rel:
                rel_ref  = rel.get("relative_to")
                rel_uuid = ref_to_uuid.get(rel_ref)
                if rel_uuid and rel_uuid in positions:
                    p_rel    = positions[rel_uuid]
                    offset   = rel.get("offset_mm", 3.0)
                    direction = rel.get("direction", "right")
                    dir_map = {
                        "right": ( 1, 0),
                        "left":  (-1, 0),
                        "below": ( 0, 1),
                        "above": ( 0,-1),
                    }
                    dx_dir, dy_dir = dir_map.get(direction, (1, 0))
                    target = [p_rel[0] + dx_dir * offset, p_rel[1] + dy_dir * offset]
                    dx = target[0] - p1[0]
                    dy = target[1] - p1[1]
                    dist = math.sqrt(dx**2 + dy**2)
                    if dist > EPSILON:
                        # Hookean: force proportional to displacement from target
                        fm = K_SPRING * 2.0 * dist
                        forces[u1][0] += fm * (dx / dist)
                        forces[u1][1] += fm * (dy / dist)

            # --- F. Positional Keep-Clear Repulsion (§2.11) ---
            for kcz in positional_keep_clears:
                dx = p1[0] - kcz["cx"]
                dy = p1[1] - kcz["cy"]
                dist = math.sqrt(dx**2 + dy**2)
                if dist < kcz["radius"] and dist > EPSILON:
                    # Push out of keep-clear zone
                    fm = K_REPULSION * 2.0 * (kcz["radius"] - dist) / kcz["radius"]
                    forces[u1][0] += fm * (dx / dist)
                    forces[u1][1] += fm * (dy / dist)

            # --- G. Boundary Restoring Force ---
            margin = 1.0  # mm margin inside bounds
            bx = max(bounds["min_x"] + margin, min(p1[0], bounds["max_x"] - margin))
            by = max(bounds["min_y"] + margin, min(p1[1], bounds["max_y"] - margin))
            if bx != p1[0] or by != p1[1]:
                dx = bx - p1[0]
                dy = by - p1[1]
                dist = math.sqrt(dx**2 + dy**2)
                if dist > EPSILON:
                    fm = K_SPRING * 5.0 * dist
                    forces[u1][0] += fm * (dx / dist)
                    forces[u1][1] += fm * (dy / dist)

        # --- H. Integrate velocities & positions ---
        for fp in movable:
            u1 = fp.m_Uuid.AsString()
            fx, fy = forces[u1]
            velocities[u1][0] = (velocities[u1][0] + fx) * DAMP
            velocities[u1][1] = (velocities[u1][1] + fy) * DAMP

            move_x = max(min(velocities[u1][0], temp), -temp)
            move_y = max(min(velocities[u1][1], temp), -temp)

            move_dist = math.sqrt(move_x**2 + move_y**2)
            if move_dist > MAX_DISP:
                scale  = MAX_DISP / move_dist
                move_x *= scale
                move_y *= scale
                move_dist = MAX_DISP

            positions[u1][0] += move_x
            positions[u1][1] += move_y

            if move_dist > max_movement:
                max_movement = move_dist

        if max_movement < EARLY_STOP:
            print(f"[Physics] Converged at iteration {iterations_run} (max_move={max_movement:.4f}mm)")
            result["converged"] = True
            break

        temp *= P["cooling_rate"]

    opt_time = time.time() - opt_start

    # --------------------------------------------------------
    # STEP 8: Write positions back to KiCad (§2.12 fix)
    #   Add BuildConnectivity() for ratsnest sync.
    # --------------------------------------------------------
    for fp in movable:
        u1 = fp.m_Uuid.AsString()
        px, py = clamp_to_bounds(positions[u1], bounds)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py)))

    board.BuildConnectivity()  # §2.12 fix — sync ratsnest
    pcbnew.Refresh()

    # --------------------------------------------------------
    # METRICS & STRUCTURED RESULT (§3 improvement)
    # --------------------------------------------------------
    final_ratsnest = calculate_total_ratsnest(positions, adj_list)
    final_overlaps = calculate_overlapping_pairs(positions, radii)
    reduction = 0.0
    if initial_ratsnest > 0:
        reduction = ((initial_ratsnest - final_ratsnest) / initial_ratsnest) * 100.0

    total_time = time.time() - start_time

    result["iterations_run"] = iterations_run
    result["ratsnest_after"] = final_ratsnest
    result["overlaps_after"] = final_overlaps
    result["unresolved_refs"] = C.unresolved_refs

    print("\n========== Rule 9B Placement Summary ==========")
    print(f"YAML Constraints  : {'Loaded' if C.valid else 'NOT LOADED'}")
    print(f"Components        : {len(footprints)} ({len(anchors_fp)} locked, {len(movable)} movable)")
    print(f"Tight Groups      : {len(C.tight_groups)}")
    print(f"Zone Preferences  : {len(C.zone_prefs)}")
    print(f"Iterations run    : {iterations_run} / {P['iterations']}")
    print(f"Converged         : {result['converged']}")
    print(f"Physics time      : {opt_time:.2f}s  |  Total: {total_time:.2f}s")
    print(f"\nRatsnest  Before  : {initial_ratsnest:.1f} mm")
    print(f"          After   : {final_ratsnest:.1f} mm  ({reduction:.1f}% reduction)")
    print(f"\nOverlaps  Before  : {initial_overlaps}")
    print(f"          After   : {final_overlaps}")
    if C.unresolved_refs:
        print(f"\n⚠ Unresolved refs : {C.unresolved_refs}")
    print("================================================")
    print(f"RESULT: {json.dumps(result, default=str)}")
    print()

    return result

# Need json for structured output
import json

if __name__ == "__main__":
    import sys
    yaml_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_physics_placer(yaml_path=yaml_arg, strict=False)
