#!/usr/bin/env python3
"""
The parts of the V3 that stand on the tracks of the v2.

The v2 layout is finished.  Its tracks are the physical design of the
board, and a part that stands on one of them can not be soldered: the
track runs under the part, and the pad of the part is shorted to the
copper of the track.

This script finds the parts of the V3 that stand on a track of the v2,
and the pads of the V3 that a track of the v2 runs into.  It is the
list of the parts that have to be moved.

Run:  parts_on_v2_tracks.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = "/Users/modmj/dev/BirdNest/hardware/BirdNest_pcb/BirdNest_pcb.kicad_pcb"
V3 = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")


def mm(v):
    return v / 1000000.0


def point_seg(p, a, b):
    """The distance of the point p from the segment a-b."""
    (px, py) = p
    (ax, ay) = a
    (bx, by) = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def main():
    import pcbnew
    v2 = pcbnew.LoadBoard(V2)
    v3 = pcbnew.LoadBoard(V3)

    # the tracks of the v2
    v2tracks = []
    for t in v2.GetTracks():
        a, e = t.GetStart(), t.GetEnd()
        v2tracks.append((t.GetNetname(),
                         (mm(a.x), mm(a.y)), (mm(e.x), mm(e.y)),
                         mm(t.GetWidth()),
                         "VIA" if t.GetClass() == "PCB_VIA" else t.GetLayerName()))

    # the parts of the V3 that are not in the v2
    v2refs = {fp.GetReference() for fp in v2.GetFootprints() if fp.GetReference()}
    new_parts = []
    for fp in v3.GetFootprints():
        ref = fp.GetReference()
        if not ref or ref in v2refs:
            continue
        bb = fp.GetBoundingBox()
        new_parts.append((ref, mm(bb.GetLeft()), mm(bb.GetTop()),
                          mm(bb.GetRight()), mm(bb.GetBottom()),
                          fp.GetValue()))

    print("=" * 78)
    print("the new parts of the V3 that stand on a track of the v2")
    print("=" * 78)
    hits = 0
    for (ref, x0, y0, x1, y1, val) in sorted(new_parts):
        bad = []
        for (net, a, b, w, lay) in v2tracks:
            if lay == "VIA":
                continue
            # the track has to cross the box of the part
            lo_x, hi_x = min(a[0], b[0]) - w / 2, max(a[0], b[0]) + w / 2
            lo_y, hi_y = min(a[1], b[1]) - w / 2, max(a[1], b[1]) + w / 2
            if lo_x >= x1 or hi_x <= x0 or lo_y >= y1 or hi_y <= y0:
                continue
            # and it has to be close to the track
            d = min(point_seg((x0, y0), a, b), point_seg((x1, y0), a, b),
                    point_seg((x0, y1), a, b), point_seg((x1, y1), a, b))
            if d < 2.0:
                bad.append((net, lay, round(d, 2)))
        if bad:
            hits += 1
            print(f"  {ref:5} {val[:14]:16} at ({x0:6.2f},{y0:6.2f})-"
                  f"({x1:6.2f},{y1:6.2f})")
            for (net, lay, d) in bad[:5]:
                print(f"        a track of {net:20} on {lay} is {d} mm away")
    print(f"\n  {hits} of {len(new_parts)} new parts stand on a track of the v2")

    print()
    print("=" * 78)
    print("the pads of the V3 that a track of the v2 runs into")
    print("=" * 78)
    for fp in sorted(v3.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if not ref:
            continue
        for p in fp.Pads():
            pos = p.GetPosition()
            px, py = mm(pos.x), mm(pos.y)
            sz = p.GetSize()
            hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
            for (net, a, b, w, lay) in v2tracks:
                if lay == "VIA":
                    continue
                if abs(px - a[0]) > 50 or abs(py - a[1]) > 50:
                    continue
                d = point_seg((px, py), a, b)
                if d < w / 2 + 0.3:
                    print(f"  {ref:5}.{p.GetNumber():4} on {p.GetNetname():18}"
                          f" @({px:7.2f},{py:7.2f})"
                          f"  a track of {net:18} on {lay} is {d:.2f} mm away")
                    break


if __name__ == "__main__":
    main()
