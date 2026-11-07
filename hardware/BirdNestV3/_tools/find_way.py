#!/usr/bin/env python3
"""
Find a way for a line on the board.

The line may not come closer to the copper of another net than the
clearance of the net, and it may not touch it at all.  The script
looks for such a way on a grid of a quarter of a millimetre, and it
says where the way is.

The obstacles are the pads and the tracks of the other nets.  The
distance to them is measured exactly, not with their box: a line may
go past the corner of a track, and the rules checker lets it.

The pads of the net itself are free: the line has to arrive at them.
The copper of the net itself is free as well: the line may cross its
own older pieces.

The script only reads, it does not change anything.

Run:  find_way.py <net> <x1> <y1> <x2> <y2> [layer]
"""
import heapq
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

import safe_board

from safe_board import PCB    # noqa: E402

STEP = 0.25      # the size of the grid, in millimetres
CLEAR = 0.2      # the clearance that is used when the net has no rule


def mm(v):
    return pcbnew.ToMM(v)


def rule_of(board, net):
    """The rules of a net: the clearance and the width."""
    path = os.path.join(os.path.dirname(PCB), "BirdNestV3.kicad_pro")
    try:
        from maze4 import load_classes
        classes = load_classes(path)
        return classes.get(net, classes.get("Default", {}))
    except Exception:
        return {}


def point_seg(p, a, b):
    """The distance of a point and a segment."""
    (px, py) = p
    (ax, ay) = a
    (bx, by) = b
    dx = bx - ax
    dy = by - ay
    length = dx * dx + dy * dy
    if length == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / length
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def point_rect(p, rect):
    """The distance of a point and a rectangle."""
    (px, py) = p
    (x0, y0, x1, y1) = rect
    cx = min(max(px, x0), x1)
    cy = min(max(py, y0), y1)
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def obstacles(board, net, layer, clearance=None):
    """The places where the line may not go.

    The answer holds for every obstacle the kind of it, its place and
    the name of it.  The kind is "rect" for a pad, "seg" for a track
    and "circle" for a via.
    """
    out = []
    rule = rule_of(board, net)
    if clearance is None:
        clearance = rule.get("clearance", CLEAR)

    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net or not p.GetNetname():
                continue
            if not p.IsOnLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu):
                continue
            local = p.GetLocalClearance()
            gap = mm(local) if local else clearance
            bb = p.GetBoundingBox()
            out.append(("rect",
                        (mm(bb.GetLeft()), mm(bb.GetTop()),
                         mm(bb.GetRight()), mm(bb.GetBottom())),
                        gap,
                        f"the pad {fp.GetReference()}.{p.GetNumber()}"))

    for t in board.GetTracks():
        if t.GetNetname() == net or t.GetNetname() == "GND":
            continue
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition()
            out.append(("circle", (mm(q.x), mm(q.y)),
                        mm(t.GetWidth()) / 2 + clearance, "a via"))
            continue
        if t.GetLayer() != (pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu):
            continue
        a = t.GetStart()
        c = t.GetEnd()
        out.append(("seg", ((mm(a.x), mm(a.y)), (mm(c.x), mm(c.y))),
                    mm(t.GetWidth()) / 2 + clearance, "a track"))

    return out


def blocked_at(boxes, x, y, half):
    """Is a place in the way of one of the obstacles?"""
    for (kind, place, gap, name) in boxes:
        if kind == "rect":
            d = point_rect((x, y), place)
        elif kind == "circle":
            d = ((x - place[0]) ** 2 + (y - place[1]) ** 2) ** 0.5
        else:
            d = point_seg((x, y), place[0], place[1])
        if d < half + gap:
            return name
    return None


def find(board, net, start, goal, layer, width, clearance=None):
    """The way from the start to the goal, or None.

    The way is a list of points.
    """
    boxes = obstacles(board, net, layer, clearance)
    half = width / 2
    sx, sy = start
    gx, gy = goal

    x0 = int((min(sx, gx) - 8) / STEP)
    x1 = int((max(sx, gx) + 8) / STEP) + 1
    y0 = int((min(sy, gy) - 8) / STEP)
    y1 = int((max(sy, gy) + 8) / STEP) + 1

    def cell(x, y):
        return (x * STEP, y * STEP)

    def near(x, y, tx, ty):
        return abs(x * STEP - tx) < STEP and abs(y * STEP - ty) < STEP

    start_cell = None
    goal_cell = None
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if near(x, y, sx, sy):
                start_cell = (x, y)
            if near(x, y, gx, gy):
                goal_cell = (x, y)
    if start_cell is None or goal_cell is None:
        return None

    # The start and the goal stand on a pad of the net, and the pad is
    # free.  So the places around them are free as well.
    free_cells = set()
    for cell0 in (start_cell, goal_cell):
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                c = (cell0[0] + dx, cell0[1] + dy)
                px, py = cell(*c)
                if not blocked_at(boxes, px, py, half):
                    free_cells.add(c)

    # the search: the cheapest way first
    open_set = [(0.0, start_cell)]
    came = {start_cell: None}
    cost = {start_cell: 0.0}
    steps = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.41), (1, -1, 1.41), (-1, 1, 1.41), (-1, -1, 1.41))
    found = False
    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur == goal_cell:
            found = True
            break
        for (dx, dy, w) in steps:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt not in free_cells and not (x0 <= nxt[0] <= x1
                                              and y0 <= nxt[1] <= y1):
                continue
            if nxt in cost:
                continue
            px, py = cell(*nxt)
            if nxt not in free_cells and blocked_at(boxes, px, py, half):
                continue
            cost[nxt] = cost[cur] + w
            came[nxt] = cur
            heapq.heappush(open_set, (cost[nxt], nxt))
    if not found:
        return None

    path = []
    cur = goal_cell
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    path.reverse()

    # The points of the way, without the ones that lie in a straight
    # line.  The way is walked on a grid, so it has many points that
    # lie on one line, and only the corners are of use.
    out = []
    for i, p in enumerate(path):
        if i == 0 or i == len(path) - 1:
            out.append(cell(*p))
            continue
        a = out[-1]
        b = cell(*path[i + 1])
        if (b[0] - a[0]) * (p[1] - a[1]) != (b[1] - a[1]) * (p[0] - a[0]):
            out.append(cell(*p))
    if out and out[0] != (sx, sy):
        out.insert(0, (sx, sy))
    if out and out[-1] != (gx, gy):
        out.append((gx, gy))
    return simplify(out)


def simplify(points):
    """The points of a way, with the short ones left out.

    A point that lies on the line between its two neighbours is left
    out, as long as the line between them is free.  The script tries
    the longest lines first, so that the way becomes straight where it
    can be.
    """
    if len(points) < 3:
        return points
    keep = [0]
    i = 0
    while i < len(points) - 1:
        # the longest line that starts at the point i and ends at a
        # later point
        best = i + 1
        for j in range(len(points) - 1, i + 1, -1):
            a = points[i]
            b = points[j]
            # the line may not bend
            if bend(a, b, points[i + 1:j + 1]):
                continue
            best = j
            break
        keep.append(best)
        i = best
    return [points[k] for k in keep]


def bend(a, b, between):
    """Does a line from a to b bend on its way?

    The answer is True when one of the points between them does not
    lie on the line.
    """
    (ax, ay) = a
    (bx, by) = b
    dx = bx - ax
    dy = by - ay
    length = (dx * dx + dy * dy) ** 0.5
    if length < 0.001:
        return True
    for (px, py) in between:
        if abs((px - ax) * dy - (py - ay) * dx) / length > 0.01:
            return True
    return False


def main():
    if len(sys.argv) < 6:
        print("usage: find_way.py <net> <x1> <y1> <x2> <y2> [layer] [width]"
              " [clearance]")
        return 1
    net = sys.argv[1]
    start = (float(sys.argv[2]), float(sys.argv[3]))
    goal = (float(sys.argv[4]), float(sys.argv[5]))
    layer = sys.argv[6] if len(sys.argv) > 6 else "F"
    board = pcbnew.LoadBoard(PCB)
    width = float(sys.argv[7]) if len(sys.argv) > 7 else 0.25
    clearance = float(sys.argv[8]) if len(sys.argv) > 8 else None
    way = find(board, net, start, goal, layer, width, clearance)
    if way is None:
        print(f"there is no way on the {layer} copper")
        return 1
    print(f"the way on the {layer} copper, {len(way)} points:")
    for (x, y) in way:
        print(f"    ({x:.3f}, {y:.3f}),")
    return 0


if __name__ == "__main__":
    sys.exit(main())
