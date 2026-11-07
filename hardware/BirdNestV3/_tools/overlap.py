#!/usr/bin/env python3
"""
Check every track on the board against every pad of another net.

The DRC reports the overlaps, but not by how much.  This script measures
the real overlap, so that the tracks can be corrected by hand: a track
that only grazes a pad needs a nudge of a tenth of a millimetre, a track
that runs right across it needs to be moved.

Run:  overlap.py [net name]
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def seg_rect_overlap(a, b, r):
    """How much of the segment a-b lies inside the rectangle r
    (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = r
    # sample the segment
    n = max(2, int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / 0.05) + 1)
    inside = 0
    total = 0
    for i in range(n + 1):
        t = i / n
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        total += 1
        if x0 <= x <= x1 and y0 <= y <= y1:
            inside += 1
    if inside == 0:
        return 0.0
    # the length of the part inside, in mm
    seglen = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    return seglen * inside / total


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    b = pcbnew.LoadBoard(V3)

    pads = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        for p in fp.Pads():
            pos = p.GetPosition()
            w = pcbnew.ToMM(p.GetSize().x)
            h = pcbnew.ToMM(p.GetSize().y)
            x = pcbnew.ToMM(pos.x)
            y = pcbnew.ToMM(pos.y)
            layers = set()
            for l in (pcbnew.F_Cu, pcbnew.B_Cu):
                if p.IsOnLayer(l):
                    layers.add(l)
            pads.append((ref, p.GetNumber(), p.GetNetname(), x, y, w, h, layers))

    hits = defaultdict(list)
    for t in b.GetTracks():
        net = t.GetNetname()
        if not net or (only and net != only):
            continue
        if t.GetClass() == "PCB_VIA":
            a = e = t.GetPosition()
            ax = pcbnew.ToMM(a.x)
            ay = pcbnew.ToMM(a.y)
            half = pcbnew.ToMM(t.GetWidth()) / 2
            r = (ax - half, ay - half, ax + half, ay + half)
            layers = {pcbnew.F_Cu, pcbnew.B_Cu}
            for (ref, num, pnet, px, py, pw, ph, plats) in pads:
                if pnet == net:
                    continue
                if not (plats & layers):
                    continue
                ov = seg_rect_overlap((ax, ay), (ax, ay),
                                      (px - pw / 2, py - ph / 2,
                                       px + pw / 2, py + ph / 2))
                if ov > 0:
                    hits[(net, pnet)].append(
                        (f"{ref}.{num}", f"via@({ax:.2f},{ay:.2f})", ov))
            continue

        a = t.GetStart()
        e = t.GetEnd()
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        layer = t.GetLayer()
        for (ref, num, pnet, px, py, pw, ph, plats) in pads:
            if pnet == net:
                continue
            if layer not in plats:
                continue
            ov = seg_rect_overlap((ax, ay), (ex, ey),
                                  (px - pw / 2, py - ph / 2,
                                   px + pw / 2, py + ph / 2))
            if ov > 0:
                hits[(net, pnet)].append(
                    (f"{ref}.{num}",
                     f"({ax:.2f},{ay:.2f})->({ex:.2f},{ey:.2f})", ov))

    print("overlapping track and pad pairs, by how much they overlap")
    total = 0
    for (net, pnet), items in sorted(hits.items(),
                                     key=lambda kv: -sum(i[2] for i in kv[1])):
        items.sort(key=lambda i: -i[2])
        tot = sum(i[2] for i in items)
        total += len(items)
        print(f"\n{net}  vs  {pnet}   ({len(items)} overlaps, {tot:.2f} mm)")
        for name, what, ov in items[:6]:
            print(f"    {ov:6.3f} mm   {name:10} {what}")
    print(f"\ntotal: {total} overlapping track/pad pairs")


if __name__ == "__main__":
    main()
