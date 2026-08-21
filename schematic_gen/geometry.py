"""
kaibridge/geometry.py -- the only place in Kaibridge that knows what "overlap" means.
Everything is mm. KiCad's Y axis points DOWN, so y0 is the TOP edge.
"""
from dataclasses import dataclass

@dataclass
class Box:
    ref: str
    x0: float; y0: float; x1: float; y1: float   # courtyard, absolute board coords
    ox: float; oy: float                          # origin == what SetPosition() takes
    rot: float = 0.0
    locked: bool = False
    source: str = "courtyard"                     # courtyard | pad_hull | bbox_with_text

    @property
    def cx(self): return (self.x0 + self.x1) / 2.0
    @property
    def cy(self): return (self.y0 + self.y1) / 2.0
    @property
    def w(self): return self.x1 - self.x0
    @property
    def h(self): return self.y1 - self.y0

    @property
    def anchor_offset(self):
        """origin -> courtyard centre at the CURRENT rotation.
        This is the number the AI never had, which is why headers landed off-centre."""
        return (round(self.cx - self.ox, 4), round(self.cy - self.oy, 4))

    def origin_for_centre(self, cx, cy):
        dx, dy = self.anchor_offset
        return (round(cx - dx, 4), round(cy - dy, 4))

    def shifted(self, dx, dy):
        return Box(self.ref, self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy,
                   self.ox + dx, self.oy + dy, self.rot, self.locked, self.source)

def mtv(a, b, clearance=0.0):
    """None if a and b are at least `clearance` apart, else the shortest vector
    that moves b clear of a."""
    m = clearance / 2.0
    push_r = (a.x1 + m) - (b.x0 - m)     # move b +x by this to clear
    push_l = (b.x1 + m) - (a.x0 - m)     # move b -x by this
    push_d = (a.y1 + m) - (b.y0 - m)     # move b +y by this
    push_u = (b.y1 + m) - (a.y0 - m)     # move b -y by this
    if min(push_r, push_l, push_d, push_u) <= 0:
        return None
    px = push_r if push_r < push_l else -push_l
    py = push_d if push_d < push_u else -push_u
    return (round(px, 4), 0.0) if abs(px) <= abs(py) else (0.0, round(py, 4))

def find_overlaps(boxes, clearance=0.25):
    out = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            v = mtv(a, b, clearance)
            if v:
                out.append({"a": a.ref, "b": b.ref,
                            "overlap_mm": round(max(abs(v[0]), abs(v[1])), 3),
                            "move_b_by": [v[0], v[1]]})
    return out

def outside(boxes, bounds, margin=0.5):
    bx0, by0, bx1, by1 = bounds
    out = []
    for b in boxes:
        dx = dy = 0.0
        if b.x0 < bx0 + margin: dx = (bx0 + margin) - b.x0
        elif b.x1 > bx1 - margin: dx = (bx1 - margin) - b.x1
        if b.y0 < by0 + margin: dy = (by0 + margin) - b.y0
        elif b.y1 > by1 - margin: dy = (by1 - margin) - b.y1
        if dx or dy:
            out.append({"ref": b.ref, "move_by": [round(dx, 3), round(dy, 3)]})
    return out

def _clamp(box, bounds, margin):
    if box.locked:
        return box
    hit = outside([box], bounds, margin)
    return box.shifted(*hit[0]["move_by"]) if hit else box

def separate(boxes, clearance=0.25, bounds=None, margin=0.5, passes=80):
    """Relaxation: nudge unlocked parts apart along the shortest escape until
    nothing touches. Deterministic, fine up to a few hundred parts.
    Returns ({ref: (origin_x, origin_y)} for what moved, [remaining overlaps])."""
    work = {b.ref: b for b in boxes}
    order = [b.ref for b in boxes]
    for _ in range(passes):
        clashes = 0
        for i, ra in enumerate(order):
            for rb in order[i + 1:]:
                a, b = work[ra], work[rb]
                v = mtv(a, b, clearance)
                if not v:
                    continue
                clashes += 1
                if a.locked and b.locked:
                    continue
                sa, sb = (0.0, 1.0) if a.locked else (1.0, 0.0) if b.locked else (0.5, 0.5)
                work[ra] = a.shifted(-v[0] * sa, -v[1] * sa)
                work[rb] = b.shifted(v[0] * sb, v[1] * sb)
        if bounds:
            for r in order:
                work[r] = _clamp(work[r], bounds, margin)
        if not clashes:
            break
    moved = {r: (round(work[r].ox, 4), round(work[r].oy, 4))
             for r in order
             if abs(work[r].ox - next(b.ox for b in boxes if b.ref == r)) > 1e-4
             or abs(work[r].oy - next(b.oy for b in boxes if b.ref == r)) > 1e-4}
    return moved, find_overlaps(list(work.values()), clearance)
