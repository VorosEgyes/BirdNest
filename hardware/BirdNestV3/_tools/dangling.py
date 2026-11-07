#!/usr/bin/env python3
"""
The tracks that hang loose on the board.

A track has an unconnected end when one of its ends does not touch a
pad of its net.  The tracks of the V2 layout are copied over to the V3,
and some of them end where a part of the V2 stood - a part that is not
on the V3, or a part that stands somewhere else now.  Those tracks are
left over: they carry copper that does not go anywhere.

This script lists them, so that they can be removed and routed again.

Run:  dangling.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")


def mm(v):
    return v / 1000000.0


def main():
    import pcbnew
    b = pcbnew.LoadBoard(PCB)

    # the pads of every net, with the layer they are on
    pads = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if not net:
                continue
            pos = p.GetPosition()
            sz = p.GetSize()
            layers = []
            if p.IsOnLayer(pcbnew.F_Cu):
                layers.append(pcbnew.F_Cu)
            if p.IsOnLayer(pcbnew.B_Cu):
                layers.append(pcbnew.B_Cu)
            pads.setdefault(net, []).append(
                (mm(pos.x), mm(pos.y),
                 mm(sz.x) / 2, mm(sz.y) / 2, layers))

    def on_pad(net, x, y, layer):
        """Is the point on a pad of the net?"""
        for (px, py, hx, hy, layers) in pads.get(net, []):
            if layer not in layers:
                continue
            if abs(x - px) <= hx + 0.05 and abs(y - py) <= hy + 0.05:
                return True
        return False

    def on_via(x, y):
        for t in b.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            pos = t.GetPosition()
            if abs(mm(pos.x) - x) < 0.35 and abs(mm(pos.y) - y) < 0.35:
                return True
        return False

    def on_track(net, x, y, layer):
        """Is the point on another track of the net?"""
        for t in b.GetTracks():
            if t.GetNetname() != net or t.GetClass() == "PCB_VIA":
                continue
            if t.GetLayer() != layer:
                continue
            a, e = t.GetStart(), t.GetEnd()
            ax, ay = mm(a.x), mm(a.y)
            ex, ey = mm(e.x), mm(e.y)
            dx, dy = ex - ax, ey - ay
            L = dx * dx + dy * dy
            if L == 0:
                d = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
            else:
                t2 = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
                d = ((x - ax - t2 * dx) ** 2 + (y - ay - t2 * dy) ** 2) ** 0.5
            if d < 0.15:
                return True
        return False

    print("the tracks with an end that hangs loose")
    n = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        net = t.GetNetname()
        layer = t.GetLayer()
        for pos in (t.GetStart(), t.GetEnd()):
            x, y = mm(pos.x), mm(pos.y)
            if on_pad(net, x, y, layer):
                continue
            if on_via(x, y):
                continue
            if on_track(net, x, y, layer):
                continue
            n += 1
            print(f"  {net:18} {layer:5} end at ({x:8.3f},{y:8.3f})"
                  f"  length {mm(t.GetLength()):.2f} mm")
            break
    print(f"\n  {n} tracks hang loose")


if __name__ == "__main__":
    main()
