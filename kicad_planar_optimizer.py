import os
import sys
import json
import math
import time
import random
from pathlib import Path
from typing import Dict, List, Tuple, Any

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kaibridge.core.paths import load_kicad_python
import subprocess


def ccw(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]) -> float:
    return (p3[1] - p1[1]) * (p2[0] - p1[0]) - (p2[1] - p1[1]) * (p3[0] - p1[0])


def segments_intersect(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float]
) -> bool:
    """Strict 2D line segment intersection test (excludes identical endpoints)."""
    eps = 1e-4
    if (abs(p1[0] - p3[0]) < eps and abs(p1[1] - p3[1]) < eps) or \
       (abs(p1[0] - p4[0]) < eps and abs(p1[1] - p4[1]) < eps) or \
       (abs(p2[0] - p3[0]) < eps and abs(p2[1] - p3[1]) < eps) or \
       (abs(p2[0] - p4[0]) < eps and abs(p2[1] - p4[1]) < eps):
        return False

    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    return False


def rotate_point(dx: float, dy: float, rot_deg: float) -> Tuple[float, float]:
    """Rotates relative coordinate (dx, dy) by 0, 90, 180, or 270 degrees."""
    r = round(rot_deg) % 360
    if r == 0:
        return dx, dy
    elif r == 90:
        return -dy, dx
    elif r == 180:
        return -dx, -dy
    elif r == 270:
        return dy, -dx
    else:
        rad = math.radians(r)
        c = math.cos(rad)
        s = math.sin(rad)
        return dx * c - dy * s, dx * s + dy * c


def get_mst(points: List[Tuple[float, float]]) -> List[Tuple[int, int, float]]:
    """Calculates Minimum Spanning Tree (MST) on 2D points using Kruskal's algorithm."""
    n = len(points)
    if n <= 1:
        return []
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            d = math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])
            edges.append((d, i, j))
    edges.sort()
    parent = list(range(n))

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    mst = []
    for d, u, v in edges:
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[ru] = rv
            mst.append((u, v, d))
            if len(mst) == n - 1:
                break
    return mst


def get_footprint_data_from_pcb(pcb_path: str | Path) -> Dict[str, Any]:
    """Extracts exact relative pad positions and physical body sizes using KiCad python."""
    kicad_py = load_kicad_python()
    script = f'''
import pcbnew, json
b = pcbnew.LoadBoard(r"{str(pcb_path)}")
data = {{}}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    pos = fp.GetPosition()
    rot = fp.GetOrientationDegrees()
    r = round(rot) % 360
    pads = {{}}
    pads_list = list(fp.Pads())
    for pad in pads_list:
        ppos = pad.GetPosition()
        rx = (ppos.x - pos.x) / 1e6
        ry = (ppos.y - pos.y) / 1e6
        if r == 90:
            rx, ry = ry, -rx
        elif r == 180:
            rx, ry = -rx, -ry
        elif r == 270:
            rx, ry = -ry, rx
        pads[pad.GetName()] = (round(rx, 3), round(ry, 3))
    
    # Extract exact KiCad courtyard bounding box from F_CrtYd layer
    cbox = None
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_CrtYd:
            gb = g.GetBoundingBox()
            if cbox is None:
                cbox = gb
            else:
                cbox.Merge(gb)

    bw, bh = 2.5, 2.5
    if cbox:
        bw = round(cbox.GetWidth() / 1e6, 2)
        bh = round(cbox.GetHeight() / 1e6, 2)
        if r % 180 == 90:
            bw, bh = bh, bw

    if pads_list:
        min_x = min(p.GetPosition().x - p.GetSize().x // 2 for p in pads_list) / 1e6
        max_x = max(p.GetPosition().x + p.GetSize().x // 2 for p in pads_list) / 1e6
        min_y = min(p.GetPosition().y - p.GetSize().y // 2 for p in pads_list) / 1e6
        max_y = max(p.GetPosition().y + p.GetSize().y // 2 for p in pads_list) / 1e6
        pbw = round(max_x - min_x, 2)
        pbh = round(max_y - min_y, 2)
        if r % 180 == 90:
            pbw, pbh = pbh, pbw
        bw = max(bw, pbw)
        bh = max(bh, pbh)

    data[ref] = {{
        "pads": pads,
        "width": bw,
        "height": bh,
        "locked": fp.IsLocked()
    }}
print("JSON_START" + json.dumps(data) + "JSON_END")
'''
    res = subprocess.run([kicad_py, "-c", script], capture_output=True, text=True, check=True)
    out = res.stdout
    start = out.find("JSON_START") + len("JSON_START")
    end = out.find("JSON_END")
    return json.loads(out[start:end])


class PlanarLayoutOptimizer:
    def __init__(
        self,
        project_dir: str | Path,
        board_width: float = 55.0,
        board_height: float = 40.0,
        origin_x: float = 100.0,
        origin_y: float = 100.0,
        margin: float = 3.0,
        clearance: float = 0.8,
        ignore_gnd: bool = True
    ):
        self.proj_dir = Path(project_dir).resolve()
        self.pcb_path = list(self.proj_dir.glob("*.kicad_pcb"))[0]
        self.design_file = self.proj_dir / "kaibridge_dump" / "design.json"
        if not self.design_file.exists():
            self.design_file = self.proj_dir / "design.json"

        with open(self.design_file, "r", encoding="utf-8") as f:
            self.design = json.load(f)

        self.fp_data = get_footprint_data_from_pcb(self.pcb_path)
        
        self.board_w = board_width
        self.board_h = board_height
        self.ox = origin_x
        self.oy = origin_y
        self.margin = margin
        self.clearance = clearance
        self.ignore_gnd = ignore_gnd

        self.min_x = self.ox + margin
        self.max_x = self.ox + self.board_w - margin
        self.min_y = self.oy + margin
        self.max_y = self.oy + self.board_h - margin

        # Extract nets
        self.nets = {}
        for net_name, net_data in self.design.get("nets", {}).items():
            if self.ignore_gnd and net_name == "GND":
                continue
            pins = net_data.get("connections", net_data) if isinstance(net_data, dict) else net_data
            if isinstance(pins, list) and len(pins) >= 2:
                # filter pins that exist
                valid_pins = []
                for p in pins:
                    if "." in p:
                        ref, pad = p.split(".", 1)
                        if ref in self.fp_data:
                            valid_pins.append((ref, pad))
                if len(valid_pins) >= 2:
                    self.nets[net_name] = valid_pins

    def get_pad_pos(self, state: Dict[str, Dict[str, Any]], ref: str, pad_num: str) -> Tuple[float, float]:
        comp = state[ref]
        cx, cy = comp["x"], comp["y"]
        rot = comp["rot"]
        dx, dy = self.fp_data[ref]["pads"].get(pad_num, (0.0, 0.0))
        rdx, rdy = rotate_point(dx, dy, rot)
        return (cx + rdx, cy + rdy)

    def evaluate_state(self, state: Dict[str, Dict[str, Any]]) -> Tuple[float, int, float, int]:
        """Calculates cost: Crossings * 5000 + Overlaps * 1e6 + HPWL."""
        refs = list(state.keys())
        overlaps = 0

        # 1. Strict Boundary and Courtyard Overlap Check
        for i in range(len(refs)):
            rA = refs[i]
            cA = state[rA]
            wA = self.fp_data[rA]["width"]
            hA = self.fp_data[rA]["height"]
            if round(cA["rot"]) % 180 == 90:
                wA, hA = hA, wA

            # Boundary constraint only on movable components
            if not cA.get("locked"):
                if cA["x"] - wA / 2 < self.min_x or cA["x"] + wA / 2 > self.max_x or \
                   cA["y"] - hA / 2 < self.min_y or cA["y"] + hA / 2 > self.max_y:
                    overlaps += 1

            for j in range(i + 1, len(refs)):
                rB = refs[j]
                cB = state[rB]
                wB = self.fp_data[rB]["width"]
                hB = self.fp_data[rB]["height"]
                if round(cB["rot"]) % 180 == 90:
                    wB, hB = hB, wB

                dx = abs(cA["x"] - cB["x"])
                dy = abs(cA["y"] - cB["y"])
                min_dx = (wA + wB) / 2.0 + self.clearance
                min_dy = (hA + hB) / 2.0 + self.clearance

                if dx < min_dx and dy < min_dy:
                    overlaps += 1

        # 2. Build MST for each net based on current pad positions
        all_edges = []
        total_hpwl = 0.0
        for net_name, pin_list in self.nets.items():
            pts = [self.get_pad_pos(state, ref, pad) for ref, pad in pin_list]
            mst = get_mst(pts)
            for u, v, d in mst:
                all_edges.append((pts[u], pts[v], net_name))
                total_hpwl += d

        # 3. Count Cross-Net Intersections
        crossings = 0
        n_edges = len(all_edges)
        for i in range(n_edges):
            p1, p2, n1 = all_edges[i]
            for j in range(i + 1, n_edges):
                p3, p4, n2 = all_edges[j]
                if n1 != n2 and segments_intersect(p1, p2, p3, p4):
                    crossings += 1

        # Decoupling Proximity Penalties (e.g. C1 near U1, C2/C3 near U1, C4/C5 near U2)
        decoupling_penalty = 0.0
        prox_pairs = [
            ("C1", "U1", 5.0),
            ("C2", "U1", 5.0),
            ("C3", "U1", 5.0),
            ("C4", "U2", 6.0),
            ("C5", "U2", 6.0),
        ]
        for c_ref, u_ref, max_dist in prox_pairs:
            if c_ref in state and u_ref in state:
                dist = math.hypot(state[c_ref]["x"] - state[u_ref]["x"], state[c_ref]["y"] - state[u_ref]["y"])
                if dist > max_dist:
                    decoupling_penalty += (dist - max_dist) * 20.0

        # 4. Total Cost Calculation
        total_cost = (crossings * 5000.0) + (total_hpwl * 2.0) + (overlaps * 100000.0) + decoupling_penalty
        return total_cost, crossings, total_hpwl, overlaps

    def optimize(
        self,
        initial_ops: List[Dict[str, Any]],
        steps: int = 6000,
        temp_init: float = 80.0,
        cooling: float = 0.9985
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Simulated annealing to minimize cross-net airwire intersections."""
        state = {}
        for op in initial_ops:
            if op.get("op") == "footprint.place":
                ref = op["ref"]
                state[ref] = {
                    "x": op.get("x", 120.0),
                    "y": op.get("y", 120.0),
                    "rot": op.get("rot", 0.0),
                    "locked": bool(op.get("locked", False))
                }

        best_state = {r: dict(v) for r, v in state.items()}
        current_state = {r: dict(v) for r, v in state.items()}

        current_cost, cur_cross, cur_hpwl, cur_ov = self.evaluate_state(current_state)
        best_cost = current_cost
        best_crossings = cur_cross
        best_ov = cur_ov

        print(f"[*] Initial State: Cross-Net Crossings = {cur_cross}, Overlaps = {cur_ov}, HPWL = {cur_hpwl:.1f}mm, Cost = {current_cost:.1f}")

        t0 = time.time()
        T = temp_init
        unlocked_refs = [r for r, d in state.items() if not d["locked"]]

        for step in range(steps):
            ref = random.choice(unlocked_refs)
            orig = dict(current_state[ref])

            # Mutation strategy: 40% rotation, 60% translation
            if random.random() < 0.40:
                new_rot = (orig["rot"] + random.choice([90, 180, 270])) % 360
                current_state[ref]["rot"] = new_rot
            else:
                # Nudge position on 0.5mm grid
                jitter_x = random.choice([-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0])
                jitter_y = random.choice([-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0])
                nx = max(self.min_x, min(self.max_x, round((orig["x"] + jitter_x) * 2.0) / 2.0))
                ny = max(self.min_y, min(self.max_y, round((orig["y"] + jitter_y) * 2.0) / 2.0))
                current_state[ref]["x"] = nx
                current_state[ref]["y"] = ny

            new_cost, new_cross, new_hpwl, new_ov = self.evaluate_state(current_state)
            delta = new_cost - current_cost

            # Acceptance criterion
            if delta < 0 or random.random() < math.exp(-delta / max(1e-5, T)):
                current_cost = new_cost
                # Best state must prioritize 0 overlaps first, then lowest cost
                if (new_ov == 0 and (best_ov > 0 or new_cost < best_cost)) or (best_ov > 0 and new_ov < best_ov):
                    best_cost = new_cost
                    best_crossings = new_cross
                    best_ov = new_ov
                    best_state = {r: dict(v) for r, v in current_state.items()}
                    if step % 250 == 0 or (best_ov == 0 and best_crossings < 3):
                        print(f"  [Step {step:4d}] Improved! Crossings = {new_cross}, Overlaps = {new_ov}, HPWL = {new_hpwl:.1f}mm, T = {T:.2f}")
                    if best_ov == 0 and best_crossings == 0:
                        print(f"\n[!] ZERO CROSSINGS & ZERO OVERLAPS ACHIEVED AT STEP {step}! Converged early.")
                        break
            else:
                # Reject mutation
                current_state[ref] = orig

            T *= cooling

        # Local greedy quench on best state
        print("[*] Running local greedy quench...")
        for ref in unlocked_refs:
            orig = dict(best_state[ref])
            best_local_cost = best_cost
            for test_rot in [0, 90, 180, 270]:
                best_state[ref]["rot"] = test_rot
                cost, cross, hpwl, ov = self.evaluate_state(best_state)
                if ov == 0 and cost < best_local_cost:
                    best_local_cost = cost
                    orig = dict(best_state[ref])
            best_state[ref] = orig

        elapsed = time.time() - t0
        _, final_cross, final_hpwl, final_ov = self.evaluate_state(best_state)
        print(f"\n=== Optimization Complete in {elapsed:.2f}s ===")
        print(f"  Final Cross-Net Crossings: {final_cross}")
        print(f"  Final Overlaps           : {final_ov}")
        print(f"  Final HPWL               : {final_hpwl:.1f} mm")

        # Generate new ops.json
        optimized_ops = []
        for op in initial_ops:
            if op.get("op") == "board.set_size":
                optimized_ops.append(op)
                break

        for ref, d in best_state.items():
            op_dict = {
                "op": "footprint.place",
                "ref": ref,
                "x": d["x"],
                "y": d["y"],
                "rot": int(d["rot"])
            }
            if d.get("locked"):
                op_dict["locked"] = True
            optimized_ops.append(op_dict)

        return optimized_ops, final_cross


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kaibridge Planar Layout Optimizer (Simulated Annealing + Kruskal MST)")
    parser.add_argument("project_path", nargs="?", default="projects/sample_pulse_generator", help="Path to KiCad project directory")
    parser.add_argument("--steps", type=int, default=6000, help="Number of annealing iterations (default: 6000)")
    parser.add_argument("--temp", type=float, default=70.0, help="Initial temperature (default: 70.0)")
    args = parser.parse_args()

    proj = Path(args.project_path)
    ops_file = proj / "kaibridge_dump" / "ops.json"
    if not ops_file.exists():
        print(f"Error: Ops file not found at {ops_file}")
        sys.exit(1)

    with open(ops_file, "r") as f:
        init_ops = json.load(f)

    bw, bh = 55.0, 40.0
    for op in init_ops:
        if op.get("op") == "board.set_size":
            bw = float(op.get("width", bw))
            bh = float(op.get("height", bh))
            break

    opt = PlanarLayoutOptimizer(proj, board_width=bw, board_height=bh)
    best_ops, crossings = opt.optimize(init_ops, steps=args.steps, temp_init=args.temp)
    
    out_ops_file = proj / "kaibridge_dump" / "ops.json"
    with open(out_ops_file, "w") as f:
        json.dump(best_ops, f, indent=2)
    print(f"\nSaved optimized ops to: {out_ops_file}")

